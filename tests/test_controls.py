"""The controls around the picture are flat: icons and text on the window's own background.

No panel behind the buttons, no filled box when a toggle is on, no border lines.
"""

import unittest
from unittest import mock

from support import pixel, qapp

from PySide6.QtCore import QPoint

from app import adb, settings, tasks


class ControlsAreFlat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qapp()
        tasks.init()
        # system boundaries: no phone attached, a fresh settings file that never gets written
        cls._patches = [mock.patch.object(adb, "devices", return_value=[]),
                        mock.patch.object(settings, "load", return_value=dict(settings.DEFAULTS)),
                        mock.patch.object(settings, "save")]
        for p in cls._patches:
            p.start()
        from app.main import MainWindow
        cls.win = MainWindow()
        cls.win.resize(460, 900)
        cls.win.b_mouse.setChecked(True)       # one toggle on ...
        cls.win.b_sound.setChecked(False)      # ... and one off
        cls.shot = cls.win.grab().toImage()
        cls.background = pixel(cls.shot, 3, 3)  # an empty corner of the window

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        for p in cls._patches:
            p.stop()

    def at(self, widget, x, y):
        pos = widget.mapTo(self.win, QPoint(x, y))
        return pixel(self.shot, pos.x(), pos.y())

    def assert_background(self, widget, x, y, what):
        self.assertEqual(self.at(widget, x, y), self.background, what)

    def test_buttons_have_no_box_when_off(self):
        b = self.win.b_sound
        self.assert_background(b, 2, 2, "a box shows behind a switched-off button")

    def test_buttons_have_no_box_when_on(self):
        b = self.win.b_mouse
        self.assert_background(b, 2, 2, "a filled box shows behind a switched-on button")
        self.assert_background(b, b.width() - 3, b.height() - 3, "a filled box shows behind a switched-on button")

    def test_button_column_has_no_panel_or_border(self):
        dock = self.win.sidebar
        self.assert_background(dock, 0, dock.height() // 2, "a border line runs down the button column")
        self.assert_background(dock, dock.width() // 2, 2, "a panel sits behind the buttons")

    def test_phone_name_has_no_box(self):
        pill = self.win.pill
        self.assert_background(pill, 1, 1, "the phone name sits in a box")
        self.assert_background(pill, 0, pill.height() // 2, "the phone name has a border")

    def test_bottom_bar_has_no_border(self):
        bar = self.win.statusbar
        self.assert_background(bar, bar.width() // 2, 0, "a border line runs along the bottom bar")


if __name__ == "__main__":
    unittest.main()
