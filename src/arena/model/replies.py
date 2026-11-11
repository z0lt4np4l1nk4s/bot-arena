"""A bot's answer for one turn, as stored and shown in the match log."""

from dataclasses import dataclass

from arena.model.actions import Action


@dataclass(frozen=True)
class BotReply:
    """A bot's answer for one turn, with how long it took.

    ``error`` holds what went wrong (the turn then counts as ``wait``) and
    ``timed_out`` is set when the bot did not answer in time.
    """

    turn: int
    action: Action
    elapsed_ms: float
    error: str | None = None
    timed_out: bool = False
