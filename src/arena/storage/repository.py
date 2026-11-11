"""Where matches are kept: the repository interface and an in-memory one.

The rest of the application only knows :class:`MatchRepository` (the
Repository pattern); which storage is used is decided when the
application is put together.
"""

from abc import ABC, abstractmethod
from dataclasses import replace

from arena.model.state import ModeKind
from arena.storage.records import MatchSummary, RecordedMatch, SoloRecord


class MatchRepository(ABC):
    """Stores finished matches and the best solo result per seed."""

    @abstractmethod
    def save_match(self, match: RecordedMatch) -> int:
        """Store a match and return its new id."""

    @abstractmethod
    def list_matches(
        self, mode: ModeKind | None = None, bot: str | None = None
    ) -> list[MatchSummary]:
        """Return match summaries, newest first, optionally filtered.

        Args:
            mode: Only matches of this mode.
            bot: Only matches in which a bot with this name played.
        """

    @abstractmethod
    def load_match(self, match_id: int) -> RecordedMatch:
        """Return a stored match.

        Raises:
            KeyError: If there is no match with this id.
        """

    @abstractmethod
    def delete_match(self, match_id: int) -> None:
        """Remove a match and all its turns."""

    @abstractmethod
    def solo_record(self, seed: int) -> SoloRecord | None:
        """Return the best solo result for a seed, if there is one."""

    @abstractmethod
    def save_solo_record(self, record: SoloRecord) -> bool:
        """Store a solo result if it beats the current record.

        Returns:
            Whether the result became the new record.
        """

    @abstractmethod
    def solo_records(self) -> list[SoloRecord]:
        """Return every solo record, ordered by seed."""

    def close(self) -> None:  # noqa: B027 - optional hook, empty on purpose
        """Release resources; storage without any does nothing."""


class InMemoryMatchRepository(MatchRepository):
    """Keeps everything in dictionaries; used in tests."""

    def __init__(self) -> None:
        """Start empty."""
        self._matches: dict[int, RecordedMatch] = {}
        self._solo: dict[int, SoloRecord] = {}
        self._next_id = 1

    def save_match(self, match: RecordedMatch) -> int:
        """Store a match under the next free id."""
        match_id = self._next_id
        self._next_id += 1
        summary = match.summary.with_id(match_id)
        self._matches[match_id] = replace(match, summary=summary)
        return match_id

    def list_matches(
        self, mode: ModeKind | None = None, bot: str | None = None
    ) -> list[MatchSummary]:
        """Return the matching summaries, newest first."""
        summaries = [
            match.summary
            for match in self._matches.values()
            if (mode is None or match.summary.mode is mode)
            and (bot is None or bot in match.summary.bots.values())
        ]
        return sorted(
            summaries,
            key=lambda summary: (summary.played_at, summary.match_id or 0),
            reverse=True,
        )

    def load_match(self, match_id: int) -> RecordedMatch:
        """Return the match with this id."""
        return self._matches[match_id]

    def delete_match(self, match_id: int) -> None:
        """Forget the match with this id."""
        self._matches.pop(match_id, None)

    def solo_record(self, seed: int) -> SoloRecord | None:
        """Return the record for a seed."""
        return self._solo.get(seed)

    def save_solo_record(self, record: SoloRecord) -> bool:
        """Keep the record if it is the first or a better one."""
        current = self._solo.get(record.seed)
        if current is not None and current.turns_used <= record.turns_used:
            return False
        self._solo[record.seed] = record
        return True

    def solo_records(self) -> list[SoloRecord]:
        """Return all records by seed."""
        return [self._solo[seed] for seed in sorted(self._solo)]
