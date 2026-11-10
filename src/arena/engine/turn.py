"""Turn resolution: one pure function from a state and actions to the next.

The steps run in the order the game rules define. Each step is a small
function working on a private, mutable :class:`_Turn` scratchpad, which is
turned back into an immutable :class:`GameState` at the end.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from arena.model.actions import Action, ActionKind
from arena.model.geometry import Direction, Position
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
    _place_traps(turn, chosen)
    _move(turn, chosen)
    _trigger_traps(turn)
    _shoot(turn, chosen)
    _collect_crystals(turn)
    _tick_traps(turn)
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
    moved: list[Side] = field(default_factory=list)
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

    def refuse(self, side: Side, reason: str) -> None:
        """Record that ``side``'s action was turned into a wait."""
        position = self.players[side].position
        self.events.append(
            Event(EventKind.ACTION_REFUSED, side, position, reason=reason)
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


def _place_traps(turn: _Turn, chosen: Mapping[Side, Action]) -> None:
    """Place requested traps on the bots' current cells (rules step 2)."""
    for side, action in chosen.items():
        if action.kind is not ActionKind.TRAP:
            continue
        player = turn.players[side]
        reason = _trap_refusal(turn, player)
        if reason:
            turn.refuse(side, reason)
            continue
        turn.traps.append(
            Trap(side, player.position, turn.rules.trap_lifetime)
        )
        turn.players[side] = replace(player, free_traps=player.free_traps - 1)


def _trap_refusal(turn: _Turn, player: PlayerState) -> str:
    """Why ``player`` may not place a trap now; empty if it may."""
    if player.free_traps == 0:
        return "no free trap"
    if player.position in turn.map.bases.values():
        return "base"
    if any(trap.position == player.position for trap in turn.traps):
        return "trap already here"
    return ""


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
        turn.moved.append(side)
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


def _trigger_traps(turn: _Turn) -> None:
    """Catch bots that moved onto an opponent's trap (rules step 4)."""
    for side in turn.moved:
        player = turn.players[side]
        trap = next(
            (
                trap
                for trap in turn.traps
                if trap.position == player.position and trap.owner is not side
            ),
            None,
        )
        if trap is None:
            continue
        turn.traps.remove(trap)
        turn.spent_traps.append(trap)
        turn.events.append(Event(EventKind.TRAPPED, side, player.position))
        turn.players[side] = replace(
            player,
            trapped_turns=max(
                player.trapped_turns, turn.rules.trap_stuck_turns
            ),
        )


def _shoot(turn: _Turn, chosen: Mapping[Side, Action]) -> None:
    """Fire every allowed shot at the opponents' new positions (step 5).

    All hits are found first and applied afterwards, so when both bots
    shoot, both bullets count.
    """
    hits: list[Side] = []
    for side, action in chosen.items():
        if action.kind is not ActionKind.SHOOT or action.direction is None:
            continue
        shooter = turn.players[side]
        if side not in turn.may_shoot:
            turn.refuse(side, "cooldown")
            continue
        turn.players[side] = replace(
            shooter, shoot_cooldown=turn.rules.shoot_cooldown
        )
        path = bullet_path(
            turn.map,
            shooter.position,
            action.direction,
            turn.rules.bullet_range,
        )
        hits.extend(
            other
            for other, player in turn.players.items()
            if other is not side and player.position in path
        )
    for side in hits:
        _hit(turn, side)


def _hit(turn: _Turn, side: Side) -> None:
    """Stun a hit bot and drop the crystals it carries on its cell."""
    player = turn.players[side]
    turn.events.append(Event(EventKind.HIT, side, player.position))
    if player.carrying > 0:
        on_ground = turn.crystals.get(player.position, 0)
        _set_crystals(turn, player.position, on_ground + player.carrying)
        turn.events.append(
            Event(
                EventKind.CRYSTALS_DROPPED,
                side,
                player.position,
                amount=player.carrying,
            )
        )
    turn.players[side] = replace(
        player,
        carrying=0,
        stunned_turns=max(player.stunned_turns, turn.rules.stun_turns),
    )


def bullet_path(
    game_map: GameMap,
    start: Position,
    direction: Direction,
    bullet_range: int,
) -> list[Position]:
    """Return the cells a bullet passes, nearest first.

    The bullet starts next to ``start`` and flies at most ``bullet_range``
    cells; it stops before a wall or the edge of the map.

    Args:
        game_map: The map the bullet flies over.
        start: The shooter's cell (not part of the path).
        direction: The direction of the shot.
        bullet_range: The maximum number of cells.

    Returns:
        The cells the bullet reaches.

    >>> walled = GameMap(6, frozenset({Position(3, 0)}), {})
    >>> bullet_path(walled, Position(0, 0), Direction.RIGHT, 5)
    [Position(x=1, y=0), Position(x=2, y=0)]
    """
    path: list[Position] = []
    cell = start
    for _ in range(bullet_range):
        cell = cell.moved(direction)
        if not game_map.is_walkable(cell):
            break
        path.append(cell)
    return path


def _collect_crystals(turn: _Turn) -> None:
    """Pick up crystals, then deliver at the own base (rules step 6)."""
    for side, player in turn.players.items():
        if turn.is_inactive(side):
            continue
        # Only a bot that enters a cell picks up its crystals, so crystals
        # dropped by a hit bot can be taken by the other bot.
        if side in turn.moved:
            player = _pick_up(turn, player)  # noqa: PLW2901 - same bot
        turn.players[side] = _deliver(turn, player)


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


def _tick_traps(turn: _Turn) -> None:
    """Age every trap; expired traps go back to their owners (step 7)."""
    turn.traps = _age(turn, turn.traps)
    turn.spent_traps = _age(turn, turn.spent_traps)


def _age(turn: _Turn, traps: list[Trap]) -> list[Trap]:
    """Count traps down by one turn and return the ones still running."""
    running: list[Trap] = []
    for trap in traps:
        if trap.turns_left > 1:
            running.append(replace(trap, turns_left=trap.turns_left - 1))
            continue
        owner = turn.players[trap.owner]
        turn.players[trap.owner] = replace(
            owner, free_traps=owner.free_traps + 1
        )
    return running
