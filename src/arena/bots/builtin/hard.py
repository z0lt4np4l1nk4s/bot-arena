"""Hard: collects cleverly, shoots, sets traps and avoids the opponent's.

This is the most complete example. Each turn it tries, in order:

1. **Shoot** if the opponent stands in a straight line within range and
   no wall is in the way.
2. **Set a trap** a few steps ahead on the opponent's likely path.
3. **Move** towards the best crystal (or home), avoiding the cells where
   the opponent stood recently, because it may have left a trap there.
"""

from collections import deque

from arena.api import (
    Action,
    BotState,
    Direction,
    OpponentView,
    Position,
    bullet_path,
    distance,
    distances_from,
    shortest_path,
)
from arena.bots.registry import register_builtin

# How many of the opponent's recent positions to remember and avoid.
TRAIL_LENGTH = 10
# Skip a crystal if the opponent is at least this many steps closer to it.
OPPONENT_LEAD = 2
# Which steps of the opponent's path to consider for a trap (1 = next step).
TRAP_STEPS = range(1, 4)


@register_builtin
class HardBot:
    """A bot that combines collecting, shooting and traps."""

    name = "Hard"

    def __init__(self) -> None:
        """Start with an empty memory of the opponent's positions."""
        self.opponent_trail: deque[Position] = deque(maxlen=TRAIL_LENGTH)

    def decide(self, state: BotState) -> Action:
        """Shoot, trap or move, in that order of preference."""
        opponent = state.opponent
        if opponent is not None:
            self.opponent_trail.append(opponent.position)
            shot = self.try_shooting(state, opponent)
            if shot is not None:
                return shot
            trap = self.try_trapping(state, opponent)
            if trap is not None:
                return trap
        return self.move(state)

    # ------------------------------------------------------------ shooting

    def try_shooting(
        self, state: BotState, opponent: OpponentView
    ) -> Action | None:
        """Shoot if the opponent is in a clear straight line and in range."""
        me = state.me
        if me.shoot_cooldown > 0:
            return None
        # Hitting a stunned bot that carries nothing gains nothing.
        if opponent.stunned_turns > 0 and opponent.carrying == 0:
            return None
        for direction in Direction:
            path = bullet_path(
                state.map, me.position, direction, state.rules.bullet_range
            )
            if opponent.position in path:
                return Action.shoot(
                    direction, f"opponent in line {direction.name}"
                )
        return None

    # --------------------------------------------------------------- traps

    def try_trapping(
        self, state: BotState, opponent: OpponentView
    ) -> Action | None:
        """Place a trap on the opponent's path towards its likely goal."""
        me = state.me
        if me.trap_cooldown > 0 or me.free_traps == 0:
            return None
        if opponent.stunned_turns > 0 or opponent.trapped_turns > 0:
            return None
        goal = self.opponent_goal(state, opponent)
        path = shortest_path(state.map, opponent.position, goal)
        taken = {trap.position for trap in state.my_traps}
        bases = set(state.map.bases.values())
        for index in TRAP_STEPS:
            if index >= len(path):
                break
            cell = path[index]
            far_enough = (
                distance(cell, opponent.position)
                >= state.rules.trap_min_distance
            )
            free = cell not in taken and cell not in bases
            if far_enough and free and cell != me.position:
                return Action.trap(
                    cell, f"trap at ({cell.x}, {cell.y}) on its path"
                )
        return None

    def opponent_goal(
        self, state: BotState, opponent: OpponentView
    ) -> Position:
        """Guess where the opponent is heading: a crystal or its base."""
        home = state.map.base_of(opponent.side)
        if opponent.carrying >= state.rules.carry_capacity:
            return home
        steps_to = {
            cell: steps
            for cell in state.crystals
            if (
                steps := distances_from(state.map, cell).get(opponent.position)
            )
            is not None
        }
        if not steps_to:
            return home
        return min(steps_to, key=lambda cell: (steps_to[cell], cell.y))

    # ------------------------------------------------------------- moving

    def move(self, state: BotState) -> Action:
        """Walk towards the chosen crystal, or home."""
        me = state.me
        full = me.carrying >= state.rules.carry_capacity
        target = None if full else self.best_crystal(state)
        if target is None:
            home = state.map.base_of(me.side)
            if me.position == home:
                return Action.wait("at home")
            return self.step_towards(
                state, home, f"going home with {me.carrying}"
            )
        return self.step_towards(
            state, target, f"best crystal at ({target.x}, {target.y})"
        )

    def best_crystal(self, state: BotState) -> Position | None:
        """Pick the crystal with the most crystals per step of walking.

        Crystals the opponent will clearly reach first are skipped.
        """
        opponent = state.opponent
        best: tuple[float, int, int, int, Position] | None = None
        for cell, count in state.crystals.items():
            # Measured from the crystal: cached for the whole match.
            from_crystal = distances_from(state.map, cell)
            steps = from_crystal.get(state.me.position)
            if steps is None:
                continue
            if opponent is not None:
                their_steps = from_crystal.get(opponent.position)
                if (
                    their_steps is not None
                    and their_steps + OPPONENT_LEAD <= steps
                ):
                    continue
            score = count / (steps + 1)
            candidate = (-score, steps, cell.y, cell.x, cell)
            if best is None or candidate < best:
                best = candidate
        return None if best is None else best[-1]

    def step_towards(
        self, state: BotState, goal: Position, message: str
    ) -> Action:
        """Take a shortest-path step, avoiding suspicious cells if possible.

        Among the neighbours that bring the bot one step closer, a cell
        the opponent did not recently stand on is preferred.
        """
        me = state.me
        to_goal = distances_from(state.map, goal)
        if me.position not in to_goal:
            return Action.wait(f"cannot reach ({goal.x}, {goal.y})")
        closer = [
            direction
            for direction in Direction
            if to_goal.get(me.position.moved(direction))
            == to_goal[me.position] - 1
        ]
        if not closer:
            return Action.wait("already there")
        safe = [
            direction
            for direction in closer
            if me.position.moved(direction) not in self.opponent_trail
        ]
        return Action.move((safe or closer)[0], message)
