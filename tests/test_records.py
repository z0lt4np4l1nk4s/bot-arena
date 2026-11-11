"""Tests for match and turn records."""

import dataclasses
import unittest
from datetime import datetime

from arena.model.side import Side
from arena.model.state import EventKind, ModeKind
from arena.storage.records import MatchSummary
from recorded import record_match

SUMMARY = MatchSummary(
    match_id=None,
    played_at=datetime(2026, 11, 11, 10, 30),
    mode=ModeKind.DUEL,
    seed=7,
    bots={Side.BLUE: "Hard", Side.RED: "Medium"},
    winner=Side.BLUE,
    delivered={Side.BLUE: 9, Side.RED: 7},
    turns=170,
    solo_turns_used=None,
)


class RecordsTest(unittest.TestCase):
    def test_summary_with_id_keeps_other_fields(self) -> None:
        stored = SUMMARY.with_id(12)
        self.assertEqual(stored.match_id, 12)
        self.assertEqual(dataclasses.replace(stored, match_id=None), SUMMARY)

    def test_records_are_immutable(self) -> None:
        with self.assertRaises(dataclasses.FrozenInstanceError):
            SUMMARY.seed = 3  # type: ignore[misc]


class RecordedHelperTest(unittest.TestCase):
    def test_recorded_helper_contains_traps_shots_and_events(self) -> None:
        match = record_match()
        kinds = {
            event.kind
            for record in match.turns
            for event in record.state.events
        }
        self.assertTrue(
            {EventKind.HIT, EventKind.TRAPPED, EventKind.DELIVERED} <= kinds
        )
        self.assertTrue(any(record.state.traps for record in match.turns))
        replies = [
            reply
            for record in match.turns
            for reply in record.replies.values()
        ]
        self.assertTrue(any(reply.error for reply in replies))
        self.assertTrue(any(reply.timed_out for reply in replies))
        self.assertEqual(match.summary.turns, len(match.turns))


if __name__ == "__main__":
    unittest.main()
