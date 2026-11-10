"""The game state: map, players, traps, events, and what a bot sees.

All classes are immutable. The engine never changes a state; it builds the
next one. Mappings stored in these objects are never mutated after
creation.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from arena.model.geometry import Position
from arena.model.side import Side
from arena.rules import Rules


class ModeKind(Enum):
    """The kind of match being played."""

    DUEL = "duel"
    SOLO = "solo"


@dataclass(frozen=True)
class GameMap:
    """The fixed part of a match: grid size, walls and bases."""

    size: int
    walls: frozenset[Position]
    # A dict cannot be hashed; leaving it out of the hash keeps maps usable
    # as cache keys, while equality still compares the bases.
    bases: Mapping[Side, Position] = field(hash=False)

    def is_walkable(self, position: Position) -> bool:
        """Check whether a bot may stand on ``position``.

        Args:
            position: The cell to check.

        Returns:
            ``True`` if the cell is on the grid and not a wall.

        >>> game_map = GameMap(4, frozenset({Position(1, 1)}), {})
        >>> game_map.is_walkable(Position(1, 1))
        False
        >>> game_map.is_walkable(Position(0, 3))
        True
        """
        return position.is_inside(self.size) and position not in self.walls

    def base_of(self, side: Side) -> Position:
        """Return the base cell of ``side``."""
        return self.bases[side]


@dataclass(frozen=True)
class Trap:
    """A hidden trap placed by ``owner``."""

    owner: Side
    position: Position
    turns_left: int


@dataclass(frozen=True)
class PlayerState:
    """Everything the engine knows about one bot."""

    side: Side
    position: Position
    carrying: int = 0
    delivered: int = 0
    shoot_cooldown: int = 0
    stunned_turns: int = 0
    trapped_turns: int = 0
    free_traps: int = 0
    trap_cooldown: int = 0

    @property
    def is_disabled(self) -> bool:
        """Whether the bot skips its action (stunned or trapped)."""
        return self.stunned_turns > 0 or self.trapped_turns > 0


@dataclass(frozen=True)
class OpponentView:
    """What a bot may know about its opponent: no trap information."""

    side: Side
    position: Position
    carrying: int
    delivered: int
    shoot_cooldown: int
    stunned_turns: int
    trapped_turns: int

    @classmethod
    def of(cls, player: PlayerState) -> "OpponentView":
        """Build the public view of ``player``."""
        return cls(
            side=player.side,
            position=player.position,
            carrying=player.carrying,
            delivered=player.delivered,
            shoot_cooldown=player.shoot_cooldown,
            stunned_turns=player.stunned_turns,
            trapped_turns=player.trapped_turns,
        )


class EventKind(Enum):
    """Something notable that happened during a turn."""

    HIT = "hit"
    CRYSTALS_DROPPED = "crystals_dropped"
    TRAPPED = "trapped"
    DELIVERED = "delivered"
    ACTION_REFUSED = "action_refused"


@dataclass(frozen=True)
class Event:
    """One event of a turn; ``side`` is the bot it happened to."""

    kind: EventKind
    side: Side
    position: Position
    amount: int = 0
    reason: str = ""


@dataclass(frozen=True)
class GameState:
    """The complete state of a match after a turn."""

    mode: ModeKind
    turn: int
    max_turns: int
    map: GameMap
    crystals: Mapping[Position, int]
    players: Mapping[Side, PlayerState]
    traps: tuple[Trap, ...] = ()
    spent_traps: tuple[Trap, ...] = ()
    events: tuple[Event, ...] = ()

    def player(self, side: Side) -> PlayerState:
        """Return the state of the bot playing ``side``."""
        return self.players[side]

    @property
    def crystals_left(self) -> int:
        """Crystals not yet delivered: on the ground plus carried."""
        carried = sum(player.carrying for player in self.players.values())
        return sum(self.crystals.values()) + carried

    @property
    def is_finished(self) -> bool:
        """Whether the turn limit is reached or every crystal delivered."""
        return self.turn >= self.max_turns or self.crystals_left == 0


@dataclass(frozen=True)
class BotState:
    """What one bot sees when it decides its action."""

    turn: int
    max_turns: int
    mode: ModeKind
    map: GameMap
    crystals: Mapping[Position, int]
    me: PlayerState
    my_traps: tuple[Trap, ...]
    opponent: OpponentView | None
    events: tuple[Event, ...]
    rules: Rules
