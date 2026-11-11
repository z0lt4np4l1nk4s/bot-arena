"""Tests for the match repositories (in memory and SQLite).

The same contract runs against both implementations.
"""

import dataclasses
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from arena.model.side import Side
from arena.model.state import ModeKind
from arena.storage.records import RecordedMatch, SoloRecord
from arena.storage.repository import InMemoryMatchRepository, MatchRepository
from arena.storage.sqlite_repository import SqliteMatchRepository
from recorded import record_match

RECORDED: RecordedMatch = record_match()


def with_summary(match: RecordedMatch, **changes: object) -> RecordedMatch:
    """A copy of ``match`` with some summary fields changed."""
    # Field names and values vary per test, so they cannot be typed here.
    summary = dataclasses.replace(
        match.summary,
        **changes,  # type: ignore[arg-type]
    )
    return dataclasses.replace(match, summary=summary)


def solo(seed: int, turns_used: int, bot: str = "Medium") -> SoloRecord:
    """A solo record played at a fixed time."""
    return SoloRecord(seed, turns_used, bot, datetime(2026, 11, 11, 9, 0))


class Contracts:
    """Holds the shared contract so unittest does not run it on its own."""

    class Repository(unittest.TestCase):
        """Behaviour every MatchRepository must have."""

        repository: MatchRepository

        def test_saved_match_can_be_loaded(self) -> None:
            match_id = self.repository.save_match(RECORDED)
            loaded = self.repository.load_match(match_id)
            self.assertEqual(
                loaded.summary, RECORDED.summary.with_id(match_id)
            )
            self.assertEqual(loaded.initial_state, RECORDED.initial_state)
            self.assertEqual(len(loaded.turns), len(RECORDED.turns))
            for saved, original in zip(
                loaded.turns, RECORDED.turns, strict=True
            ):
                self.assertEqual(saved, original)

        def test_ids_increase(self) -> None:
            first = self.repository.save_match(RECORDED)
            second = self.repository.save_match(RECORDED)
            self.assertTrue(second > first)

        def test_list_is_newest_first(self) -> None:
            start = RECORDED.summary.played_at
            for hours in range(3):
                self.repository.save_match(
                    with_summary(
                        RECORDED, played_at=start + timedelta(hours=hours)
                    )
                )
            times = [s.played_at for s in self.repository.list_matches()]
            self.assertEqual(times, sorted(times, reverse=True))

        def test_list_filters_by_mode_and_bot(self) -> None:
            self.repository.save_match(RECORDED)
            self.repository.save_match(
                with_summary(
                    RECORDED,
                    mode=ModeKind.SOLO,
                    bots={Side.BLUE: "Medium"},
                    delivered={Side.BLUE: 8},
                    winner=Side.BLUE,
                    solo_turns_used=120,
                )
            )
            self.assertEqual(
                len(self.repository.list_matches(mode=ModeKind.SOLO)), 1
            )
            self.assertEqual(
                len(self.repository.list_matches(bot="Medium")), 1
            )
            self.assertEqual(len(self.repository.list_matches(bot="Hard")), 1)

        def test_delete_removes_match(self) -> None:
            match_id = self.repository.save_match(RECORDED)
            self.repository.delete_match(match_id)
            self.assertEqual(self.repository.list_matches(), [])

        def test_load_missing_raises_key_error(self) -> None:
            with self.assertRaises(KeyError):
                self.repository.load_match(999)

        def test_first_solo_result_becomes_record(self) -> None:
            self.assertTrue(self.repository.save_solo_record(solo(4, 130)))
            self.assertEqual(self.repository.solo_record(4), solo(4, 130))

        def test_better_solo_result_replaces_record(self) -> None:
            self.repository.save_solo_record(solo(4, 130))
            self.assertTrue(
                self.repository.save_solo_record(solo(4, 110, "Hard"))
            )
            record = self.repository.solo_record(4)
            assert record is not None
            self.assertEqual((record.turns_used, record.bot), (110, "Hard"))

        def test_worse_solo_result_is_ignored(self) -> None:
            self.repository.save_solo_record(solo(4, 110))
            self.assertFalse(self.repository.save_solo_record(solo(4, 150)))
            record = self.repository.solo_record(4)
            assert record is not None
            self.assertEqual(record.turns_used, 110)

        def test_missing_solo_record_is_none(self) -> None:
            self.assertIsNone(self.repository.solo_record(99))

        def test_solo_records_sorted_by_seed(self) -> None:
            for seed in [9, 2, 5]:
                self.repository.save_solo_record(solo(seed, 100))
            seeds = [record.seed for record in self.repository.solo_records()]
            self.assertEqual(seeds, [2, 5, 9])


class InMemoryRepositoryTest(Contracts.Repository):
    def setUp(self) -> None:
        self.repository = InMemoryMatchRepository()


class SqliteRepositoryTest(Contracts.Repository):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "history.db"
        repository = SqliteMatchRepository(self.path)
        self.addCleanup(repository.close)
        self.repository = repository

    def test_reopening_keeps_matches(self) -> None:
        match_id = self.repository.save_match(RECORDED)
        with SqliteMatchRepository(self.path) as reopened:
            self.assertEqual(
                reopened.load_match(match_id),
                self.repository.load_match(match_id),
            )

    def test_failed_save_leaves_no_partial_match(self) -> None:
        last = RECORDED.turns[-1]
        broken_reply = dataclasses.replace(
            last.replies[Side.BLUE],
            elapsed_ms="not a number",  # type: ignore[arg-type]
        )
        broken_turn = dataclasses.replace(
            last, replies={**last.replies, Side.BLUE: broken_reply}
        )
        broken = dataclasses.replace(
            RECORDED, turns=(*RECORDED.turns[:-1], broken_turn)
        )
        with self.assertRaises((TypeError, ValueError, sqlite3.Error)):
            self.repository.save_match(broken)
        with sqlite3.connect(self.path) as connection:
            for table in ["matches", "turn_players", "turn_crystals"]:
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                self.assertEqual(count, 0, table)

    def test_deleting_a_match_deletes_its_turns(self) -> None:
        match_id = self.repository.save_match(RECORDED)
        self.repository.delete_match(match_id)
        with sqlite3.connect(self.path) as connection:
            for table in ["turn_players", "turn_events", "match_walls"]:
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                self.assertEqual(count, 0, table)

    def test_values_are_queryable_with_sql(self) -> None:
        self.repository.save_match(RECORDED)
        with sqlite3.connect(self.path) as connection:
            average = connection.execute(
                "SELECT AVG(elapsed_ms) FROM turn_players "
                "WHERE side = 'blue' AND turn > 0"
            ).fetchone()[0]
        self.assertTrue(average > 1.0)


if __name__ == "__main__":
    unittest.main()
