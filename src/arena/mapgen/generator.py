"""Fair random maps (the Factory for maps).

A map is built from a seed, so the same seed always gives the same map.
Every wall and crystal is placed together with its partner on the cell
rotated by 180 degrees, so both bases see exactly the same map.
"""

import random
from collections.abc import Callable, Iterable, Mapping
from typing import Final

from arena.errors import MapGenerationError
from arena.mapgen.paths import bfs_distances
from arena.model.geometry import Position, manhattan
from arena.model.side import Side
from arena.model.state import GameMap
from arena.rules import Rules

MAX_ATTEMPTS: Final = 100


def generate(seed: int, rules: Rules) -> tuple[GameMap, dict[Position, int]]:
    """Generate a fair map and its crystals from a seed.

    Args:
        seed: Any integer; equal seeds give equal maps.
        rules: The rules giving the grid size, wall share and crystal count.

    Returns:
        The map and its crystals (each crystal cell holds one crystal).

    Raises:
        MapGenerationError: If no valid map is found in ``MAX_ATTEMPTS``.
    """
    rng = random.Random(seed)
    for _ in range(MAX_ATTEMPTS):
        result = _attempt(rng, rules)
        if result is not None:
            return result
    message = f"no valid map for seed {seed} in {MAX_ATTEMPTS} attempts"
    raise MapGenerationError(message)


def solo_crystals(
    game_map: GameMap, crystals: Mapping[Position, int]
) -> dict[Position, int]:
    """Keep only the crystals closer to the Blue base than to the Red base.

    Args:
        game_map: The duel map the crystals belong to.
        crystals: The duel crystals.

    Returns:
        The crystals on the Blue half of the map.

    >>> game_map = GameMap(4, frozenset(), _bases(4))
    >>> solo_crystals(game_map, {Position(1, 0): 1, Position(2, 3): 1})
    {Position(x=1, y=0): 1}
    """
    blue = game_map.base_of(Side.BLUE)
    red = game_map.base_of(Side.RED)
    return {
        cell: count
        for cell, count in crystals.items()
        if manhattan(cell, blue) < manhattan(cell, red)
    }


def _attempt(
    rng: random.Random, rules: Rules
) -> tuple[GameMap, dict[Position, int]] | None:
    """Try to build one map; return ``None`` if it is not valid."""
    size = rules.grid_size
    bases = _bases(size)
    protected = _protected_cells(bases.values(), size)

    walls: set[Position] = set()
    wall_target = size * size * rules.wall_percent // 100 // 2 * 2
    if not _place_pairs(
        rng,
        walls,
        wall_target // 2,
        size,
        lambda cell: cell not in protected and cell not in walls,
    ):
        return None

    crystals: set[Position] = set()
    if not _place_pairs(
        rng,
        crystals,
        rules.crystal_pairs,
        size,
        lambda cell: (
            cell not in walls
            and cell not in crystals
            and cell not in bases.values()
            and cell.x + cell.y != size - 1
        ),
    ):
        return None

    game_map = GameMap(size, frozenset(walls), bases)
    reachable = bfs_distances(game_map, bases[Side.BLUE])
    if bases[Side.RED] not in reachable or not crystals <= set(reachable):
        return None
    return game_map, dict.fromkeys(sorted(crystals, key=_order), 1)


def _place_pairs(
    rng: random.Random,
    target: set[Position],
    pair_count: int,
    size: int,
    is_free: Callable[[Position], bool],
) -> bool:
    """Add ``pair_count`` symmetric cell pairs to ``target``.

    The cells are shuffled once and taken in that order, so every free
    cell has the same chance and the result depends only on ``rng``.

    Returns:
        ``False`` if there were not enough free cells.
    """
    cells = [Position(x, y) for y in range(size) for x in range(size)]
    rng.shuffle(cells)
    placed = 0
    for cell in cells:
        if placed == pair_count:
            break
        partner = cell.rotated(size)
        if is_free(cell) and is_free(partner):
            target.update({cell, partner})
            placed += 1
    return placed == pair_count


def _bases(size: int) -> dict[Side, Position]:
    """Blue base top-left, Red base bottom-right."""
    return {Side.BLUE: Position(0, 0), Side.RED: Position(size - 1, size - 1)}


def _protected_cells(
    bases: Iterable[Position], size: int
) -> frozenset[Position]:
    """Each base and its eight neighbours that lie on the grid."""
    return frozenset(
        Position(base.x + dx, base.y + dy)
        for base in bases
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if Position(base.x + dx, base.y + dy).is_inside(size)
    )


def _order(cell: Position) -> tuple[int, int]:
    """Row-major sort key, so results do not depend on set order."""
    return (cell.y, cell.x)
