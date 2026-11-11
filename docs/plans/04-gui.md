# GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tkinter window where the user starts a duel or solo match, watches it live or rewinds it turn by turn, and browses, replays and deletes the match history.

**Architecture:** A new package `arena.gui` depends on `arena.application`, `arena.runtime` and `arena.storage`; nothing below it imports it. Logic that needs no widgets (action descriptions, the playback state machine, history sorting and filtering, the match session that drains the event queue) lives in plain modules with unittest/doctest tests; the widget classes stay thin and get a few smoke tests on a hidden `Tk()` root. The match runs in the background thread from plan 3; the window reads its `queue.Queue` with `root.after(...)`, so tkinter is only touched from the main thread and the window never waits on the match.

**Tech Stack:** Python 3.10 standard library (`tkinter`, `tkinter.ttk`, `tkinter.messagebox`, `queue`, `random`, `wave`, `struct`, `math`, `winsound` on Windows, `subprocess` + `shutil` elsewhere); `unittest` + `doctest`.

**Spec:** `docs/specs/01-bot-arena-design.md` (sections 5, 5.1, 5.2, 5.4, 7.2, 7.4).

## Global Constraints

- Python 3.10, standard library only, everything in English (also every label and message in the window), full names. Rules in `CLAUDE.md` and `.claude/rules/` apply to every task.
- Dependencies: `gui → application/runtime/storage → engine → model`. Only `arena.gui` imports `tkinter`.
- Tkinter is used only from the main thread. The main thread never calls `MatchHandle.join()` without a zero timeout and never sleeps.
- GUI tests create their root through `tests/gui_support.py` (`hidden_root(test_case)`), which skips the test when no display is available, withdraws the window and destroys it in `addCleanup`. Tests never open `arena.db`: they inject `InMemoryMatchRepository` into `Application`.
- Tests that start bot processes use `Rules(turn_time_limit_ms=200, bot_kill_timeout_ms=600, duel_max_turns=20, solo_max_turns=20)`.
- Commit points: run the `verify` skill, then commit with a lowercase plain-language message. The `reviewer` agent runs once at the end of the plan.
- Run one test file: `../venv/Scripts/python -m unittest discover -s tests -p "test_<name>.py" -v` (from `Projekt/`).

## Decisions this plan makes (spec is silent)

1. **Shots are recorded as an event.** The viewer must draw the bullet line, but today a shot leaves no trace when it misses. The engine gets `EventKind.SHOT` (`side` = shooter, `position` = the last cell the bullet reached, or the shooter's cell if a wall is right next to it), emitted for every shot actually fired (not for one refused by cooldown). Both bots see it, like every other event except a refused action. Old recordings simply have no shot lines.
2. **Playback buttons are vector icons drawn in code.** Tk 8.6 cannot read SVG without a third-party package, and font symbols (⏮ ◀ ▶ ⏭) are missing from minimal font sets. So every icon is defined like an SVG path: a list of polygons in a 24×24 box (`arena.gui.icons`), drawn on a small `tk.Canvas` button that scales them, with hover, pressed and disabled looks. Icons: first, previous, play, pause, next, last, stop, sound on, sound off.
3. **Live viewing:** a new match starts in the viewer at turn 0, playing. While "playing" and standing on the newest turn, every arriving turn is shown immediately; the speed slider (1–20 turns per second, default 5) only matters when there are turns left to catch up with. Any manual navigation (`|<`, `<`, `>`, the turn slider, a click in the log) pauses; `>|` jumps to the newest turn and, while the match is live, resumes following it. The label shows `Turn N / max_turns` while the match runs and `Turn N / turns` when it is finished.
4. **One match in the viewer at a time.** Opening a match from history while a live match runs shows the replay; the live match keeps running in the background, is saved when it ends and stays stoppable from the Play tab, but the viewer no longer follows it.
5. **Command line:** with no command (`python src/main.py`) the window opens; `python src/main.py gui [--log-level ...]` does the same with options; `play` keeps working as before. The shared options `--log-level`, `--log-file`, `--database` belong to both commands.
6. **Bot drop-down labels:** built-in bots appear as `Hard (built-in)`, user bots by their file name (`my_bot`). The list is read again every time the Play tab is shown, so files added to `user_bots/` (or by the editor in plan 5) appear without a restart.
7. **Seed:** a whole number from 0 to 2**63 - 1 (what SQLite can store). "Random" picks from 0 to 999 999, like the command line. An invalid seed shows an error under the field and starts nothing.
8. **Closing the window while a match runs** stops the match, hides the window, and waits for the background thread with `after` polling (at most 10 s) before destroying the root and closing the application, so no bot process is left behind.
9. **Animations** play when the viewer moves exactly one turn forward (playing, live or `>`); jumping, rewinding and the slider show the new state at once. Effects, found by comparing the previous and the new state: a **shot** (a bullet travels along the line, then fades), a **hit** (a flash on the hit bot), a **trap placed** (a ring that shrinks onto the cell in the owner's colour), a **trap triggered** (the trap snaps shut with a burst), a **delivery** (the base pulses). An animation lasts `min(300 ms, 80 % of the time per turn)`; below 60 ms it is skipped. A new turn cancels a running animation.
10. **Sound** for the same five effects. Sounds are synthesised in code at start-up with `wave` + `struct` (short tones and noise bursts, no audio files in the repo) and played without blocking through a `SoundPlayer` protocol chosen in one place: `winsound` on Windows, the `aplay` or `paplay` command on Linux if present, otherwise silent. A sound button in the viewer mutes and unmutes (on by default). A missing or broken audio device only disables sound, it never shows an error. Only one sound per effect kind per turn, and none while jumping.

## Review Focus

1. A bot that fails to load must not leave the Play tab stuck with Start disabled; the user sees the error. → Task 6, `test_failed_match_reports_error_and_enables_start`.
2. Closing the window during a live match must not freeze it and must not leave bot processes. → Task 6, `test_closing_during_a_match_stops_it_and_destroys_the_root`.
3. A computer without sound (no device, no `aplay`, the command failing) must play matches silently, never show an error or block. → Task 5, `test_failing_player_is_disabled_silently`, `test_choose_player_falls_back_to_silent`.
4. History sorting by seed or turns must be numeric, not text (`10` after `9`), and dates must sort by time. → Task 7, `test_sort_by_seed_is_numeric`, `test_sort_by_date_is_chronological`.
5. Deleting the match that is open in the viewer, or deleting with nothing selected, must not crash. → Task 7, `test_delete_without_selection_does_nothing`, `test_deleting_the_open_match_clears_the_viewer`.

Also covered by tests, less likely to bite: a burst of queued turns is handled at most 50 events per poll (Task 6, `test_poll_takes_at_most_fifty_events`); a fast jump through many turns starts no animations and no sounds (Task 5, `test_jump_plays_no_effects`).

---

### Task 1: Shot events and text for the viewer

**Files:**
- Modify: `src/arena/model/state.py` (add `EventKind.SHOT = "shot"`), `src/arena/engine/turn.py` (`_shoot` emits it), `docs/specs/01-bot-arena-design.md` (4.4 and 6.2: shots appear as an event)
- Create: `src/arena/gui/__init__.py`, `src/arena/gui/formatting.py`
- Test: `tests/test_turn_shooting.py` (extend), `tests/test_formatting.py`, `tests/test_repository.py` (one extra contract test)

**Interfaces:**
- Produces (all pure, in `formatting.py`, with doctests):
  - `describe_action(action: Action) -> str`: `"move right"`, `"shoot up"`, `"trap at (4, 5)"`, `"wait"`.
  - `@dataclass(frozen=True) class LogRow`: `turn: int`, `side: Side`, `action: str`, `message: str`, `thinking_ms: str` (e.g. `"12.3"`), `problem: str` (`"timed out"`, the error text, or `""`).
  - `log_rows(record: TurnRecord) -> list[LogRow]`: one row per side, Blue first.
  - `player_status(player: PlayerState, rules: Rules) -> str`: `"carrying 2/3 · shot ready · traps 3"`; `"shot in 4"` while cooling down; appends `" · stunned 2"` / `" · trapped 3"` when disabled.
  - `score_text(state: GameState) -> str`: duel `"Blue 3 : 2 Red"`, solo `"Delivered 3 of 8"` (8 = delivered + carried + crystals left).
  - `bot_label(source: BotSource) -> str`: `"Hard (built-in)"` or `"my_bot"`.
  - `result_text(summary: MatchSummary) -> str`: `"Blue wins 9:7"`, `"Red wins 2:5"`, `"Draw 8:8"`, solo `"Finished in 104 turns"` or `"Not finished (5 delivered)"`, `"Stopped"` is never stored so it needs no text.
  - `shot_lines(state: GameState, rules: Rules) -> list[tuple[Side, list[Position]]]`: for every `SHOT` event in `state.events`, the cells from the shooter's position (in `state`) to the event's position, using `bullet_path` and cut at the event's cell.

- [ ] **Step 1: Write the failing tests**:
  - Engine: `test_shot_is_recorded_as_event` (a shot into open space: one `SHOT` event for the shooter whose position is the 5th cell), `test_shot_stopped_by_wall_ends_before_wall`, `test_refused_shot_has_no_shot_event`, `test_opponent_sees_shot_event` (`Duel.state_for_bot` for the other side keeps it).
  - Repository contract: `test_shot_events_survive_saving` (a recorded match with a shot loads back with the same `SHOT` event).
  - Formatting: one test per function above with the exact strings listed, plus `test_log_rows_show_timeout_and_error`, `test_solo_score_counts_all_crystals`, `test_shot_lines_from_shooter_to_end`.
- [ ] **Step 2: Run**; expected: failures (`SHOT` and `arena.gui.formatting` missing).
- [ ] **Step 3: Implement** (doctests are collected automatically by `tests/test_doctests.py`).
- [ ] **Step 4: Run** the whole suite; expected: pass.

---

### Task 2: Playback state machine

**Files:**
- Create: `src/arena/gui/playback.py`
- Test: `tests/test_playback.py`

**Interfaces:**
- Produces:
  - `class Playback` (no tkinter): `__init__(self, max_turns: int, available: int = 0, finished: bool = False, playing: bool = False)`; attributes `current: int` (0 = start state), `available: int`, `max_turns: int`, `finished: bool`, `playing: bool`.
  - Navigation (each pauses, clamps to `0..available`): `first()`, `previous()`, `next()`, `jump(turn: int)`. `last()` goes to `available` and sets `playing = not finished`. `toggle()` flips `playing` (starting play at the end of a finished match restarts from 0).
  - `add_turn() -> None`: `available += 1`; if `playing` and `current == available - 1`, `current` follows.
  - `finish() -> None`: `finished = True`.
  - `tick() -> bool`: if `playing` and `current < available`, advance by one and return `True`; at the end of a finished match set `playing = False`; otherwise `False`.
  - `label` property: `"Turn 47 / 200"` (see decision 3), with a doctest.
  - `make_jump_to(playback: Playback, turn: int) -> Callable[[], None]`: a closure used as a callback by the turn log (spec 7.4), with a doctest.
  - `SPEED_RANGE: Final = (1, 20)`, `DEFAULT_SPEED: Final = 5`, `tick_delay_ms(speed: int) -> int` (`1000 // speed`, clamped to the range; doctest).

- [ ] **Step 1: Write the failing tests**: `test_live_match_follows_new_turns`, `test_paused_playback_does_not_follow`, `test_manual_navigation_pauses`, `test_last_resumes_following_while_live`, `test_last_on_finished_match_does_not_play`, `test_tick_catches_up_then_waits`, `test_tick_stops_at_end_of_finished_match`, `test_toggle_at_end_restarts`, `test_navigation_is_clamped` (`jump(-3)` → 0, `jump(999)` → `available`), `test_label_uses_max_turns_until_finished`, `test_jump_callback_moves_and_pauses`.
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run**; expected: pass.
- [ ] **Step 5: Commit point A**: `describe turns and control playback for the viewer`

---

### Task 3: Map canvas

**Files:**
- Create: `src/arena/gui/map_canvas.py`, `tests/gui_support.py`
- Test: `tests/test_map_canvas.py`

**Interfaces:**
- Produces:
  - `tests/gui_support.py`: `hidden_root(test_case: unittest.TestCase) -> tk.Tk` (skips with `unittest.SkipTest` on `tk.TclError`, calls `withdraw()`, `addCleanup(root.destroy)`).
  - `cell_box(position: Position, cell_size: int) -> tuple[int, int, int, int]`: pure, doctest (`cell_box(Position(2, 1), 10) == (20, 10, 30, 20)`).
  - `class MapCanvas(tk.Canvas)`: `__init__(self, master: tk.Misc, rules: Rules)`; `draw(self, state: GameState | None) -> None` redraws everything (`delete("all")`; `None` shows the text "No match yet"); redraws the last state on `<Configure>`; cell size = `max(8, min(width, height) // state.map.size)`.
  - Every item carries one tag: `"wall"`, `"base"`, `"crystal"` (with the count as text when > 1), `"trap"` (an X in the owner's colour, for both owners), `"bot"` (circle in the side colour with the carried count; an outline marker and the letter `S`/`T` when stunned/trapped), `"shot"` (a line from `shot_lines`). Colours: Blue `#2f6fdd`, Red `#d64545`, walls `#555555`, crystals `#2bb3a3`.

- [ ] **Step 1: Write the failing tests** (on a hidden root, canvas 400×400, a real `Duel` start state and a `tests/recorded.py` match): `test_draws_every_wall` (`len(canvas.find_withtag("wall")) == len(state.map.walls)`), `test_draws_both_bases_and_bots`, `test_draws_traps_of_both_owners`, `test_draws_shot_line_in_a_turn_with_a_shot`, `test_crystal_count_shown_when_several`, `test_none_shows_placeholder`.
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run**; expected: pass.

---

### Task 4: Icons and match viewer

**Files:**
- Create: `src/arena/gui/icons.py`, `src/arena/gui/match_viewer.py`
- Test: `tests/test_icons.py`, `tests/test_match_viewer.py`

**Interfaces:**
- Consumes: `MapCanvas`, `Playback`, `make_jump_to`, `tick_delay_ms`, formatting functions, `RecordedMatch`, `MatchSummary`, `TurnRecord`.
- Produces in `icons.py` (decision 2):
  - `Polygon: TypeAlias = tuple[tuple[float, float], ...]`; `class IconName(Enum)`: `FIRST, PREVIOUS, PLAY, PAUSE, NEXT, LAST, STOP, SOUND_ON, SOUND_OFF`; `ICONS: Final[Mapping[IconName, tuple[Polygon, ...]]]` in a 24×24 box (read-only `MappingProxyType`).
  - `scale_polygon(polygon: Polygon, size: int) -> list[float]`: pure, doctest, flat coordinate list for `create_polygon`.
  - `class IconButton(tk.Canvas)`: `__init__(self, master: tk.Misc, icon: IconName, command: Callable[[], None], tooltip: str, size: int = 28)`; `set_icon(icon: IconName)`; `set_enabled(enabled: bool)`; `invoke()` (calls `command` only when enabled); hover lightens the background, a press darkens it, a disabled button is grey and ignores clicks; the tooltip text is shown in the viewer's status line on hover.
- Produces: `class MatchViewer(ttk.Frame)`: `__init__(self, master: tk.Misc, rules: Rules)`.
  - `start_live(self, summary: MatchSummary, initial_state: GameState) -> None` (new `Playback(max_turns, playing=True)`; clears the log),
  - `add_turn(self, record: TurnRecord) -> None` (appends log rows; updates slider range and view),
  - `finish_live(self, match: RecordedMatch) -> None`,
  - `show_recorded(self, match: RecordedMatch) -> None` (finished playback at turn 0, paused),
  - `clear(self) -> None`, property `match_id: int | None` (of the shown match, `None` for live or empty), property `is_live: bool`.
  - Layout: top `score_text` and one `player_status` label per bot; left `MapCanvas`; below the map the `IconButton`s first, previous, play/pause (the icon switches), next, last, a turn `ttk.Scale`, a speed `ttk.Scale` (`SPEED_RANGE`), the `playback.label`; right a `ttk.Treeview` log with columns Turn, Bot, Action, Message, Thinking (ms), Problem; selecting a row calls that row's `make_jump_to` callback (kept in a dict by item id).
  - Timer: one `after(tick_delay_ms(speed), ...)` loop that calls `playback.tick()` and refreshes only when it returns `True`; the loop is cancelled in `destroy()`. Slider updates made by the code must not trigger `jump` (guard flag).
  - The current turn's state is `initial_state` for turn 0, otherwise `records[turn - 1].state`.

- [ ] **Step 1: Write the failing tests**. Icons: `test_every_icon_name_has_polygons`, `test_polygons_fit_in_the_box` (all points within 0..24), `test_scale_polygon_doubles_at_48`, `test_disabled_button_ignores_invoke`, `test_set_icon_redraws` (hidden root). Viewer (hidden root, recorded match from `tests/recorded.py`): `test_recorded_match_starts_at_turn_zero_paused` (label `f"Turn 0 / {turns}"`), `test_log_has_two_rows_per_turn`, `test_next_button_moves_one_turn` (`viewer.next_button.invoke()`), `test_selecting_a_log_row_jumps_to_its_turn`, `test_live_turns_are_followed` (`start_live` + three `add_turn` calls → label `"Turn 3 / 20"`), `test_clear_shows_empty_viewer`.
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the whole suite; expected: pass.
- [ ] **Step 5: Commit point B**: `show matches on a map and step through them`

---

### Task 5: Animations and sound

**Files:**
- Create: `src/arena/gui/effects.py`, `src/arena/gui/animations.py`, `src/arena/gui/sounds.py`
- Modify: `src/arena/gui/match_viewer.py` (play effects on a one-turn step; sound button), `docs/specs/01-bot-arena-design.md` (5.2: animations and sound with a mute button)
- Test: `tests/test_effects.py`, `tests/test_sounds.py`, `tests/test_animations.py`

**Interfaces:**
- Produces in `effects.py` (pure, no tkinter):
  - `class EffectKind(Enum)`: `SHOT, HIT, TRAP_PLACED, TRAP_TRIGGERED, DELIVERED`.
  - `@dataclass(frozen=True) class Effect`: `kind: EffectKind`, `side: Side`, `cells: tuple[Position, ...]` (the bullet line for `SHOT`, one cell otherwise).
  - `turn_effects(previous: GameState, current: GameState, rules: Rules) -> list[Effect]`: `SHOT` from `shot_lines`; `HIT`, `TRAP_TRIGGERED` (from `TRAPPED`), `DELIVERED` from the events of `current`; `TRAP_PLACED` for every trap in `current.traps` that is not in `previous.traps` (same owner and position). Order: shots, trap placements, hits, triggered traps, deliveries.
- Produces in `animations.py`:
  - `animation_duration_ms(tick_ms: int) -> int`: `min(300, tick_ms * 4 // 5)`, `0` below 60 (doctest).
  - `class EffectAnimator`: `__init__(self, canvas: MapCanvas)`; `play(self, effects: Sequence[Effect], duration_ms: int) -> None` (draws frames every 30 ms with `after`, items tagged `"effect"`; a new `play` or `cancel` removes them first); `cancel(self) -> None`; property `is_running: bool`. `MapCanvas` gains `cell_center(position: Position) -> tuple[float, float]` for it.
- Produces in `sounds.py`:
  - `SAMPLE_RATE: Final = 22050`; `synthesize(kind: EffectKind) -> bytes`: a complete mono 16-bit WAV file built with `wave` into `io.BytesIO` (shot: short falling tone with noise, hit: low thump, trap placed: two soft clicks, trap triggered: metallic snap, delivered: rising chime); each under 0.4 s.
  - `class SoundPlayer(Protocol)`: `play(self, sound: bytes) -> None` (must not block).
  - `WindowsSoundPlayer` (`winsound.PlaySound(sound, SND_MEMORY | SND_ASYNC | SND_NODEFAULT)`; imported inside the class so other systems never import `winsound`), `CommandSoundPlayer(command: Sequence[str])` (writes each sound once to a temporary file and starts the command with `subprocess.Popen`, output discarded), `SilentSoundPlayer`.
  - `choose_player(platform: str = sys.platform, which: Callable[[str], str | None] = shutil.which) -> SoundPlayer` (the factory: Windows, else `aplay -q`, else `paplay`, else silent).
  - `class SoundEffects`: `__init__(self, player: SoundPlayer)`; `enabled: bool` (default `True`); `play(self, effects: Sequence[Effect]) -> None` (one sound per effect kind; the first exception from the player logs a warning under `"gui"` and switches to silent for the rest of the session); sounds are synthesised once, lazily.
- `MatchViewer` changes: `__init__` gains `sounds: SoundEffects` (injected; `MainWindow` passes `SoundEffects(choose_player())`, tests pass a recording fake player). When a refresh moves exactly one turn forward, it calls `turn_effects`, then `animator.play(...)` and `sounds.play(...)` when the duration is not 0; every other move calls `animator.cancel()` only. A sound `IconButton` (sound on / sound off) toggles `sounds.enabled`.

- [ ] **Step 1: Write the failing tests**:
  - Effects (states from `tests/builders.py`): `test_shot_effect_has_bullet_cells`, `test_new_trap_is_placed_effect`, `test_existing_trap_is_not_placed_again`, `test_hit_trapped_and_delivered_effects`, `test_quiet_turn_has_no_effects`, `test_effects_are_in_fixed_order`.
  - Sounds: `test_every_effect_has_a_valid_wav` (open with `wave`: 1 channel, 2 bytes, `SAMPLE_RATE`, under 0.4 s), `test_choose_player_on_windows`, `test_choose_player_uses_aplay_when_present`, `test_choose_player_falls_back_to_silent` (`which` returns `None`), `test_failing_player_is_disabled_silently` (a player that raises: no exception, one warning in `assertLogs("arena.gui", "WARNING")`, the next `play` does not call it), `test_muted_effects_play_nothing`, `test_one_sound_per_kind`.
  - Animations (hidden root): `test_duration_follows_speed`, `test_animation_draws_and_then_clears` (after `play` items tagged `"effect"` exist; pump `root.update()` for 0.5 s; none left), `test_new_play_cancels_previous`.
  - Viewer: `test_step_forward_plays_effects` (a turn with a shot: the fake player received one sound), `test_jump_plays_no_effects` (`jump` over 10 turns: no sounds, no `"effect"` items), `test_sound_button_mutes`.
- [ ] **Step 2: Run**; expected: import errors.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the whole suite; expected: pass. By hand: watch a duel and check that shots, traps and hits look and sound right at speeds 1, 5 and 20.
- [ ] **Step 5: Commit point C**: `animate shots and traps and play sounds`

---

### Task 6: Match session, Play tab, main window and start-up

**Files:**
- Create: `src/arena/gui/match_session.py`, `src/arena/gui/play_tab.py`, `src/arena/gui/main_window.py`
- Modify: `src/main.py` (decision 5), `docs/specs/01-bot-arena-design.md` (7.1: `main.py` opens the window; `play` stays)
- Test: `tests/test_match_session.py`, `tests/test_play_tab.py`, `tests/test_main_window.py`, `tests/test_application.py` (extend; it already tests the command line)

**Interfaces:**
- Produces:
  - `class MatchSession` (no tkinter): `__init__(self, application: Application)`; `start(self, mode: ModeKind, blue: BotSource, red: BotSource | None, seed: int) -> None` (raises `RuntimeError` if a match is running; builds the runner with `application.create_match(..., observers=[QueueObserver(self._events)])` and calls `run_in_background(seed)`); `stop(self) -> None`; `poll(self, limit: int = 50) -> list[MatchEvent]` (non-blocking `get_nowait` loop); property `is_running: bool` (thread alive or events still queued).
  - `parse_seed(text: str) -> int` in `play_tab.py`: pure, doctest, raises `ValueError` with a readable message outside `0..2**63 - 1` or for non-numbers (spaces trimmed).
  - `class PlayTab(ttk.Frame)`: `__init__(self, master: tk.Misc, list_bots: Callable[[], list[BotSource]], on_start: Callable[[ModeKind, BotSource, BotSource | None, int], None], on_stop: Callable[[], None])` (callbacks injected; the tab knows nothing about sessions); `refresh_bots()`; `set_running(running: bool)` (Start disabled and Stop enabled while running); `show_error(message: str)`; the Red drop-down is disabled in Solo. Defaults: Blue `Medium`, Red `Easy`.
  - `class MainWindow`: `__init__(self, root: tk.Tk, application: Application)`; builds a `ttk.Notebook` with the tabs Play, Match Viewer, History (Task 7 adds the last); polls the session every 50 ms with `root.after`; dispatches `MatchStarted` → `viewer.start_live` and selects the viewer tab, `TurnPlayed` → `viewer.add_turn` (only while the viewer is live), `MatchFinished` → `viewer.finish_live`, history refresh, `set_running(False)`, `MatchFailed` → `play_tab.show_error`, `messagebox.showerror`, `set_running(False)`; `close()` implements decision 8 and is bound to `WM_DELETE_WINDOW`. Window title `"Bot Arena"`, minimum size 1000×650.
  - `src/main.py`: `run_window(application: Application) -> int` creates `tk.Tk()`, `MainWindow`, runs `mainloop()`; `main` dispatches `gui` (also the default) and `play`.

- [ ] **Step 1: Write the failing tests**:
  - Session (`Application` with in-memory repository and the short rules): `test_session_plays_a_match_and_reports_events` (poll until `MatchFinished`, at most 20 s; first event `MatchStarted`), `test_second_start_while_running_is_refused`, `test_stop_ends_the_match`, `test_poll_takes_at_most_fifty_events` (put 120 events into the queue directly: three polls return 50, 50, 20), `test_failed_match_reports_error` (a broken user file → `MatchFailed`).
  - `parse_seed`: `test_seed_accepts_numbers_with_spaces`, `test_seed_rejects_text_negative_and_too_large`.
  - Play tab (hidden root, fake callbacks): `test_start_calls_back_with_choices`, `test_solo_disables_red`, `test_invalid_seed_shows_error_and_does_not_start`, `test_running_disables_start`, `test_new_user_bot_appears_after_refresh`.
  - Main window (hidden root, real session, short rules): `test_started_match_opens_viewer_and_finishes` (pump `root.update()` until the Play tab's Start is enabled again, at most 20 s; one match in the repository), `test_failed_match_reports_error_and_enables_start` (patch `messagebox.showerror`), `test_closing_during_a_match_stops_it_and_destroys_the_root` (Hard vs Hard with `duel_max_turns=200`; `close()` then pump until the root no longer exists, at most 12 s; nothing saved).
  - Command line: `test_no_command_means_window`, `test_window_command_accepts_log_level` (both via `parse_arguments`).
- [ ] **Step 2: Run**; expected: import errors.
- [ ] **Step 3: Implement**; update the module docstring of `src/main.py` and the spec line.
- [ ] **Step 4: Run** the whole suite; expected: pass. Start the window by hand (`../venv/Scripts/python src/main.py`), play Hard vs Medium and a solo match, and check live viewing, rewinding and Stop.
- [ ] **Step 5: Commit point D**: `open a window to start matches and watch them live`

---

### Task 7: History tab

**Files:**
- Create: `src/arena/gui/history_table.py`, `src/arena/gui/history_tab.py`
- Modify: `src/arena/gui/main_window.py` (add the tab, wire opening and deleting)
- Test: `tests/test_history_table.py`, `tests/test_history_tab.py`

**Interfaces:**
- Produces:
  - In `history_table.py` (pure, no tkinter): `COLUMNS: Final = ("date", "mode", "blue", "red", "seed", "result", "turns")`; `history_row(summary: MatchSummary) -> tuple[str, ...]` (date as `"2026-11-11 14:05"`, mode `"Duel"`/`"Solo"`, red `"-"` in solo, `result_text`); `sort_summaries(summaries: Sequence[MatchSummary], column: str, descending: bool) -> list[MatchSummary]` (typed keys: `played_at`, `seed`, `turns` numeric, others by text); `filter_summaries(summaries, mode: ModeKind | None, bot: str | None) -> list[MatchSummary]`; `bot_names(summaries) -> list[str]` (sorted, unique); `solo_record_row(record: SoloRecord) -> tuple[str, ...]`.
  - `class HistoryTab(ttk.Frame)`: `__init__(self, master: tk.Misc, repository: MatchRepository, on_open: Callable[[RecordedMatch], None], on_delete: Callable[[int], None])`; `refresh()` reloads from the repository keeping sort and filters; header click sorts (second click reverses); filters "All modes/Duel/Solo" and "All bots/<names>"; double-click loads with `repository.load_match` and calls `on_open`; "Delete match" asks `messagebox.askyesno`, deletes, calls `on_delete(match_id)`, refreshes; a second `Treeview` "Solo records" (Seed, Best turns, Bot, Date).
  - `MainWindow`: `on_open` → `viewer.show_recorded` and select the viewer tab; `on_delete(match_id)` → `viewer.clear()` if `viewer.match_id == match_id`; the history refreshes when its tab is selected and after every finished match.

- [ ] **Step 1: Write the failing tests**:
  - Table: `test_row_for_duel_and_solo`, `test_sort_by_seed_is_numeric`, `test_sort_by_date_is_chronological`, `test_descending_reverses`, `test_filter_by_mode_and_bot` (a bot matches on either side), `test_bot_names_are_unique_and_sorted`.
  - Tab (hidden root, in-memory repository with matches from `tests/recorded.py`): `test_lists_all_matches`, `test_double_click_opens_match` (call the handler with the first row selected), `test_delete_removes_selected_match` (patch `askyesno` → `True`), `test_delete_without_selection_does_nothing`, `test_shows_solo_records`.
  - Main window: `test_deleting_the_open_match_clears_the_viewer`.
- [ ] **Step 2: Run**; expected: import errors.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** the whole suite; expected: pass. By hand: play two matches, sort, filter, open one, delete one.
- [ ] **Step 5: Commit point E**: `browse, replay and delete past matches`
- [ ] **Step 6:** Final review (reviewer agent on the whole plan), fix pass with a failing test per fix, update `../docs/notes/status.md` and `../docs/ai-contributions.md`, push after asking the user.
