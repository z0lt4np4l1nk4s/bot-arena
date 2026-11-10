"""Turn resolution: one pure function from a state and actions to the next.

The steps run in the order the game rules define. Each step is a small
function working on a private, mutable :class:`_Turn` scratchpad, which is
turned back into an immutable :class:`GameState` at the end.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from arena.model.actions import Action, ActionKind
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import (
    Event,
    EventKind,
    GameMap,
    GameState,
    PlayerState,
    Trap,
)
from arena.rules import Rules


def resolve_turn(
    state: GameState, actions: Mapping[Side, Action], rules: Rules
) -> GameState:
    """Resolve one turn and return the resulting state.

    Args:
        state: The state before the turn.
        actions: The action of each side; a missing side waits.
        rules: The game rules.

    Returns:
        The state after the turn, with ``turn`` increased by one and the
        events of this turn.
    """
    turn = _Turn.start(state, rules)
    chosen = _choose_actions(turn, actions)
    _move(turn, chosen)
    _collect_crystals(turn)
    return turn.finish(state)


@dataclass
class _Turn:
    """Mutable working copy of the state while one turn is resolved."""

    rules: Rules
    map: GameMap
    players: dict[Side, PlayerState]
    crystals: dict[Position, int]
    traps: list[Trap]
    spent_traps: list[Trap]
    disabled: set[Side] = field(default_factory=set)
    may_shoot: set[Side] = field(default_factory=set)
    events: list[Event] = field(default_factory=list)

    @classmethod
    def start(cls, state: GameState, rules: Rules) -> "_Turn":
        """Note who may act this turn, then count the timers down."""
        turn = cls(
            rules=rules,
            map=state.map,
            players=dict(state.players),
            crystals=dict(state.crystals),
            traps=list(state.traps),
            spent_traps=list(state.spent_traps),
        )
        for side, player in state.players.items():
            if player.is_disabled:
                turn.disabled.add(side)
            if player.shoot_cooldown == 0:
                turn.may_shoot.add(side)
            turn.players[side] = replace(
                player,
                stunned_turns=max(player.stunned_turns - 1, 0),
                trapped_turns=max(player.trapped_turns - 1, 0),
                shoot_cooldown=max(player.shoot_cooldown - 1, 0),
            )
        return turn

    def finish(self, previous: GameState) -> GameState:
        """Build the immutable state after this turn."""
        return replace(
            previous,
            turn=previous.turn + 1,
            players=self.players,
            crystals=self.crystals,
            traps=tuple(self.traps),
            spent_traps=tuple(self.spent_traps),
            events=tuple(self.events),
        )

    def is_inactive(self, side: Side) -> bool:
        """Whether ``side`` was disabled at the start or became disabled."""
        return side in self.disabled or self.players[side].is_disabled


def _choose_actions(
    turn: _Turn, actions: Mapping[Side, Action]
) -> dict[Side, Action]:
    """Disabled bots and bots without an action wait."""
    return {
        side: Action.wait()
        if side in turn.disabled
        else actions.get(side, Action.wait())
        for side in turn.players
    }


def _move(turn: _Turn, chosen: Mapping[Side, Action]) -> None:
    """Move every bot whose move is not blocked (rules step 3)."""
    current = {side: player.position for side, player in turn.players.items()}
    wanted = {side: _target(turn, side, chosen[side]) for side in current}
    final = dict(current)
    for side, position in current.items():
        target = wanted[side]
        if target == position:
            continue
        others = [other for other in current if other is not side]
        if any(_blocked_by(target, current, wanted, side, o) for o in others):
            continue
        final[side] = target
    for side, position in final.items():
        turn.players[side] = replace(turn.players[side], position=position)


def _target(turn: _Turn, side: Side, action: Action) -> Position:
    """The cell a bot tries to reach; its own cell if it does not move."""
    position = turn.players[side].position
    if action.kind is not ActionKind.MOVE or action.direction is None:
        return position
    target = position.moved(action.direction)
    return target if turn.map.is_walkable(target) else position


def _blocked_by(
    target: Position,
    current: Mapping[Side, Position],
    wanted: Mapping[Side, Position],
    side: Side,
    other: Side,
) -> bool:
    """Whether ``other`` stops ``side`` from moving to ``target``.

    Blocked when both want the same cell, when they would swap cells, or
    when ``other`` stands on the target and does not leave it.
    """
    if wanted[other] == target:
        return True
    if target == current[other]:
        swapping = wanted[other] == current[side]
        staying = wanted[other] == current[other]
        return swapping or staying
    return False


def _collect_crystals(turn: _Turn) -> None:
    """Pick up crystals, then deliver at the own base (rules step 6)."""
    for side, player in turn.players.items():
        if not turn.is_inactive(side):
            turn.players[side] = _deliver(turn, _pick_up(turn, player))


def _pick_up(turn: _Turn, player: PlayerState) -> PlayerState:
    """Take as many crystals from the bot's cell as it can carry."""
    on_ground = turn.crystals.get(player.position, 0)
    taken = min(on_ground, turn.rules.carry_capacity - player.carrying)
    if taken <= 0:
        return player
    _set_crystals(turn, player.position, on_ground - taken)
    return replace(player, carrying=player.carrying + taken)


def _deliver(turn: _Turn, player: PlayerState) -> PlayerState:
    """Hand in everything the bot carries if it stands on its own base."""
    at_base = player.position == turn.map.base_of(player.side)
    if not at_base or player.carrying == 0:
        return player
    turn.events.append(
        Event(
            EventKind.DELIVERED,
            player.side,
            player.position,
            amount=player.carrying,
        )
    )
    return replace(
        player, carrying=0, delivered=player.delivered + player.carrying
    )


def _set_crystals(turn: _Turn, cell: Position, count: int) -> None:
    """Store a crystal count, dropping cells that become empty."""
    if count > 0:
        turn.crystals[cell] = count
    else:
        turn.crystals.pop(cell, None)
