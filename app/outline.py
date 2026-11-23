"""Outline of protected screens.

Android blocks the *picture* of secure screens (PIN pads, "Verify it's you", banking apps) from
every kind of capture, but the accessibility layout (what screen readers use) still lists their
buttons, text and PIN boxes with exact positions. `uiautomator dump` reads that layout, and this
module turns it into a simple outline that can be drawn where the black picture is.
"""

import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import adb

DUMP_PATH = "/data/local/tmp/phonecast-ui.xml"
DUMP_CMD = (f"rm -f {DUMP_PATH}; uiautomator dump {DUMP_PATH} >/dev/null 2>&1; "
            f"cat {DUMP_PATH} 2>/dev/null; rm -f {DUMP_PATH}")

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
BIG_AREA = 0.45   # clickable areas larger than this share of the screen are backgrounds, not buttons

# Two uiautomator runs at once break each other (one file, one accessibility connection)
_dump_lock = threading.Lock()


@dataclass
class Node:
    left: int
    top: int
    right: int
    bottom: int
    kind: str            # "button", "field" or "text"
    label: str = ""
    focused: bool = False
    password: bool = False

    @property
    def center(self):
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    @property
    def area(self):
        return (self.right - self.left) * (self.bottom - self.top)

    def contains(self, x, y):
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass
class Outline:
    nodes: list
    width: int           # screen size the node positions refer to
    height: int
    package: str = ""


def _label(el, password):
    text = (el.get("text") or "").strip()
    desc = (el.get("content-desc") or "").strip()
    if password:
        # never show what was typed, only how many characters
        return "•" * len(text) if text else ""
    label = text or desc
    label = " ".join(label.split())
    return label[:60] + "…" if len(label) > 60 else label


def parse(xml_text, width, height):
    """Turn a uiautomator dump into an Outline, or None if it can't be read."""
    start = xml_text.find("<hierarchy")
    if start < 0:
        return None
    end = xml_text.rfind("</hierarchy>")
    try:
        root = ET.fromstring(xml_text[start:end + len("</hierarchy>")])
    except ET.ParseError:
        return None
    screen_area = max(1, width * height)
    nodes = []
    packages = []

    def walk(el, button_labels):
        m = _BOUNDS.match(el.get("bounds") or "")
        labels = button_labels
        if m:
            left, top, right, bottom = (int(v) for v in m.groups())
            left, top = max(0, left), max(0, top)
            right, bottom = min(width, right), min(height, bottom)
            if right - left > 2 and bottom - top > 2:
                if el.get("package") and not packages:
                    packages.append(el.get("package"))
                cls = el.get("class") or ""
                password = el.get("password") == "true"
                field = password or cls.endswith("EditText") or cls.endswith("AutoCompleteTextView")
                clickable = any(el.get(a) == "true" for a in ("clickable", "long-clickable", "checkable"))
                label = _label(el, password)
                area = (right - left) * (bottom - top)
                kind = None
                if field:
                    kind = "field"
                elif clickable and area < BIG_AREA * screen_area:
                    kind = "button"
                    if label:
                        labels = button_labels + (label,)
                elif label and label not in button_labels:
                    kind = "text"
                if kind:
                    nodes.append(Node(left, top, right, bottom, kind, label,
                                      el.get("focused") == "true", password))
        for child in el:
            walk(child, labels)

    for child in root:
        walk(child, ())
    return Outline(nodes, width, height, packages[0] if packages else "")


def dump(serial, width, height, attempts=1):
    """Read the phone's current screen layout (takes 2-3 s). Returns an Outline or None."""
    for attempt in range(attempts):
        if attempt:
            time.sleep(0.5)
        with _dump_lock:
            code, out = adb.shell(serial, DUMP_CMD, timeout=20)
        result = parse(out, width, height) if code == 0 else None
        if result is not None:
            return result
    return None


def _digit(label):
    s = label.strip()
    if s and s[0].isdigit() and (len(s) == 1 or not s[1].isalnum() or s[1:].strip().isalpha()):
        return s[0]
    return None


def pin_target(outline, pin):
    """Where a PIN can go on this screen.

    Returns ("field", node) for a password box, ("keypad", {digit: node}) for an on-screen
    number pad that has every digit 0-9, or None. Ordinary text boxes are never used, so a
    PIN can't end up in a chat or search box.
    """
    if outline is None:
        return None
    fields = [n for n in outline.nodes if n.kind == "field" and n.password]
    if fields:
        focused = [n for n in fields if n.focused]
        return "field", (focused or fields)[0]
    if not pin.isdigit():
        return None
    keys = {}
    for n in outline.nodes:
        d = _digit(n.label) if n.kind in ("button", "text") else None
        if d is not None and d not in keys:
            keys[d] = n
    if len(keys) == 10:
        return "keypad", keys
    return None
