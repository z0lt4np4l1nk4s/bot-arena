"""Rows, sorting and filters of the history table, without any widgets."""

from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Final

from arena.gui.formatting import result_text
from arena.model.side import Side
from arena.model.state import ModeKind
from arena.storage.records import MatchSummary, SoloRecord

COLUMNS: Final = ("date", "mode", "blue", "red", "seed", "result", "turns")
DATE_FORMAT: Final = "%Y-%m-%d %H:%M"
NO_BOT: Final = "-"

SortKey = Callable[[MatchSummary], "str | int | float"]


def _red_bot(summary: MatchSummary) -> str:
    """Red's name, or a dash in solo."""
    return summary.bots.get(Side.RED, NO_BOT)


# Dates, seeds and turns sort by value, everything else as text.
_SORT_KEYS: Final[Mapping[str, SortKey]] = MappingProxyType(
    {
        "date": lambda summary: summary.played_at.timestamp(),
        "mode": lambda summary: summary.mode.value,
        "blue": lambda summary: summary.bots[Side.BLUE].casefold(),
        "red": lambda summary: _red_bot(summary).casefold(),
        "seed": lambda summary: summary.seed,
        "result": lambda summary: result_text(summary).casefold(),
        "turns": lambda summary: summary.turns,
    }
)


def history_row(summary: MatchSummary) -> tuple[str, ...]:
    """The cells of one match in the history table, in :data:`COLUMNS`.

    Args:
        summary: A saved match.

    Returns:
        Date, mode, Blue, Red (``-`` in solo), seed, result and turns.
    """
    return (
        summary.played_at.strftime(DATE_FORMAT),
        summary.mode.value.capitalize(),
        summary.bots[Side.BLUE],
        _red_bot(summary),
        str(summary.seed),
        result_text(summary),
        str(summary.turns),
    )


def solo_record_row(record: SoloRecord) -> tuple[str, ...]:
    """The cells of one solo record: seed, best turns, bot and date."""
    return (
        str(record.seed),
        str(record.turns_used),
        record.bot,
        record.played_at.strftime(DATE_FORMAT),
    )


def sort_summaries(
    summaries: Iterable[MatchSummary], column: str, descending: bool
) -> list[MatchSummary]:
    """The matches ordered by one column.

    Args:
        summaries: The matches.
        column: One of :data:`COLUMNS`.
        descending: Largest first.

    Returns:
        A new, sorted list.

    Raises:
        KeyError: If ``column`` is not one of the columns.
    """
    return sorted(summaries, key=_SORT_KEYS[column], reverse=descending)


def filter_summaries(
    summaries: Iterable[MatchSummary],
    mode: ModeKind | None,
    bot: str | None,
) -> list[MatchSummary]:
    """The matches of one mode and with one bot (on either side).

    ``None`` means "any" for both filters.
    """
    return [
        summary
        for summary in summaries
        if (mode is None or summary.mode is mode)
        and (bot is None or bot in summary.bots.values())
    ]


def bot_names(summaries: Iterable[MatchSummary]) -> list[str]:
    """Every bot that played, once, in alphabetical order.

    >>> from datetime import datetime
    >>> summary = MatchSummary(
    ...     None, datetime(2026, 1, 1), ModeKind.DUEL, 1,
    ...     {Side.BLUE: "Hard", Side.RED: "Easy"}, None,
    ...     {Side.BLUE: 0, Side.RED: 0}, 0, None,
    ... )
    >>> bot_names([summary, summary])
    ['Easy', 'Hard']
    """
    names = {name for summary in summaries for name in summary.bots.values()}
    return sorted(names, key=str.casefold)
