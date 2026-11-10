# Game Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure-Python game engine that generates fair maps and resolves Bot Arena turns exactly as the spec describes, with no GUI, no bot processes and no storage.

**Architecture:** Immutable value objects in `arena.model` (positions, actions, map, state). `arena.rules` holds every game number behind validated descriptors. `arena.map_generator` builds a 180°-symmetric map from a seed. `arena.engine.turn` is one pure function `resolve_turn(state, actions, rules) -> GameState`; `arena.engine.modes` wraps it in the `GameMode` ABC with `Duel` and `Solo`.

**Tech Stack:** Python 3.10 standard library only (`dataclasses`, `enum`, `abc`, `random`, `collections`, `typing`); `unittest` + `doctest`.

**Spec:** `docs/specs/01-bot-arena-design.md` (sections 4, 6.2, 7.3, 7.5, 7.6, 7.8).

## Global Constraints

- Python 3.10; no 3.11+ features. Standard library only.
- Everything in English. Rules in `CLAUDE.md`, `.claude/rules/python.md`, `.claude/rules/tests.md` apply to every task.
- Value objects are `@dataclass(frozen=True)`; the engine never mutates a state, it builds a new one.
- `arena.model`, `arena.rules`, `arena.map_generator` and `arena.engine` never import anything from `gui`, `runtime` or `storage`.
- Every game number comes from `Rules` (never a literal in engine code): grid 20, walls 15%, 8 crystal pairs (16 crystals), carry 3, bullet range 5, shoot cooldown 5, stun 2, traps 3 / trap lifetime 5 / stuck 3, duel 200 turns, solo 300 turns, turn limit 100 ms, kill timeout 2000 ms.
- Run a single test file: `../venv/Scripts/python -m unittest discover -s tests -p "test_<name>.py" -v` (from `Projekt/`).
- Every commit point: run the `verify` skill (all gates must pass), then commit with a lowercase plain-language message (no file or code names). The `reviewer` agent runs once, when the whole plan is finished.

## Decisions this plan makes (spec is silent)

These are implementation choices; they are listed here so the user can veto them before work starts.

1. **Counter timing.** At the start of `resolve_turn`, a bot is *disabled* if `stunned_turns > 0` or `trapped_turns > 0`, and it *may shoot* only if `shoot_cooldown == 0`; then these three counters each drop by 1 (not below 0). Effect: a hit in turn *t* (stun 2) makes the bot skip turns *t+1* and *t+2*; a shot in turn *t* (cooldown 5) allows the next shot in turn *t+6*.
2. **Trap lifetime** counts down at the *end* of each turn, starting the turn it is placed; at 0 the trap is removed and returned to its owner (`free_traps + 1`). A trap placed in turn *t* is live for the moves of turns *t … t+4* (5 turns).
3. **Disabled bots do not pick up or deliver crystals.** A hit bot's crystals scatter onto the nearest free cells around it (decided with the user after the plan was done; spec 4.2 and 4.4 updated), so the other bot can collect them while it is stunned.
4. **Stun and trap do not stack:** a new stun sets `stunned_turns = max(current, stun_turns)`, same for traps; a bot is disabled while either is positive, so the longer one applies (spec 4.7 minor rules).
5. **Refused actions become `wait`** and add an `ACTION_REFUSED` event with a reason: shooting during cooldown, placing a trap with no free trap, on a base, or on a cell that already has a trap; in Solo, any shoot or trap.
6. **Solo crystals** are those of a generated duel map whose cell is closer (Manhattan) to the Blue base than to the Red base. The generator never puts a crystal on the anti-diagonal (`x + y == size - 1`), so exactly one crystal of every pair qualifies: 8 crystals.
7. **Bot view.** `BotState.me` is the bot's full `PlayerState`; its active traps are in `BotState.my_traps`; the opponent is an `OpponentView` without any trap information (not even `free_traps`). All events of the previous turn are visible to both bots.

## Review Focus

1. A bot hit while standing on crystals must not pick its dropped crystals back up while stunned; the opponent can take them. → Task 7, `test_hit_bot_does_not_repick_dropped_crystals`.
2. Bullet range edge: a target exactly 5 cells away is hit, 6 cells away is not; a bullet reaching the map edge stops without error. → Task 7, `test_range_is_exactly_five_cells`, `test_bullet_stops_at_map_edge`.
3. Chained move conflict: Blue moves into Red's cell while Red tries to move into a wall, so Red stays and Blue must be blocked too. → Task 6, `test_cannot_follow_opponent_that_stays`.
4. A full bot (3 crystals) walking over crystals leaves them on the ground; a bot reaching its base delivers in the same turn. → Task 6, `test_full_bot_leaves_crystals`, `test_delivery_on_arrival_at_base`.
5. A trap placed this turn catches an opponent who steps on that cell in the same turn; the 4th simultaneous trap is refused; an expired trap returns to its owner after exactly 5 turns. → Task 8.

---

### Task 1: Rules configuration with validated descriptors

**Files:**
- Create: `src/arena/errors.py`, `src/arena/rules.py`
- Test: `tests/test_rules.py`
- Also commit the pending one-line change in `CLAUDE.md`.

**Interfaces:**
- Produces:
  - `class ArenaError(Exception)`; `class RulesError(ArenaError)` in `arena.errors`.
  - `class Bounded` (data descriptor): `__init__(self, minimum: int, maximum: int)`, `__set_name__`, `__get__` (overloaded: class access returns the descriptor, instance access returns `int`), `__set__(self, instance: object, value: int) -> None` raising `RulesError` when `value` is not an `int` (a `bool` is rejected) or outside `[minimum, maximum]`.
  - `class Rules` with these `Bounded` fields, defaults and bounds: `grid_size` 20 (6..50, must be even), `wall_percent` 15 (0..40), `crystal_pairs` 8 (1..40), `carry_capacity` 3 (1..10), `bullet_range` 5 (1..20), `shoot_cooldown` 5 (0..50), `stun_turns` 2 (0..20), `traps_per_bot` 3 (0..10), `trap_lifetime` 5 (1..50), `trap_stuck_turns` 3 (0..20), `duel_max_turns` 200 (1..10000), `solo_max_turns` 300 (1..10000), `turn_time_limit_ms` 100 (10..10000), `bot_kill_timeout_ms` 2000 (100..60000).
  - `Rules(**overrides: int)`: unknown names raise `RulesError`; odd `grid_size` raises `RulesError`; after `__init__` the instance is frozen (any attribute assignment raises `RulesError`).
  - `DEFAULT_RULES: Final[Rules] = Rules()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_rules.py`

```python
class RulesTest(unittest.TestCase):
    def test_defaults_match_spec(self) -> None:
        rules = Rules()
        self.assertEqual(
            (rules.grid_size, rules.wall_percent, rules.crystal_pairs,
             rules.carry_capacity, rules.bullet_range, rules.shoot_cooldown,
             rules.stun_turns, rules.traps_per_bot, rules.trap_lifetime,
             rules.trap_stuck_turns, rules.duel_max_turns,
             rules.solo_max_turns, rules.turn_time_limit_ms,
             rules.bot_kill_timeout_ms),
            (20, 15, 8, 3, 5, 5, 2, 3, 5, 3, 200, 300, 100, 2000),
        )

    def test_override_within_bounds(self) -> None:
        self.assertEqual(Rules(bullet_range=7).bullet_range, 7)

    def test_value_outside_bounds_is_rejected(self) -> None:
        for name, value in [("bullet_range", 0), ("wall_percent", 41)]:
            with self.subTest(name=name), self.assertRaises(RulesError):
                Rules(**{name: value})

    def test_non_integer_is_rejected(self) -> None:
        with self.assertRaises(RulesError):
            Rules(carry_capacity=True)

    def test_odd_grid_size_is_rejected(self) -> None:
        with self.assertRaises(RulesError):
            Rules(grid_size=7)

    def test_unknown_rule_is_rejected(self) -> None:
        with self.assertRaises(RulesError):
            Rules(bullet_speed=3)

    def test_rules_are_frozen_after_creation(self) -> None:
        with self.assertRaises(RulesError):
            Rules().bullet_range = 3
```

- [ ] **Step 2: Run** the file; expected: `ModuleNotFoundError: No module named 'arena.rules'`.
- [ ] **Step 3: Implement** `arena/errors.py` and `arena/rules.py`. `Bounded` stores the value in the instance `__dict__` under the name from `__set_name__`. Add a doctest to `Bounded` showing a rejected value. `Rules.__init__` applies class-level defaults (a `ClassVar[dict[str, int]]` of defaults) then overrides, then sets a private frozen flag that `__setattr__` checks.
- [ ] **Step 4: Run** the file; expected: all pass. Run the whole suite.
- [ ] **Step 5: Commit point A** (verify, commit): `add game rules configuration`

---

### Task 2: Sides and actions

**Files:**
- Create: `src/arena/model/side.py`, `src/arena/model/actions.py`
- Modify: `src/arena/errors.py` (add `InvalidActionError(ArenaError)`)
- Test: `tests/test_actions.py`

**Interfaces:**
- Consumes: `Direction` from `arena.model.geometry`.
- Produces:
  - `class Side(Enum)`: `BLUE = "blue"`, `RED = "red"`; property `opponent -> Side`.
  - `class ActionKind(Enum)`: `MOVE`, `SHOOT`, `TRAP`, `WAIT`.
  - `MAX_MESSAGE_LENGTH: Final = 200`.
  - `@dataclass(frozen=True) class Action`: `kind: ActionKind`, `direction: Direction | None = None`, `message: str = ""`. Class methods `move(direction, message="")`, `shoot(direction, message="")`, `trap(message="")`, `wait(message="")`. `__post_init__` raises `InvalidActionError` if MOVE/SHOOT has no direction or TRAP/WAIT has one, or if `message` is not a `str`; messages longer than `MAX_MESSAGE_LENGTH` are cut to that length.

- [ ] **Step 1: Write the failing tests**

```python
def test_opponent_of_blue_is_red(self) -> None:
    self.assertIs(Side.BLUE.opponent, Side.RED)
    self.assertIs(Side.RED.opponent, Side.BLUE)

def test_factories_build_matching_kind(self) -> None:
    self.assertEqual(Action.move(Direction.UP).kind, ActionKind.MOVE)
    self.assertEqual(Action.shoot(Direction.LEFT).direction, Direction.LEFT)
    self.assertEqual(Action.trap().kind, ActionKind.TRAP)
    self.assertEqual(Action.wait("idle").message, "idle")

def test_move_without_direction_is_invalid(self) -> None:
    with self.assertRaises(InvalidActionError):
        Action(ActionKind.MOVE)

def test_wait_with_direction_is_invalid(self) -> None:
    with self.assertRaises(InvalidActionError):
        Action(ActionKind.WAIT, Direction.UP)

def test_long_message_is_truncated(self) -> None:
    self.assertEqual(len(Action.wait("x" * 500).message), 200)
```

- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** both modules, with doctests on `Side.opponent` and `Action.move`.
- [ ] **Step 4: Run**; expected: pass.

---

### Task 3: Map, player state, events, game state and bot view

**Files:**
- Create: `src/arena/model/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `Position`, `Side`, `Action`.
- Produces (all `@dataclass(frozen=True)` unless noted):
  - `class ModeKind(Enum)`: `DUEL = "duel"`, `SOLO = "solo"`.
  - `GameMap`: `size: int`, `walls: frozenset[Position]`, `bases: Mapping[Side, Position]`; methods `is_walkable(position) -> bool` (inside the grid and not a wall), `base_of(side) -> Position`.
  - `Trap`: `owner: Side`, `position: Position`, `turns_left: int`.
  - `PlayerState`: `side: Side`, `position: Position`, `carrying: int = 0`, `delivered: int = 0`, `shoot_cooldown: int = 0`, `stunned_turns: int = 0`, `trapped_turns: int = 0`, `free_traps: int = 0`; property `is_disabled -> bool`.
  - `OpponentView`: same fields as `PlayerState` except `free_traps`; class method `of(player: PlayerState) -> OpponentView`.
  - `class EventKind(Enum)`: `HIT`, `CRYSTALS_DROPPED`, `TRAPPED`, `DELIVERED`, `ACTION_REFUSED`.
  - `Event`: `kind: EventKind`, `side: Side` (the bot the event happened to), `position: Position`, `amount: int = 0`, `reason: str = ""`.
  - `GameState`: `mode: ModeKind`, `turn: int`, `max_turns: int`, `map: GameMap`, `crystals: Mapping[Position, int]` (cells with ≥1 crystal only), `players: Mapping[Side, PlayerState]`, `traps: tuple[Trap, ...] = ()` (live traps on the map), `spent_traps: tuple[Trap, ...] = ()` (triggered traps still counting down until they return to their owner), `events: tuple[Event, ...] = ()`. Method `player(side) -> PlayerState`. Properties `crystals_left -> int` (on the ground plus carried) and `is_finished -> bool` (`turn >= max_turns or crystals_left == 0`).
  - `BotState`: `turn`, `max_turns`, `mode`, `map`, `crystals`, `me: PlayerState`, `my_traps: tuple[Trap, ...]`, `opponent: OpponentView | None`, `events: tuple[Event, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_walls_and_outside_are_not_walkable(self) -> None:
    game_map = GameMap(6, frozenset({Position(2, 2)}), BASES)
    self.assertFalse(game_map.is_walkable(Position(2, 2)))
    self.assertFalse(game_map.is_walkable(Position(6, 0)))
    self.assertTrue(game_map.is_walkable(Position(1, 1)))

def test_player_is_disabled_when_stunned_or_trapped(self) -> None:
    base = PlayerState(Side.BLUE, Position(0, 0))
    self.assertFalse(base.is_disabled)
    self.assertTrue(replace(base, stunned_turns=1).is_disabled)
    self.assertTrue(replace(base, trapped_turns=2).is_disabled)

def test_opponent_view_hides_free_traps(self) -> None:
    view = OpponentView.of(PlayerState(Side.RED, Position(5, 5), free_traps=2))
    self.assertFalse(hasattr(view, "free_traps"))

def test_crystals_left_counts_ground_and_carried(self) -> None:
    state = make_game_state(crystals={Position(1, 1): 2}, blue_carrying=1)
    self.assertEqual(state.crystals_left, 3)

def test_finished_when_turn_limit_reached_or_no_crystals(self) -> None:
    self.assertTrue(make_game_state(turn=200, max_turns=200).is_finished)
    self.assertTrue(make_game_state(crystals={}).is_finished)
    self.assertFalse(make_game_state(turn=10).is_finished)
```

`BASES` and `make_game_state(...)` are small module-level helpers inside the test file (6×6 map, bases at `(0, 0)` and `(5, 5)`, one crystal by default).

- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** `arena/model/state.py` with doctests on `GameMap.is_walkable`.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point B**: `add game state and actions`

---

### Task 4: Shortest-path distances

**Files:**
- Create: `src/arena/map_generator/__init__.py`, `src/arena/map_generator/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Consumes: `GameMap`, `Position`, `Direction`.
- Produces: `bfs_distances(game_map: GameMap, start: Position) -> dict[Position, int]` (walkable cells reachable from `start` mapped to their step count; `start` maps to 0; walls are never entered; bases are walkable).

- [ ] **Step 1: Write the failing tests**: `test_start_has_distance_zero`, `test_open_grid_distance_is_manhattan` (6×6 without walls: `(5, 5)` is 10), `test_walls_force_a_detour` (a wall row with one gap makes the far cell's distance larger than Manhattan, exact value asserted), `test_enclosed_cell_is_unreachable` (absent from the result).
- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** with `collections.deque`; iterate `Direction` in enum order so results are deterministic.
- [ ] **Step 4: Run**; expected: pass.

---

### Task 5: Symmetric map generator

**Files:**
- Create: `src/arena/map_generator/generator.py`
- Modify: `src/arena/errors.py` (add `MapGenerationError(ArenaError)`)
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: `Rules`, `GameMap`, `Side`, `bfs_distances`, `Position.rotated`.
- Produces:
  - `MAX_ATTEMPTS: Final = 100`.
  - `generate(seed: int, rules: Rules) -> tuple[GameMap, dict[Position, int]]`: the map and its crystals (each crystal cell holds 1).
  - `solo_crystals(game_map: GameMap, crystals: Mapping[Position, int]) -> dict[Position, int]`: the crystals closer (Manhattan) to the Blue base.

Algorithm (fixed by this plan so results are reproducible): one `random.Random(seed)` for the whole call. Each attempt: (1) protected cells = each base and its 8 neighbours inside the grid; (2) target wall count = `size * size * wall_percent // 100` rounded down to even; add walls in pairs (`cell`, `cell.rotated(size)`) choosing `cell` uniformly from unprotected empty cells until the target is reached; (3) add `crystal_pairs` crystal pairs the same way from cells that are not walls, not bases, not already crystals and not on the anti-diagonal (`x + y == size - 1`); (4) accept if the Red base and every crystal are in `bfs_distances(map, blue_base)`, otherwise start the next attempt with the same `Random`. After `MAX_ATTEMPTS` failures raise `MapGenerationError`.

- [ ] **Step 1: Write the failing tests**

```python
def test_same_seed_gives_same_map(self) -> None:
    self.assertEqual(generate(42, Rules()), generate(42, Rules()))

def test_different_seeds_give_different_maps(self) -> None:
    self.assertNotEqual(generate(1, Rules())[0].walls,
                        generate(2, Rules())[0].walls)

def test_map_is_rotationally_symmetric(self) -> None:
    for seed in range(20):
        game_map, crystals = generate(seed, Rules())
        with self.subTest(seed=seed):
            for wall in game_map.walls:
                self.assertIn(wall.rotated(20), game_map.walls)
            for cell in crystals:
                self.assertIn(cell.rotated(20), crystals)

def test_counts_match_rules(self) -> None:
    game_map, crystals = generate(7, Rules())
    self.assertEqual(len(game_map.walls), 60)   # 15 % of 400
    self.assertEqual(sum(crystals.values()), 16)

def test_bases_and_their_neighbours_are_free(self) -> None:
    game_map, _ = generate(3, Rules())
    for cell in [Position(0, 0), Position(1, 0), Position(0, 1),
                 Position(1, 1), Position(19, 19), Position(18, 18)]:
        self.assertNotIn(cell, game_map.walls)

def test_every_crystal_reachable_from_both_bases(self) -> None: ...
    # for 20 seeds: every crystal in bfs_distances from each base

def test_both_bases_have_equal_path_lengths(self) -> None: ...
    # for 20 seeds: sorted distances from Blue to all crystals ==
    # sorted distances from Red to all crystals

def test_solo_keeps_exactly_eight_crystals_on_blue_half(self) -> None: ...
    # sum == 8 and every cell has x + y < 19

def test_impossible_rules_raise(self) -> None:
    with self.assertRaises(MapGenerationError):
        generate(0, Rules(grid_size=6, wall_percent=40, crystal_pairs=10))
```

- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** `generate` and `solo_crystals`, split into small private helpers (protected cells, place pairs, is valid). Doctest on `solo_crystals` with a 2-crystal input.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point C**: `add fair map generator`

---

### Task 6: Turn resolution: counters, moves and crystals

**Files:**
- Create: `src/arena/engine/__init__.py`, `src/arena/engine/turn.py`, `tests/builders.py`
- Test: `tests/test_turn_moves.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces:
  - `resolve_turn(state: GameState, actions: Mapping[Side, Action], rules: Rules) -> GameState`. A side missing from `actions` waits. Returns a new state with `turn + 1` and this turn's `events`. This task implements resolution steps 0, 1, 3 and 6 below; Tasks 7 and 8 fill in 2, 4 and 5 (leave clearly named private functions for them).
  - Order (spec 4.2 plus decisions 1–3): **0** note who is disabled / may shoot, then decrement `stunned_turns`, `trapped_turns`, `shoot_cooldown`; **1** disabled bots wait; **2** trap placement; **3** moves; **4** trap triggers; **5** shooting; **6** crystals (pick up, then deliver; disabled bots skip); **7** trap lifetimes tick down, expired traps return to owners; **8** `turn + 1`.
  - Move rules: a target outside the grid or on a wall → stay. Same target → both stay. Swap → both stay. Moving into the opponent's cell is allowed only if the opponent actually leaves it this turn (resolve the opponent's move first).
  - Delivery adds a `DELIVERED` event with `amount`.
  - `tests/builders.py`: `make_state(rows: Sequence[str], *, max_turns: int = 200, rules: Rules = ...) -> GameState` builds a square map from strings: `#` wall, `B` Blue bot, `R` Red bot, `*` one crystal, `2`–`9` that many crystals, `.` empty. Bases are always at `(0, 0)` and `(n-1, n-1)`; a bot letter may stand anywhere; mode is `SOLO` when there is no `R`. Bots start with `free_traps = rules.traps_per_bot`. Also `with_player(state, side, **changes) -> GameState`. Used with `Rules(grid_size=6)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_turn_moves.py`

```python
def test_move_to_empty_cell(self) -> None
def test_move_into_wall_keeps_position(self) -> None
def test_move_off_map_keeps_position(self) -> None
def test_same_target_both_stay(self) -> None
def test_swap_both_stay(self) -> None
def test_can_follow_opponent_that_leaves(self) -> None
def test_cannot_follow_opponent_that_stays(self) -> None   # Review Focus 3
def test_picks_up_crystals_up_to_capacity(self) -> None    # cell "5", carries 0 -> carries 3, 2 left
def test_full_bot_leaves_crystals(self) -> None            # Review Focus 4
def test_delivery_on_arrival_at_base(self) -> None         # carrying 2 -> delivered 2, DELIVERED event
def test_disabled_bot_ignores_action_and_counter_drops(self) -> None
def test_stunned_two_turns_skips_exactly_two_turns(self) -> None  # decision 1
def test_disabled_bot_does_not_pick_up(self) -> None       # decision 3
def test_turn_number_increases(self) -> None
```

Each test builds a 6×6 map with `make_state`, calls `resolve_turn` once (or in a loop for the counter test) and asserts exact positions, counts and events. Example:

```python
def test_cannot_follow_opponent_that_stays(self) -> None:
    state = make_state(["......",
                        "..BR#.",
                        "......",
                        "......",
                        "......",
                        "......"])
    after = resolve_turn(state, {Side.BLUE: Action.move(Direction.RIGHT),
                                 Side.RED: Action.move(Direction.RIGHT)},
                         RULES)
    self.assertEqual(after.player(Side.BLUE).position, Position(2, 1))
    self.assertEqual(after.player(Side.RED).position, Position(3, 1))
```

- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** `resolve_turn` as a short pipeline of private step functions working on a dict of `PlayerState` updated with `dataclasses.replace`, plus a list of events.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point D**: `resolve moves and crystal pickup`

---

### Task 7: Shooting

**Files:**
- Modify: `src/arena/engine/turn.py`
- Test: `tests/test_turn_shooting.py`

**Interfaces:**
- Produces: resolution step 5. A shooter that is not disabled and had `shoot_cooldown == 0` at step 0 fires; its cooldown becomes `rules.shoot_cooldown`. A shooter that may not fire waits with `ACTION_REFUSED` (`reason="cooldown"`). The bullet path is the up to `bullet_range` cells after the shooter's cell in the direction, stopping before a wall or the map edge. If the opponent's *post-move* position is on the path: `HIT` event, the opponent's carried crystals are added to its cell (`CRYSTALS_DROPPED` event with `amount`, only if it carried any), `carrying = 0`, `stunned_turns = max(current, rules.stun_turns)`. Both shots are computed from post-move positions before either is applied.
- Also add a pure helper with a doctest: `bullet_path(game_map: GameMap, start: Position, direction: Direction, bullet_range: int) -> list[Position]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_hit_in_straight_line(self) -> None
def test_wall_blocks_bullet(self) -> None
def test_range_is_exactly_five_cells(self) -> None   # 5 away: hit; 6 away: miss (10x10 rules)
def test_bullet_stops_at_map_edge(self) -> None
def test_hit_uses_position_after_moves(self) -> None # target steps into the line -> hit; steps out -> miss
def test_shooter_does_not_move(self) -> None
def test_hit_drops_carried_crystals_and_stuns(self) -> None  # carrying 3 -> cell has 3, stunned 2
def test_hit_bot_does_not_repick_dropped_crystals(self) -> None  # Review Focus 1
def test_opponent_can_take_dropped_crystals(self) -> None
def test_cooldown_blocks_next_five_turns(self) -> None  # shot at t: refused t+1..t+5, allowed t+6
def test_both_bots_shoot_each_other(self) -> None
def test_stun_does_not_stack(self) -> None           # stunned 2 + hit again -> still 2
```

- [ ] **Step 2: Run**; expected: failures (shooting not resolved).
- [ ] **Step 3: Implement** step 5 and `bullet_path`.
- [ ] **Step 4: Run**; expected: pass.

---

### Task 8: Traps

**Files:**
- Modify: `src/arena/engine/turn.py`
- Test: `tests/test_turn_traps.py`

**Interfaces:**
- Produces: resolution steps 2, 4 and 7.
  - Step 2: `trap()` by a bot that is not disabled places `Trap(owner, position, rules.trap_lifetime)` and `free_traps - 1`; refused (`ACTION_REFUSED`, reasons `"no free trap"`, `"base"`, `"trap already here"`) otherwise.
  - Step 4: a bot whose position changed onto an opponent's trap: `trapped_turns = max(current, rules.trap_stuck_turns)`, `TRAPPED` event, trap removed from the map (it still returns to its owner later, see step 7). Own traps have no effect.
  - Step 7: every trap still on the map, and every triggered trap, counts down; at 0 it is gone and the owner gets `free_traps + 1`. Triggered traps move from `GameState.traps` to `GameState.spent_traps`.

- [ ] **Step 1: Write the failing tests**

```python
def test_place_trap_uses_a_free_trap(self) -> None
def test_fourth_active_trap_is_refused(self) -> None       # Review Focus 5
def test_trap_on_base_is_refused(self) -> None
def test_second_trap_on_same_cell_is_refused(self) -> None
def test_opponent_stepping_on_trap_is_stuck_three_turns(self) -> None
def test_trap_placed_this_turn_catches_opponent_this_turn(self) -> None  # Review Focus 5
def test_own_trap_does_not_affect_owner(self) -> None
def test_trap_expires_after_five_turns_and_returns(self) -> None          # Review Focus 5
def test_triggered_trap_returns_when_lifetime_ends(self) -> None
def test_trapped_and_stunned_longer_applies(self) -> None
```

- [ ] **Step 2: Run**; expected: failures.
- [ ] **Step 3: Implement** steps 2, 4 and 7.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point E**: `add shooting and traps`

---

### Task 9: Game modes (Duel and Solo)

**Files:**
- Create: `src/arena/engine/modes.py`
- Test: `tests/test_modes.py`

**Interfaces:**
- Consumes: `generate`, `solo_crystals`, `resolve_turn`, state types, `Rules`, `DEFAULT_RULES`.
- Produces:
  - `class GameMode(ABC)`: `kind: ClassVar[ModeKind]`, `sides: ClassVar[tuple[Side, ...]]`; `__init__(self, rules: Rules = DEFAULT_RULES)`; `__init_subclass__` registers every concrete subclass in a class-level registry by `kind`; `@classmethod create(cls, kind: ModeKind, rules: Rules = DEFAULT_RULES) -> GameMode` (Factory); abstract `setup_map(self, seed: int) -> GameState`, abstract `allows(self, action: Action) -> bool`, abstract `winner(self, state: GameState) -> Side | None`; concrete `state_for_bot(self, state, side) -> BotState`, `step(self, state, actions) -> GameState` (turns disallowed actions into `wait` with an `ACTION_REFUSED` event, then `resolve_turn`), `is_over(self, state) -> bool` (`state.is_finished`).
  - `class Duel(GameMode)`: both sides, max turns `rules.duel_max_turns`, all 16 crystals, all actions allowed; `winner` is the side with more delivered crystals, `None` on a draw.
  - `class Solo(GameMode)`: Blue only, max turns `rules.solo_max_turns`, `solo_crystals(...)`; shoot and trap not allowed; `winner` is `Side.BLUE` if all crystals were delivered, else `None`; extra `turns_used(self, state) -> int | None` (the turn number when finished with all crystals, else `None`).

- [ ] **Step 1: Write the failing tests**

```python
def test_create_returns_registered_mode(self) -> None:
    self.assertIsInstance(GameMode.create(ModeKind.DUEL), Duel)
    self.assertIsInstance(GameMode.create(ModeKind.SOLO), Solo)

def test_duel_setup(self) -> None:
    state = Duel().setup_map(5)
    self.assertEqual(state.player(Side.BLUE).position, Position(0, 0))
    self.assertEqual(state.player(Side.RED).position, Position(19, 19))
    self.assertEqual(state.player(Side.RED).free_traps, 3)
    self.assertEqual((state.turn, state.max_turns, state.crystals_left),
                     (0, 200, 16))

def test_solo_setup(self) -> None:
    state = Solo().setup_map(5)
    self.assertEqual(set(state.players), {Side.BLUE})
    self.assertEqual((state.max_turns, state.crystals_left), (300, 8))

def test_bot_sees_own_traps_but_not_opponents(self) -> None
def test_solo_bot_has_no_opponent(self) -> None
def test_solo_refuses_shoot_and_trap(self) -> None
def test_duel_winner_has_more_delivered(self) -> None
def test_duel_draw_has_no_winner(self) -> None
def test_duel_ends_at_turn_200(self) -> None
def test_solo_turns_used_when_all_delivered(self) -> None
def test_solo_not_finished_returns_none(self) -> None
```

- [ ] **Step 2: Run**; expected: import error.
- [ ] **Step 3: Implement** `modes.py`.
- [ ] **Step 4: Run**; expected: pass. Run the whole suite.
- [ ] **Step 5: Commit point F**: `add duel and solo game modes`
- [ ] **Step 6:** Update `../docs/notes/status.md` and `../docs/ai-contributions.md` (outside the repo) with what was built.
