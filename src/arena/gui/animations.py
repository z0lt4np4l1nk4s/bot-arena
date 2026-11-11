"""Short animations of a turn's effects, drawn over the map.

Every animation runs for a fixed time, one frame about every 30 ms,
with tkinter's ``after`` so the window never waits. All drawn items
carry the tag ``effect`` and are removed when the animation ends or a
new one starts.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Final

from arena.gui.effects import Effect, EffectKind
from arena.gui.map_canvas import DISABLED_COLOUR, SIDE_COLOURS, MapCanvas

FRAME_MS: Final = 30
LONGEST_MS: Final = 300
SHORTEST_MS: Final = 60
FLASH_COLOUR: Final = "#ffd34d"
TAG: Final = "effect"


def animation_duration_ms(tick_ms: int) -> int:
    """How long a turn's animation may run when turns are ``tick_ms`` apart.

    At most 300 ms and 80 % of a turn; shorter than 60 ms is not worth
    showing, so it becomes 0 (no animation).

    >>> animation_duration_ms(1000), animation_duration_ms(200)
    (300, 160)
    >>> animation_duration_ms(50)
    0
    """
    duration = min(LONGEST_MS, tick_ms * 4 // 5)
    return duration if duration >= SHORTEST_MS else 0


class EffectAnimator:
    """Plays effect animations on a :class:`MapCanvas`."""

    def __init__(self, canvas: MapCanvas) -> None:
        """Animate on ``canvas``."""
        self.canvas = canvas
        self._timer: str | None = None
        self._drawers: Mapping[EffectKind, Callable[[Effect, float], None]] = {
            EffectKind.SHOT: self._draw_shot,
            EffectKind.TRAP_PLACED: self._draw_trap_placed,
            EffectKind.HIT: self._draw_hit,
            EffectKind.TRAP_TRIGGERED: self._draw_trap_triggered,
            EffectKind.DELIVERED: self._draw_delivered,
        }

    @property
    def is_running(self) -> bool:
        """Whether an animation is being shown."""
        return self._timer is not None

    def play(self, effects: Sequence[Effect], duration_ms: int) -> None:
        """Animate ``effects`` for ``duration_ms``, replacing any animation.

        Args:
            effects: The effects of one turn.
            duration_ms: The length; 0 shows nothing.
        """
        self.cancel()
        if duration_ms <= 0 or not effects:
            return
        frames = max(2, duration_ms // FRAME_MS)
        self._show_frame(list(effects), 0, frames)

    def cancel(self) -> None:
        """Stop the animation and remove what it drew."""
        if self._timer is not None:
            self.canvas.after_cancel(self._timer)
            self._timer = None
        self.canvas.delete(TAG)

    def _show_frame(
        self, effects: list[Effect], frame: int, frames: int
    ) -> None:
        """Draw one frame and schedule the next, or clean up at the end."""
        self.canvas.delete(TAG)
        if frame >= frames:
            self._timer = None
            return
        progress = frame / (frames - 1)
        for effect in effects:
            self._drawers[effect.kind](effect, progress)
        self.canvas.tag_raise(TAG)
        self._timer = self.canvas.after(
            FRAME_MS, self._show_frame, effects, frame + 1, frames
        )

    def _draw_shot(self, effect: Effect, progress: float) -> None:
        """A bullet flying from the shooter along its path, with a trail."""
        start_x, start_y = self.canvas.cell_center(effect.cells[0])
        end_x, end_y = self.canvas.cell_center(effect.cells[-1])
        x = start_x + (end_x - start_x) * progress
        y = start_y + (end_y - start_y) * progress
        colour = SIDE_COLOURS[effect.side]
        trail = max(0.0, progress - 0.35)
        self.canvas.create_line(
            start_x + (end_x - start_x) * trail,
            start_y + (end_y - start_y) * trail,
            x,
            y,
            fill=colour,
            width=max(2, self.canvas.cell_size // 6),
            tags=TAG,
        )
        radius = max(3, self.canvas.cell_size // 5)
        self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=FLASH_COLOUR,
            outline=colour,
            width=2,
            tags=TAG,
        )

    def _draw_trap_placed(self, effect: Effect, progress: float) -> None:
        """A ring in the owner's colour shrinking onto the cell."""
        size = self.canvas.cell_size * (1.6 - 1.2 * progress)
        self._ring(effect, size / 2, SIDE_COLOURS[effect.side], 3)

    def _draw_hit(self, effect: Effect, progress: float) -> None:
        """A growing, thinning flash on the hit bot."""
        radius = self.canvas.cell_size * (0.3 + 0.7 * progress)
        width = max(1, round(6 * (1 - progress)))
        self._ring(effect, radius, FLASH_COLOUR, width)

    def _draw_trap_triggered(self, effect: Effect, progress: float) -> None:
        """A trap snapping shut: short rays bursting from the cell."""
        center_x, center_y = self.canvas.cell_center(effect.cells[0])
        inner = self.canvas.cell_size * (0.2 + 0.4 * progress)
        outer = inner + self.canvas.cell_size * 0.35 * (1 - progress / 2)
        for ray in range(8):
            angle = ray * math.pi / 4
            self.canvas.create_line(
                center_x + inner * math.cos(angle),
                center_y + inner * math.sin(angle),
                center_x + outer * math.cos(angle),
                center_y + outer * math.sin(angle),
                fill=DISABLED_COLOUR,
                width=3,
                tags=TAG,
            )

    def _draw_delivered(self, effect: Effect, progress: float) -> None:
        """The base pulsing outwards in the bot's colour."""
        center_x, center_y = self.canvas.cell_center(effect.cells[0])
        half = self.canvas.cell_size * (
            0.5 + 0.6 * math.sin(math.pi * progress)
        )
        self.canvas.create_rectangle(
            center_x - half,
            center_y - half,
            center_x + half,
            center_y + half,
            outline=SIDE_COLOURS[effect.side],
            width=3,
            tags=TAG,
        )

    def _ring(
        self, effect: Effect, radius: float, colour: str, width: int
    ) -> None:
        """A circle around the effect's cell."""
        center_x, center_y = self.canvas.cell_center(effect.cells[0])
        self.canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            outline=colour,
            width=width,
            tags=TAG,
        )
