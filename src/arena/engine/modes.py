"""Game modes: the rules that differ between a duel and a solo run.

:class:`GameMode` is an abstract base class (Strategy pattern): the match
runner works with any mode the same way. Every concrete mode registers
itself when it is defined, so :meth:`GameMode.create` can build one from
its :class:`ModeKind` (Factory pattern).
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import replace
from typing import ClassVar

from arena.engine.turn import resolve_turn
from arena.map_generator.generator import generate, solo_crystals
from arena.model.actions import Action, ActionKind
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import (
    BotState,
    Event,
    EventKind,
    GameMap,
    GameState,
    ModeKind,
    OpponentView,
    PlayerState,
)
from arena.rules import DEFAULT_RULES, Rules


class GameMode(ABC):
    """A kind of match: how it starts, what is allowed and who wins."""

    kind: ClassVar[ModeKind]
    sides: ClassVar[tuple[Side, ...]]
    _registry: ClassVar[dict[ModeKind, type["GameMode"]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Register every subclass that declares its own ``kind``."""
        super().__init_subclass__(**kwargs)
        if "kind" in cls.__dict__:
            GameMode._registry[cls.kind] = cls

    def __init__(self, rules: Rules = DEFAULT_RULES) -> None:
        """Create the mode.

        Args:
            rules: The rules every match of this mode uses.
        """
        self.rules: Rules = rules

    @classmethod
    def create(
        cls, kind: ModeKind, rules: Rules = DEFAULT_RULES
    ) -> "GameMode":
        """Build the registered mode of the given kind.

        Args:
            kind: Which mode to build.
            rules: The rules the mode uses.

        Returns:
            A new mode instance.
        """
        return GameMode._registry[kind](rules)

    @abstractmethod
    def setup_map(self, seed: int) -> GameState:
        """Return the starting state of a match generated from ``seed``."""

    @abstractmethod
    def allows(self, action: Action) -> bool:
        """Whether ``action`` may be used in this mode."""

    @abstractmethod
    def winner(self, state: GameState) -> Side | None:
        """The winning side of a finished match, or ``None``."""

    def turns_used(self, state: GameState) -> int | None:
        """Turns needed to finish, for modes that measure it."""
        del state
        return None

    def is_over(self, state: GameState) -> bool:
        """Whether the match has ended."""
        return state.is_finished

    def state_for_bot(self, state: GameState, side: Side) -> BotState:
        """Return what ``side``'s bot may see: no opponent traps.

        The opponent's refused actions are hidden too, because a refused
        trap would reveal where its traps are or how many it has left.
        The view gets its own copy of the crystals, so a bot cannot change
        the game by changing what it sees.

        Args:
            state: The full game state.
            side: The bot that is about to decide.

        Returns:
            The bot's view of the game.
        """
        opponent = state.players.get(side.opponent)
        return BotState(
            turn=state.turn,
            max_turns=state.max_turns,
            mode=state.mode,
            map=state.map,
            crystals=dict(state.crystals),
            me=state.player(side),
            my_traps=tuple(t for t in state.traps if t.owner is side),
            opponent=None if opponent is None else OpponentView.of(opponent),
            events=tuple(
                event
                for event in state.events
                if event.kind is not EventKind.ACTION_REFUSED
                or event.side is side
            ),
            rules=self.rules,
        )

    def step(
        self, state: GameState, actions: Mapping[Side, Action]
    ) -> GameState:
        """Play one turn, turning actions this mode forbids into waits.

        Args:
            state: The state before the turn.
            actions: The action of each side; a missing side waits.

        Returns:
            The state after the turn.
        """
        allowed: dict[Side, Action] = {}
        refused: list[Event] = []
        for side in self.sides:
            action = actions.get(side, Action.wait())
            if self.allows(action):
                allowed[side] = action
            else:
                allowed[side] = Action.wait(action.message)
                refused.append(
                    Event(
                        EventKind.ACTION_REFUSED,
                        side,
                        state.player(side).position,
                        reason=f"not allowed in {self.kind.value}",
                    )
                )
        after = resolve_turn(state, allowed, self.rules)
        return replace(after, events=(*refused, *after.events))

    def _start_state(
        self,
        game_map: GameMap,
        crystals: Mapping[Position, int],
        max_turns: int,
    ) -> GameState:
        """Build turn 0 with every side's bot standing on its base."""
        players = {
            side: PlayerState(
                side,
                game_map.base_of(side),
                free_traps=self.rules.traps_per_bot,
            )
            for side in self.sides
        }
        return GameState(
            mode=self.kind,
            turn=0,
            max_turns=max_turns,
            map=game_map,
            crystals=dict(crystals),
            players=players,
        )


class Duel(GameMode):
    """Two bots compete for all crystals; more delivered crystals wins."""

    kind = ModeKind.DUEL
    sides = (Side.BLUE, Side.RED)

    def setup_map(self, seed: int) -> GameState:
        """Start a duel on the full generated map."""
        game_map, crystals = generate(seed, self.rules)
        return self._start_state(game_map, crystals, self.rules.duel_max_turns)

    def allows(self, action: Action) -> bool:
        """Every action is allowed in a duel."""
        del action
        return True

    def winner(self, state: GameState) -> Side | None:
        """The side with more delivered crystals.

        With equal scores, the side that delivered its last crystal in an
        earlier turn wins; if that is equal too, it is a draw (``None``).
        """
        blue, red = state.player(Side.BLUE), state.player(Side.RED)
        if blue.delivered != red.delivered:
            return Side.BLUE if blue.delivered > red.delivered else Side.RED
        blue_last, red_last = blue.last_delivery_turn, red.last_delivery_turn
        if blue_last is None or red_last is None or blue_last == red_last:
            return None
        return Side.BLUE if blue_last < red_last else Side.RED


class Solo(GameMode):
    """One bot delivers the crystals on its half as fast as it can."""

    kind = ModeKind.SOLO
    sides = (Side.BLUE,)

    def setup_map(self, seed: int) -> GameState:
        """Start a solo run with only the Blue half's crystals."""
        game_map, crystals = generate(seed, self.rules)
        return self._start_state(
            game_map,
            solo_crystals(game_map, crystals),
            self.rules.solo_max_turns,
        )

    def allows(self, action: Action) -> bool:
        """Only moving and waiting: there is no one to shoot or trap."""
        return action.kind in {ActionKind.MOVE, ActionKind.WAIT}

    def winner(self, state: GameState) -> Side | None:
        """Blue if every crystal was delivered, otherwise ``None``."""
        return Side.BLUE if state.crystals_left == 0 else None

    def turns_used(self, state: GameState) -> int | None:
        """The number of turns needed, or ``None`` if not finished."""
        return state.turn if state.crystals_left == 0 else None
