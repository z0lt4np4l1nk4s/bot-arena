"""The main window: a notebook with the Play, Match Viewer and History tabs.

Matches run in a background thread; the window polls their events every
50 ms with ``after`` and is the only code that touches tkinter, always on
the main thread. Closing the window stops a running match and waits for
it in the same way, so the window never freezes and no bot process is
left behind.
"""

import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Final

from arena.application import Application
from arena.bots.source import BotSource
from arena.gui.formatting import result_text
from arena.gui.history_tab import HistoryTab
from arena.gui.match_session import MatchSession, find_saved_match_id
from arena.gui.match_viewer import MatchViewer
from arena.gui.play_tab import PlayTab
from arena.gui.sounds import SoundEffects
from arena.model.state import ModeKind
from arena.runtime.observers import (
    MatchEvent,
    MatchFailed,
    MatchFinished,
    MatchStarted,
    TurnPlayed,
)
from arena.storage.records import RecordedMatch

POLL_MS: Final = 50
CLOSE_POLL_MS: Final = 100
CLOSE_WAIT_SECONDS: Final = 10.0
TITLE: Final = "Bot Arena"
MINIMUM_SIZE: Final = (1000, 650)


class MainWindow:
    """Puts the tabs into a window and connects them to the matches."""

    def __init__(
        self,
        window: tk.Tk | tk.Toplevel,
        application: Application,
        sounds: SoundEffects,
    ) -> None:
        """Build the window's content.

        Args:
            window: The window to fill; it is destroyed by :meth:`close`.
            application: Builds matches and holds the history.
            sounds: Plays the viewer's sound effects.
        """
        self.window = window
        self.application = application
        self.session = MatchSession(application)
        self.closed = False
        self._closing = False
        self._close_deadline = 0.0
        window.title(TITLE)
        window.minsize(*MINIMUM_SIZE)
        self.notebook = ttk.Notebook(window)
        self.notebook.pack(fill="both", expand=True)
        self.play_tab = PlayTab(
            self.notebook,
            application.bot_sources,
            self.start_match,
            self.session.stop,
        )
        self.viewer = MatchViewer(
            self.notebook, application.settings.rules, sounds
        )
        self.history_tab = HistoryTab(
            self.notebook,
            application.repository,
            self.open_match,
            self._on_deleted,
        )
        self.notebook.add(self.play_tab, text="Play")
        self.notebook.add(self.viewer, text="Match Viewer")
        self.notebook.add(self.history_tab, text="History")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        window.protocol("WM_DELETE_WINDOW", self.close)
        self._timer: str | None = window.after(POLL_MS, self._poll)

    def start_match(
        self,
        mode: ModeKind,
        blue: BotSource,
        red: BotSource | None,
        seed: int,
    ) -> None:
        """Start a match in the background (from the Play tab)."""
        if self._closing:
            return
        try:
            self.session.start(mode, blue, red, seed)
        except RuntimeError as error:
            self.play_tab.show_error(str(error))
            return
        self.play_tab.set_running(True)
        self.play_tab.show_info(f"Playing seed {seed}...")

    def open_match(self, match: RecordedMatch) -> None:
        """Show a saved match in the viewer.

        A live match keeps running and is saved when it ends, but the
        viewer no longer follows it.
        """
        self.viewer.show_recorded(match)
        self.show_tab(self.viewer)

    @property
    def current_tab(self) -> str:
        """The name of the tab that is shown."""
        # Typeshed leaves Notebook.select unannotated; wrapped once here.
        return str(self.notebook.select())  # type: ignore[no-untyped-call]

    def show_tab(self, tab: tk.Widget) -> None:
        """Bring ``tab`` to the front."""
        self.notebook.select(tab)  # type: ignore[no-untyped-call]

    def close(self) -> None:
        """Stop a running match, wait for it, then destroy the window."""
        if self._closing:
            return
        self._closing = True
        self.session.stop()
        self.window.withdraw()
        self._close_deadline = time.monotonic() + CLOSE_WAIT_SECONDS
        self._finish_closing()

    def _finish_closing(self) -> None:
        """Destroy the window once the match thread has ended."""
        self.session.poll(limit=1_000_000)
        waiting = self.session.is_running
        if waiting and time.monotonic() < self._close_deadline:
            self.window.after(CLOSE_POLL_MS, self._finish_closing)
            return
        if self._timer is not None:
            self.window.after_cancel(self._timer)
            self._timer = None
        self.window.destroy()
        self.closed = True

    def _poll(self) -> None:
        """Handle the waiting match events, then poll again later."""
        self._timer = None
        if self._closing:
            return
        for event in self.session.poll():
            self._handle(event)
        self._timer = self.window.after(POLL_MS, self._poll)

    def _handle(self, event: MatchEvent) -> None:
        """Pass one match event to the tabs."""
        if isinstance(event, MatchStarted):
            self.viewer.start_live(event.summary, event.initial_state)
            self.show_tab(self.viewer)
        elif isinstance(event, TurnPlayed):
            if self.viewer.is_live:
                self.viewer.add_turn(event.record)
        elif isinstance(event, MatchFinished):
            self._on_finished(event)
        else:
            self._on_failed(event)

    def _on_finished(self, event: MatchFinished) -> None:
        """A match ended: show where it is saved and allow a new one."""
        summary = event.match.summary
        match_id = find_saved_match_id(self.application.repository, summary)
        if self.viewer.is_live:
            self.viewer.finish_live(event.match, match_id)
        self.play_tab.set_running(False)
        self.history_tab.refresh()
        if event.stopped:
            self.play_tab.show_info("The match was stopped and not saved.")
        else:
            self.play_tab.show_info(f"Last match: {result_text(summary)}")

    def _on_failed(self, event: MatchFailed) -> None:
        """A match could not be played: tell the user."""
        self.play_tab.set_running(False)
        self.play_tab.show_error(event.message)
        self.show_tab(self.play_tab)
        messagebox.showerror(
            "The match could not start", event.message, parent=self.window
        )

    def _on_deleted(self, match_id: int) -> None:
        """A match was deleted; stop showing it if it is open."""
        if self.viewer.match_id == match_id:
            self.viewer.clear()

    def _on_tab_changed(self, _event: object) -> None:
        """Read the bots or the history again when their tab is shown."""
        if self.current_tab == str(self.play_tab):
            self.play_tab.refresh_bots()
        elif self.current_tab == str(self.history_tab):
            self.history_tab.refresh()
