# Bot Arena: project design

Status: approved topic. Implementation is split into five plans in `docs/plans/`: 1) game engine, 2) bots and bot runtime, 3) match runner and storage, 4) GUI, 5) editor, solo, series and final README.

---

## 1. Summary

**Bot Arena** is a desktop application (Python + tkinter) in which the user writes their own bot, i.e. a Python class, that plays turn by turn on a 20×20 grid. The bot collects crystals and carries them to its base. In a duel it can fight an opponent by shooting and with hidden traps.

What the user can do:
- **write a bot in the built-in editor**, which highlights syntax and shows the line with an error, and save it under their own name
- **play a duel** (their bot against a built-in bot or another of their own bots) or **solo** (the bot collects crystals alone against the clock)
- **watch a match turn by turn, like analysing a chess game**: forward, back, jump to a turn, with a log showing what the bot decided and *why* (with every move the bot can return a message)
- **browse the history of all played matches** and reopen any of them
- **run a series**: the same pair of bots plays e.g. 50 matches on different maps in parallel, and the result is the win percentage

The application ships with **3 built-in bots** (Easy, Medium, Hard). They are both opponents and examples that the user can copy and improve.

---

## 2. Goals, non-goals, anti-goals

**Goals**
- A fun, original application in which the difference between bad and good bots is immediately visible.
- Every advanced technique (decorators, closures, protocols and ABCs, concurrency, design patterns, metaprogramming, testing) has a **natural** place in the code; nothing is forced in.
- The code passes all quality gates (see section 3): VS Code Pylance type checking in **standard** mode with no errors, `mypy --strict`, `ruff check`, `ruff format --check`, `pycodestyle`, and all unittest + doctest tests pass.
- The application is self-contained: it needs nothing but Python and its standard library to run.

**Non-goals** (deliberately not done)
- Real-time play. The game is turn-based.
- Graphics with images or sprites. Squares, circles and text are drawn on a tkinter Canvas.
- Networking and online play. More than 2 bots per match, tournaments, ELO.
- A real security sandbox for user code. It is isolated in a separate process for stability and the time limit, not for security.
- An advanced IDE. The editor is simple.

**Anti-goals** (the project is broken if this happens, even if it "works")
- The map favours one bot.
- The GUI freezes while a match or series is running.
- A bad user bot (infinite loop, exception) crashes the application.
- The type checker reports errors.
- The application needs external packages or the internet.

---

## 3. Constraints

- **Python 3.10.** Features from 3.11+ (e.g. `typing.Self`, `except*`, `tomllib`) are not used.
- **Standard library only at runtime**: `tkinter`, `sqlite3`, `multiprocessing`, `concurrent.futures`, `threading`, `asyncio`, `tokenize`, `importlib`, `dataclasses`, `enum`, `typing`, `abc`, `json`, `random`, `logging`.
- `requirements.txt` lists only development tools (`ruff`, `mypy`, `pycodestyle`), with a note that they are needed only for development; the application itself needs nothing beyond the standard library.
- **Everything is in English.**
- The virtualenv lives **outside** the repository. `arena.db`, `arena.log` and `__pycache__/` go into `.gitignore`.
- The project is developed with **test-driven development**.
- **Quality gates:**
  - VS Code Pylance type checking in **standard** mode with no errors
  - `mypy --strict`
  - `ruff check`
  - `ruff format --check`
  - `pycodestyle`
  - all unittest and doctest tests pass

---

## 4. Game rules

### 4.1 Map
- The grid is **20×20**. A cell is empty, a wall or a base. An empty cell can hold 0 or more crystals.
- The **Blue base** is in the top-left corner `(0, 0)` and the **Red base** in the bottom-right corner `(19, 19)`.
- The map is generated **randomly from a seed** (an integer). The same seed always gives the same map.
- **Fairness:** the map is **180° rotationally symmetric**, i.e. cell `(x, y)` corresponds to cell `(19-x, 19-y)`. Every wall and crystal has its pair. Since the grid size is even, no cell maps onto itself.
- About **15% of the cells are walls**. The generator keeps each base and its neighbouring cells free.
- **16 crystals** (8 pairs).
- The generator **verifies** (BFS) that every crystal is reachable from both bases. If not, it generates again, deterministically from the same seed.

### 4.2 Turn flow
In every turn both bots **simultaneously** receive their state and return one action. The turn is then resolved in this order:

1. **Stunned and trapped** bots skip their action (the log says "stunned" or "trapped").
2. **Trap placement.**
3. **Moves.** Moving into a wall or off the map means the bot stays in place. If both bots move to the same cell or swap cells, neither moves. A bot cannot enter the cell occupied by the opponent, unless the opponent leaves it in the same turn. **Two bots never share a cell.**
4. **Traps:** a bot that stepped on an opponent's trap is stuck for **3 turns**, and the trap disappears.
5. **Shooting** (based on the new positions, see 4.4).
6. **Crystals:** a bot on a cell with crystals automatically picks up as many as it can carry (at most **3** in hand). Stunned or trapped bots pick up and deliver nothing. A bot on **its own base** automatically delivers everything it carries. Delivered crystals are points.

### 4.3 Actions
| Action | Description |
|---|---|
| `move(direction)` | up / down / left / right by one cell |
| `shoot(direction)` | a bullet in a straight line, see 4.4 |
| `trap(position)` | place a hidden trap on any cell of the map (see 4.5) |
| `wait()` | do nothing |

Every action can carry an optional **message** (a string, e.g. `"going for crystal (5,7), 4 cells"`). The message is shown in the match viewer log.

### 4.4 Shooting
- The bullet travels from the shooter's cell in the given direction, **at most 5 cells**. **A wall stops it.**
- Shooting takes the whole turn, so the bot does not move that turn.
- A hit is checked **after the moves**: the shooter has to predict where the opponent will be.
- The hit bot **drops all crystals it carries**: they **scatter one per cell onto the nearest free cells** it could walk to (first the four neighbours up, down, left, right, then further out). They never land on a wall, outside the map or under the other bot; if there is no room at all, they stay on the hit bot's cell. **Anyone can pick them up.** In addition, the hit bot is **stunned for 2 turns**, which gives the shooter time to collect them.
- After shooting there is a **cooldown of 5 turns** before the next shot, whether it hit or not.
- If both bots shoot in the same turn, both bullets are resolved.
- Every shot that is fired is recorded as a **shot event** (who shot and the last cell the bullet reached), so both bots and the viewer see it, even when it misses. A shot refused because of the cooldown is not an event.

### 4.5 Traps
- `trap(position)` places a trap on **any cell of the map**; it takes the whole turn, so the bot does not move. The target must be walkable, not a base, not a cell with a bot, not a cell that already has a trap, and **at least 2 cells (Manhattan) away from the opponent**, so a trap cannot be dropped at its feet: the owner has to predict where the opponent will go.
- After placing a trap there is a **cooldown of 8 turns** before the next one.
- Every bot has **3 traps**: at most 3 can be active on the map at the same time.
- **A trap lasts 25 turns** from placement. After that it disappears from the map and **returns to the bot**, so it can be placed again. The total number of traps in a match is unlimited; only the number of simultaneously active traps is limited (with a cooldown of 8, a third trap is placed while the first is still active).
- A refused trap (any rule above broken) counts as `wait()`, and the reason is written to the log. Only the bot itself sees its refusals.
- **The opponent does not see someone else's traps.** In its state a bot sees only its own traps, with the number of remaining turns for each.
- A bot's own trap does not affect its owner.
- When the opponent steps on a trap, it is stuck for 3 turns (cannot do anything) and the trap disappears. The trap returns to its owner when its 25 turns from placement run out, the same as if it had not been triggered. Both bots see that the trigger happened through the `events` field of the state (see 6.2).

### 4.6 End of match
- A **Duel** ends after **200 turns** or when all crystals have been delivered. The bot with more delivered crystals wins. If they are equal, the bot that delivered its **last crystal in an earlier turn** wins; if that is equal too (the same turn, or nothing delivered), it is a draw.
- **Solo:** one bot on the same kind of map (Blue base), **with no opponent, shooting or traps**. The map has only **8 crystals** (the half of the map closer to the Blue base). The goal is to deliver all 8 in as few turns as possible, at most **300**. The result is the number of turns, or "did not finish" together with the number of delivered crystals. For every seed the **best result (record)** is kept, along with which bot set it.

### 4.7 A bot that is late or crashes
- The limit is **100 ms per turn**. If the bot does not answer in time or raises an exception, the turn counts as `wait()`. The log records "timed out" or the error text with the **line number**.
- A late answer from the previous turn is discarded (turns are numbered).
- If the bot does not answer even after **2 seconds**, its process is killed and restarted with a new bot instance. The bot's internal state is lost in that case, which is acceptable.
- If the bot cannot be loaded at all (syntax error, no class that satisfies the protocol), the match does not start and the GUI shows the error.

**Minor rules:** if a bot is stunned and trapped at the same time, the longer of the two durations applies (they do not add up). The shooting cooldown and trap durations keep counting down while the bot is stunned or trapped.

All numbers (20×20, 15%, 16 crystals, carrying capacity 3, range 5, cooldown 5, stun 2, traps 3 / duration 25 / cooldown 8 / minimum distance 2 / stuck 3, 200, 300, 100 ms) are kept in **one place** as the rules configuration (see 7.6), so they are easy to change.

---

## 5. Screens (GUI)

The main window is a `ttk.Notebook` with tabs. The **Match Viewer** tab opens when a match is started or opened from history.

### 5.1 Play
- Mode selection: **Duel** / **Solo**.
- Drop-down menus: **Blue bot**, **Red bot** (duel only). The list contains the 3 built-in bots and all user bots.
- **Seed**: a number field + a "Random" button.
- The **Start** button is disabled while the previous match is running (next to it is a **Stop** button). The match runs in the background and the view switches immediately to the *Match Viewer*, which shows turns as they arrive.

### 5.2 Match Viewer
- **Left:** a Canvas with the map. Walls, bases, crystals (a count if there are several on a cell), both bots (colour and number of carried crystals, a marker when stunned or trapped) and the bullet line in a turn where a shot was fired. Traps are shown **for both bots, marked with their owner**, because this is the analyst's view, not the bot's.
- **Below the map:** ⏮ ◀ ▶/⏸ ▶ ⏭, a slider to jump to a turn, a slider for playback speed, a label "Turn 47 / 200".
- **Right:** the turn log. For every turn, each bot's action, its message, thinking time (ms) and errors or timeouts. Clicking a row jumps to that turn.
- **Top:** the score (delivered crystals Blue : Red) and the bot state (carrying, shooting cooldown, remaining traps).
- While the match is still running, it can be watched live or the already played turns can be rewound.

### 5.3 Editor
- **Left:** the list of bots. Built-in bots are marked with a lock and are read-only.
- **Right:** a `tk.Text` with **line numbers** and **syntax highlighting** (keywords, built-in functions, strings, comments, numbers), using `tokenize` and `keyword` from the standard library.
- Buttons: **New bot** (from a template), **Copy** (makes a user copy of the selected bot, asks for a name), **Save**, **Rename**, **Delete** (user bots only) and **Check**.
- **Check** compiles the code, loads it in a separate process and checks whether there is a class that satisfies the `Bot` protocol. The error is shown below the editor, and the line is **highlighted with a red background**.
- User bots are `.py` files in the `user_bots/` folder. The bot's name is the file name. The folder is scanned at startup, so a bot saved once also shows up next time.

### 5.4 History
- A table (`ttk.Treeview`) of **all** played matches: date, mode, bots, seed, result, number of turns. It is sorted by clicking a header and filtered by bot and mode.
- Double-clicking opens the match in the *Match Viewer*.
- A sub-table **Solo records**: seed, best number of turns, bot, date.
- A button to delete the selected match.

### 5.5 Series
- Selection of two bots, the number of matches (e.g. 10 to 200) and a starting seed. Seeds follow in order: the starting seed, +1, +2...
- Matches run **in parallel in multiple processes**. The GUI shows a progress bar and stays responsive. A **Stop** button.
- **Series fairness:** every seed is played twice, with sides swapped. "50 matches" means 25 seeds × 2 sides, so the number of matches is always even.
- Result: wins, losses and draws (%), average delivered crystals, average time per turn and the number of errors or timeouts per bot.
- Matches from a series are **not** saved individually to history. Only the series summary is saved.

---

## 6. How to write a bot

### 6.1 Form
A bot is a class in a `.py` file. No inheritance is needed: it is enough for the class to satisfy the `Bot` **protocol**.

```python
from arena.api import Action, BotState, Direction


class MyBot:
    name = "My bot"

    def decide(self, state: BotState) -> Action:
        if state.me.carrying == 3:
            return Action.move(Direction.UP, message="full, heading home")
        return Action.wait()
```

API names: the actions are `Action.move(direction)`, `Action.shoot(direction)`, `Action.trap(position)` and `Action.wait()`, each with an optional `message=`. The directions are `Direction.UP/DOWN/LEFT/RIGHT`. The state is `BotState` with the fields `turn`, `max_turns`, `mode`, `map`, `crystals`, `me`, `opponent` and `events`. The helper functions are `distance`, `distances_from`, `shortest_path`, `next_step` and `bullet_path`.

- The bot is an instance that **lives for the whole match**, so it can remember things between turns.
- A file may contain only one class that satisfies the protocol. If there are several or none, it is a loading error.
- `arena.api` is the only application module a bot may use. It exposes `Action`, `Direction`, `BotState`, `Position`, `Rules` and helper functions (`distance`, `distances_from`, `shortest_path`, `next_step`, `bullet_path`), to make writing a bot pleasant.

### 6.2 What the bot sees (`BotState`, immutable)
- `turn`, `max_turns`, `mode` (duel or solo)
- `map`: dimensions, walls, the position of both bases
- `crystals`: positions of the crystals on the ground and the count on each cell
- `me`: position, how many it carries, delivered, shooting cooldown, trap cooldown, stunned/trapped (remaining turns), free traps, **my active traps** (position and remaining turns)
- `opponent` (`None` in solo): position, how many it carries, delivered, shooting cooldown, stunned/trapped. **Without its traps.**
- `events`: what happened in the previous turn (a shot, a hit, stepping into a trap and whose it is, dropped crystals)
- `rules`: the numbers of the game (carrying capacity, bullet range, cooldowns...), so a bot never has to hard-code them

### 6.3 Built-in bots
- **Easy:** a random valid move. Sometimes shoots randomly.
- **Medium:** BFS to the nearest reachable crystal. When it is full or there are no crystals left, it goes home. It does not shoot or place traps. Its messages explain its goal.
- **Hard:** picks a crystal by the ratio of value to distance, taking the opponent's distance into account. Shoots when it predicts the opponent will be in the line of fire. Places traps in narrow passages in front of its base, on crystals the opponent is heading for, or on the opponent's likely path. Avoids cells where the opponent has stood (a possible trap).
- All of them are thoroughly commented because they serve as examples.

---

## 7. Technical design

### 7.1 Structure (outline)
```
bot-arena/
  README.md
  requirements.txt
  src/
    main.py                # entry point; `python src/main.py play Hard Medium` until the GUI
    arena/
      api.py                 # public interface for bot authors
      rules.py               # rules configuration (descriptors)
      model/                 # Position, Direction, Action, BotState, GameState (dataclasses)
      map_generator/                # map generator (seed, symmetry, BFS check)
      engine/                # GameMode (ABC), Duel, Solo, turn resolution
      bots/                  # Bot protocol, loading, registry, built-in bots
      runtime/               # bot processes, time limit, series
      storage/               # SQLite repository
      gui/                   # tkinter: tabs, Canvas, editor, viewer
      utilities/             # decorators, memoization, logging
  user_bots/               # .py files of user bots
  tests/                   # unittest
```
The implementer may change the layout if there is a good reason. The important split is: **the engine knows nothing about the GUI**.

### 7.2 Concurrency: all three models, each in its natural place
- **multiprocessing:** every bot runs in **its own process** (`multiprocessing.Process` + `Pipe`/`Queue`). This gives isolation and the ability to kill a blocked bot.
- **asyncio:** in every turn the match runner asks both bots for an answer **simultaneously** and waits for them with a time limit (`asyncio.gather` + `asyncio.wait_for`, with reading from the pipe done via `run_in_executor`). The match runner runs in a background thread with its own event loop.
- **threading:** a background thread runs the match, and the GUI receives turns through a `queue.Queue` that is read with `root.after(...)`. Tkinter is touched only from the main thread.
- **concurrent.futures.ProcessPoolExecutor:** match series in parallel, with progress reported to the GUI and the ability to stop.

### 7.3 Interfaces, Protocols, ABC
- `Bot`: a `typing.Protocol` (`@runtime_checkable`). A user bot inherits nothing (structural typing).
- `GameMode`: an `abc.ABC` with abstract methods (`setup_map`, `allows`, `winner`) and shared concrete methods (`state_for_bot`, `step`, `is_over`). The implementations are `Duel` and `Solo`; each registers itself by its kind, and `GameMode.create(kind)` builds one.
- `MatchRepository`: an ABC with the implementations `SqliteMatchRepository` and `InMemoryMatchRepository` (for tests).
- `MatchObserver`: a Protocol for event receivers (GUI, saving to the database).
- `BotClient`: a Protocol for anything the match runner can ask for an action: a bot in its own process (`BotProcess`) or a bot called directly (`InProcessBotClient`, for tests and fast series).
- **Dependency injection:** the match runner receives its game mode, bot clients and observers; the storage observer receives a repository. Only the composition root (`arena.application.Application`, used by `src/main.py`) chooses the concrete classes.

### 7.4 Decorators and closures
- `@measure_time`: measures the bot's thinking time (used in the bot process).
- `@log_exceptions(logger_name)`: a parameterized decorator that logs exceptions through the standard `logging` module.
- **Logging levels are configurable** at start-up: `ERROR`, `WARNING` (default), `INFO` or `DEBUG`, written to `arena.log`. Bot processes use the same settings.
- `@register_builtin`: a class decorator that adds a built-in bot to the registry.
- `@memoize`: memoization implemented with a **closure** (a dictionary in the enclosing scope), used for shortest paths on the immutable map.
- Closures are also used in the GUI (callback factories for buttons, e.g. `make_jump_to(turn)`) and in the turn ID counter.
- All decorators use `functools.wraps` and are correctly typed (`ParamSpec`/`TypeVar` from `typing`, available in 3.10).

### 7.5 Design patterns
- **Strategy:** bots and game modes.
- **Observer:** the engine emits turn events, and the GUI and storage listen to them.
- **Factory:** the map generator from a seed; the bot factory (built-in or from a file).
- **Command:** `Action` as a command object that the engine executes.
- **Repository:** match storage.
- **Memento:** recorded per-turn states for rewinding.

### 7.6 Metaprogramming
- **Validated descriptors** in `rules.py`, e.g. `Bounded(min, max)`: values such as `crystal_count` or `bullet_range` cannot be set outside their bounds.
- A **metaclass** or `__init_subclass__` for the registry of game modes and/or built-in bots.
- **`importlib`** for dynamically loading a user bot from a file and finding the class that satisfies the protocol (introspection).
- `@property` for derived values (e.g. `GameState.is_finished`).

### 7.7 PEP 8, PEP 484, PEP 526
- All functions and methods are fully annotated. Variables are annotated per PEP 526, and class constants via `ClassVar`.
- Generics where they make sense (`TypeVar`, `Generic`), `Final`, `Literal`, `TypeAlias`.
- **0 errors** in VS Code Pylance type checking (standard mode), `mypy --strict`, `ruff check`, `ruff format --check` and `pycodestyle`.

### 7.8 Doctest and unittest
- **doctest** in pure functions: cell rotation, distance, directions, action parsing and validation, descriptors.
- **unittest**:
  - map generator (determinism per seed, symmetry, reachability, equal paths)
  - turn resolution (move conflicts, shooting after moves, a wall blocks the bullet, cooldown, stun, traps and visibility, pick up/deliver, dropped crystals)
  - end conditions and the winner
  - bot loading (a good bot, a syntax error with the line number, no class)
  - time limit and bot crash
  - repository (in memory or `:memory:` SQLite)
- Everything runs with `python -m unittest discover -s tests` (doctests are included via `load_tests`).

### 7.9 Storage
- `arena.db` (SQLite) in the project folder, **one column per value** (no JSON or pickle), so the history can be explored with plain SQL: `matches` (mode, seed, bots, result, date, number of turns), `match_walls`, per turn `turn_players` (each bot's state and its reply: action, message, thinking time, error, timeout), `turn_crystals`, `turn_traps`, `turn_events`, plus `solo_records` and later series summaries. A `metadata` table keeps the schema version.
- **Every** match from the Play tab is saved (not matches from series).
- Replays do not run the bots again. The recording is loaded.

---

## 8. Left to the implementer
- The exact module layout and class names, except for the names visible in the bot API (section 6).
- The SQLite table schema and the JSON recording format.
- Colours, fonts and the exact widget layout, provided it is clear and readable.
- The wall generation algorithm, subject to the conditions in 4.1.
- The exact "intelligence" of the Hard bot, provided that in a series it convincingly beats Medium, and Medium beats Easy.
- Whether `ProcessPoolExecutor` in series is used for whole matches, with the bots in the same process for speed (recommended), or with nested processes.
