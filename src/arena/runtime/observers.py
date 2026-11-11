"""Listeners that the match runner informs about a match (Observer).

The runner does not know who listens: the GUI, the database or a test
just implement :class:`MatchObserver` and are passed to the runner.
"""

from typing import Protocol

from arena.model.state import GameState
from arena.storage.records import MatchSummary, RecordedMatch, TurnRecord


class MatchObserver(Protocol):
    """Receives the start, every turn and the end of a match."""

    def on_match_started(
        self, summary: MatchSummary, initial_state: GameState
    ) -> None:
        """The match is about to begin."""

    def on_turn(self, record: TurnRecord) -> None:
        """A turn was played."""

    def on_match_finished(self, match: RecordedMatch, stopped: bool) -> None:
        """The match ended; ``stopped`` means the user ended it early."""
