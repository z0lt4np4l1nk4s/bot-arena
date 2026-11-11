"""Listeners that the match runner informs about a match (Observer).

The runner does not know who listens: the GUI, the database or a test
just implement :class:`MatchObserver` and are passed to the runner.
"""

import queue
from dataclasses import dataclass
from typing import Protocol, TypeAlias

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

    def on_match_failed(self, message: str) -> None:
        """The match could not be played (e.g. a bot did not load)."""


@dataclass(frozen=True)
class MatchStarted:
    """GUI event: a match began."""

    summary: MatchSummary
    initial_state: GameState


@dataclass(frozen=True)
class TurnPlayed:
    """GUI event: a turn was played."""

    record: TurnRecord


@dataclass(frozen=True)
class MatchFinished:
    """GUI event: the match ended (``stopped`` if the user stopped it)."""

    match: RecordedMatch
    stopped: bool


@dataclass(frozen=True)
class MatchFailed:
    """GUI event: the match could not go on, e.g. a bot did not load."""

    message: str


MatchEvent: TypeAlias = MatchStarted | TurnPlayed | MatchFinished | MatchFailed


class QueueObserver:
    """Passes match events to another thread through a queue.

    The match runs in a background thread, but tkinter may only be used
    from the main thread; the GUI reads this queue from there.
    """

    def __init__(self, events: "queue.Queue[MatchEvent]") -> None:
        """Send events to ``events`` (an unbounded queue, never blocks)."""
        self.events = events

    def on_match_started(
        self, summary: MatchSummary, initial_state: GameState
    ) -> None:
        """Queue a :class:`MatchStarted` event."""
        self.events.put(MatchStarted(summary, initial_state))

    def on_turn(self, record: TurnRecord) -> None:
        """Queue a :class:`TurnPlayed` event."""
        self.events.put(TurnPlayed(record))

    def on_match_finished(self, match: RecordedMatch, stopped: bool) -> None:
        """Queue a :class:`MatchFinished` event."""
        self.events.put(MatchFinished(match, stopped))

    def on_match_failed(self, message: str) -> None:
        """Queue a :class:`MatchFailed` event."""
        self.events.put(MatchFailed(message))
