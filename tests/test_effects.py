"""Tests for finding what to animate and sound between two turns."""

import unittest
from dataclasses import replace

from arena.gui.effects import Effect, EffectKind, turn_effects
from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import Event, EventKind, GameState, Trap
from arena.rules import Rules
from builders import make_state

RULES = Rules(grid_size=10)
EMPTY = "." * 10
# Blue at (1, 0), Red at (4, 0).
BEFORE = make_state([".B..R.....", *[EMPTY] * 9], rules=RULES)


def after(*events: Event, traps: tuple[Trap, ...] = ()) -> GameState:
    """The next turn's state with the given events and traps."""
    return replace(BEFORE, turn=1, events=events, traps=traps)


class TurnEffectsTest(unittest.TestCase):
    def test_shot_effect_has_bullet_cells(self) -> None:
        shot = Event(EventKind.SHOT, Side.BLUE, Position(3, 0))
        self.assertEqual(
            turn_effects(BEFORE, after(shot)),
            [
                Effect(
                    EffectKind.SHOT,
                    Side.BLUE,
                    (Position(1, 0), Position(2, 0), Position(3, 0)),
                )
            ],
        )

    def test_new_trap_is_placed_effect(self) -> None:
        trap = Trap(Side.RED, Position(6, 6), 25)
        self.assertEqual(
            turn_effects(BEFORE, after(traps=(trap,))),
            [Effect(EffectKind.TRAP_PLACED, Side.RED, (Position(6, 6),))],
        )

    def test_existing_trap_is_not_placed_again(self) -> None:
        trap = Trap(Side.RED, Position(6, 6), 25)
        previous = replace(BEFORE, traps=(trap,))
        older = replace(trap, turns_left=24)
        self.assertEqual(turn_effects(previous, after(traps=(older,))), [])

    def test_hit_trapped_and_delivered_effects(self) -> None:
        events = (
            Event(EventKind.HIT, Side.RED, Position(4, 0)),
            Event(EventKind.TRAPPED, Side.BLUE, Position(1, 0)),
            Event(EventKind.DELIVERED, Side.RED, Position(9, 9), amount=2),
        )
        self.assertEqual(
            [effect.kind for effect in turn_effects(BEFORE, after(*events))],
            [
                EffectKind.HIT,
                EffectKind.TRAP_TRIGGERED,
                EffectKind.DELIVERED,
            ],
        )

    def test_quiet_turn_has_no_effects(self) -> None:
        refused = Event(
            EventKind.ACTION_REFUSED, Side.BLUE, Position(1, 0), reason="x"
        )
        self.assertEqual(turn_effects(BEFORE, after(refused)), [])

    def test_effects_are_in_fixed_order(self) -> None:
        events = (
            Event(EventKind.DELIVERED, Side.RED, Position(9, 9), amount=1),
            Event(EventKind.HIT, Side.RED, Position(4, 0)),
            Event(EventKind.SHOT, Side.BLUE, Position(4, 0)),
        )
        trap = Trap(Side.BLUE, Position(7, 7), 25)
        kinds = [
            effect.kind
            for effect in turn_effects(BEFORE, after(*events, traps=(trap,)))
        ]
        self.assertEqual(
            kinds,
            [
                EffectKind.SHOT,
                EffectKind.TRAP_PLACED,
                EffectKind.HIT,
                EffectKind.DELIVERED,
            ],
        )


if __name__ == "__main__":
    unittest.main()
