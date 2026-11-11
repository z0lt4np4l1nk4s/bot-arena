# Match Runner and Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Play whole matches with real bot processes, in the background, report every turn to listeners, and keep every match in an SQLite history that can be replayed without running the bots again.

**Architecture:** A `MatchRunner` drives one match: each turn it asks both bots at the same time with `asyncio` (blocking `BotProcess.ask` calls run in a thread pool through `run_in_executor`), steps the `GameMode`, and notifies `MatchObserver`s. `run_in_background` runs that loop in a separate thread with its own event loop; a `QueueObserver` hands events to the GUI thread through `queue.Queue`. Storage sits behind the `MatchRepository` ABC (SQLite and in-memory), and a `StorageObserver` saves a finished match. **Dependency injection is explicit:** the runner receives its mode, bot clients and observers; the storage observer receives a repository; only the composition root (`arena.application` and `src/main.py`) knows the concrete classes.

**Tech Stack:** Python 3.10 standard library (`asyncio`, `concurrent.futures`, `threading`, `queue`, `sqlite3`, `argparse`, `datetime`); `unittest` + `doctest`.

**Spec:** `docs/specs/01-bot-arena-design.md` (sections 4.6, 5.4, 7.2, 7.3, 7.5, 7.9).

## Global Constraints

- Python 3.10, standard library only, everything in English, full names. Rules in `CLAUDE.md` and `.claude/rules/` apply to every task.
- Only `arena.utilities.logger` imports `logging`.
- The runner and storage never import anything from a GUI; the engine never imports the runner or storage.
- Tests never touch `arena.db` in the project folder: they use `InMemoryMatchRepository` or SQLite on `":memory:"` / a temporary file.
- Tests that start bot processes stop them in `addCleanup`, and use `Rules(turn_time_limit_ms=200, bot_kill_timeout_ms=600)` unless the test is about real limits.
- Commit points: run the `verify` skill, then commit with a lowercase plain-language message. The `reviewer` agent runs once at the end of the plan.
- Run one test file: `../venv/Scripts/python -m unittest discover -s tests -p "test_<name>.py" -v` (from `Projekt/`).

## Decisions this plan makes (spec is silent)

1. **What is stored per turn (the Memento):** the full `GameState` after the turn plus, for each side, the `BotReply` (action with message, thinking time, error, timed out). A replay rebuilds the view from these records only.
2. **Relational tables, no JSON or pickle (user's choice):** every value has its own column, so history can be queried with plain SQL (e.g. average thinking time per bot). Tables: `matches` (one row per match), `match_walls`, `match_start_crystals`, `turn_players` (per turn and side: the player state and the bot's reply), `turn_crystals`, `turn_traps` (live and spent), `turn_events`, `solo_records`. A `schema_version` row in a `metadata` table allows later migrations.
3. **When a match is saved:** once, when it finishes normally. A match stopped by the user is not saved (the spec's Stop button means "abandon"). Series matches are not saved (spec 5.5; series come in plan 5).
4. **Solo records:** when a finished solo match beats the stored record for its seed (fewer turns), the record is replaced. A solo run that did not finish never becomes a record.
5. **`BotClient` protocol:** the runner talks to bots through `start()`, `ask(turn, state) -> BotReply` and `stop()`. `BotProcess` already fits; `InProcessBotClient` wraps a plain `Bot` without processes or time limits (for tests now and fast series later).
6. **Command line before the GUI:** `src/main.py play BLUE [RED] [--seed N] [--solo] [--log-level LEVEL] [--database PATH]` plays one match with real bot processes, saves it, and prints the result. Plan 4 makes the GUI the default command.

## Review Focus

1. A bot that crashes, hangs or fails to load must not leave bot processes running after the match (or after `start` fails for the second bot). → Task 3, `test_processes_are_stopped_even_if_a_bot_fails_to_start`.
2. Stopping a background match must end it within about one turn and never save it. → Task 4, `test_stop_ends_the_match_quickly_and_is_not_saved`.
3. Both bots are asked at the same time: a turn where both take 150 ms must take well under 300 ms. → Task 3, `test_bots_are_asked_in_parallel`.
4. A database file that is opened twice, or by a newer schema, must not corrupt history: tables are created only if missing, and every write is one transaction. → Task 2, `test_reopening_keeps_matches`, `test_failed_save_leaves_no_partial_match`.
5. An observer that raises must not kill the match or other observers; the error is logged. → Task 3, `test_failing_observer_does_not_stop_the_match`.

---

### Task 1: Match and turn records

**Files:**
- Create: `src/arena/storage/__init__.py`, `src/arena/storage/records.py`
- Test: `tests/test_records.py`

**Interfaces:**
- Consumes: `GameState`, `PlayerState`, `GameMap`, `Trap`, `Event`, `Action`, `BotReply`, `Position`, `Side`, `ModeKind`.
- Produces (in `records.py`, all frozen dataclasses):
  - `TurnRecord`: `turn: int`, `state: GameState` (after the turn), `replies: Mapping[Side, BotReply]`.
  - `MatchSummary`: `match_id: int | None`, `played_at: datetime`, `mode: ModeKind`, `seed: int`, `bots: Mapping[Side, str]` (display names), `winner: Side | None`, `delivered: Mapping[Side, int]`, `turns: int`, `solo_turns_used: int | None`; method `with_id(match_id: int) -> MatchSummary`.
  - `RecordedMatch`: `summary: MatchSummary`, `initial_state: GameState`, `turns: tuple[TurnRecord, ...]`.
  - `SoloRecord`: `seed: int`, `turns_used: int`, `bot: str`, `played_at: datetime`.
- Also `tests/recorded.py` (helper): `record_match(seed: int, turns: int) -> RecordedMatch` plays a short in-process Hard vs Medium duel and records it turn by turn, so the repository tests have real data with traps, shots, events, errors and timeouts (inject one error reply and one timed-out reply into the records).

- [ ] **Step 1: Write the failing tests**: `test_summary_with_id_keeps_other_fields`, `test_records_are_immutable`, `test_recorded_helper_contains_traps_shots_and_events` (guards the helper itself).
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** the records and the helper.
- [ ] **Step 4: Run**; expected: pass.

---

### Task 2: Match repository (ABC, in-memory and SQLite)

**Files:**
- Create: `src/arena/storage/repository.py`, `src/arena/storage/sqlite_repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces:
  - `class MatchRepository(ABC)` (Repository pattern) with abstract methods: `save_match(self, match: RecordedMatch) -> int` (returns the new id), `list_matches(self, mode: ModeKind | None = None, bot: str | None = None) -> list[MatchSummary]` (newest first), `load_match(self, match_id: int) -> RecordedMatch` (raises `KeyError` if missing), `delete_match(self, match_id: int) -> None`, `solo_record(self, seed: int) -> SoloRecord | None`, `save_solo_record(self, record: SoloRecord) -> bool` (stores it only if it beats the current one; returns whether it did), `solo_records(self) -> list[SoloRecord]` (by seed).
  - `InMemoryMatchRepository(MatchRepository)`: dictionaries; ids start at 1.
  - `SqliteMatchRepository(MatchRepository)` in `sqlite_repository.py`, with the table definitions in `sqlite_schema.py` (`SCHEMA_VERSION: Final = 1`, `CREATE_STATEMENTS: Final[tuple[str, ...]]`): `__init__(self, path: Path | str)`, `close()`, context manager; `PRAGMA foreign_keys = ON`; child tables reference `matches(id) ON DELETE CASCADE` and have primary keys on `(match_id, turn, ...)`.
    - `matches(id INTEGER PRIMARY KEY, played_at TEXT, mode TEXT, seed INTEGER, grid_size INTEGER, max_turns INTEGER, blue_bot TEXT, red_bot TEXT, winner TEXT, blue_delivered INTEGER, red_delivered INTEGER, turns INTEGER, solo_turns_used INTEGER)`
    - `match_walls(match_id, x, y)`, `match_start_crystals(match_id, x, y, count)`
    - `turn_players(match_id, turn, side, x, y, carrying, delivered, shoot_cooldown, stunned_turns, trapped_turns, free_traps, trap_cooldown, last_delivery_turn, action_kind, action_direction, action_target_x, action_target_y, message, elapsed_ms, error, timed_out)`; turn 0 holds the start state with no action
    - `turn_crystals(match_id, turn, x, y, count)`, `turn_traps(match_id, turn, owner, x, y, turns_left, spent)`, `turn_events(match_id, turn, sequence, kind, side, x, y, amount, reason)`
    - `solo_records(seed INTEGER PRIMARY KEY, turns_used INTEGER, bot TEXT, played_at TEXT)`, `metadata(key TEXT PRIMARY KEY, value TEXT)` with `schema_version`
    - Tables are created with `CREATE TABLE IF NOT EXISTS`; inserts use `executemany`; each save is one transaction (`with connection:`). Listing reads only `matches`. Loading rebuilds `GameState`s turn by turn from the rows (bases from `grid_size`, as in the map generator).

- [ ] **Step 1: Write the failing tests** as a contract mixin `RepositoryContract` run by two `TestCase` classes (in-memory, and SQLite on a temporary file), using `tests/recorded.py`: `test_saved_match_can_be_loaded` (the loaded match equals the saved one: every turn's state and replies, field by field), `test_ids_increase`, `test_list_is_newest_first`, `test_list_filters_by_mode_and_bot`, `test_delete_removes_match`, `test_load_missing_raises_key_error`, `test_first_solo_result_becomes_record`, `test_better_solo_result_replaces_record`, `test_worse_solo_result_is_ignored`, `test_solo_records_sorted_by_seed`. SQLite only: `test_reopening_keeps_matches`, `test_failed_save_leaves_no_partial_match` (a match with an invalid turn row, e.g. a reply whose action kind is not storable, makes `save_match` raise and leaves every table empty), `test_deleting_a_match_deletes_its_turns` (child tables empty afterwards), `test_values_are_queryable_with_sql` (e.g. `SELECT AVG(elapsed_ms) FROM turn_players WHERE side = 'blue'` returns a number).
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** both repositories.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point A**: `store finished matches and solo records`

---

### Task 3: Match runner with observers

**Files:**
- Create: `src/arena/runtime/clients.py`, `src/arena/runtime/observers.py`, `src/arena/runtime/match_runner.py`
- Test: `tests/test_match_runner.py`

**Interfaces:**
- Consumes: `GameMode`, `BotProcess`, `BotReply`, `Bot`, `TurnRecord`, `MatchSummary`, `RecordedMatch`, `measure_time`, `get_logger`.
- Produces:
  - `class BotClient(Protocol)`: `name: str`; `start(self) -> None`; `ask(self, turn: int, state: BotState) -> BotReply`; `stop(self) -> None`. (`BotProcess` gains a `name` property returning `source.name`.)
  - `class InProcessBotClient`: `__init__(self, bot: Bot)`; calls `decide` directly (timed with `measure_time`), turns exceptions into `wait()` with an error, never times out.
  - `class MatchObserver(Protocol)`: `on_match_started(self, summary: MatchSummary, initial_state: GameState) -> None`, `on_turn(self, record: TurnRecord) -> None`, `on_match_finished(self, match: RecordedMatch, stopped: bool) -> None`.
  - `class MatchRunner`: `__init__(self, mode: GameMode, clients: Mapping[Side, BotClient], observers: Sequence[MatchObserver] = ())` — **everything it uses is injected**; `run(self, seed: int, stop_event: threading.Event | None = None) -> RecordedMatch` (sync wrapper around `asyncio.run(self.run_async(...))`); `async run_async(self, seed: int, stop_event: threading.Event | None = None) -> RecordedMatch`. Each turn: build both views with `mode.state_for_bot`, ask all clients concurrently with `loop.run_in_executor(executor, client.ask, turn, view)` gathered by `asyncio.gather`, each wrapped in `asyncio.wait_for(..., timeout=limit + 1 s)` as a last line of defence (on that timeout the reply is `wait()` with `timed_out=True`); then `mode.step`; then notify observers. Clients are started before the first turn and **always** stopped in a `finally`, including when one fails to start. Observer exceptions are caught and logged per observer (`arena.runtime`), never propagated.
  - The executor is a `concurrent.futures.ThreadPoolExecutor(max_workers=len(clients))` owned by the run.
  - `MatchSummary.played_at` uses the current local time; bot names come from `client.name`.

- [ ] **Step 1: Write the failing tests** (in-process clients unless the test needs processes):
  - `test_runs_a_full_duel` (Hard vs Medium in process, seed 4: result has `turns == final state turn`, `winner == Duel().winner(final)`)
  - `test_runs_a_full_solo`
  - `test_observers_see_every_turn_in_order` (a recording observer collects turn numbers 1..N, then one finished call with `stopped=False`)
  - `test_failing_observer_does_not_stop_the_match` (first observer raises in `on_turn`; second still sees every turn; `self.assertLogs("arena.runtime", "ERROR")`)
  - `test_bot_error_is_recorded_in_the_turn` (a client whose `ask` returns an error reply; the record keeps it)
  - `test_stop_event_ends_the_match_early` (event set from an observer after turn 3: match has 3 turns, finished with `stopped=True`)
  - `test_bots_are_asked_in_parallel` (two fake clients sleeping 150 ms each: a 5-turn match takes under 1.25 s, i.e. clearly less than 10 × 150 ms)
  - `test_processes_are_stopped_even_if_a_bot_fails_to_start` (real `BotProcess` for Blue, a broken user file for Red: `run` raises `BotLoadError` and Blue's process is no longer alive)
  - `test_real_processes_play_a_match` (Medium vs Easy as `BotProcess`es with `Rules(turn_time_limit_ms=200)` and `Duel` limited to 30 turns via `Rules(duel_max_turns=30, ...)`: 30 turn records)
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** clients, observer protocol and runner.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point B**: `play matches with both bots answering at the same time`

---

### Task 4: Background matches for the GUI

**Files:**
- Modify: `src/arena/runtime/match_runner.py`, `src/arena/runtime/observers.py`
- Test: `tests/test_background_match.py`

**Interfaces:**
- Produces:
  - `class MatchHandle`: returned by `MatchRunner.run_in_background(seed: int) -> MatchHandle`; runs `run` in a `threading.Thread(daemon=True)`; methods `stop(self) -> None` (sets the stop event), `join(self, timeout: float | None = None) -> RecordedMatch | None` (the result, or `None` if still running), properties `is_running: bool`, `error: BaseException | None` (an exception from the match thread is kept here and logged, not lost).
  - `@dataclass(frozen=True)` event types for the GUI queue: `MatchStarted(summary, initial_state)`, `TurnPlayed(record)`, `MatchFinished(match, stopped)`, `MatchFailed(message)`.
  - `class QueueObserver(MatchObserver)`: `__init__(self, events: queue.Queue[MatchEvent])` where `MatchEvent: TypeAlias = MatchStarted | TurnPlayed | MatchFinished | MatchFailed`; puts one event per callback (never blocks: unbounded queue). `MatchHandle` puts `MatchFailed` into every `QueueObserver` when the thread fails.

- [ ] **Step 1: Write the failing tests**: `test_background_match_finishes_and_returns_result`, `test_queue_receives_events_in_order` (first `MatchStarted`, then `TurnPlayed` for 1..N, then `MatchFinished`), `test_stop_ends_the_match_quickly_and_is_not_saved` (a slow fake client of 50 ms per turn; `stop()` after 0.3 s; `join(2)` returns within 0.5 s and the recording observer's finished call has `stopped=True`; that stopped matches are not saved is tested in Task 5), `test_thread_error_is_reported` (a client whose `start` raises: `join` returns `None`, `handle.error` is set, the queue gets `MatchFailed`).
- [ ] **Step 2: Run**; expected: failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run**; expected: pass.
- [ ] **Step 5: Commit point C**: `run matches in the background and report each turn`

---

### Task 5: Saving matches, composition root and command line

**Files:**
- Create: `src/arena/storage/storage_observer.py`, `src/arena/application.py`, `src/main.py`
- Modify: `docs/specs/01-bot-arena-design.md` (7.1: `main.py` command line; 7.3: `BotClient`, `MatchObserver` now exist; mention the composition root)
- Test: `tests/test_storage_observer.py`, `tests/test_application.py`

**Interfaces:**
- Produces:
  - `class StorageObserver(MatchObserver)`: `__init__(self, repository: MatchRepository)` (injected); on a finished, not stopped match: `save_match`, and for solo with `solo_turns_used` set, `save_solo_record`. Keeps `last_saved_id: int | None`.
  - `@dataclass(frozen=True) class ApplicationSettings`: `database: Path = Path("arena.db")`, `rules: Rules = DEFAULT_RULES`, `log_settings: LogSettings = LogSettings()`, `user_bots_folder: Path = Path("user_bots")`.
  - `class Application` — **the composition root**: `__init__(self, settings: ApplicationSettings, repository: MatchRepository | None = None)` (a repository can be injected for tests; otherwise `SqliteMatchRepository(settings.database)`); `configure()` calls `configure_logging`; `create_match(self, mode: ModeKind, blue: BotSource, red: BotSource | None, observers: Sequence[MatchObserver] = ()) -> MatchRunner` builds `GameMode.create`, one `BotProcess` per side (with the settings' rules and log settings) and adds a `StorageObserver` to the given observers; `bot_sources(self) -> list[BotSource]` (the built-ins plus every `*.py` in `user_bots_folder`, sorted by name); `close()`.
  - `src/main.py`: `main(arguments: Sequence[str] | None = None) -> int`; subcommand `play` as described in decision 6; prints a short result (`"Blue (Hard) wins 9:7 in 170 turns"`, `"Draw 8:8"`, `"Solo (Medium): finished in 104 turns"` / `"did not finish (5 of 8)"`); returns exit code 0, or 2 with a message on stderr for a bot that cannot be loaded. `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 1: Write the failing tests**:
  - Storage observer: `test_finished_match_is_saved`, `test_stopped_match_is_not_saved`, `test_finished_solo_updates_record`, `test_unfinished_solo_is_not_a_record`.
  - Application (with an injected `InMemoryMatchRepository` and short rules): `test_bot_sources_lists_builtins_and_user_files` (temporary `user_bots` folder with `a_bot.py`), `test_created_match_is_saved_after_running` (Medium vs Easy, `duel_max_turns=20`).
  - Command line: `test_main_plays_and_prints_result` (`main(["play", "Medium", "Easy", "--seed", "2", "--database", <temp file>])` returns 0, output contains `"Medium"` and the database has one match; capture stdout with `contextlib.redirect_stdout`), `test_main_reports_broken_bot` (exit code 2).
- [ ] **Step 2: Run**; expected: import errors.
- [ ] **Step 3: Implement**; update the spec lines.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point D**: `save played matches and add a command line to play them`
- [ ] **Step 6:** Final review (reviewer agent on the whole plan), fix pass, update `../docs/notes/status.md` and `../docs/ai-contributions.md`; tell the user the console tool in `NTP/tools` is replaced by `src/main.py play`.
