"""Tests for the effect animations on the map canvas."""

import time
import tkinter as tk
import unittest

from arena.engine.modes import Duel
from arena.gui.animations import EffectAnimator, animation_duration_ms
from arena.gui.effects import Effect, EffectKind
from arena.gui.map_canvas import MapCanvas
from arena.model.geometry import Position
from arena.model.side import Side
from arena.rules import DEFAULT_RULES
from gui_support import hidden_root

EFFECTS = [
    Effect(EffectKind.SHOT, Side.BLUE, (Position(2, 1), Position(3, 1))),
    Effect(EffectKind.TRAP_PLACED, Side.RED, (Position(5, 5),)),
    Effect(EffectKind.HIT, Side.RED, (Position(3, 1),)),
    Effect(EffectKind.TRAP_TRIGGERED, Side.BLUE, (Position(6, 6),)),
    Effect(EffectKind.DELIVERED, Side.RED, (Position(19, 19),)),
]


def pump(root: tk.Tk, seconds: float) -> None:
    """Let tkinter run its timers for ``seconds``."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


class DurationTest(unittest.TestCase):
    def test_duration_follows_speed(self) -> None:
        cases = [(1000, 300), (200, 160), (100, 80), (70, 0), (50, 0)]
        for tick_ms, duration in cases:
            with self.subTest(tick_ms=tick_ms):
                self.assertEqual(animation_duration_ms(tick_ms), duration)


class EffectAnimatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = hidden_root(self)
        self.canvas = MapCanvas(self.root, DEFAULT_RULES, size=400)
        self.canvas.draw(Duel().setup_map(4))
        self.animator = EffectAnimator(self.canvas)

    def effect_items(self) -> tuple[int, ...]:
        return self.canvas.find_withtag("effect")

    def test_animation_draws_and_then_clears(self) -> None:
        self.animator.play(EFFECTS, 150)
        self.assertNotEqual(self.effect_items(), ())
        self.assertTrue(self.animator.is_running)
        pump(self.root, 0.5)
        self.assertEqual(self.effect_items(), ())
        self.assertFalse(self.animator.is_running)

    def test_new_play_cancels_previous(self) -> None:
        self.animator.play(EFFECTS, 300)
        self.animator.play(EFFECTS[:1], 300)
        shots_only = len(self.effect_items())
        self.animator.cancel()
        self.assertEqual(self.effect_items(), ())
        self.assertFalse(self.animator.is_running)
        self.assertGreater(shots_only, 0)

    def test_zero_duration_draws_nothing(self) -> None:
        self.animator.play(EFFECTS, 0)
        self.assertEqual(self.effect_items(), ())
        self.assertFalse(self.animator.is_running)


if __name__ == "__main__":
    unittest.main()
