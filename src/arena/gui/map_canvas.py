"""Draw a game state on a tkinter canvas.

This is the analyst's view, not a bot's: traps of both bots are shown,
marked with their owner's colour.
"""

import tkinter as tk
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from arena.gui.formatting import shot_lines
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import GameState, PlayerState
from arena.rules import Rules

SIDE_COLOURS: Final[Mapping[Side, str]] = MappingProxyType(
    {Side.BLUE: "#2f6fdd", Side.RED: "#d64545"}
)
BASE_COLOURS: Final[Mapping[Side, str]] = MappingProxyType(
    {Side.BLUE: "#cfdcf7", Side.RED: "#f5d0d0"}
)
BACKGROUND: Final = "#e4e0d8"
FLOOR_COLOUR: Final = "#f4f1ea"
GRID_COLOUR: Final = "#e2ddd2"
WALL_COLOUR: Final = "#555555"
CRYSTAL_COLOUR: Final = "#2bb3a3"
DISABLED_COLOUR: Final = "#f2b134"
MINIMUM_CELL_SIZE: Final = 8

Box = tuple[float, float, float, float]


def cell_box(position: Position, cell_size: int) -> tuple[int, int, int, int]:
    """The pixel box of a cell, relative to the top-left corner of the map.

    >>> cell_box(Position(2, 1), 10)
    (20, 10, 30, 20)
    """
    left, top = position.x * cell_size, position.y * cell_size
    return left, top, left + cell_size, top + cell_size


class MapCanvas(tk.Canvas):
    """A canvas that shows one game state and redraws when resized.

    Every item has one tag naming what it shows: ``floor``, ``wall``,
    ``base``, ``crystal``, ``trap``, ``bot``, ``shot`` or ``placeholder``.
    """

    def __init__(self, master: tk.Misc, rules: Rules, size: int = 560) -> None:
        """Create an empty map.

        Args:
            master: The parent widget.
            rules: The rules of the match.
            size: The starting width and height in pixels.
        """
        super().__init__(
            master,
            width=size,
            height=size,
            background=BACKGROUND,
            highlightthickness=0,
        )
        self.rules = rules
        self.cell_size = MINIMUM_CELL_SIZE
        self._state: GameState | None = None
        self._origin = (0, 0)
        self.bind("<Configure>", lambda _event: self.draw(self._state))
        self.draw(None)

    def draw(self, state: GameState | None) -> None:
        """Show ``state``; ``None`` shows that there is no match yet."""
        self._state = state
        self.delete("all")
        width, height = self._size()
        if state is None:
            self.create_text(
                width // 2,
                height // 2,
                text="No match yet",
                fill=WALL_COLOUR,
                font=("TkDefaultFont", 14),
                tags="placeholder",
            )
            return
        grid = state.map.size
        self.cell_size = max(MINIMUM_CELL_SIZE, min(width, height) // grid)
        side_length = self.cell_size * grid
        self._origin = (
            max(0, (width - side_length) // 2),
            max(0, (height - side_length) // 2),
        )
        self._draw_floor(state)
        self._draw_walls(state)
        self._draw_crystals(state)
        self._draw_traps(state)
        self._draw_shots(state)
        for player in state.players.values():
            self._draw_bot(player)

    def cell_center(self, position: Position) -> tuple[float, float]:
        """The pixel centre of a cell on the canvas."""
        left, top, right, bottom = self._box(position)
        return (left + right) / 2, (top + bottom) / 2

    def _size(self) -> tuple[int, int]:
        """The canvas size, also before the window is shown."""
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1 or height <= 1:
            return int(self.cget("width")), int(self.cget("height"))
        return width, height

    def _box(self, position: Position) -> tuple[int, int, int, int]:
        """The pixel box of a cell on the canvas."""
        left, top, right, bottom = cell_box(position, self.cell_size)
        x, y = self._origin
        return left + x, top + y, right + x, bottom + y

    def _inner_box(self, position: Position, margin: float) -> Box:
        """A cell's box shrunk by ``margin`` (a share of the cell size)."""
        left, top, right, bottom = self._box(position)
        inset = self.cell_size * margin
        return left + inset, top + inset, right - inset, bottom - inset

    def _draw_floor(self, state: GameState) -> None:
        """The floor with a light grid, then both bases."""
        for x in range(state.map.size):
            for y in range(state.map.size):
                self.create_rectangle(
                    *self._box(Position(x, y)),
                    fill=FLOOR_COLOUR,
                    outline=GRID_COLOUR,
                    tags="floor",
                )
        for side, base in state.map.bases.items():
            self.create_rectangle(
                *self._box(base),
                fill=BASE_COLOURS[side],
                outline=SIDE_COLOURS[side],
                width=2,
                tags="base",
            )

    def _draw_walls(self, state: GameState) -> None:
        """One dark square per wall."""
        for wall in state.map.walls:
            self.create_rectangle(
                *self._box(wall), fill=WALL_COLOUR, outline="", tags="wall"
            )

    def _draw_crystals(self, state: GameState) -> None:
        """A diamond per crystal cell, with the count if there are several."""
        for cell, count in state.crystals.items():
            left, top, right, bottom = self._inner_box(cell, 0.25)
            middle_x, middle_y = (left + right) / 2, (top + bottom) / 2
            corners = (
                (middle_x, top),
                (right, middle_y),
                (middle_x, bottom),
                (left, middle_y),
            )
            self.create_polygon(
                [coordinate for corner in corners for coordinate in corner],
                fill=CRYSTAL_COLOUR,
                outline="",
                tags="crystal",
            )
            if count > 1:
                self.create_text(
                    middle_x,
                    middle_y,
                    text=str(count),
                    fill="white",
                    font=("TkDefaultFont", max(7, self.cell_size // 3)),
                    tags="crystal",
                )

    def _draw_traps(self, state: GameState) -> None:
        """An X in the owner's colour for every active trap."""
        width = max(2, self.cell_size // 8)
        for trap in state.traps:
            left, top, right, bottom = self._inner_box(trap.position, 0.25)
            colour = SIDE_COLOURS[trap.owner]
            self.create_line(
                left, top, right, bottom, fill=colour, width=width, tags="trap"
            )
            self.create_line(
                left, bottom, right, top, fill=colour, width=width, tags="trap"
            )

    def _draw_shots(self, state: GameState) -> None:
        """A dashed line from each shooter to where its bullet stopped."""
        for side, cells in shot_lines(state):
            if not cells:
                continue
            start_x, start_y = self.cell_center(state.player(side).position)
            end_x, end_y = self.cell_center(cells[-1])
            self.create_line(
                start_x,
                start_y,
                end_x,
                end_y,
                fill=SIDE_COLOURS[side],
                width=max(2, self.cell_size // 6),
                dash=(4, 3),
                tags="shot",
            )

    def _draw_bot(self, player: PlayerState) -> None:
        """A circle with the carried count, and a marker when disabled."""
        disabled = player.is_disabled
        self.create_oval(
            *self._inner_box(player.position, 0.1),
            fill=SIDE_COLOURS[player.side],
            outline=DISABLED_COLOUR if disabled else "white",
            width=3 if disabled else 1,
            tags="bot",
        )
        center_x, center_y = self.cell_center(player.position)
        font_size = max(7, self.cell_size // 3)
        self.create_text(
            center_x,
            center_y,
            text=str(player.carrying),
            fill="white",
            font=("TkDefaultFont", font_size, "bold"),
            tags="bot",
        )
        if disabled:
            _, top, right, _ = self._box(player.position)
            self.create_text(
                right - 1,
                top + 1,
                text="S" if player.stunned_turns > 0 else "T",
                anchor="ne",
                fill=DISABLED_COLOUR,
                font=("TkDefaultFont", max(6, font_size - 2), "bold"),
                tags="bot",
            )
