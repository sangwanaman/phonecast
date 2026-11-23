"""scrcpy 5.0.1 control protocol (client -> phone) and the keyboard map.

Layouts mirror server/src/main/java/com/genymobile/scrcpy/control/ControlMessageReader.java.
"""

import struct

from PySide6.QtCore import Qt

# Control message types
INJECT_KEYCODE = 0
INJECT_TEXT = 1
INJECT_TOUCH = 2
INJECT_SCROLL = 3
BACK_OR_SCREEN_ON = 4
EXPAND_NOTIFICATION_PANEL = 5
EXPAND_SETTINGS_PANEL = 6
COLLAPSE_PANELS = 7
GET_CLIPBOARD = 8
SET_CLIPBOARD = 9
SET_DISPLAY_POWER = 10
ROTATE_DEVICE = 11
RESET_VIDEO = 17
SCAN_FILE = 22

# Device message types (phone -> client)
DEVICE_CLIPBOARD = 0
DEVICE_ACK_CLIPBOARD = 1
DEVICE_UHID_OUTPUT = 2

# Android constants
ACTION_DOWN = 0
ACTION_UP = 1
ACTION_MOVE = 2
BUTTON_PRIMARY = 1

POINTER_MOUSE = -1
POINTER_FINGER = -2
POINTER_VIRTUAL_FINGER = -3

KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_VOLUME_UP = 24
KEYCODE_VOLUME_DOWN = 25
KEYCODE_POWER = 26
KEYCODE_ENTER = 66
KEYCODE_MENU = 82
KEYCODE_VOLUME_MUTE = 164
KEYCODE_APP_SWITCH = 187
KEYCODE_WAKEUP = 224

META_SHIFT = 0x01 | 0x40
META_ALT = 0x02 | 0x10
META_CTRL = 0x1000 | 0x2000

TEXT_MAX_BYTES = 300


def inject_keycode(action, keycode, repeat=0, meta=0):
    return struct.pack(">BBiii", INJECT_KEYCODE, action, keycode, repeat, meta)


def inject_text(text):
    data = text.encode("utf-8")[:TEXT_MAX_BYTES]
    return struct.pack(">BI", INJECT_TEXT, len(data)) + data


def _u16_fixed(value):
    value = max(0.0, min(1.0, value))
    return 0xFFFF if value >= 1.0 else int(value * 65536)


def _i16_fixed(value):
    value = max(-1.0, min(1.0, value))
    return 0x7FFF if value >= 1.0 else int(value * 32768)


def inject_touch(action, pointer_id, x, y, width, height, pressure=1.0, action_button=0, buttons=0):
    return struct.pack(">BBqiiHHHii", INJECT_TOUCH, action, pointer_id, int(x), int(y),
                       width, height, _u16_fixed(pressure), action_button, buttons)


def inject_scroll(x, y, width, height, hscroll, vscroll, buttons=0):
    # The wire range is [-16, 16], encoded as a fixed point value over [-1, 1]
    return struct.pack(">BiiHHhhi", INJECT_SCROLL, int(x), int(y), width, height,
                       _i16_fixed(hscroll / 16), _i16_fixed(vscroll / 16), buttons)


def back_or_screen_on(action):
    return struct.pack(">BB", BACK_OR_SCREEN_ON, action)


def simple(msg_type):
    return struct.pack(">B", msg_type)


def get_clipboard(copy_key=0):
    return struct.pack(">BB", GET_CLIPBOARD, copy_key)


def set_clipboard(sequence, text, paste):
    data = text.encode("utf-8")
    return struct.pack(">BqBI", SET_CLIPBOARD, sequence, 1 if paste else 0, len(data)) + data


def set_display_power(on):
    return struct.pack(">BB", SET_DISPLAY_POWER, 1 if on else 0)


def scan_file(path):
    """Ask the phone's media scanner to index a file we pushed (so it shows in Gallery)."""
    data = path.encode("utf-8")
    return struct.pack(">BI", SCAN_FILE, len(data)) + data


# Qt key -> Android keycode, for keys that are not typed as text.
SPECIAL_KEYS = {
    Qt.Key_Return: 66, Qt.Key_Enter: 66, Qt.Key_Backspace: 67, Qt.Key_Delete: 112,
    Qt.Key_Tab: 61, Qt.Key_Backtab: 61, Qt.Key_Escape: 111,
    Qt.Key_Up: 19, Qt.Key_Down: 20, Qt.Key_Left: 21, Qt.Key_Right: 22,
    Qt.Key_Home: 122, Qt.Key_End: 123, Qt.Key_PageUp: 92, Qt.Key_PageDown: 93,
    Qt.Key_Insert: 124, Qt.Key_Menu: 82,
    Qt.Key_MediaPlay: 85, Qt.Key_MediaPause: 85, Qt.Key_MediaTogglePlayPause: 85,
    Qt.Key_MediaNext: 87, Qt.Key_MediaPrevious: 88, Qt.Key_MediaStop: 86,
}
for _i in range(12):
    SPECIAL_KEYS[Qt.Key_F1 + _i] = 131 + _i

# Keys sent as keycodes when Ctrl/Alt is held (Ctrl+A, Ctrl+C, Ctrl+Z, ...)
CHORD_KEYS = {Qt.Key_Space: 62}
for _i in range(26):
    CHORD_KEYS[Qt.Key_A + _i] = 29 + _i
for _i in range(10):
    CHORD_KEYS[Qt.Key_0 + _i] = 7 + _i


def meta_state(modifiers):
    meta = 0
    if modifiers & Qt.ShiftModifier:
        meta |= META_SHIFT
    if modifiers & Qt.ControlModifier:
        meta |= META_CTRL
    if modifiers & Qt.AltModifier:
        meta |= META_ALT
    return meta
