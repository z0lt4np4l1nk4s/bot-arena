"""Run one bot in its own process, with a time limit for every answer.

A separate process keeps a broken or slow bot from freezing or crashing
the application, and lets a bot that hangs be killed and restarted. The
process is started with *spawn* on every operating system, so it gets only
picklable data (the bot's source, the logging settings) and creates the
bot itself.
"""

import contextlib
import multiprocessing
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.process import BaseProcess
from types import TracebackType
from typing import Final, Protocol

from arena.bots.loader import error_line_in_file
from arena.bots.source import BotSource
from arena.errors import BotLoadError
from arena.model.actions import Action
from arena.model.state import BotState
from arena.rules import Rules
from arena.utilities.decorators import Timed, log_exceptions, measure_time
from arena.utilities.logger import LogSettings, configure_logging, get_logger

STARTUP_TIMEOUT_SECONDS: Final = 10.0
JOIN_TIMEOUT_SECONDS: Final = 2.0

logger = get_logger("runtime")


class Pipe(Protocol):
    """The end of a ``multiprocessing`` pipe (its type differs by OS)."""

    def send(self, obj: object) -> None:
        """Send a picklable object."""

    def recv(self) -> object:
        """Receive the next object."""

    def poll(self, timeout: float | None = 0.0) -> bool:
        """Wait up to ``timeout`` seconds for something to receive."""

    def close(self) -> None:
        """Close this end."""


@dataclass(frozen=True)
class Handshake:
    """The child's first message: ready, or why the bot did not load."""

    error: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class BotReply:
    """A bot's answer for one turn, with how long it took."""

    turn: int
    action: Action
    elapsed_ms: float
    error: str | None = None
    timed_out: bool = False


class BotProcess:
    """One bot running in a child process.

    Use it as a context manager, or call :meth:`start` and :meth:`stop`.
    """

    def __init__(
        self,
        source: BotSource,
        rules: Rules,
        log_settings: LogSettings | None = None,
    ) -> None:
        """Prepare the process; nothing runs until :meth:`start`.

        Args:
            source: Which bot to run.
            rules: Gives the time limit and the kill timeout.
            log_settings: Logging for the child process.
        """
        self.source = source
        self.rules = rules
        self.log_settings = log_settings or LogSettings()
        self.restarts = 0
        self._process: BaseProcess | None = None
        self._connection: Pipe | None = None
        self._waiting_since: float | None = None

    def __enter__(self) -> "BotProcess":
        """Start the bot when entering a ``with`` block."""
        self.start()
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop the bot when leaving a ``with`` block."""
        self.stop()

    @property
    def is_alive(self) -> bool:
        """Whether the child process is running."""
        return self._process is not None and self._process.is_alive()

    def start(self) -> None:
        """Start the child process and wait until the bot is ready.

        Raises:
            BotLoadError: If the bot cannot be created, or does not start
                within ``STARTUP_TIMEOUT_SECONDS``.
        """
        context = multiprocessing.get_context("spawn")
        parent_end, child_end = context.Pipe()
        process = context.Process(
            target=_run_bot,
            args=(self.source, child_end, self.log_settings),
            name=f"bot-{self.source.name}",
            daemon=True,
        )
        process.start()
        child_end.close()
        self._process, self._connection = process, parent_end
        if not parent_end.poll(STARTUP_TIMEOUT_SECONDS):
            self.stop()
            message = f"bot {self.source.name!r} did not start in time"
            raise BotLoadError(message)
        handshake = parent_end.recv()
        if not isinstance(handshake, Handshake):
            self.stop()
            message = f"bot {self.source.name!r} sent no handshake"
            raise BotLoadError(message)
        if handshake.error is not None:
            self.stop()
            raise BotLoadError(handshake.error, handshake.line)
        logger.info("bot %s started", self.source.name)

    def ask(self, turn: int, state: BotState) -> BotReply:
        """Ask the bot for its action and wait at most the turn limit.

        Answers for earlier turns that arrive late are thrown away. A bot
        that has been silent for longer than the kill timeout is replaced
        by a fresh one first.

        Args:
            turn: The turn number; the answer must carry the same number.
            state: What the bot sees.

        Returns:
            The bot's reply, or a ``wait`` marked as timed out.
        """
        self._restart_if_hanging()
        connection = self._require_connection()
        sent_at = time.monotonic()
        connection.send((turn, state))
        if self._waiting_since is None:
            self._waiting_since = sent_at
        deadline = sent_at + self.rules.turn_time_limit_ms / 1000
        while (remaining := deadline - time.monotonic()) > 0:
            if not connection.poll(remaining):
                break
            reply = connection.recv()
            if isinstance(reply, BotReply) and reply.turn == turn:
                self._waiting_since = None
                self._log_reply(reply)
                return reply
            # A late answer for an older turn: the bot is alive again and
            # is now working on this turn.
            self._waiting_since = sent_at
        logger.warning("bot %s timed out in turn %d", self.source.name, turn)
        return BotReply(
            turn,
            Action.wait(),
            float(self.rules.turn_time_limit_ms),
            timed_out=True,
        )

    def stop(self) -> None:
        """Stop the child process; calling it again does nothing."""
        connection, process = self._connection, self._process
        self._connection = None
        self._process = None
        if connection is not None:
            # The child may already be gone; then there is no one to tell.
            with contextlib.suppress(OSError):
                connection.send(None)
            connection.close()
        if process is not None:
            process.join(timeout=0.2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=JOIN_TIMEOUT_SECONDS)
            logger.info("bot %s stopped", self.source.name)

    def _restart_if_hanging(self) -> None:
        """Replace a bot that has not answered for the kill timeout."""
        if self._waiting_since is None:
            return
        silent_ms = (time.monotonic() - self._waiting_since) * 1000
        if silent_ms <= self.rules.bot_kill_timeout_ms:
            return
        logger.info(
            "bot %s silent for %.0f ms, restarting",
            self.source.name,
            silent_ms,
        )
        self.stop()
        self._waiting_since = None
        self.start()
        self.restarts += 1

    def _require_connection(self) -> Pipe:
        """Return the pipe to the child, which must be running."""
        if self._connection is None:
            message = "the bot process is not running; call start() first"
            raise RuntimeError(message)
        return self._connection

    def _log_reply(self, reply: BotReply) -> None:
        """Log errors at ERROR level and every reply at DEBUG level."""
        if reply.error is not None:
            logger.error(
                "bot %s failed in turn %d: %s",
                self.source.name,
                reply.turn,
                reply.error,
            )
        logger.debug(
            "bot %s turn %d: %s in %.1f ms",
            self.source.name,
            reply.turn,
            reply.action.kind.value,
            reply.elapsed_ms,
        )


@log_exceptions("runtime")
def _run_bot(
    source: BotSource, connection: Pipe, log_settings: LogSettings
) -> None:
    """Child process: create the bot, then answer until told to stop.

    Requests are ``(turn, state)`` pairs; ``None`` means stop.
    """
    configure_logging(log_settings)
    try:
        bot = source.create()
    except BotLoadError as error:
        connection.send(Handshake(error.reason, error.line))
        return
    except Exception as error:  # user code may raise anything
        line = _line_in_bot(error, source)
        reason = f"{type(error).__name__}: {error}"
        connection.send(Handshake(reason, line))
        return
    connection.send(Handshake())
    decide = measure_time(bot.decide)
    while True:
        try:
            request = connection.recv()
        except EOFError:
            return
        if not isinstance(request, tuple):
            return
        turn, state = request
        connection.send(_answer(decide, turn, state, source))


def _answer(
    decide: Callable[[BotState], Timed[Action]],
    turn: int,
    state: BotState,
    source: BotSource,
) -> BotReply:
    """Call the bot once and turn any problem into a ``wait`` reply."""
    try:
        timed = decide(state)
    except Exception as error:  # user code may raise anything
        line = _line_in_bot(error, source)
        suffix = "" if line is None else f" (line {line})"
        message = f"{type(error).__name__}: {error}{suffix}"
        return BotReply(turn, Action.wait(), 0.0, error=message)
    # Typed as Action, but the bot is untrusted code and may return anything.
    value: object = timed.value
    if not isinstance(value, Action):
        message = f"decide() must return an Action, got {type(value).__name__}"
        return BotReply(turn, Action.wait(), timed.elapsed_ms, error=message)
    return BotReply(turn, value, timed.elapsed_ms)


def _line_in_bot(error: BaseException, source: BotSource) -> int | None:
    """The line in the bot's own file where ``error`` happened, if any."""
    if source.path is None:
        return None
    return error_line_in_file(error, source.path)
