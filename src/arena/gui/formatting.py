"""Texts and lines the window shows for matches, without any widgets.

Keeping these pure makes the look of the viewer testable without a
display.
"""

from dataclasses import dataclass

from arena.bots.source import BotSource
from arena.model.actions import Action, ActionKind
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import EventKind, GameState, ModeKind, PlayerState
from arena.rules import Rules
from arena.storage.records import MatchSummary, TurnRecord


@dataclass(frozen=True)
class LogRow:
    """One line of the turn log: what one bot did in one turn."""

    turn: int
    side: Side
    action: str
    message: str
    thinking_ms: str
    problem: str


def describe_action(action: Action) -> str:
    """A short text for an action.

    >>> from arena.model.geometry import Direction
    >>> describe_action(Action.shoot(Direction.LEFT))
    'shoot left'
    >>> describe_action(Action.trap(Position(4, 5)))
    'trap at (4, 5)'
    """
    if action.kind is ActionKind.TRAP and action.target is not None:
        return f"trap at ({action.target.x}, {action.target.y})"
    if action.direction is not None:
        return f"{action.kind.value} {action.direction.name.lower()}"
    return action.kind.value


def log_rows(record: TurnRecord) -> list[LogRow]:
    """One log row per bot of a turn, Blue first.

    Args:
        record: The played turn.

    Returns:
        The rows in side order.
    """
    rows: list[LogRow] = []
    for side in Side:
        reply = record.replies.get(side)
        if reply is None:
            continue
        problem = "timed out" if reply.timed_out else reply.error or ""
        rows.append(
            LogRow(
                record.turn,
                side,
                describe_action(reply.action),
                reply.action.message,
                f"{reply.elapsed_ms:.1f}",
                problem,
            )
        )
    return rows


def player_status(player: PlayerState, rules: Rules) -> str:
    """What a bot carries and can do, in one line.

    Args:
        player: The bot.
        rules: For the carry capacity.

    Returns:
        For example ``"carrying 2/3 · shot ready · traps 3"``.
    """
    shot = (
        "shot ready"
        if player.shoot_cooldown == 0
        else f"shot in {player.shoot_cooldown}"
    )
    parts = [
        f"carrying {player.carrying}/{rules.carry_capacity}",
        shot,
        f"traps {player.free_traps}",
    ]
    if player.stunned_turns > 0:
        parts.append(f"stunned {player.stunned_turns}")
    if player.trapped_turns > 0:
        parts.append(f"trapped {player.trapped_turns}")
    return " · ".join(parts)


def score_text(state: GameState) -> str:
    """The score: delivered crystals per side, or solo progress.

    Args:
        state: The state to describe.

    Returns:
        ``"Blue 3 : 2 Red"`` in a duel, ``"Delivered 3 of 8"`` in solo.
    """
    if state.mode is ModeKind.SOLO:
        delivered = state.player(Side.BLUE).delivered
        return f"Delivered {delivered} of {delivered + state.crystals_left}"
    blue = state.player(Side.BLUE).delivered
    red = state.player(Side.RED).delivered
    return f"Blue {blue} : {red} Red"


def bot_label(source: BotSource) -> str:
    """The name of a bot in a drop-down list.

    >>> bot_label(BotSource.builtin("Easy"))
    'Easy (built-in)'
    """
    return f"{source.name} (built-in)" if source.is_builtin else source.name


def result_text(summary: MatchSummary) -> str:
    """How a saved match ended, for the history table.

    Args:
        summary: The finished match.

    Returns:
        For example ``"Blue wins 9:7"`` or ``"Finished in 104 turns"``.
    """
    if summary.mode is ModeKind.SOLO:
        if summary.solo_turns_used is not None:
            return f"Finished in {summary.solo_turns_used} turns"
        delivered = summary.delivered[Side.BLUE]
        return f"Not finished ({delivered} delivered)"
    score = f"{summary.delivered[Side.BLUE]}:{summary.delivered[Side.RED]}"
    if summary.winner is None:
        return f"Draw {score}"
    return f"{summary.winner.name.capitalize()} wins {score}"


def shot_lines(state: GameState) -> list[tuple[Side, list[Position]]]:
    """The cells every bullet of the last turn flew over.

    A shooter does not move while shooting, so each line runs from the
    cell next to the shooter's position to the shot's last cell.

    Args:
        state: The state after the turn.

    Returns:
        The shooter and its bullet's cells, nearest first.
    """
    lines: list[tuple[Side, list[Position]]] = []
    for event in state.events:
        if event.kind is EventKind.SHOT:
            start = state.player(event.side).position
            lines.append((event.side, cells_between(start, event.position)))
    return lines


def cells_between(start: Position, end: Position) -> list[Position]:
    """The cells of a straight line after ``start`` up to ``end``.

    >>> cells_between(Position(1, 0), Position(3, 0))
    [Position(x=2, y=0), Position(x=3, y=0)]
    >>> cells_between(Position(2, 2), Position(2, 2))
    []
    """
    step_x = (end.x > start.x) - (end.x < start.x)
    step_y = (end.y > start.y) - (end.y < start.y)
    count = max(abs(end.x - start.x), abs(end.y - start.y))
    return [
        Position(start.x + step_x * index, start.y + step_y * index)
        for index in range(1, count + 1)
    ]
