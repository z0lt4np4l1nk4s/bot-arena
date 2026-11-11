"""Tests for the main window: starting, watching and closing matches.

These tests play real (short) matches with bot processes.
"""

import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from applications import add_broken_bot, make_application, wait_for
from arena.bots.source import BotSource
from arena.gui.main_window import MainWindow
from arena.gui.sounds import SilentSoundPlayer, SoundEffects
from arena.model.state import ModeKind
from arena.rules import Rules
from gui_support import hidden_root
from recorded import record_match

RECORDED = record_match(turns=10)
MEDIUM = BotSource.builtin("Medium")
EASY = BotSource.builtin("Easy")
# Answers too late every turn, so its matches take a while.
SLOW = BotSource.from_file(Path(__file__).parent / "bot_files" / "slow.py")


class MainWindowTest(unittest.TestCase):
    def open_window(self, rules: Rules | None = None) -> MainWindow:
        """A main window on a new top-level window of the test root."""
        self.root = hidden_root(self)
        self.application = (
            make_application(self) if rules is None
            else make_application(self, rules)
        )  # fmt: skip
        window = MainWindow(
            tk.Toplevel(self.root),
            self.application,
            SoundEffects(SilentSoundPlayer()),
        )
        self.addCleanup(self.close_window, window)
        return window

    def close_window(self, window: MainWindow) -> None:
        window.close()
        wait_for(lambda: window.closed, 15, self.root.update)

    def match_over(self, window: MainWindow) -> bool:
        """Whether the Play tab can start a new match again."""
        return not window.play_tab.start_button.instate(["disabled"])

    def test_started_match_opens_viewer_and_finishes(self) -> None:
        window = self.open_window()
        window.start_match(ModeKind.DUEL, MEDIUM, EASY, 3)
        self.assertTrue(window.play_tab.start_button.instate(["disabled"]))
        self.assertTrue(
            wait_for(lambda: self.match_over(window), 20, self.root.update)
        )
        self.assertEqual(window.current_tab, str(window.viewer))
        saved = self.application.repository.list_matches()
        self.assertEqual(len(saved), 1)
        self.assertEqual(window.viewer.match_id, saved[0].match_id)
        self.assertFalse(window.viewer.is_live)
        self.assertEqual(len(window.history_tab.table.get_children()), 1)

    def test_start_waits_until_the_match_thread_has_ended(self) -> None:
        # The slow bot is still thinking when the last turn ends, so the
        # match thread needs a moment to stop it after the result is in.
        window = self.open_window(
            Rules(
                turn_time_limit_ms=200,
                bot_kill_timeout_ms=600,
                duel_max_turns=2,
            )
        )
        window.start_match(ModeKind.DUEL, SLOW, EASY, 3)

        def result_shown() -> bool:
            text = str(window.play_tab.message_label.cget("text"))
            return text.startswith("Last match")

        self.assertTrue(wait_for(result_shown, 15, self.root.update))
        self.assertTrue(window.session.is_running)
        self.assertTrue(window.play_tab.start_button.instate(["disabled"]))
        self.assertTrue(
            wait_for(lambda: self.match_over(window), 10, self.root.update)
        )
        self.assertFalse(window.session.is_running)

    def test_failed_match_reports_error_and_enables_start(self) -> None:
        window = self.open_window()
        broken = BotSource.from_file(add_broken_bot(self.application))
        with mock.patch(
            "arena.gui.main_window.messagebox.showerror"
        ) as show_error:
            window.start_match(ModeKind.DUEL, broken, EASY, 3)
            self.assertTrue(
                wait_for(lambda: self.match_over(window), 10, self.root.update)
            )
        show_error.assert_called_once()
        message = str(window.play_tab.message_label.cget("text"))
        self.assertIn("SyntaxError", message)

    def test_closing_during_a_match_stops_it_and_destroys_the_root(
        self,
    ) -> None:
        long_rules = Rules(
            turn_time_limit_ms=200,
            bot_kill_timeout_ms=600,
            duel_max_turns=200,
        )
        window = self.open_window(long_rules)
        window.start_match(ModeKind.DUEL, SLOW, EASY, 3)
        wait_for(lambda: False, 1.0, self.root.update)
        window.close()
        self.assertTrue(wait_for(lambda: window.closed, 12, self.root.update))
        self.assertFalse(window.session.is_running)
        self.assertEqual(self.application.repository.list_matches(), [])

    def test_play_tab_lists_new_user_bots_when_shown(self) -> None:
        window = self.open_window()
        folder = self.application.settings.user_bots_folder
        (folder / "late_bot.py").write_text("", encoding="utf-8")
        window.show_tab(window.viewer)
        self.root.update()
        window.show_tab(window.play_tab)
        self.root.update()
        self.assertIn("late_bot", window.play_tab.blue_combo.cget("values"))

    def open_from_history(self, window: MainWindow) -> int:
        """Save the recorded match and open it from the History tab."""
        match_id = self.application.repository.save_match(RECORDED)
        history = window.history_tab
        history.refresh()
        history.table.selection_set(history.table.get_children()[0])
        history.open_selected()
        return match_id

    def test_opening_a_match_from_history_shows_it(self) -> None:
        window = self.open_window()
        match_id = self.open_from_history(window)
        self.assertEqual(window.current_tab, str(window.viewer))
        self.assertEqual(window.viewer.match_id, match_id)

    def test_deleting_the_open_match_clears_the_viewer(self) -> None:
        window = self.open_window()
        self.open_from_history(window)
        with mock.patch(
            "arena.gui.history_tab.messagebox.askyesno", return_value=True
        ):
            window.history_tab.delete_button.invoke()
        self.assertIsNone(window.viewer.match_id)
        self.assertIsNone(window.viewer.playback)

    def test_history_is_read_again_when_shown(self) -> None:
        window = self.open_window()
        self.application.repository.save_match(RECORDED)
        window.show_tab(window.history_tab)
        self.root.update()
        self.assertEqual(len(window.history_tab.table.get_children()), 1)


if __name__ == "__main__":
    unittest.main()
