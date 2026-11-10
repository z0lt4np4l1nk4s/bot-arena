"""Shortest-path distances on a game map."""

from collections import deque

from arena.model.geometry import Direction, Position
from arena.model.state import GameMap


def bfs_distances(game_map: GameMap, start: Position) -> dict[Position, int]:
    """Return the number of steps from ``start`` to every reachable cell.

    Breadth-first search over walkable cells; walls are never entered.

    Args:
        game_map: The map to search.
        start: The cell to measure from.

    Returns:
        Every reachable cell mapped to its distance; ``start`` maps to 0.

    >>> open_map = GameMap(3, frozenset(), {})
    >>> bfs_distances(open_map, Position(0, 0))[Position(2, 2)]
    4
    """
    distances = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for direction in Direction:
            neighbour = current.moved(direction)
            if neighbour in distances or not game_map.is_walkable(neighbour):
                continue
            distances[neighbour] = distances[current] + 1
            queue.append(neighbour)
    return distances
