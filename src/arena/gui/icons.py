"""Vector icons drawn in code, and a button that shows one.

Each icon is defined like an SVG path: polygons in a 24 by 24 box. A
button scales them to its size, so the icons stay sharp at any size and
need neither image files nor symbol fonts.
"""

import tkinter as tk
from collections.abc import Callable, Mapping
from enum import Enum
from types import MappingProxyType
from typing import Final, TypeAlias

Polygon: TypeAlias = tuple[tuple[float, float], ...]

ICON_BOX: Final = 24
NORMAL_BACKGROUND: Final = "#e9e6df"
HOVER_BACKGROUND: Final = "#f7f4ee"
PRESSED_BACKGROUND: Final = "#d3cfc6"
ICON_COLOUR: Final = "#2b2d33"
DISABLED_COLOUR: Final = "#a8a8a8"


class IconName(Enum):
    """The icons the window uses."""

    FIRST = "first"
    PREVIOUS = "previous"
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    LAST = "last"
    STOP = "stop"
    SOUND_ON = "sound_on"
    SOUND_OFF = "sound_off"


def _rectangle(
    left: float, top: float, right: float, bottom: float
) -> Polygon:
    """A rectangle as a polygon."""
    return ((left, top), (right, top), (right, bottom), (left, bottom))


_SPEAKER: Final[Polygon] = (
    (3, 9), (8, 9), (13, 4), (13, 20), (8, 15), (3, 15),
)  # fmt: skip

ICONS: Final[Mapping[IconName, tuple[Polygon, ...]]] = MappingProxyType(
    {
        IconName.FIRST: (
            _rectangle(4, 5, 7, 19),
            ((20, 5), (20, 19), (8, 12)),
        ),
        IconName.PREVIOUS: (((18, 5), (18, 19), (6, 12)),),
        IconName.PLAY: (((7, 4), (7, 20), (20, 12)),),
        IconName.PAUSE: (_rectangle(6, 5, 10, 19), _rectangle(14, 5, 18, 19)),
        IconName.NEXT: (((6, 5), (6, 19), (18, 12)),),
        IconName.LAST: (
            ((4, 5), (4, 19), (16, 12)),
            _rectangle(17, 5, 20, 19),
        ),
        IconName.STOP: (_rectangle(6, 6, 18, 18),),
        IconName.SOUND_ON: (
            _SPEAKER,
            _rectangle(15.5, 9, 17, 15),
            _rectangle(19, 6, 20.5, 18),
        ),
        IconName.SOUND_OFF: (
            _SPEAKER,
            ((15, 9.5), (16.5, 8), (22, 14.5), (20.5, 16)),
            ((15, 14.5), (20.5, 8), (22, 9.5), (16.5, 16)),
        ),
    }
)


def scale_polygon(polygon: Polygon, size: int) -> list[float]:
    """Flat canvas coordinates of ``polygon`` drawn ``size`` pixels wide.

    >>> scale_polygon(((0, 0), (24, 12), (12, 24)), 12)
    [0.0, 0.0, 12.0, 6.0, 6.0, 12.0]
    """
    factor = size / ICON_BOX
    return [float(value * factor) for point in polygon for value in point]


class IconButton(tk.Canvas):
    """A small square button showing a vector icon.

    It lightens under the mouse, darkens while pressed and turns grey
    and ignores clicks when disabled.
    """

    def __init__(
        self,
        master: tk.Misc,
        icon: IconName,
        command: Callable[[], None],
        tooltip: str,
        size: int = 28,
    ) -> None:
        """Create the button.

        Args:
            master: The parent widget.
            icon: The icon to show.
            command: Called when the button is clicked.
            tooltip: A short description, shown by the parent on hover.
            size: Width and height in pixels.
        """
        super().__init__(
            master,
            width=size,
            height=size,
            background=NORMAL_BACKGROUND,
            highlightthickness=0,
            cursor="hand2",
        )
        self.icon = icon
        self.command = command
        self.tooltip = tooltip
        self.enabled = True
        self._size = size
        self.bind(
            "<Enter>", lambda _event: self._set_background(HOVER_BACKGROUND)
        )
        self.bind(
            "<Leave>", lambda _event: self._set_background(NORMAL_BACKGROUND)
        )
        self.bind("<ButtonPress-1>", lambda _event: self._press())
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def set_icon(self, icon: IconName) -> None:
        """Show a different icon (e.g. pause instead of play)."""
        if icon is not self.icon:
            self.icon = icon
            self._draw()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the button."""
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def invoke(self) -> None:
        """Run the command, unless the button is disabled."""
        if self.enabled:
            self.command()

    def _draw(self) -> None:
        """Draw the icon in the current colour."""
        self.delete("icon")
        # A small margin keeps the icon off the edges of the button.
        inner = self._size - 8
        colour = ICON_COLOUR if self.enabled else DISABLED_COLOUR
        for polygon in ICONS[self.icon]:
            points = [value + 4 for value in scale_polygon(polygon, inner)]
            self.create_polygon(points, fill=colour, outline="", tags="icon")

    def _set_background(self, colour: str) -> None:
        """Change the background if the button is enabled."""
        if self.enabled:
            self.configure(background=colour)

    def _press(self) -> None:
        """Darken while the mouse button is down."""
        self._set_background(PRESSED_BACKGROUND)

    def _release(self, event: "tk.Event[tk.Misc]") -> None:
        """Click when released over the button."""
        inside = 0 <= event.x < self._size and 0 <= event.y < self._size
        self._set_background(HOVER_BACKGROUND if inside else NORMAL_BACKGROUND)
        if inside:
            self.invoke()
