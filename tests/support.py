"""Shared test helpers: one offscreen Qt application, styled like the real app."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no windows pop up while testing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import theme  # noqa: E402

_app = None


def qapp():
    global _app
    _app = QApplication.instance() or QApplication([])
    _app.setStyle("Fusion")
    theme.apply(_app)
    return _app


class PhoneStandIn:
    """The phone side of a mirroring session: a screen size and a pipe that accepts input."""

    has_control = True

    def __init__(self, width=1080, height=2340):
        self.video_size = (width, height)
        self.sent = []

    def send(self, data):
        self.sent.append(data)


def pixel(image, x, y):
    return image.pixelColor(x, y).name()
