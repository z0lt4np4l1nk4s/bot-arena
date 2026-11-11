"""How the match runner talks to a bot: the ``BotClient`` protocol.

:class:`~arena.runtime.bot_process.BotProcess` runs a bot in its own
process; :class:`InProcessBotClient` calls a bot directly, without
processes or time limits, which is useful for tests and fast series.
"""

from typing import Protocol

from arena.bots.loader import describe_error
from arena.bots.protocol import Bot
from arena.errors import InvalidActionError
from arena.model.actions import Action
from arena.model.state import BotState
from arena.runtime.bot_process import BotReply, rebuild_action
from arena.utilities.decorators import measure_time


class BotClient(Protocol):
    """Anything the match runner can ask for a bot's action."""

    @property
    def name(self) -> str:
        """The bot's display name."""
        ...

    def start(self) -> None:
        """Get the bot ready to play."""

    def ask(self, turn: int, state: BotState) -> BotReply:
        """Return the bot's answer for one turn."""
        ...

    def stop(self) -> None:
        """Release everything the bot uses."""


class InProcessBotClient:
    """Calls a bot directly in this process; never times out."""

    def __init__(self, bot: Bot) -> None:
        """Wrap a bot instance.

        Args:
            bot: The bot to ask.
        """
        self.bot = bot
        self._decide = measure_time(bot.decide)

    @property
    def name(self) -> str:
        """The bot's display name."""
        return self.bot.name

    def start(self) -> None:
        """Nothing to start: the bot already exists."""

    def ask(self, turn: int, state: BotState) -> BotReply:
        """Call ``decide`` and turn any problem into a ``wait`` reply."""
        try:
            timed = self._decide(state)
        except Exception as error:  # bots may raise anything
            return BotReply(turn, Action.wait(), 0.0, describe_error(error))
        try:
            action = rebuild_action(timed.value)
        except InvalidActionError as error:
            return BotReply(turn, Action.wait(), timed.elapsed_ms, str(error))
        return BotReply(turn, action, timed.elapsed_ms)

    def stop(self) -> None:
        """Nothing to stop."""
