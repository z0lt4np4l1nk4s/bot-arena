"""The tables of the match history database.

Every value has its own column, so the history can be explored with plain
SQL, for example the average thinking time of a bot.
"""

from typing import Final

SCHEMA_VERSION: Final = 1

CREATE_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY,
        played_at TEXT NOT NULL,
        mode TEXT NOT NULL,
        seed INTEGER NOT NULL,
        grid_size INTEGER NOT NULL,
        max_turns INTEGER NOT NULL,
        blue_bot TEXT NOT NULL,
        red_bot TEXT,
        winner TEXT,
        blue_delivered INTEGER NOT NULL,
        red_delivered INTEGER,
        turns INTEGER NOT NULL,
        solo_turns_used INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS match_walls (
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        PRIMARY KEY (match_id, x, y)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS turn_players (
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        turn INTEGER NOT NULL,
        side TEXT NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        carrying INTEGER NOT NULL,
        delivered INTEGER NOT NULL,
        shoot_cooldown INTEGER NOT NULL,
        stunned_turns INTEGER NOT NULL,
        trapped_turns INTEGER NOT NULL,
        free_traps INTEGER NOT NULL,
        trap_cooldown INTEGER NOT NULL,
        last_delivery_turn INTEGER,
        action_kind TEXT,
        action_direction TEXT,
        action_target_x INTEGER,
        action_target_y INTEGER,
        message TEXT,
        elapsed_ms REAL,
        error TEXT,
        timed_out INTEGER,
        PRIMARY KEY (match_id, turn, side)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS turn_crystals (
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        turn INTEGER NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY (match_id, turn, x, y)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS turn_traps (
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        turn INTEGER NOT NULL,
        sequence INTEGER NOT NULL,
        owner TEXT NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        turns_left INTEGER NOT NULL,
        spent INTEGER NOT NULL,
        PRIMARY KEY (match_id, turn, spent, sequence)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS turn_events (
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        turn INTEGER NOT NULL,
        sequence INTEGER NOT NULL,
        kind TEXT NOT NULL,
        side TEXT NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        reason TEXT NOT NULL,
        PRIMARY KEY (match_id, turn, sequence)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS solo_records (
        seed INTEGER PRIMARY KEY,
        turns_used INTEGER NOT NULL,
        bot TEXT NOT NULL,
        played_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS matches_by_time ON matches(played_at)",
)
