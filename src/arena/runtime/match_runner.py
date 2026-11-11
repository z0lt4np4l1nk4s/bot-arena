"""Play one match from start to end.

Every turn both bots are asked **at the same time**: their blocking
``ask`` calls run in a thread pool and are awaited together with
``asyncio.gather``. Everything the runner needs (the game mode, the bot
clients and the observers) is passed in, so tests can use fake bots and
the GUI can listen in, without the runner knowing about either.
"""

import asyncio
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Final

from arena.engine.modes import GameMode
from arena.model.actions import Action
from arena.model.side import Side
from arena.model.state import GameState
from arena.runtime.bot_process import STARTUP_TIMEOUT_SECONDS, BotReply
from arena.runtime.clients import BotClient
from arena.runtime.observers import MatchObserver
from arena.storage.records import MatchSummary, RecordedMatch, TurnRecord
from arena.utilities.logger import get_logger

logger: Final = get_logger("runtime")


class MatchRunner:
    """Plays a match with the given mode, bots and observers."""

    def __init__(
        self,
        mode: GameMode,
        clients: Mapping[Side, BotClient],
        observers: Sequence[MatchObserver] = (),
    ) -> None:
        """Create a runner; nothing starts until :meth:`run`.

        Args:
            mode: The game mode (duel or solo).
            clients: One bot client per side the mode needs.
            observers: Everyone to inform about the match.
        """
        self.mode = mode
        self.clients = dict(clients)
        self.observers = list(observers)

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
        """The asynchronous version of :meth:`run`."""
        executor = ThreadPoolExecutor(
            max_workers=len(self.clients), thread_name_prefix="bot-ask"
        )
        try:
            for client in self.clients.values():
                client.start()
            return await self._play(seed, stop_event, executor)
        finally:
            self._stop_clients()
            executor.shutdown(wait=False, cancel_futures=True)

    async def _play(
        self,
        seed: int,
        stop_event: threading.Event | None,
        executor: ThreadPoolExecutor,
    ) -> RecordedMatch:
        """The turn loop."""
        initial = self.mode.setup_map(seed)
        played_at = datetime.now()
        self._notify(
            "on_match_started",
            self._summary(seed, played_at, initial),
            initial,
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
            self._notify("on_turn", record)
        match = RecordedMatch(
            self._summary(seed, played_at, state), initial, tuple(records)
        )
        self._notify("on_match_finished", match, not self.mode.is_over(state))
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
        """Ask one bot, with a generous last-resort time limit."""
        client = self.clients[side]
        view = self.mode.state_for_bot(state, side)
        loop = asyncio.get_running_loop()
        # The client enforces the real limit; this only guards against a
        # client that never returns, and allows for a bot restart.
        limit = (
            self.mode.rules.turn_time_limit_ms / 1000 + STARTUP_TIMEOUT_SECONDS
        )
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(executor, client.ask, turn, view), limit
            )
        except asyncio.TimeoutError:
            logger.error("bot %s never answered turn %d", client.name, turn)
            return BotReply(turn, Action.wait(), limit * 1000, timed_out=True)
        except Exception as error:  # keep the match going
            logger.exception("asking bot %s failed", client.name)
            return BotReply(turn, Action.wait(), 0.0, error=str(error))

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

    def _notify(self, method: str, *arguments: object) -> None:
        """Call ``method`` on every observer; one failing does not stop it."""
        for observer in self.observers:
            try:
                getattr(observer, method)(*arguments)
            except Exception:  # observers must not end a match
                logger.exception(
                    "observer %s failed in %s", type(observer).__name__, method
                )

    def _stop_clients(self) -> None:
        """Stop every client, even if some of them fail to stop."""
        for client in self.clients.values():
            try:
                client.stop()
            except Exception:  # stop the others anyway
                logger.exception("stopping bot %s failed", client.name)
