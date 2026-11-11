"""Save every finished match: an observer that writes to a repository."""

from arena.model.state import GameState
from arena.storage.records import (
    MatchSummary,
    RecordedMatch,
    SoloRecord,
    TurnRecord,
)
from arena.storage.repository import MatchRepository


class StorageObserver:
    """Stores finished matches and solo records in the given repository.

    The repository is passed in (dependency injection), so the same
    observer saves to SQLite in the application and to memory in tests.
    Matches the user stopped are not saved.
    """

    def __init__(self, repository: MatchRepository) -> None:
        """Save into ``repository``."""
        self.repository = repository
        self.last_saved_id: int | None = None

    def on_match_started(
        self, summary: MatchSummary, initial_state: GameState
    ) -> None:
        """Nothing is saved until the match ends."""

    def on_turn(self, record: TurnRecord) -> None:
        """Nothing is saved until the match ends."""

    def on_match_finished(self, match: RecordedMatch, stopped: bool) -> None:
        """Save a match that ended normally, and a better solo result."""
        if stopped:
            return
        self.last_saved_id = self.repository.save_match(match)
        summary = match.summary
        if summary.solo_turns_used is not None:
            bot = next(iter(summary.bots.values()))
            self.repository.save_solo_record(
                SoloRecord(
                    summary.seed,
                    summary.solo_turns_used,
                    bot,
                    summary.played_at,
                )
            )
