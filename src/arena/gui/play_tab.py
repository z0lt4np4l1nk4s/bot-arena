"""The Play tab: choose the mode, the bots and the map seed, then start.

The tab knows nothing about matches: it calls the ``on_start`` and
``on_stop`` callbacks it was given, and the window tells it with
:meth:`PlayTab.set_running` whether a match is running.
"""

import random
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Final

from arena.bots.source import BotSource
from arena.gui.formatting import bot_label
from arena.model.state import ModeKind

LARGEST_SEED: Final = 2**63 - 1
RANDOM_SEED_LIMIT: Final = 1_000_000
DEFAULT_BLUE: Final = "Medium (built-in)"
DEFAULT_RED: Final = "Easy (built-in)"
ERROR_COLOUR: Final = "#b3261e"
INFO_COLOUR: Final = "#2e6b30"

StartCallback = Callable[[ModeKind, BotSource, BotSource | None, int], None]


def parse_seed(text: str) -> int:
    """Read a map seed typed by the user.

    >>> parse_seed(" 17 ")
    17
    >>> parse_seed("-3")
    Traceback (most recent call last):
    ...
    ValueError: the seed must be a whole number from 0 to 9223372036854775807

    Raises:
        ValueError: If the text is not a whole number in the allowed range.
    """
    message = f"the seed must be a whole number from 0 to {LARGEST_SEED}"
    stripped = text.strip()
    if not (stripped.isascii() and stripped.isdigit()):
        raise ValueError(message)
    seed = int(stripped)
    if seed > LARGEST_SEED:
        raise ValueError(message)
    return seed


class PlayTab(ttk.Frame):
    """The form that starts a match."""

    def __init__(
        self,
        master: tk.Misc,
        list_bots: Callable[[], list[BotSource]],
        on_start: StartCallback,
        on_stop: Callable[[], None],
    ) -> None:
        """Create the form.

        Args:
            master: The parent widget.
            list_bots: Returns every bot that can play, built-ins first.
            on_start: Called with the mode, both bots and the seed.
            on_stop: Called when the user stops the match.
        """
        super().__init__(master, padding=24)
        self.list_bots = list_bots
        self.on_start = on_start
        self.on_stop = on_stop
        self._sources: dict[str, BotSource] = {}
        self.mode_variable = tk.StringVar(value=ModeKind.DUEL.value)
        self._build()
        self.refresh_bots()
        self._new_random_seed()
        self.set_running(False)

    def refresh_bots(self) -> None:
        """Read the list of bots again, keeping the current choices."""
        self._sources = {
            bot_label(source): source for source in self.list_bots()
        }
        labels = list(self._sources)
        for combo, default in (
            (self.blue_combo, DEFAULT_BLUE),
            (self.red_combo, DEFAULT_RED),
        ):
            combo.configure(values=labels)
            if combo.get() not in self._sources:
                combo.set(default if default in self._sources else "")

    def set_running(self, running: bool) -> None:
        """Allow starting a match only when none is running."""
        self.start_button.state(["disabled" if running else "!disabled"])
        self.stop_button.state(["!disabled" if running else "disabled"])

    def show_error(self, message: str) -> None:
        """Show a problem under the buttons."""
        self.message_label.configure(text=message, foreground=ERROR_COLOUR)

    def show_info(self, message: str) -> None:
        """Show a note (e.g. the last result) under the buttons."""
        self.message_label.configure(text=message, foreground=INFO_COLOUR)

    def _build(self) -> None:
        """Lay out the form in a grid."""
        ttk.Label(
            self, text="Start a match", font=("TkDefaultFont", 16, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Label(self, text="Mode").grid(row=1, column=0, sticky="w")
        modes = ttk.Frame(self)
        modes.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
        self.duel_button = ttk.Radiobutton(
            modes,
            text="Duel",
            value=ModeKind.DUEL.value,
            variable=self.mode_variable,
            command=self._on_mode,
        )
        self.duel_button.pack(side="left", padx=(0, 12))
        self.solo_button = ttk.Radiobutton(
            modes,
            text="Solo",
            value=ModeKind.SOLO.value,
            variable=self.mode_variable,
            command=self._on_mode,
        )
        self.solo_button.pack(side="left")
        self.blue_combo = self._bot_row("Blue bot", 2)
        self.red_combo = self._bot_row("Red bot", 3)
        ttk.Label(self, text="Seed").grid(row=4, column=0, sticky="w")
        self.seed_entry = ttk.Entry(self, width=24)
        self.seed_entry.grid(row=4, column=1, sticky="w", pady=4)
        self.random_button = ttk.Button(
            self, text="Random", command=self._new_random_seed
        )
        self.random_button.grid(row=4, column=2, sticky="w", padx=8)
        buttons = ttk.Frame(self)
        buttons.grid(row=5, column=0, columnspan=3, sticky="w", pady=16)
        self.start_button = ttk.Button(
            buttons, text="Start", command=self._on_start
        )
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(
            buttons, text="Stop", command=self.on_stop
        )
        self.stop_button.pack(side="left")
        self.message_label = ttk.Label(self, wraplength=520)
        self.message_label.grid(row=6, column=0, columnspan=3, sticky="w")

    def _bot_row(self, title: str, row: int) -> ttk.Combobox:
        """A labelled drop-down list of bots."""
        ttk.Label(self, text=title).grid(row=row, column=0, sticky="w")
        combo = ttk.Combobox(self, state="readonly", width=30)
        combo.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        return combo

    @property
    def mode(self) -> ModeKind:
        """The chosen mode."""
        return ModeKind(self.mode_variable.get())

    def _on_mode(self) -> None:
        """Red plays only in a duel."""
        solo = self.mode is ModeKind.SOLO
        self.red_combo.state(["disabled" if solo else "!disabled"])

    def _new_random_seed(self) -> None:
        """Fill the seed field with a random seed."""
        self.seed_entry.delete(0, "end")
        self.seed_entry.insert(0, str(random.randrange(RANDOM_SEED_LIMIT)))

    def _on_start(self) -> None:
        """Check the choices and ask for the match to start."""
        try:
            seed = parse_seed(self.seed_entry.get())
        except ValueError as error:
            self.show_error(f"Invalid seed: {error}")
            return
        blue = self._sources.get(self.blue_combo.get())
        red = self._sources.get(self.red_combo.get())
        solo = self.mode is ModeKind.SOLO
        if blue is None or (red is None and not solo):
            self.show_error("Choose a bot for every side.")
            return
        self.message_label.configure(text="")
        self.on_start(self.mode, blue, None if solo else red, seed)
