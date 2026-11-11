"""Play one match from start to end.

Every turn both bots are asked **at the same time**: their blocking
``ask`` calls run in a thread pool and are awaited together with
``asyncio.gather``. Everything the runner needs (the game mode, the bot
clients and the observers) is passed in, so tests can use fake bots and
the GUI can listen in, without the runner knowing about either.

A bot client is never asked twice at once: if its previous answer is
still being computed (for example while a hanging bot is restarted), the
turn counts as timed out for that bot without asking it again.
"""

import asyncio
import concurrent.futures
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Final

from arena.engine.modes import GameMode
from arena.model.actions import Action
from arena.model.replies import BotReply
from arena.model.side import Side
from arena.model.state import GameState
from arena.runtime.bot_process import (
    JOIN_TIMEOUT_SECONDS,
    STARTUP_TIMEOUT_SECONDS,
)
from arena.runtime.clients import BotClient
from arena.runtime.observers import MatchObserver
from arena.storage.records import MatchSummary, RecordedMatch, TurnRecord
from arena.utilities.logger import get_logger

# Extra time on top of the turn limit before the runner gives up on a
# client: enough for a bot process to be killed and started again.
DEFAULT_SAFETY_MARGIN_SECONDS: Final = (
    STARTUP_TIMEOUT_SECONDS + JOIN_TIMEOUT_SECONDS + 1.0
)

logger: Final = get_logger("runtime")


class MatchRunner:
    """Plays a match with the given mode, bots and observers."""

    def __init__(
        self,
        mode: GameMode,
        clients: Mapping[Side, BotClient],
        observers: Sequence[MatchObserver] = (),
        safety_margin_seconds: float = DEFAULT_SAFETY_MARGIN_SECONDS,
    ) -> None:
        """Create a runner; nothing starts until :meth:`run`.

        Args:
            mode: The game mode (duel or solo).
            clients: One bot client per side the mode needs.
            observers: Everyone to inform about the match.
            safety_margin_seconds: How much longer than the turn limit to
                wait for a client before treating it as timed out.
        """
        self.mode = mode
        self.clients = dict(clients)
        self.observers = list(observers)
        self.safety_margin_seconds = safety_margin_seconds
        self._pending: dict[Side, Future[BotReply]] = {}

    def run_in_background(self, seed: int) -> "MatchHandle":
        """Play the match in a background thread.

        Args:
            seed: The map seed.

        Returns:
            A handle to stop the match or wait for its result.
        """
        return MatchHandle(self, seed)

    def run(
        self, seed: int, stop_event: threading.Event | None = None
    ) -> RecordedMatch:
        """Play the match to its end (or until ``stop_event`` is set).

        Args:
            seed: The map seed.
            stop_event: Set it from another thread to stop early.

        Returns:
            The recorded match.

        Raises:
            BotLoadError: If a bot cannot be started.
        """
        return asyncio.run(self.run_async(seed, stop_event))

    async def run_async(
        self, seed: int, stop_event: threading.Event | None = None
    ) -> RecordedMatch:
        """Play the match inside an already running event loop.

        Args:
            seed: The map seed.
            stop_event: Set it from another thread to stop early.

        Returns:
            The recorded match.

        Raises:
            BotLoadError: If a bot cannot be started.
        """
        self._pending = {}
        executor = ThreadPoolExecutor(
            max_workers=len(self.clients), thread_name_prefix="bot-ask"
        )
        try:
            for client in self.clients.values():
                client.start()
            return await self._play(seed, stop_event, executor)
        finally:
            self._wait_for_pending_questions()
            self._stop_clients()
            executor.shutdown(wait=False, cancel_futures=True)

    def notify_failure(self, message: str) -> None:
        """Tell every observer that the match could not be played."""
        self._notify(
            "on_match_failed",
            lambda observer: observer.on_match_failed(message),
        )

    async def _play(
        self,
        seed: int,
        stop_event: threading.Event | None,
        executor: ThreadPoolExecutor,
    ) -> RecordedMatch:
        """The turn loop."""
        initial = self.mode.setup_map(seed)
        played_at = datetime.now()
        started = self._summary(seed, played_at, initial)
        self._notify(
            "on_match_started",
            lambda observer: observer.on_match_started(started, initial),
        )
        state = initial
        records: list[TurnRecord] = []
        while not self.mode.is_over(state):
            if stop_event is not None and stop_event.is_set():
                break
            turn = state.turn + 1
            replies = await self._ask_all(executor, turn, state)
            actions = {side: reply.action for side, reply in replies.items()}
            state = self.mode.step(state, actions)
            record = TurnRecord(turn, state, replies)
            records.append(record)
            self._notify("on_turn", _turn_reporter(record))
        match = RecordedMatch(
            self._summary(seed, played_at, state), initial, tuple(records)
        )
        stopped = not self.mode.is_over(state)
        self._notify(
            "on_match_finished",
            lambda observer: observer.on_match_finished(match, stopped),
        )
        return match

    async def _ask_all(
        self, executor: ThreadPoolExecutor, turn: int, state: GameState
    ) -> dict[Side, BotReply]:
        """Ask every bot at once and wait for all answers."""
        sides = list(self.clients)
        replies = await asyncio.gather(
            *(self._ask(executor, side, turn, state) for side in sides)
        )
        return dict(zip(sides, replies, strict=True))

    async def _ask(
        self,
        executor: ThreadPoolExecutor,
        side: Side,
        turn: int,
        state: GameState,
    ) -> BotReply:
        """Ask one bot, unless it is still busy with an earlier question."""
        client = self.clients[side]
        pending = self._pending.get(side)
        if pending is not None and not pending.done():
            return self._no_answer(turn)
        view = self.mode.state_for_bot(state, side)
        future = executor.submit(client.ask, turn, view)
        self._pending[side] = future
        try:
            return await asyncio.wait_for(
                asyncio.wrap_future(future), self._safety_limit()
            )
        except asyncio.TimeoutError:
            logger.error("bot %s never answered turn %d", client.name, turn)
            return self._no_answer(turn)
        except Exception as error:  # keep the match going
            logger.exception("asking bot %s failed", client.name)
            return BotReply(turn, Action.wait(), 0.0, error=str(error))

    def _safety_limit(self) -> float:
        """Seconds to wait for a client before giving up on this turn."""
        turn_limit = self.mode.rules.turn_time_limit_ms / 1000
        return turn_limit + self.safety_margin_seconds

    def _no_answer(self, turn: int) -> BotReply:
        """A timed-out ``wait``, the same as a bot process reports."""
        limit_ms = float(self.mode.rules.turn_time_limit_ms)
        return BotReply(turn, Action.wait(), limit_ms, timed_out=True)

    def _summary(
        self, seed: int, played_at: datetime, state: GameState
    ) -> MatchSummary:
        """Describe the match as it stands in ``state``."""
        finished = self.mode.is_over(state)
        return MatchSummary(
            match_id=None,
            played_at=played_at,
            mode=state.mode,
            seed=seed,
            bots={side: client.name for side, client in self.clients.items()},
            winner=self.mode.winner(state) if finished else None,
            delivered={
                side: player.delivered
                for side, player in state.players.items()
            },
            turns=state.turn,
            solo_turns_used=self.mode.turns_used(state),
        )

    def _notify(
        self, event: str, call: Callable[[MatchObserver], None]
    ) -> None:
        """Inform every observer; one failing does not stop the others."""
        for observer in self.observers:
            try:
                call(observer)
            except Exception:  # observers must not end a match
                logger.exception(
                    "observer %s failed in %s", type(observer).__name__, event
                )

    def _wait_for_pending_questions(self) -> None:
        """Let unfinished questions end before the clients are stopped.

        Otherwise a bot being restarted inside ``ask`` could finish its
        restart after :meth:`_stop_clients` and leave a process behind.
        """
        unfinished = [f for f in self._pending.values() if not f.done()]
        if unfinished:
            # At least as long as a bot restart can take, however small the
            # per-turn margin is.
            longest = max(self._safety_limit(), DEFAULT_SAFETY_MARGIN_SECONDS)
            concurrent.futures.wait(unfinished, timeout=longest)

    def _stop_clients(self) -> None:
        """Stop every client, even if some of them fail to stop."""
        for client in self.clients.values():
            try:
                client.stop()
            except Exception:  # stop the others anyway
                logger.exception("stopping bot %s failed", client.name)


class MatchHandle:
    """A match running in a background thread.

    The GUI keeps the handle to stop the match or collect its result; the
    match itself reports progress through its observers.
    """

    def __init__(self, runner: MatchRunner, seed: int) -> None:
        """Start the match thread right away.

        Args:
            runner: The runner to use.
            seed: The map seed.
        """
        self.error: BaseException | None = None
        self._result: RecordedMatch | None = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(runner, seed), name="match", daemon=True
        )
        self._thread.start()

    @property
    def is_running(self) -> bool:
        """Whether the match thread is still working."""
        return self._thread.is_alive()

    def stop(self) -> None:
        """Ask the match to end after the current turn."""
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> RecordedMatch | None:
        """Wait for the match to end.

        Args:
            timeout: The longest wait in seconds; ``None`` waits forever.

        Returns:
            The recorded match, or ``None`` if it is still running or
            failed (see :attr:`error`).
        """
        self._thread.join(timeout)
        return None if self._thread.is_alive() else self._result

    def _run(self, runner: MatchRunner, seed: int) -> None:
        """The thread body: play, and report a failure instead of losing it."""
        try:
            self._result = runner.run(seed, self._stop_event)
        except Exception as error:  # reported to the observers instead
            self.error = error
            logger.exception("the match could not be played")
            runner.notify_failure(str(error))


def _turn_reporter(record: TurnRecord) -> Callable[[MatchObserver], None]:
    """A call that reports ``record`` to one observer."""

    def report(observer: MatchObserver) -> None:
        observer.on_turn(record)

    return report
