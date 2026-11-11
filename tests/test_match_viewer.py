"""Tests for the match viewer: map, playback controls and turn log."""

import unittest
from dataclasses import replace

from arena.gui.icons import IconName
from arena.gui.match_viewer import MatchViewer
from arena.gui.sounds import SoundEffects
from arena.model.state import EventKind
from arena.rules import Rules
from gui_support import hidden_root
from recorded import record_match

RECORDED = record_match(turns=30)
TURNS = len(RECORDED.turns)
LONG = record_match()
FIRST_SHOT_TURN = next(
    record.turn
    for record in LONG.turns
    if any(event.kind is EventKind.SHOT for event in record.state.events)
)


class RecordingPlayer:
    """Remembers every sound it is asked to play."""

    def __init__(self) -> None:
        self.sounds: list[bytes] = []

    def play(self, sound: bytes) -> None:
        self.sounds.append(sound)


class MatchViewerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = hidden_root(self)
        self.player = RecordingPlayer()
        self.viewer = MatchViewer(
            self.root, Rules(), SoundEffects(self.player)
        )

    def label(self) -> str:
        """The turn counter text."""
        return str(self.viewer.turn_label.cget("text"))

    def test_recorded_match_starts_at_turn_zero_paused(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.assertEqual(self.label(), f"Turn 0 / {TURNS}")
        self.assertFalse(self.viewer.is_live)

    def test_log_has_two_rows_per_turn(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.assertEqual(len(self.viewer.log.get_children()), 2 * TURNS)

    def test_next_button_moves_one_turn(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.viewer.next_button.invoke()
        self.assertEqual(self.label(), f"Turn 1 / {TURNS}")

    def test_selecting_a_log_row_jumps_to_its_turn(self) -> None:
        self.viewer.show_recorded(RECORDED)
        rows = self.viewer.log.get_children()
        self.viewer.log.selection_set(rows[9])  # Red's row of turn 5
        self.root.update()
        self.assertEqual(self.label(), f"Turn 5 / {TURNS}")

    def test_current_turn_rows_are_highlighted(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.viewer.next_button.invoke()
        self.viewer.next_button.invoke()
        highlighted = [
            self.viewer.log.set(item, "turn")
            for item in self.viewer.log.tag_has("current")
        ]
        self.assertEqual(highlighted, ["2", "2"])

    def test_live_turns_wait_for_playback(self) -> None:
        self.viewer.start_live(RECORDED.summary, RECORDED.initial_state)
        for record in RECORDED.turns[:3]:
            self.viewer.add_turn(record)
            self.root.update()
        self.assertTrue(self.viewer.is_live)
        # The tick timer may already have shown a turn, but never all three.
        playback = self.viewer.playback
        assert playback is not None
        self.assertEqual(playback.available, 3)
        self.assertLess(playback.current, 3)
        self.viewer.last_button.invoke()
        self.assertEqual(self.label(), "Turn 3 / 30")

    def test_finishing_live_match_shows_played_turns(self) -> None:
        self.viewer.start_live(RECORDED.summary, RECORDED.initial_state)
        for record in RECORDED.turns:
            self.viewer.add_turn(record)
        self.viewer.finish_live(RECORDED, match_id=7)
        self.assertFalse(self.viewer.is_live)
        self.assertEqual(self.viewer.match_id, 7)
        self.assertEqual(self.label(), f"Turn 0 / {TURNS}")
        self.viewer.last_button.invoke()
        self.assertEqual(self.label(), f"Turn {TURNS} / {TURNS}")

    def test_recorded_match_keeps_its_id(self) -> None:
        saved = replace(RECORDED, summary=RECORDED.summary.with_id(4))
        self.viewer.show_recorded(saved)
        self.assertEqual(self.viewer.match_id, 4)

    def test_step_forward_plays_effects(self) -> None:
        self.viewer.show_recorded(LONG)
        rows = self.viewer.log.get_children()
        self.viewer.log.selection_set(rows[2 * (FIRST_SHOT_TURN - 2)])
        self.root.update()
        self.assertEqual(self.player.sounds, [])
        self.viewer.next_button.invoke()
        self.assertEqual(len(self.player.sounds), 1)
        effects = self.viewer.map_canvas.find_withtag("effect")
        self.assertNotEqual(effects, ())

    def test_jump_plays_no_effects(self) -> None:
        self.viewer.show_recorded(LONG)
        rows = self.viewer.log.get_children()
        self.viewer.log.selection_set(rows[-1])
        self.root.update()
        self.assertEqual(self.player.sounds, [])
        self.assertEqual(self.viewer.map_canvas.find_withtag("effect"), ())

    def test_new_live_turns_keep_the_log_where_the_user_scrolled(
        self,
    ) -> None:
        self.viewer.start_live(LONG.summary, LONG.initial_state)
        for record in LONG.turns[:60]:
            self.viewer.add_turn(record)
        self.viewer.log.selection_set(self.viewer.log.get_children()[0])
        self.root.update()
        self.viewer.log.yview_moveto(0.5)
        self.root.update()
        scrolled = self.viewer.log.yview()
        for record in LONG.turns[60:65]:
            self.viewer.add_turn(record)
            self.root.update()
        self.assertEqual(self.viewer.log.yview()[0], scrolled[0])

    def test_new_live_turns_do_not_interrupt_an_animation(self) -> None:
        self.viewer.start_live(LONG.summary, LONG.initial_state)
        for record in LONG.turns[:FIRST_SHOT_TURN]:
            self.viewer.add_turn(record)
        rows = self.viewer.log.get_children()
        self.viewer.log.selection_set(rows[2 * (FIRST_SHOT_TURN - 2)])
        self.root.update()
        self.viewer.next_button.invoke()
        drawn = self.viewer.map_canvas.find_withtag("effect")
        self.assertNotEqual(drawn, ())
        self.viewer.add_turn(LONG.turns[FIRST_SHOT_TURN])
        self.root.update_idletasks()
        self.assertEqual(self.viewer.map_canvas.find_withtag("effect"), drawn)

    def test_sound_button_mutes(self) -> None:
        self.viewer.sound_button.invoke()
        self.assertFalse(self.viewer.sounds.enabled)
        self.assertIs(self.viewer.sound_button.icon, IconName.SOUND_OFF)
        self.viewer.sound_button.invoke()
        self.assertTrue(self.viewer.sounds.enabled)

    def test_clear_shows_empty_viewer(self) -> None:
        self.viewer.show_recorded(RECORDED)
        self.viewer.clear()
        self.assertEqual(self.viewer.log.get_children(), ())
        self.assertIsNone(self.viewer.match_id)
        self.assertNotEqual(
            self.viewer.map_canvas.find_withtag("placeholder"), ()
        )


if __name__ == "__main__":
    unittest.main()
