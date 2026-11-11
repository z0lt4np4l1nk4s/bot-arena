"""The match history in an SQLite database, one column per value.

Saving writes one row per turn and side (player state and the bot's reply)
plus rows for crystals, traps and events. Loading rebuilds every
:class:`GameState` from those rows. Each save is a single transaction, so
a failure never leaves half a match behind. Table and column names put
into SQL text are constants of this module, never user input; every
value is passed as a ``?`` parameter.
"""

import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import TypeAlias

from arena.model.actions import Action, ActionKind
from arena.model.geometry import Direction, Position
from arena.model.side import Side
from arena.model.state import (
    Event,
    EventKind,
    GameMap,
    GameState,
    ModeKind,
    PlayerState,
    Trap,
)
from arena.runtime.bot_process import BotReply
from arena.storage.records import (
    MatchSummary,
    RecordedMatch,
    SoloRecord,
    TurnRecord,
)
from arena.storage.repository import MatchRepository
from arena.storage.sqlite_schema import CREATE_STATEMENTS, SCHEMA_VERSION

Row: TypeAlias = tuple[object, ...]

_SUMMARY_COLUMNS = (
    "id, played_at, mode, seed, blue_bot, red_bot, winner, "
    "blue_delivered, red_delivered, turns, solo_turns_used"
)


class SqliteMatchRepository(MatchRepository):
    """Keeps matches and solo records in an SQLite file.

    The repository may be used from several threads (the match runs in a
    background thread); a lock makes every operation run on its own.
    """

    def __init__(self, path: Path | str) -> None:
        """Open (or create) the database and its tables.

        Args:
            path: The database file, or ``":memory:"``.
        """
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._transaction() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            for statement in CREATE_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                "INSERT OR IGNORE INTO metadata VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def __enter__(self) -> "SqliteMatchRepository":
        """Use the repository in a ``with`` block."""
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the database when the ``with`` block ends."""
        self.close()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._connection.close()

    def save_match(self, match: RecordedMatch) -> int:
        """Store a match and all its turns in one transaction."""
        with self._transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO matches (played_at, mode, seed, grid_size, "
                "max_turns, blue_bot, red_bot, winner, blue_delivered, "
                "red_delivered, turns, solo_turns_used) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _match_row(match),
            )
            match_id = cursor.lastrowid
            if match_id is None:
                message = "the database did not return the new match id"
                raise sqlite3.DatabaseError(message)
            _insert_match_rows(connection, match_id, match)
        return match_id

    def list_matches(
        self, mode: ModeKind | None = None, bot: str | None = None
    ) -> list[MatchSummary]:
        """Return the matching summaries, newest first."""
        mode_value = None if mode is None else mode.value
        with self._lock:
            rows = self._connection.execute(
                f"SELECT {_SUMMARY_COLUMNS} FROM matches "
                "WHERE (? IS NULL OR mode = ?) "
                "AND (? IS NULL OR blue_bot = ? OR red_bot = ?) "
                "ORDER BY played_at DESC, id DESC",
                (mode_value, mode_value, bot, bot, bot),
            ).fetchall()
        return [_summary(row) for row in rows]

    def load_match(self, match_id: int) -> RecordedMatch:
        """Rebuild a stored match from its rows.

        Raises:
            KeyError: If there is no match with this id.
        """
        with self._lock:
            return _load(self._connection, match_id)

    def delete_match(self, match_id: int) -> None:
        """Remove a match; its turns are removed with it (cascade)."""
        with self._transaction() as connection:
            connection.execute("DELETE FROM matches WHERE id = ?", (match_id,))

    def solo_record(self, seed: int) -> SoloRecord | None:
        """Return the best solo result for a seed."""
        with self._lock:
            row = self._connection.execute(
                "SELECT seed, turns_used, bot, played_at FROM solo_records "
                "WHERE seed = ?",
                (seed,),
            ).fetchone()
        return None if row is None else _solo(row)

    def save_solo_record(self, record: SoloRecord) -> bool:
        """Keep the result if it is the first or a better one."""
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT turns_used FROM solo_records WHERE seed = ?",
                (record.seed,),
            ).fetchone()
            if row is not None and row[0] <= record.turns_used:
                return False
            connection.execute(
                "INSERT OR REPLACE INTO solo_records VALUES (?, ?, ?, ?)",
                (
                    record.seed,
                    record.turns_used,
                    record.bot,
                    record.played_at.isoformat(),
                ),
            )
        return True

    def solo_records(self) -> list[SoloRecord]:
        """Return every solo record by seed."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT seed, turns_used, bot, played_at FROM solo_records "
                "ORDER BY seed"
            ).fetchall()
        return [_solo(row) for row in rows]

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Hold the lock and commit, or roll back on any error."""
        with self._lock, self._connection as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection


# ------------------------------------------------------------- writing ----


def _match_row(match: RecordedMatch) -> Row:
    """The values of the ``matches`` row."""
    summary = match.summary
    winner = None if summary.winner is None else summary.winner.value
    return (
        summary.played_at.isoformat(),
        summary.mode.value,
        summary.seed,
        match.initial_state.map.size,
        match.initial_state.max_turns,
        summary.bots[Side.BLUE],
        summary.bots.get(Side.RED),
        winner,
        summary.delivered[Side.BLUE],
        summary.delivered.get(Side.RED),
        summary.turns,
        summary.solo_turns_used,
    )


def _insert_match_rows(
    connection: sqlite3.Connection, match_id: int, match: RecordedMatch
) -> None:
    """Insert the walls and every turn's rows of a match."""
    connection.executemany(
        "INSERT INTO match_walls VALUES (?, ?, ?)",
        [(match_id, wall.x, wall.y) for wall in match.initial_state.map.walls],
    )
    turns: list[tuple[GameState, Mapping[Side, BotReply]]] = [
        (match.initial_state, {}),
        *((record.state, record.replies) for record in match.turns),
    ]
    statements = {
        "turn_players": 21,
        "turn_crystals": 5,
        "turn_traps": 8,
        "turn_events": 9,
    }
    rows: dict[str, list[Row]] = defaultdict(list)
    for state, replies in turns:
        rows["turn_players"].extend(_player_rows(match_id, state, replies))
        rows["turn_crystals"].extend(_crystal_rows(match_id, state))
        rows["turn_traps"].extend(_trap_rows(match_id, state))
        rows["turn_events"].extend(_event_rows(match_id, state))
    for table, width in statements.items():
        placeholders = ", ".join("?" * width)
        connection.executemany(
            f"INSERT INTO {table} VALUES ({placeholders})",
            rows[table],
        )


def _player_rows(
    match_id: int, state: GameState, replies: Mapping[Side, BotReply]
) -> Iterable[Row]:
    """One row per side: the player after the turn and its reply."""
    for side, player in state.players.items():
        yield (
            match_id,
            state.turn,
            side.value,
            player.position.x,
            player.position.y,
            player.carrying,
            player.delivered,
            player.shoot_cooldown,
            player.stunned_turns,
            player.trapped_turns,
            player.free_traps,
            player.trap_cooldown,
            player.last_delivery_turn,
            *_reply_columns(replies.get(side)),
        )


def _reply_columns(reply: BotReply | None) -> Row:
    """The eight reply columns; all empty for the start of the match."""
    if reply is None:
        return (None,) * 8
    action = reply.action
    target = action.target
    return (
        action.kind.value,
        None if action.direction is None else action.direction.name,
        None if target is None else target.x,
        None if target is None else target.y,
        action.message,
        _number(reply.elapsed_ms),
        reply.error,
        int(reply.timed_out),
    )


def _number(value: object) -> float:
    """Check that a value really is a number before it is stored."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        message = f"expected a number, got {value!r}"
        raise TypeError(message)
    return float(value)


def _crystal_rows(match_id: int, state: GameState) -> Iterable[Row]:
    """One row per cell with crystals."""
    for cell, count in state.crystals.items():
        yield (match_id, state.turn, cell.x, cell.y, count)


def _trap_rows(match_id: int, state: GameState) -> Iterable[Row]:
    """Live traps (spent = 0) and triggered ones (spent = 1), in order."""
    for spent, traps in ((0, state.traps), (1, state.spent_traps)):
        for sequence, trap in enumerate(traps):
            yield (
                match_id,
                state.turn,
                sequence,
                trap.owner.value,
                trap.position.x,
                trap.position.y,
                trap.turns_left,
                spent,
            )


def _event_rows(match_id: int, state: GameState) -> Iterable[Row]:
    """One row per event, in the order they happened."""
    for sequence, event in enumerate(state.events):
        yield (
            match_id,
            state.turn,
            sequence,
            event.kind.value,
            event.side.value,
            event.position.x,
            event.position.y,
            event.amount,
            event.reason,
        )


# ------------------------------------------------------------- reading ----


def _summary(row: tuple[object, ...]) -> MatchSummary:
    """Build a summary from a row of ``_SUMMARY_COLUMNS``."""
    (
        match_id,
        played_at,
        mode,
        seed,
        blue_bot,
        red_bot,
        winner,
        blue_delivered,
        red_delivered,
        turns,
        solo_turns_used,
    ) = row
    bots = {Side.BLUE: str(blue_bot)}
    delivered = {Side.BLUE: _integer(blue_delivered)}
    if red_bot is not None:
        bots[Side.RED] = str(red_bot)
        delivered[Side.RED] = _integer(red_delivered)
    return MatchSummary(
        match_id=_integer(match_id),
        played_at=datetime.fromisoformat(str(played_at)),
        mode=ModeKind(mode),
        seed=_integer(seed),
        bots=bots,
        winner=None if winner is None else Side(winner),
        delivered=delivered,
        turns=_integer(turns),
        solo_turns_used=(
            None if solo_turns_used is None else _integer(solo_turns_used)
        ),
    )


def _integer(value: object) -> int:
    """Read an integer column."""
    if not isinstance(value, int):
        message = f"expected an integer in the database, got {value!r}"
        raise TypeError(message)
    return value


def _solo(row: tuple[object, ...]) -> SoloRecord:
    """Build a solo record from its row."""
    seed, turns_used, bot, played_at = row
    return SoloRecord(
        _integer(seed),
        _integer(turns_used),
        str(bot),
        datetime.fromisoformat(str(played_at)),
    )


def _load(connection: sqlite3.Connection, match_id: int) -> RecordedMatch:
    """Read every row of a match and rebuild it."""
    row = connection.execute(
        f"SELECT {_SUMMARY_COLUMNS}, grid_size, max_turns "
        "FROM matches WHERE id = ?",
        (match_id,),
    ).fetchone()
    if row is None:
        raise KeyError(match_id)
    summary = _summary(row[:-2])
    grid_size, max_turns = _integer(row[-2]), _integer(row[-1])
    game_map = _load_map(connection, match_id, grid_size)
    by_turn = _rows_by_turn(connection, match_id)
    states: list[GameState] = []
    replies: list[dict[Side, BotReply]] = []
    for turn in range(summary.turns + 1):
        players, turn_replies = _players(by_turn["turn_players"][turn], turn)
        states.append(
            GameState(
                mode=summary.mode,
                turn=turn,
                max_turns=max_turns,
                map=game_map,
                crystals=_crystals(by_turn["turn_crystals"][turn]),
                players=players,
                traps=_traps(by_turn["turn_traps"][turn], spent=False),
                spent_traps=_traps(by_turn["turn_traps"][turn], spent=True),
                events=_events(by_turn["turn_events"][turn]),
            )
        )
        replies.append(turn_replies)
    records = tuple(
        TurnRecord(turn, states[turn], replies[turn])
        for turn in range(1, summary.turns + 1)
    )
    return RecordedMatch(summary, states[0], records)


def _load_map(
    connection: sqlite3.Connection, match_id: int, grid_size: int
) -> GameMap:
    """Rebuild the map; bases are always in opposite corners."""
    walls = connection.execute(
        "SELECT x, y FROM match_walls WHERE match_id = ?", (match_id,)
    ).fetchall()
    bases = {
        Side.BLUE: Position(0, 0),
        Side.RED: Position(grid_size - 1, grid_size - 1),
    }
    return GameMap(
        grid_size, frozenset(Position(x, y) for x, y in walls), bases
    )


def _rows_by_turn(
    connection: sqlite3.Connection, match_id: int
) -> dict[str, dict[int, list[tuple[object, ...]]]]:
    """Read the per-turn tables and group their rows by turn."""
    orders = {
        "turn_players": "turn, side",
        "turn_crystals": "turn, y, x",
        "turn_traps": "turn, spent, sequence",
        "turn_events": "turn, sequence",
    }
    grouped: dict[str, dict[int, list[tuple[object, ...]]]] = {}
    for table, order in orders.items():
        groups: dict[int, list[tuple[object, ...]]] = defaultdict(list)
        cursor = connection.execute(
            f"SELECT * FROM {table} WHERE match_id = ? ORDER BY {order}",
            (match_id,),
        )
        for row in cursor:
            groups[_integer(row[1])].append(row[2:])
        grouped[table] = groups
    return grouped


def _players(
    rows: list[tuple[object, ...]], turn: int
) -> tuple[dict[Side, PlayerState], dict[Side, BotReply]]:
    """Rebuild the players (Blue first) and their replies of one turn."""
    players: dict[Side, PlayerState] = {}
    replies: dict[Side, BotReply] = {}
    for row in sorted(rows, key=lambda row: str(row[0]) != Side.BLUE.value):
        side = Side(row[0])
        numbers = [_integer(value) for value in row[1:10]]
        players[side] = PlayerState(
            side,
            Position(numbers[0], numbers[1]),
            carrying=numbers[2],
            delivered=numbers[3],
            shoot_cooldown=numbers[4],
            stunned_turns=numbers[5],
            trapped_turns=numbers[6],
            free_traps=numbers[7],
            trap_cooldown=numbers[8],
            last_delivery_turn=None if row[10] is None else _integer(row[10]),
        )
        if row[11] is not None:
            replies[side] = _reply(row[11:], turn)
    return players, replies


def _reply(columns: tuple[object, ...], turn: int) -> BotReply:
    """Rebuild a bot's reply from its eight columns."""
    kind, direction, target_x, target_y, message, elapsed, error, late = (
        columns
    )
    target = (
        None
        if target_x is None
        else Position(_integer(target_x), _integer(target_y))
    )
    action = Action(
        ActionKind(kind),
        None if direction is None else Direction[str(direction)],
        str(message),
        target,
    )
    return BotReply(
        turn,
        action,
        float(str(elapsed)),
        error=None if error is None else str(error),
        timed_out=bool(late),
    )


def _crystals(rows: list[tuple[object, ...]]) -> dict[Position, int]:
    """Rebuild the crystals on the ground."""
    return {
        Position(_integer(x), _integer(y)): _integer(count)
        for x, y, count in rows
    }


def _traps(rows: list[tuple[object, ...]], *, spent: bool) -> tuple[Trap, ...]:
    """Rebuild the live or the triggered traps, in their order."""
    return tuple(
        Trap(Side(owner), Position(_integer(x), _integer(y)), _integer(left))
        for _, owner, x, y, left, is_spent in rows
        if bool(is_spent) is spent
    )


def _events(rows: list[tuple[object, ...]]) -> tuple[Event, ...]:
    """Rebuild the events, in the order they happened."""
    return tuple(
        Event(
            EventKind(kind),
            Side(side),
            Position(_integer(x), _integer(y)),
            amount=_integer(amount),
            reason=str(reason),
        )
        for _, kind, side, x, y, amount, reason in rows
    )
