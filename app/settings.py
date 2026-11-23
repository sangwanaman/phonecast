"""Persistent settings, stored in %APPDATA%\\PhoneCast\\settings.json.

The unlock PIN (only if the user asks to remember it) is encrypted with
Windows DPAPI, so only this Windows account on this computer can read it.
"""

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
from pathlib import Path

DIR = Path(os.environ.get("APPDATA", Path.home())) / "PhoneCast"
FILE = DIR / "settings.json"
OLD_FILE = DIR.parent / "ClaudeTV" / "settings.json"   # from before the rename: read once, then saved here

DEFAULTS = {
    # video
    "max_size": 0,          # 0 = phone's native resolution
    "max_fps": 60,
    "bitrate_mbps": 12,
    "codec": "h264",
    # audio
    "audio": True,
    "audio_dup": False,
    "muted": False,
    # phone
    "keep_awake": True,
    "wake_on_connect": True,
    "screen_off": False,
    "show_touches": False,
    "outline": True,
    # input
    "mouse": True,
    "keyboard": True,
    "right_click_back": True,
    # window & look
    "always_on_top": False,
    "geometry": None,
    "accent": "#0a84ff",    # blue; Settings → Appearance offers others
    # several phones: the one picked last is preferred when connecting
    "last_device": "",
    "last_device_hw": "",   # its hardware serial, so the same phone is found over USB or Wi-Fi
    # capture card mode
    "wifi_target": "",
    "capture_video": "",
    "capture_audio": "",
    # unlock
    "pin_blob": "",
}


def load():
    data = dict(DEFAULTS)
    for source in (FILE, OLD_FILE):
        try:
            data.update(json.loads(source.read_text(encoding="utf-8")))
            break
        except (OSError, ValueError):
            continue
    return data


def save(data):
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(FILE)
    except OSError:
        pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _crypt(func, data):
    blob_in, _keep = _blob(data)
    blob_out = _Blob()
    if not func(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def protect(text):
    out = _crypt(ctypes.windll.crypt32.CryptProtectData, text.encode("utf-8"))
    return base64.b64encode(out).decode("ascii")


def unprotect(blob):
    if not blob:
        return ""
    try:
        data = _crypt(ctypes.windll.crypt32.CryptUnprotectData, base64.b64decode(blob))
        return data.decode("utf-8")
    except (OSError, ValueError):
        return ""
