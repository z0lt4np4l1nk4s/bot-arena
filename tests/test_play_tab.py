"""Tests for the Play tab: choosing bots, mode and seed."""

import unittest
from pathlib import Path

from arena.bots.source import BotSource
from arena.gui.play_tab import PlayTab, parse_seed
from arena.model.state import ModeKind
from gui_support import hidden_root

BUILTINS = [BotSource.builtin(name) for name in ("Easy", "Hard", "Medium")]
StartCall = tuple[ModeKind, BotSource, BotSource | None, int]


class ParseSeedTest(unittest.TestCase):
    def test_seed_accepts_numbers_with_spaces(self) -> None:
        self.assertEqual(parse_seed(" 42 "), 42)
        self.assertEqual(parse_seed("0"), 0)
        self.assertEqual(parse_seed(str(2**63 - 1)), 2**63 - 1)

    def test_seed_rejects_text_negative_and_too_large(self) -> None:
        for text in ("", "abc", "4.5", "-1", "²", str(2**63)):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_seed(text)


class PlayTabTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bots = list(BUILTINS)
        self.starts: list[StartCall] = []
        self.stops = 0
        self.tab = PlayTab(
            hidden_root(self),
            lambda: list(self.bots),
            self.record_start,
            self.record_stop,
        )

    def record_start(
        self,
        mode: ModeKind,
        blue: BotSource,
        red: BotSource | None,
        seed: int,
    ) -> None:
        self.starts.append((mode, blue, red, seed))

    def record_stop(self) -> None:
        self.stops += 1

    def test_defaults_are_medium_against_easy(self) -> None:
        self.assertEqual(self.tab.blue_combo.get(), "Medium (built-in)")
        self.assertEqual(self.tab.red_combo.get(), "Easy (built-in)")

    def test_start_calls_back_with_choices(self) -> None:
        self.tab.blue_combo.set("Hard (built-in)")
        self.tab.seed_entry.delete(0, "end")
        self.tab.seed_entry.insert(0, "42")
        self.tab.start_button.invoke()
        self.assertEqual(
            self.starts,
            [
                (
                    ModeKind.DUEL,
                    BotSource.builtin("Hard"),
                    BotSource.builtin("Easy"),
                    42,
                )
            ],
        )

    def test_solo_disables_red(self) -> None:
        self.tab.solo_button.invoke()
        self.assertTrue(self.tab.red_combo.instate(["disabled"]))
        self.tab.start_button.invoke()
        mode, _, red, _ = self.starts[0]
        self.assertEqual((mode, red), (ModeKind.SOLO, None))

    def test_invalid_seed_shows_error_and_does_not_start(self) -> None:
        self.tab.seed_entry.delete(0, "end")
        self.tab.seed_entry.insert(0, "abc")
        self.tab.start_button.invoke()
        self.assertEqual(self.starts, [])
        self.assertNotEqual(self.tab.message_label.cget("text"), "")

    def test_random_button_fills_a_seed(self) -> None:
        self.tab.seed_entry.delete(0, "end")
        self.tab.random_button.invoke()
        self.assertLess(parse_seed(self.tab.seed_entry.get()), 1_000_000)

    def test_running_disables_start(self) -> None:
        self.tab.set_running(True)
        self.assertTrue(self.tab.start_button.instate(["disabled"]))
        self.assertFalse(self.tab.stop_button.instate(["disabled"]))
        self.tab.stop_button.invoke()
        self.assertEqual(self.stops, 1)
        self.tab.set_running(False)
        self.assertFalse(self.tab.start_button.instate(["disabled"]))
        self.assertTrue(self.tab.stop_button.instate(["disabled"]))

    def test_new_user_bot_appears_after_refresh(self) -> None:
        self.bots.append(BotSource.from_file(Path("user_bots/my_bot.py")))
        self.tab.refresh_bots()
        self.assertIn("my_bot", self.tab.blue_combo.cget("values"))
        self.assertEqual(self.tab.blue_combo.get(), "Medium (built-in)")

    def test_removed_bot_falls_back_to_default(self) -> None:
        self.bots.append(BotSource.from_file(Path("user_bots/my_bot.py")))
        self.tab.refresh_bots()
        self.tab.blue_combo.set("my_bot")
        self.bots.pop()
        self.tab.refresh_bots()
        self.assertEqual(self.tab.blue_combo.get(), "Medium (built-in)")


if __name__ == "__main__":
    unittest.main()
