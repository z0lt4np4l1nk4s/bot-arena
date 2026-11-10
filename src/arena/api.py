"""The public interface for bot authors.

A bot imports everything it needs from this module only::

    from arena.api import Action, BotState, Direction

Besides the game types it offers two helpers: :func:`distance` and the
memoized :func:`distances_from` and :func:`shortest_path` (with
:func:`next_step` built on it).
"""

from collections import deque
from collections.abc import Mapping
from types import MappingProxyType

from arena.engine.turn import bullet_path
from arena.map_generator.paths import bfs_distances
from arena.model.actions import Action
from arena.model.geometry import Direction, Position, manhattan
from arena.model.side import Side
from arena.model.state import (
    BotState,
    Event,
    EventKind,
    GameMap,
    ModeKind,
    OpponentView,
    PlayerState,
    Trap,
)
from arena.rules import Rules
from arena.utilities.decorators import memoize

__all__ = [
    "Action",
    "BotState",
    "Direction",
    "Event",
    "EventKind",
    "GameMap",
    "ModeKind",
    "OpponentView",
    "PlayerState",
    "Position",
    "Rules",
    "Side",
    "Trap",
    "bullet_path",
    "distance",
    "distances_from",
    "next_step",
    "shortest_path",
]


def distance(a: Position, b: Position) -> int:
    """Return the number of steps between two cells, ignoring walls.

    >>> distance(Position(0, 0), Position(2, 3))
    5
    """
    return manhattan(a, b)


@memoize
def distances_from(
    game_map: GameMap, start: Position
) -> Mapping[Position, int]:
    """Return the walking distance from ``start`` to every reachable cell.

    One search gives the distance to all cells at once, which is much
    faster than many separate :func:`shortest_path` calls. Cached per map
    and start cell; the result is read-only because it is shared.

    Args:
        game_map: The map to walk on.
        start: The cell to measure from.

    Returns:
        Every reachable cell mapped to its number of steps.
    """
    return MappingProxyType(bfs_distances(game_map, start))


@memoize
def shortest_path(
    game_map: GameMap, start: Position, goal: Position
) -> tuple[Position, ...]:
    """Return the cells of a shortest walk from ``start`` to ``goal``.

    The result starts with the first step and ends with ``goal``. It is
    empty if ``start`` is ``goal`` or the goal cannot be reached. Results
    are cached, because the map never changes during a match.

    Args:
        game_map: The map to walk on.
        start: Where the walk begins (not included in the result).
        goal: Where the walk ends.

    Returns:
        The cells of the walk, in order.
    """
    if start == goal:
        return ()
    came_from: dict[Position, Position] = {start: start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == goal:
            break
        for direction in Direction:
            cell = current.moved(direction)
            if cell not in came_from and game_map.is_walkable(cell):
                came_from[cell] = current
                queue.append(cell)
    if goal not in came_from:
        return ()
    path = [goal]
    while came_from[path[-1]] != start:
        path.append(came_from[path[-1]])
    return tuple(reversed(path))


def next_step(
    game_map: GameMap, start: Position, goal: Position
) -> Direction | None:
    """Return the direction of the first step towards ``goal``.

    >>> open_map = GameMap(4, frozenset(), {})
    >>> next_step(open_map, Position(0, 0), Position(0, 2))
    <Direction.DOWN: (0, 1)>
    """
    # Distances *to* the goal are cached per goal, and a match has only a
    # few goals (crystals and bases), so this stays fast every turn.
    to_goal = distances_from(game_map, goal)
    if start == goal or start not in to_goal:
        return None
    return next(
        direction
        for direction in Direction
        if to_goal.get(start.moved(direction)) == to_goal[start] - 1
    )
