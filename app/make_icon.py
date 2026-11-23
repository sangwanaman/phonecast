"""Writes assets/phonecast.ico (used by the desktop and Start menu shortcuts)."""

import struct
import sys

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

from . import theme
from .adb import ROOT


def main():
    app = QGuiApplication(sys.argv)  # needed for fonts
    icon = theme.app_icon()
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = []
    for size in sizes:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        icon.pixmap(size, size).toImage().save(buf, "PNG")
        images.append(bytes(buf.data()))
    # ICO container with PNG-compressed entries
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for size, data in zip(sizes, images):
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    out = ROOT / "assets" / "phonecast.ico"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(header + entries + blobs)
    print("wrote", out)
    app.quit()


if __name__ == "__main__":
    main()
