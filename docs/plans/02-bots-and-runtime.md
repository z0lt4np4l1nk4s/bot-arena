# Bots and Bot Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything needed to turn a bot (built-in or a user's `.py` file) into answers for the engine: the public bot API, the `Bot` protocol, safe loading with clear errors, three built-in bots, and a separate process per bot with a time limit.

**Architecture:** `arena.api` is the only module a bot imports; its path helper is memoized with a closure. `arena.bots` defines the `Bot` protocol, loads bot classes from files with `importlib`, and holds the built-in bots in a registry filled by a class decorator. `arena.runtime.bot_process` runs one bot in its own `multiprocessing.Process`, talks to it over a `Pipe`, enforces the per-turn limit, and restarts a bot that hangs.

**Tech Stack:** Python 3.10 standard library (`typing.Protocol`, `importlib.util`, `multiprocessing`, `functools`, `time`, `traceback`, `logging`, `random`); `unittest` + `doctest`.

**Spec:** `docs/specs/01-bot-arena-design.md` (sections 4.7, 6, 7.2, 7.3, 7.4, 7.6, 7.8).

## Global Constraints

- Python 3.10, standard library only, everything in English, full names (no abbreviations). Rules in `CLAUDE.md` and `.claude/rules/` apply to every task.
- Built-in bots and user bots import **only** from `arena.api`.
- Every number comes from `Rules`: turn limit `turn_time_limit_ms` (100), kill timeout `bot_kill_timeout_ms` (2000).
- Tests that start processes must finish quickly: use `Rules(turn_time_limit_ms=200, bot_kill_timeout_ms=600)` and always stop processes in `tearDown` / `addCleanup`.
- On Windows `multiprocessing` uses *spawn*: the child process must receive only picklable data (the bot's source description and the rules), never a bot class or instance, and load the bot itself.
- Commit points: run the `verify` skill, then commit with a lowercase plain-language message. The `reviewer` agent runs once at the end of the plan.
- Run one test file: `../venv/Scripts/python -m unittest discover -s tests -p "test_<name>.py" -v` (from `Projekt/`).

## Decisions this plan makes (spec is silent or must be adjusted)

1. **The utilities package is `arena.utilities`** (spec 7.1 says `utils/`; the user wants full names).
2. **`arena.api` exports `Position`, not `Cell`** (spec 6.1 lists `Cell`): one name for one concept. Spec 6.1 is updated in Task 2.
3. **The `Bot` protocol** requires a class attribute `name: str` and a method `decide(self, state: BotState) -> Action`. A user bot class must also be constructible with no arguments.
4. **Loading a user bot executes its file**, inside the bot's own process during a match. The GUI's "Check" button (plan 5) also loads it in a separate process; this plan only provides the loading function.
5. **Startup handshake:** a bot process loads the bot and answers `ready` (or the load error) before the match starts, with a startup limit of 10 seconds (constant `STARTUP_TIMEOUT_SECONDS`), so process start-up time on Windows never counts against the 100 ms turn limit.
6. **A late or crashing bot:** the reply is `wait()` with `timed_out=True` or `error="<ExceptionType>: <message> (line N)"`, where N is the line in the bot's own file. A reply for an older turn is discarded. A bot that has not answered for `bot_kill_timeout_ms` is killed and restarted with a fresh instance (spec 4.7).
7. **A bot that returns something that is not an `Action`** gets `wait()` and `error="decide() must return an Action, got <type name>"`.
8. **Configurable logging (user request).** One `configure_logging(settings)` call at start-up sets the level (`ERROR`, `WARNING`, `INFO`, `DEBUG`; default `WARNING`) and the log file (default `arena.log`). `@log_exceptions` logs through the standard `logging` module instead of writing a file itself, so the level applies. Bot processes receive the same `LogSettings` and configure themselves (spawn starts with a fresh interpreter). Spec 7.4 is updated.

## Review Focus

1. A bot whose `decide` raises: the match must go on with `wait()` and the error must name the line in the user's file, not a line inside the runtime. → Task 5, `test_exception_reports_line_in_bot_file`.
2. A bot that never returns (infinite loop): later turns must not hang; after the kill timeout the bot is restarted and answers again. → Task 5, `test_hanging_bot_is_restarted`.
3. A slow answer that arrives during a later turn must not be used as the later turn's action. → Task 5, `test_late_reply_is_discarded`.
4. A user file with two bot classes, or a bot class imported from elsewhere (e.g. `from my_other_bot import Other`): loading must be unambiguous. Only classes *defined in* the file count. → Task 3, `test_imported_class_is_not_counted`.
5. A bot file with a syntax error or an exception at import time: the error must carry the user's line number. → Task 3, `test_syntax_error_reports_line`, `test_import_time_exception_reports_line`.

---

### Task 1: Decorators and closures (`arena.utilities`)

**Files:**
- Create: `src/arena/utilities/__init__.py`, `src/arena/utilities/decorators.py`, `src/arena/utilities/logging_configuration.py`
- Test: `tests/test_decorators.py`, `tests/test_logging_configuration.py`

**Interfaces:**
- Produces:
  - `memoize(function: Callable[P, R]) -> Callable[P, R]`: caches results in a dictionary held by the closure, keyed by `(args, frozenset(kwargs.items()))`; arguments must be hashable. The wrapper exposes `cache_size() -> int` and `cache_clear() -> None` as attributes (typed via a small `Protocol`, `Memoized[P, R]`).
  - `@dataclass(frozen=True) class Timed(Generic[R])`: `value: R`, `elapsed_ms: float`.
  - `measure_time(function: Callable[P, R]) -> Callable[P, Timed[R]]`: uses `time.perf_counter`.
  - `log_exceptions(logger_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]`: on an exception, logs it with `logging.getLogger(logger_name).exception(...)` (level `ERROR`, message names the function's qualified name, traceback included), then re-raises.
  - In `logging_configuration.py`: `class LogLevel(Enum)` with `ERROR`, `WARNING`, `INFO`, `DEBUG` (values are the `logging` constants); `@dataclass(frozen=True) class LogSettings`: `level: LogLevel = LogLevel.WARNING`, `log_file: Path = Path("arena.log")`; `configure_logging(settings: LogSettings) -> None`: configures the `"arena"` logger only (not the root logger) with one file handler (format `"%(asctime)s %(levelname)s %(name)s: %(message)s"`), replacing handlers from an earlier call so it can be called again; `LogLevel.from_name(name: str) -> LogLevel` (case-insensitive, `ValueError` listing the valid names otherwise) for the command line later.
  - All wrappers use `functools.wraps`.

- [ ] **Step 1: Write the failing tests**: `test_memoize_calls_function_once_per_argument` (a counter in a closure counts calls: two calls with the same argument → 1 call, a different argument → 2), `test_memoize_keyword_arguments_are_part_of_key`, `test_memoize_cache_clear`, `test_memoize_keeps_name_and_docstring`, `test_measure_time_returns_value_and_elapsed` (a function that sleeps 20 ms → `elapsed_ms >= 15`, value unchanged), `test_log_exceptions_logs_traceback_and_reraises` (`self.assertLogs("arena.test", "ERROR")`; the record contains the function name and `ZeroDivisionError`; the exception still propagates), `test_log_exceptions_passes_results_through`. In `tests/test_logging_configuration.py`: `test_warning_level_skips_info` (temporary log file: a warning is written, an info message is not), `test_debug_level_writes_everything`, `test_error_level_writes_only_errors`, `test_reconfiguring_replaces_the_file_handler`, `test_level_from_name_is_case_insensitive`, `test_unknown_level_name_lists_valid_names`. Each test resets the `arena` logger in `tearDown` and closes handlers (Windows cannot delete open files).
- [ ] **Step 2: Run**; expected: `ModuleNotFoundError: No module named 'arena.utilities'`.
- [ ] **Step 3: Implement** with `ParamSpec`/`TypeVar` typing; doctest on `memoize` and `measure_time`.
- [ ] **Step 4: Run**; expected: pass.

---

### Task 2: Public bot API (`arena.api`)

**Files:**
- Create: `src/arena/api.py`
- Modify: `docs/specs/01-bot-arena-design.md` (6.1: `Cell` → `Position`; 6.2: `rules`; 7.1: `utils/` → `utilities/`), `src/arena/model/state.py` (`BotState` gets `rules: Rules`), `src/arena/engine/modes.py` (`state_for_bot` passes `self.rules`), `tests/test_modes.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `memoize`; `GameMap`, `Position`, `Direction`, `Action`, `BotState`, `Side`, `ModeKind`, `Trap`, `OpponentView`, `PlayerState`, `Event`, `EventKind`, `manhattan`.
- Produces:
  - `BotState.rules: Rules`: bots need the numbers (carry capacity, bullet range, trap distance) and must not hard-code them.
  - Re-exports (listed in `__all__`): `Action`, `BotState`, `Direction`, `Event`, `EventKind`, `GameMap`, `ModeKind`, `OpponentView`, `PlayerState`, `Position`, `Rules`, `Side`, `Trap`, `distance`, `shortest_path`, `next_step`.
  - `distance(a: Position, b: Position) -> int` (Manhattan; same as `manhattan`).
  - `shortest_path(game_map: GameMap, start: Position, goal: Position) -> tuple[Position, ...]`: cells from the one after `start` up to and including `goal`; `()` when `start == goal` or the goal is unreachable. Memoized with `@memoize` (the map is immutable and hashable). Ties broken by `Direction` order, so the path is deterministic.
  - `next_step(game_map, start, goal) -> Direction | None`: the direction of the first step of `shortest_path`, `None` if there is none.

- [ ] **Step 1: Write the failing tests**: `test_bot_view_carries_the_rules` (in `tests/test_modes.py`: `Duel(Rules(bullet_range=7)).state_for_bot(...).rules.bullet_range == 7`); `test_distance_is_manhattan`; `test_shortest_path_on_open_grid` (6×6, `(0,0)`→`(2,0)` is `((1,0),(2,0))`); `test_shortest_path_goes_around_walls` (exact length); `test_path_to_unreachable_goal_is_empty`; `test_path_to_start_is_empty`; `test_shortest_path_is_cached` (call twice with equal arguments, `shortest_path.cache_size()` grows by 1); `test_next_step_points_along_path`; `test_api_exports` (every name in `__all__` is importable from `arena.api`).
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement**; BFS with parent links. Doctest on `distance` and `next_step`.
- [ ] **Step 4: Run**; expected: pass. Update the spec lines.
- [ ] **Step 5: Commit point A**: `add the public bot interface and helper decorators`

---

### Task 3: Bot protocol and loading from a file

**Files:**
- Create: `src/arena/bots/__init__.py`, `src/arena/bots/protocol.py`, `src/arena/bots/loader.py`
- Modify: `src/arena/errors.py` (add `BotLoadError(ArenaError)` with attribute `line: int | None`)
- Test: `tests/test_loader.py`

**Interfaces:**
- Produces:
  - `@runtime_checkable class Bot(Protocol)`: `name: str`; `def decide(self, state: BotState) -> Action: ...`.
  - `load_bot_class(path: Path) -> type[Bot]`: imports the file under a unique module name (`spec_from_file_location`), then returns the single class *defined in that module* (`cls.__module__ == module.__name__`) that has a `str` attribute `name` and a callable `decide`. Raises `BotLoadError` for: a syntax error (`line` = the error's line), any exception while executing the file (`line` = the deepest traceback frame inside `path`), no matching class (`"no bot class found"`), several (`"several bot classes found: A, B"`), a class whose constructor needs arguments (`"bot class must be constructible without arguments"`). The message includes the line when known: `"SyntaxError: invalid syntax (line 3)"`.
  - `error_line_in_file(error: BaseException, path: Path) -> int | None`: helper reused by Task 5.

- [ ] **Step 1: Write the failing tests**, each writing a small bot file into a temporary directory: `test_loads_single_bot_class`, `test_loaded_class_satisfies_protocol` (`isinstance(cls(), Bot)`), `test_syntax_error_reports_line`, `test_import_time_exception_reports_line`, `test_no_bot_class`, `test_two_bot_classes`, `test_imported_class_is_not_counted` (file imports `Action` and defines one bot → loads fine), `test_class_without_decide_is_ignored` (helper class without `decide` next to the bot → loads the bot), `test_constructor_with_arguments_is_rejected`, `test_two_files_with_same_class_name_do_not_clash` (two temp files both defining `MyBot` load as different classes).
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement**; doctest on `error_line_in_file` is not needed (needs files); keep it covered by the tests.
- [ ] **Step 4: Run**; expected: pass.
- [ ] **Step 5: Commit point B**: `load user bots from files with clear errors`

---

### Task 4: Built-in bots and their registry

**Files:**
- Create: `src/arena/bots/registry.py`, `src/arena/bots/builtin/__init__.py`, `src/arena/bots/builtin/easy.py`, `src/arena/bots/builtin/medium.py`, `src/arena/bots/builtin/hard.py`, `src/arena/bots/source.py`
- Test: `tests/test_builtin_bots.py`, `tests/test_bot_source.py`, `tests/matches.py` (helper)

**Interfaces:**
- Consumes: `Bot`, `load_bot_class`, `arena.api` (bots import only from here), `Duel` (in tests only).
- Produces:
  - `register_builtin(cls: type[B]) -> type[B]` (class decorator, `B` bound to `Bot`): adds `cls` to the registry under `cls.name`; raises `TypeError` if the class does not satisfy `Bot` or the name is taken. `builtin_bots() -> dict[str, type[Bot]]` (imports `arena.bots.builtin` so all three are registered; names `"Easy"`, `"Medium"`, `"Hard"`).
  - `@dataclass(frozen=True) class BotSource`: `name: str`, `path: Path | None = None` (`None` = built-in). Class methods `builtin(name)`, `from_file(path)` (name = file stem). Method `create() -> Bot` (Factory): builds a built-in from the registry or loads the class from the file and instantiates it. Unknown built-in name raises `BotLoadError`.
  - **Easy**: a random valid move (never into a wall or off the map) using `random.Random` seeded from `state.turn` and its own position, so it is reproducible; shoots in a random direction about once in ten turns when allowed. Message says what it did.
  - **Medium**: walks the shortest path to the nearest reachable crystal (by path length; ties by row, then column); when `state.me.carrying == state.rules.carry_capacity` or no reachable crystals remain, walks home. Never shoots or traps. Message names its goal: `"crystal at (5, 7), 4 steps"` / `"going home with 3"`.
  - **Hard**: Medium's movement, plus: chooses the crystal with the best score `crystals / (my steps + 1)` while skipping crystals the opponent is at least 2 steps closer to; shoots when the opponent stands within range in a straight line with no wall between (current position, since a waiting or stunned opponent stays) and the shot is allowed; places a trap, when allowed, on the cell of the opponent's shortest path towards its nearest crystal that is 2–4 steps ahead of it; avoids the cells where it saw the opponent stand in the last 10 turns when an equally short path exists (a possible trap). Thoroughly commented, as it is the main example.
  - `tests/matches.py`: `play_duel(blue: Bot, red: Bot, seed: int) -> GameState` runs a full `Duel` in one process (no time limits) by calling `decide` on `state_for_bot` each turn.

- [ ] **Step 1: Write the failing tests**:
  - Registry: `test_three_builtins_registered`, `test_register_rejects_non_bot`, `test_register_rejects_duplicate_name`.
  - Source: `test_builtin_source_creates_bot`, `test_file_source_creates_bot` (temp file), `test_unknown_builtin_raises`, `test_file_source_name_is_file_stem`, `test_sources_are_picklable` (`pickle.dumps` round trip, needed for spawn).
  - Behaviour on small hand-made states: `test_easy_never_moves_into_wall`, `test_easy_is_reproducible`, `test_medium_heads_for_nearest_crystal`, `test_medium_goes_home_when_full`, `test_medium_never_shoots_or_traps` (over a full match), `test_hard_shoots_opponent_in_line`, `test_hard_does_not_shoot_through_wall`.
  - Strength, over full duels with `play_duel` on seeds 0–9, each seed played with both sides swapped (20 matches): `test_medium_beats_easy` (Medium wins at least 16), `test_hard_beats_medium` (Hard wins more than it loses and at least 12). Mark these two with a module docstring note that they take a few seconds.
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** the registry and source, then Easy, Medium, Hard. Tune Hard until `test_hard_beats_medium` passes; if it needs more than the rules above, record a ruling.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point C**: `add the three built-in bots`

---

### Task 5: Bot process with a time limit

**Files:**
- Create: `src/arena/runtime/__init__.py`, `src/arena/runtime/bot_process.py`
- Test: `tests/test_bot_process.py`, `tests/bot_files/` (small bot files used by the tests: `good.py`, `crashing.py` with a `decide` raising on line 9, `slow.py` sleeping 0.4 s, `hanging.py` looping forever on turn 1 only, `wrong_type.py` returning a string, `broken.py` with a syntax error)

**Interfaces:**
- Consumes: `BotSource`, `Rules`, `BotState`, `Action`, `measure_time`, `log_exceptions`, `error_line_in_file`.
- Produces:
  - `STARTUP_TIMEOUT_SECONDS: Final = 10.0`.
  - `@dataclass(frozen=True) class BotReply`: `turn: int`, `action: Action`, `elapsed_ms: float`, `error: str | None = None`, `timed_out: bool = False`.
  - `class BotProcess` (context manager): `__init__(self, source: BotSource, rules: Rules, log_settings: LogSettings = LogSettings())`; logs to `arena.runtime` (INFO: started, stopped, restarted; WARNING: timed out; ERROR: the bot raised, with its message; DEBUG: every reply with its time); `start(self) -> None` (spawns the child, waits for the handshake; raises `BotLoadError` with the child's message and line if loading failed); `ask(self, turn: int, state: BotState) -> BotReply` (sends `(turn, state)`, waits up to `turn_time_limit_ms`; on timeout returns `wait()` with `timed_out=True`; drops replies whose `turn` is not the current one; if the bot has been silent for `bot_kill_timeout_ms` since its oldest unanswered request, terminates it and starts a fresh process before sending); `restarts: int` (how many times it was restarted); `stop(self) -> None` (idempotent; terminates and joins).
  - Child entry `_run_bot(source: BotSource, connection: Connection, log_settings: LogSettings) -> None`: calls `configure_logging(log_settings)`, creates the bot, sends `("ready", None)` or `("error", message)`, then loops: receive `(turn, state)` (or `None` to stop), call `measure_time(bot.decide)`, validate the result, send the `BotReply`. Decorated with `@log_exceptions("arena.runtime")` so crashes of the runtime itself are logged.

- [ ] **Step 1: Write the failing tests** (rules `Rules(turn_time_limit_ms=200, bot_kill_timeout_ms=600)`; a `BotState` from `Duel().setup_map(1)`):
  - `test_good_bot_answers_with_its_action` (action equals what `good.py` returns, `error is None`, `elapsed_ms >= 0`)
  - `test_builtin_bot_runs_in_process`
  - `test_broken_file_fails_at_start_with_line`
  - `test_exception_reports_line_in_bot_file` (`"(line 9)"` in `error`, action is `wait`)
  - `test_wrong_return_type_is_an_error`
  - `test_slow_bot_times_out` (`timed_out` and `wait`)
  - `test_late_reply_is_discarded` (turn 1 times out with `slow.py`; turn 2's reply has `turn == 2` and is not turn 1's late answer)
  - `test_hanging_bot_is_restarted` (`hanging.py` hangs on turn 1; asks for turns 2, 3… until 1 s has passed; then `restarts == 1` and a later reply is a normal action)
  - `test_stop_is_idempotent_and_kills_child`
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** with `multiprocessing.get_context("spawn")` explicitly (same behaviour on every OS), `Pipe(duplex=True)`, `Connection.poll(timeout)`.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite and check it still finishes in well under a minute.
- [ ] **Step 5: Commit point D**: `run every bot in its own process with a time limit`
- [ ] **Step 6:** Final review (reviewer agent on the whole plan), fix pass, update `../docs/notes/status.md` and `../docs/ai-contributions.md`.
