"""What happened between two turns that deserves an animation and a sound.

Effects are found by comparing the state before a turn with the state
after it, so they work the same for live matches and for replays.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final

from arena.gui.formatting import shot_lines
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import EventKind, GameState


class EffectKind(Enum):
    """The kinds of effects, in the order they are shown."""

    SHOT = "shot"
    TRAP_PLACED = "trap_placed"
    HIT = "hit"
    TRAP_TRIGGERED = "trap_triggered"
    DELIVERED = "delivered"


@dataclass(frozen=True)
class Effect:
    """One effect: who caused or suffered it, and the cells it covers.

    For a shot the cells are the shooter's cell followed by the bullet's
    path; for every other effect they are the one cell where it happened.
    """

    kind: EffectKind
    side: Side
    cells: tuple[Position, ...]


_EVENT_EFFECTS: Final = {
    EventKind.HIT: EffectKind.HIT,
    EventKind.TRAPPED: EffectKind.TRAP_TRIGGERED,
    EventKind.DELIVERED: EffectKind.DELIVERED,
}
_ORDER: Final = {kind: index for index, kind in enumerate(EffectKind)}


def turn_effects(previous: GameState, current: GameState) -> list[Effect]:
    """The effects of the turn that led from ``previous`` to ``current``.

    Args:
        previous: The state before the turn.
        current: The state after the turn.

    Returns:
        Shots, placed traps, hits, triggered traps and deliveries, in
        that order.
    """
    effects = [
        Effect(
            EffectKind.SHOT,
            side,
            (current.player(side).position, *cells),
        )
        for side, cells in shot_lines(current)
    ]
    known = {(trap.owner, trap.position) for trap in previous.traps}
    effects.extend(
        Effect(EffectKind.TRAP_PLACED, trap.owner, (trap.position,))
        for trap in current.traps
        if (trap.owner, trap.position) not in known
    )
    effects.extend(
        Effect(_EVENT_EFFECTS[event.kind], event.side, (event.position,))
        for event in current.events
        if event.kind in _EVENT_EFFECTS
    )
    return sorted(effects, key=lambda effect: _ORDER[effect.kind])
