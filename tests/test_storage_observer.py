"""Tests for saving matches when they finish."""

import dataclasses
import unittest

from arena.model.side import Side
from arena.model.state import ModeKind
from arena.storage.records import RecordedMatch
from arena.storage.repository import InMemoryMatchRepository
from arena.storage.storage_observer import StorageObserver
from recorded import record_match

DUEL: RecordedMatch = record_match(turns=20)


def as_solo(match: RecordedMatch, turns_used: int | None) -> RecordedMatch:
    """Pretend ``match`` was a solo run with the given result."""
    summary = dataclasses.replace(
        match.summary,
        mode=ModeKind.SOLO,
        bots={Side.BLUE: "Medium"},
        delivered={Side.BLUE: 8},
        solo_turns_used=turns_used,
    )
    return dataclasses.replace(match, summary=summary)


class StorageObserverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryMatchRepository()
        self.observer = StorageObserver(self.repository)

    def test_finished_match_is_saved(self) -> None:
        self.observer.on_match_finished(DUEL, stopped=False)
        self.assertEqual(len(self.repository.list_matches()), 1)
        self.assertEqual(self.observer.last_saved_id, 1)

    def test_stopped_match_is_not_saved(self) -> None:
        self.observer.on_match_finished(DUEL, stopped=True)
        self.assertEqual(self.repository.list_matches(), [])
        self.assertIsNone(self.observer.last_saved_id)

    def test_finished_solo_updates_record(self) -> None:
        self.observer.on_match_finished(as_solo(DUEL, 104), stopped=False)
        record = self.repository.solo_record(DUEL.summary.seed)
        assert record is not None
        self.assertEqual((record.turns_used, record.bot), (104, "Medium"))

    def test_unfinished_solo_is_not_a_record(self) -> None:
        self.observer.on_match_finished(as_solo(DUEL, None), stopped=False)
        self.assertIsNone(self.repository.solo_record(DUEL.summary.seed))
        self.assertEqual(len(self.repository.list_matches()), 1)


if __name__ == "__main__":
    unittest.main()
