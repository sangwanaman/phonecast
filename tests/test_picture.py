"""The phone picture fills its window: no frame, band or padding around it."""

import unittest

from support import PhoneStandIn, pixel, qapp

from PySide6.QtGui import QColor, QImage

from app.widgets import ScreenView

PICTURE = "#ffffff"   # a plain white phone screen makes the picture's extent easy to see


class PictureFillsTheWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qapp()

    def show_phone_screen(self, width, height):
        view = ScreenView()
        view.resize(width, height)
        view.session = PhoneStandIn()
        w, h = view.box_size()               # the session renders frames at the size the view asks for
        frame = QImage(w, h, QImage.Format_RGB32)
        frame.fill(QColor(PICTURE))
        view.set_frame((frame, None))
        return view.grab().toImage()

    def test_picture_reaches_every_edge(self):
        shot = self.show_phone_screen(300, 650)
        w, h = shot.width(), shot.height()
        edges = {"left": (0, h // 2), "right": (w - 1, h // 2), "top": (w // 2, 0), "bottom": (w // 2, h - 1)}
        for name, (x, y) in edges.items():
            self.assertEqual(pixel(shot, x, y), PICTURE, f"a band shows at the {name} edge")

    def test_picture_corners_are_square(self):
        # the window itself already has rounded corners on Windows 11: the picture adds none of its own
        shot = self.show_phone_screen(300, 650)
        w, h = shot.width(), shot.height()
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            self.assertEqual(pixel(shot, x, y), PICTURE, f"the corner at {x},{y} is cut off")


if __name__ == "__main__":
    unittest.main()
