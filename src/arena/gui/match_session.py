"""One match at a time for the window, without any widgets.

The session starts a match in the background and collects its events in
a queue; the window empties the queue a little at a time with
:meth:`MatchSession.poll`, so tkinter is only used from the main thread.
"""

import queue
from typing import Final

from arena.application import Application
from arena.bots.source import BotSource
from arena.model.state import ModeKind
from arena.runtime.match_runner import MatchHandle
from arena.runtime.observers import MatchEvent, QueueObserver
from arena.storage.records import MatchSummary
from arena.storage.repository import MatchRepository

# The most events handled in one poll, so a burst of turns cannot freeze
# the window; the rest wait for the next poll.
POLL_LIMIT: Final = 50


class MatchSession:
    """Starts and stops matches and hands over their events."""

    def __init__(
        self,
        application: Application,
        events: "queue.Queue[MatchEvent] | None" = None,
    ) -> None:
        """Create a session.

        Args:
            application: Builds the matches.
            events: The queue to collect events in; a new one if ``None``.
        """
        self.application = application
        self._events: queue.Queue[MatchEvent] = (
            events if events is not None else queue.Queue()
        )
        self._handle: MatchHandle | None = None

    @property
    def is_running(self) -> bool:
        """Whether a match is running or its events are still waiting."""
        running = self._handle is not None and self._handle.is_running
        return running or not self._events.empty()

    def start(
        self,
        mode: ModeKind,
        blue: BotSource,
        red: BotSource | None,
        seed: int,
    ) -> None:
        """Start a match in the background.

        Raises:
            RuntimeError: If a match is still running.
        """
        if self.is_running:
            message = "a match is already running"
            raise RuntimeError(message)
        runner = self.application.create_match(
            mode, blue, red, observers=[QueueObserver(self._events)]
        )
        self._handle = runner.run_in_background(seed)

    def stop(self) -> None:
        """Ask the running match to end after the current turn."""
        if self._handle is not None:
            self._handle.stop()

    def poll(self, limit: int = POLL_LIMIT) -> list[MatchEvent]:
        """Take at most ``limit`` waiting events, without waiting."""
        events: list[MatchEvent] = []
        while len(events) < limit:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events


def find_saved_match_id(
    repository: MatchRepository, summary: MatchSummary
) -> int | None:
    """The history id of a match that was just played and saved.

    Args:
        repository: The match history.
        summary: The summary the runner reported (it has no id).

    Returns:
        The id, or ``None`` if the match was not saved (e.g. stopped).
    """
    for saved in repository.list_matches(mode=summary.mode):
        if (
            saved.played_at == summary.played_at
            and saved.seed == summary.seed
            and dict(saved.bots) == dict(summary.bots)
        ):
            return saved.match_id
    return None
