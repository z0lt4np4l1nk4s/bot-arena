"""Tests for the playback state machine of the match viewer."""

import unittest

from arena.gui.playback import Playback, make_jump_to


def live(available: int = 0) -> Playback:
    """A live match that is playing, with ``available`` turns so far."""
    playback = Playback(max_turns=200, playing=True)
    for _ in range(available):
        playback.add_turn()
    return playback


def recorded(turns: int = 10) -> Playback:
    """A finished match at turn 0, paused."""
    return Playback(max_turns=200, available=turns, finished=True)


class LiveTest(unittest.TestCase):
    def test_live_match_follows_new_turns(self) -> None:
        playback = live(3)
        self.assertEqual(playback.current, 3)

    def test_paused_playback_does_not_follow(self) -> None:
        playback = live(2)
        playback.toggle()
        playback.add_turn()
        self.assertEqual((playback.current, playback.available), (2, 3))

    def test_manual_navigation_pauses(self) -> None:
        for move in ("first", "previous", "next"):
            with self.subTest(move=move):
                playback = live(5)
                getattr(playback, move)()
                self.assertFalse(playback.playing)
        playback = live(5)
        playback.jump(2)
        self.assertFalse(playback.playing)

    def test_last_resumes_following_while_live(self) -> None:
        playback = live(5)
        playback.first()
        playback.last()
        playback.add_turn()
        self.assertTrue(playback.playing)
        self.assertEqual(playback.current, 6)

    def test_tick_catches_up_then_waits(self) -> None:
        playback = live(3)
        playback.jump(1)
        playback.toggle()
        self.assertEqual(
            [playback.tick(), playback.tick(), playback.tick()],
            [True, True, False],
        )
        self.assertEqual(playback.current, 3)
        self.assertTrue(playback.playing)


class RecordedTest(unittest.TestCase):
    def test_last_on_finished_match_does_not_play(self) -> None:
        playback = recorded()
        playback.last()
        self.assertEqual(playback.current, 10)
        self.assertFalse(playback.playing)

    def test_tick_stops_at_end_of_finished_match(self) -> None:
        playback = recorded(2)
        playback.toggle()
        self.assertEqual(
            [playback.tick(), playback.tick(), playback.tick()],
            [True, True, False],
        )
        self.assertFalse(playback.playing)

    def test_toggle_at_end_restarts(self) -> None:
        playback = recorded(4)
        playback.last()
        playback.toggle()
        self.assertEqual(playback.current, 0)
        self.assertTrue(playback.playing)

    def test_navigation_is_clamped(self) -> None:
        playback = recorded(10)
        playback.jump(-3)
        self.assertEqual(playback.current, 0)
        playback.previous()
        self.assertEqual(playback.current, 0)
        playback.jump(999)
        self.assertEqual(playback.current, 10)
        playback.next()
        self.assertEqual(playback.current, 10)

    def test_label_uses_max_turns_until_finished(self) -> None:
        playback = live(47)
        self.assertEqual(playback.label, "Turn 47 / 200")
        playback.finish()
        self.assertEqual(playback.label, "Turn 47 / 47")

    def test_finish_stops_waiting_for_turns(self) -> None:
        playback = live(3)
        playback.finish()
        self.assertFalse(playback.tick())
        self.assertFalse(playback.playing)

    def test_jump_callback_moves_and_pauses(self) -> None:
        playback = live(8)
        jump_to_three = make_jump_to(playback, 3)
        jump_to_three()
        self.assertEqual(playback.current, 3)
        self.assertFalse(playback.playing)


if __name__ == "__main__":
    unittest.main()
