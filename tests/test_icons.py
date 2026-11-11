"""Tests for the vector icons and the icon button."""

import unittest

from arena.gui.icons import (
    ICON_BOX,
    ICONS,
    IconButton,
    IconName,
    scale_polygon,
)
from gui_support import hidden_root


class IconShapeTest(unittest.TestCase):
    def test_every_icon_name_has_polygons(self) -> None:
        for name in IconName:
            with self.subTest(icon=name):
                self.assertGreater(len(ICONS[name]), 0)

    def test_polygons_fit_in_the_box(self) -> None:
        for name, polygons in ICONS.items():
            for polygon in polygons:
                with self.subTest(icon=name):
                    self.assertGreaterEqual(len(polygon), 3)
                    for x, y in polygon:
                        self.assertTrue(0 <= x <= ICON_BOX)
                        self.assertTrue(0 <= y <= ICON_BOX)

    def test_scale_polygon_doubles_at_48(self) -> None:
        polygon = ((0.0, 0.0), (12.0, 6.0), (24.0, 24.0))
        self.assertEqual(
            scale_polygon(polygon, 48),
            [0.0, 0.0, 24.0, 12.0, 48.0, 48.0],
        )


class IconButtonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[str] = []
        self.button = IconButton(
            hidden_root(self),
            IconName.PLAY,
            lambda: self.calls.append("pressed"),
            "Play",
        )

    def test_invoke_calls_the_command(self) -> None:
        self.button.invoke()
        self.assertEqual(self.calls, ["pressed"])

    def test_disabled_button_ignores_invoke(self) -> None:
        self.button.set_enabled(False)
        self.button.invoke()
        self.assertEqual(self.calls, [])
        self.button.set_enabled(True)
        self.button.invoke()
        self.assertEqual(self.calls, ["pressed"])

    def test_set_icon_redraws(self) -> None:
        self.button.set_icon(IconName.PAUSE)
        self.assertEqual(self.button.icon, IconName.PAUSE)
        shapes = self.button.find_withtag("icon")
        self.assertEqual(len(shapes), len(ICONS[IconName.PAUSE]))


if __name__ == "__main__":
    unittest.main()
