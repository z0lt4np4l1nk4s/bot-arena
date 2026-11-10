"""Medium: walks to the nearest crystal and brings it home.

It never shoots or places traps. It shows how to use the path helpers
from ``arena.api`` and how to explain each decision in the message.
"""

from arena.api import Action, BotState, Position, distances_from, next_step
from arena.bots.registry import register_builtin


@register_builtin
class MediumBot:
    """Collects the nearest crystals and delivers them when full."""

    name = "Medium"

    def decide(self, state: BotState) -> Action:
        """Go for the nearest crystal, or home when full or done."""
        me = state.me
        full = me.carrying >= state.rules.carry_capacity
        target = None if full else nearest_crystal(state)
        if target is None:
            return go_home(state)
        crystal, steps = target
        return step_towards(
            state,
            crystal,
            f"crystal at ({crystal.x}, {crystal.y}), {steps} steps",
        )


def nearest_crystal(state: BotState) -> tuple[Position, int] | None:
    """Return the closest reachable crystal cell and its distance.

    Ties are broken by row, then column, so the choice is predictable.
    Distances are measured from each crystal: crystals do not move, so
    those searches are cached for the whole match.
    """
    position = state.me.position
    reachable = [
        (steps, cell.y, cell.x, cell)
        for cell in state.crystals
        if (steps := distances_from(state.map, cell).get(position)) is not None
    ]
    if not reachable:
        return None
    steps, _, _, cell = min(reachable)
    return cell, steps


def go_home(state: BotState) -> Action:
    """Walk to the own base, or wait there."""
    me = state.me
    home = state.map.base_of(me.side)
    if me.position == home:
        return Action.wait("at home, nothing left to do")
    return step_towards(state, home, f"going home with {me.carrying}")


def step_towards(state: BotState, goal: Position, message: str) -> Action:
    """Take the first step of a shortest path to ``goal``."""
    direction = next_step(state.map, state.me.position, goal)
    if direction is None:
        return Action.wait(f"cannot reach ({goal.x}, {goal.y})")
    return Action.move(direction, message)
