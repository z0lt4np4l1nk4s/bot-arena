"""What is kept about a match: a summary and every turn (the Memento).

A replay is built only from these records; the bots are never run again.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from arena.model.replies import BotReply
from arena.model.side import Side
from arena.model.state import GameState, ModeKind


@dataclass(frozen=True)
class TurnRecord:
    """One turn: the state after it and what each bot answered."""

    turn: int
    state: GameState
    replies: Mapping[Side, BotReply]


@dataclass(frozen=True)
class MatchSummary:
    """The facts shown in the history list."""

    match_id: int | None
    played_at: datetime
    mode: ModeKind
    seed: int
    bots: Mapping[Side, str]
    winner: Side | None
    delivered: Mapping[Side, int]
    turns: int
    solo_turns_used: int | None

    def with_id(self, match_id: int) -> "MatchSummary":
        """Return the same summary with the id the database gave it."""
        return replace(self, match_id=match_id)


@dataclass(frozen=True)
class RecordedMatch:
    """A whole match: its summary, the start, and every turn."""

    summary: MatchSummary
    initial_state: GameState
    turns: tuple[TurnRecord, ...]


@dataclass(frozen=True)
class SoloRecord:
    """The best solo result for one map seed."""

    seed: int
    turns_used: int
    bot: str
    played_at: datetime
