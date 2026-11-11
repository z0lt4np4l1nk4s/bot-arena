"""Run one bot in its own process, with a time limit for every answer.

A separate process keeps a broken or slow bot from freezing or crashing
the application, and lets a bot that hangs be killed and restarted. The
process is started with *spawn* on every operating system, so it gets only
picklable data (the bot's source, the logging settings) and creates the
bot itself.

At most one request is ever waiting in the pipe: while the bot is still
busy with an older turn, it is not sent another one. This way the pipe can
never fill up, and a slow bot never falls further and further behind.
"""

import contextlib
import multiprocessing
import pickle
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.process import BaseProcess
from types import TracebackType
from typing import Final, Protocol

from arena.bots.loader import describe_error, error_line_in_file
from arena.bots.source import BotSource
from arena.errors import BotLoadError, InvalidActionError
from arena.model.actions import MAX_MESSAGE_LENGTH, Action, ActionKind
from arena.model.geometry import Direction, Position
from arena.model.replies import BotReply
from arena.model.state import BotState
from arena.rules import Rules
from arena.utilities.decorators import Timed, log_exceptions, measure_time
from arena.utilities.logger import LogSettings, configure_logging, get_logger

STARTUP_TIMEOUT_SECONDS: Final = 10.0
JOIN_TIMEOUT_SECONDS: Final = 2.0
PROCESS_ENDED: Final = "bot process ended"

logger: Final = get_logger("runtime")

# Errors that mean the pipe or the child process is gone or broken.
_CHANNEL_ERRORS: Final = (EOFError, OSError, pickle.PickleError)


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
            log_settings: Logging for the child process; ``None`` leaves
                the child's logging switched off.
        """
        self.source = source
        self.rules = rules
        self.log_settings = log_settings
        self.restarts = 0
        self._started = False
        self._process: BaseProcess | None = None
        self._connection: Pipe | None = None
        # When the request the bot is still working on was sent.
        self._busy_since: float | None = None

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
    def name(self) -> str:
        """The bot's display name."""
        return self.source.name

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
        self._busy_since = None
        self._started = True
        handshake = self._receive_handshake(parent_end)
        if handshake.error is not None:
            self._discard_process()
            raise BotLoadError(handshake.error, handshake.line)
        logger.info("bot %s started", self.source.name)

    def ask(self, turn: int, state: BotState) -> BotReply:
        """Ask the bot for its action and wait at most the turn limit.

        A bot that is still busy with an older turn is not sent a new
        request; if it does not finish in time, this turn times out. A bot
        silent for longer than the kill timeout, or whose process ended,
        is replaced by a fresh one.

        Args:
            turn: The turn number; the answer must carry the same number.
            state: What the bot sees.

        Returns:
            The bot's reply, or a ``wait`` marked as timed out or carrying
            an error.

        Raises:
            RuntimeError: If :meth:`start` was never called.
        """
        if not self._started:
            message = "the bot process was never started; call start()"
            raise RuntimeError(message)
        limit_seconds = self.rules.turn_time_limit_ms / 1000
        try:
            connection = self._ready_connection()
            # Counted only now, so restarting a bot does not eat its time.
            deadline = time.monotonic() + limit_seconds
            if self._busy_since is not None and not self._wait_until_idle(
                connection, deadline
            ):
                return self._timed_out(turn)
            connection.send((turn, state))
            self._busy_since = time.monotonic()
            reply = self._wait_for(connection, turn, deadline)
        except _CHANNEL_ERRORS:
            logger.error("bot %s: %s", self.source.name, PROCESS_ENDED)
            self._discard_process()
            return BotReply(turn, Action.wait(), 0.0, error=PROCESS_ENDED)
        except BotLoadError as error:
            logger.error(
                "bot %s could not restart: %s", self.source.name, error
            )
            message = f"bot could not be restarted: {error}"
            return BotReply(turn, Action.wait(), 0.0, error=message)
        return reply if reply is not None else self._timed_out(turn)

    def stop(self) -> None:
        """Stop the child process; calling it again does nothing."""
        connection = self._connection
        if connection is not None and self._busy_since is None:
            # The child may already be gone; then there is no one to tell.
            with contextlib.suppress(*_CHANNEL_ERRORS):
                connection.send(None)
        if self._process is not None:
            self._process.join(timeout=0.2)
            logger.info("bot %s stopped", self.source.name)
        self._discard_process()

    def _ready_connection(self) -> Pipe:
        """Return a working pipe, restarting the bot if it is needed."""
        if self._connection is None:
            self._restart()
        connection = self._require_connection()
        self._collect_late_replies(connection)
        if self._busy_since is not None:
            silent_ms = (time.monotonic() - self._busy_since) * 1000
            if silent_ms > self.rules.bot_kill_timeout_ms:
                logger.info(
                    "bot %s silent for %.0f ms, restarting",
                    self.source.name,
                    silent_ms,
                )
                self._restart()
                connection = self._require_connection()
        return connection

    def _collect_late_replies(self, connection: Pipe) -> None:
        """Read answers that arrived after their turn timed out."""
        while connection.poll(0):
            if isinstance(connection.recv(), BotReply):
                self._busy_since = None

    def _wait_until_idle(self, connection: Pipe, deadline: float) -> bool:
        """Wait for the answer to an older turn; ``False`` if none came."""
        while (remaining := deadline - time.monotonic()) > 0:
            if not connection.poll(remaining):
                return False
            if isinstance(connection.recv(), BotReply):
                self._busy_since = None
                return True
        return False

    def _wait_for(
        self, connection: Pipe, turn: int, deadline: float
    ) -> BotReply | None:
        """Wait for the answer to ``turn``; ``None`` if it is late."""
        while (remaining := deadline - time.monotonic()) > 0:
            if not connection.poll(remaining):
                return None
            reply = connection.recv()
            if isinstance(reply, BotReply):
                self._busy_since = None
                if reply.turn == turn:
                    self._log_reply(reply)
                    return reply
        return None

    def _timed_out(self, turn: int) -> BotReply:
        """A ``wait`` reply for a bot that did not answer in time."""
        logger.warning("bot %s timed out in turn %d", self.source.name, turn)
        return BotReply(
            turn,
            Action.wait(),
            float(self.rules.turn_time_limit_ms),
            timed_out=True,
        )

    def _restart(self) -> None:
        """Replace the child process with a fresh one."""
        self._discard_process()
        self.start()
        self.restarts += 1

    def _discard_process(self) -> None:
        """Close the pipe and make sure the child process is gone."""
        connection, process = self._connection, self._process
        self._connection = None
        self._process = None
        self._busy_since = None
        if connection is not None:
            connection.close()
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=JOIN_TIMEOUT_SECONDS)

    def _receive_handshake(self, connection: Pipe) -> Handshake:
        """Wait for the child's first message.

        Raises:
            BotLoadError: If the child does not answer in time, dies, or
                sends something unexpected.
        """
        try:
            ready = connection.poll(STARTUP_TIMEOUT_SECONDS)
            handshake = connection.recv() if ready else None
        except _CHANNEL_ERRORS:
            handshake = None
        if isinstance(handshake, Handshake):
            return handshake
        self._discard_process()
        message = f"bot {self.source.name!r} did not start"
        raise BotLoadError(message)

    def _require_connection(self) -> Pipe:
        """Return the pipe to the child, which must be running."""
        if self._connection is None:
            message = "the bot process is not running"
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
    source: BotSource, connection: Pipe, log_settings: LogSettings | None
) -> None:
    """Child process: create the bot, then answer until told to stop.

    Requests are ``(turn, state)`` pairs; anything else means stop.
    """
    if log_settings is not None:
        configure_logging(log_settings)
    try:
        bot = source.create()
    except BotLoadError as error:
        connection.send(Handshake(error.reason, error.line))
        return
    # User code may raise anything, including SystemExit from sys.exit().
    except (Exception, SystemExit) as error:
        connection.send(Handshake(describe_error(error), _line(error, source)))
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
    # User code may raise anything, including SystemExit from sys.exit().
    except (Exception, SystemExit) as error:
        line = _line(error, source)
        suffix = "" if line is None else f" (line {line})"
        message = f"{describe_error(error)}{suffix}"
        return BotReply(turn, Action.wait(), 0.0, error=message)
    try:
        action = rebuild_action(timed.value)
    except InvalidActionError as error:
        return BotReply(
            turn, Action.wait(), timed.elapsed_ms, error=str(error)
        )
    return BotReply(turn, action, timed.elapsed_ms)


def rebuild_action(value: object) -> Action:
    """Build a fresh, validated :class:`Action` from what a bot returned.

    A bot may return a subclass, or change an action after creating it.
    Copying the fields into a new plain ``Action`` runs all checks again,
    shortens the message and makes sure the result can be pickled.

    Args:
        value: Whatever ``decide`` returned.

    Returns:
        A plain, valid action.

    Raises:
        InvalidActionError: If ``value`` is not a usable action.

    >>> rebuild_action(Action.wait("hi"))
    Action(kind=<ActionKind.WAIT: 'wait'>, direction=None, message='hi', \
target=None)
    """
    if not isinstance(value, Action):
        message = f"decide() must return an Action, got {type(value).__name__}"
        raise InvalidActionError(message)
    # Read as plain objects: the declared types cannot be trusted here.
    kind: object = value.kind
    direction: object = value.direction
    message_text: object = value.message
    target: object = value.target
    if type(kind) is not ActionKind:
        message = "invalid action: unknown kind"
        raise InvalidActionError(message)
    if direction is not None and type(direction) is not Direction:
        message = "invalid action: direction must be a Direction"
        raise InvalidActionError(message)
    if not isinstance(message_text, str):
        message = "invalid action: message must be a string"
        raise InvalidActionError(message)
    return Action(
        kind,
        direction,
        str(message_text)[:MAX_MESSAGE_LENGTH],
        _plain_position(target),
    )


def _plain_position(target: object) -> Position | None:
    """Copy a trap target into a plain :class:`Position`."""
    if target is None:
        return None
    x = getattr(target, "x", None)
    y = getattr(target, "y", None)
    if (
        not isinstance(target, Position)
        or type(x) is not int
        or type(y) is not int
    ):
        message = "invalid action: target must be a Position"
        raise InvalidActionError(message)
    return Position(x, y)


def _line(error: BaseException, source: BotSource) -> int | None:
    """The line in the bot's own file where ``error`` happened, if any."""
    if source.path is None:
        return None
    return error_line_in_file(error, source.path)
