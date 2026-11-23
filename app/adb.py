"""Small helpers around adb.exe (always run without a console window)."""

import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = ROOT / "engine" / "scrcpy"
SERVER_FILE = ENGINE_DIR / "scrcpy-server"
SERVER_VERSION = "5.0.1"
DEVICE_SERVER_PATH = "/data/local/tmp/phonecast-server.jar"
WIFI_PORT = 5555

CREATE_NO_WINDOW = 0x08000000


def adb_exe():
    # Prefer the adb on PATH so we share the adb server the user already runs
    # (two different adb versions keep killing each other's server).
    found = shutil.which("adb")
    if found:
        return found
    return str(ENGINE_DIR / "adb.exe")


def run(args, serial=None, timeout=15):
    """Run an adb command and return (returncode, combined output)."""
    cmd = [adb_exe()]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except OSError as e:
        return -1, str(e)
    out = (p.stdout or b"") + (p.stderr or b"")
    return p.returncode, out.decode("utf-8", "replace")


def popen(args, serial=None):
    cmd = [adb_exe()]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)


def shell(serial, command, timeout=15):
    return run(["shell", command], serial=serial, timeout=timeout)


def devices():
    """List attached devices as dicts: serial, state, model, wifi."""
    code, out = run(["devices", "-l"], timeout=8)
    result = []
    if code != 0:
        return result
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("*"):
            continue
        serial, state = parts[0], parts[1]
        model = ""
        for p in parts[2:]:
            if p.startswith("model:"):
                model = p[6:].replace("_", "-")
        wifi = bool(re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", serial)) or "_adb-tls-connect" in serial
        result.append({"serial": serial, "state": state, "model": model, "wifi": wifi})
    return result


def _parse_battery(text):
    level = status = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("level:"):
            level = int(line.split(":", 1)[1].strip() or 0)
        elif line.startswith("status:"):
            status = int(line.split(":", 1)[1].strip() or 0)
    if level is None:
        return None
    return {"level": level, "charging": status in (2, 5)}   # 2 = charging, 5 = full (on the charger)


def battery(serial):
    """{'level': 0-100, 'charging': bool} or None."""
    code, out = shell(serial, "dumpsys battery", timeout=6)
    return _parse_battery(out) if code == 0 else None


def device_info(serial):
    """Friendly name, hardware serial (to spot one phone on USB and Wi-Fi), make, model, battery."""
    code, out = shell(serial, "settings get global device_name; echo @@; getprop ro.serialno; echo @@; "
                              "getprop ro.product.manufacturer; echo @@; getprop ro.product.model; "
                              "echo @@; dumpsys battery", timeout=8)
    info = {"name": "", "hw": "", "maker": "", "model": "", "battery": None}
    if code != 0:
        return info
    parts = [p.strip() for p in out.split("@@")]
    parts += [""] * (5 - len(parts))
    name, hw, maker, model, batt = parts[:5]
    info["name"] = "" if name in ("", "null") or "\n" in name else name
    info["hw"] = hw if "\n" not in hw else ""
    info["maker"] = maker.title() if "\n" not in maker else ""
    info["model"] = model if "\n" not in model else ""
    info["battery"] = _parse_battery(batt)
    if not info["name"]:
        info["name"] = " ".join(x for x in (info["maker"], info["model"]) if x)
    return info


def phone_ips(serial):
    """IPv4 addresses of the phone's Wi-Fi / hotspot interfaces."""
    code, out = shell(serial, "ip -f inet addr show")
    ips = []
    iface = ""
    for line in out.splitlines():
        m = re.match(r"^\d+:\s+([^:@]+)", line)
        if m:
            iface = m.group(1)
            continue
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", line)
        if m and (iface.startswith("wlan") or iface.startswith("swlan") or iface.startswith("ap")):
            ips.append(m.group(1))
    return ips


def enable_wifi(serial):
    """Switch adbd to TCP mode and connect over Wi-Fi. Returns (ok, message, wifi_serial)."""
    ips = phone_ips(serial)
    if not ips:
        return False, "The phone is not on Wi-Fi and its hotspot is off.", None
    code, out = run(["tcpip", str(WIFI_PORT)], serial=serial, timeout=15)
    if code != 0:
        return False, "Could not enable Wi-Fi debugging: " + out.strip(), None
    last = ""
    for _ in range(10):
        time.sleep(1.0)
        for ip in ips:
            target = f"{ip}:{WIFI_PORT}"
            code, out = run(["connect", target], timeout=8)
            last = out.strip()
            if "connected" in out and "cannot" not in out and "failed" not in out:
                return True, f"Connected over Wi-Fi ({target})", target
    return False, "Wi-Fi debugging is on, but this computer could not reach the phone: " + last, None


def connect_wifi(target):
    code, out = run(["connect", target], timeout=8)
    ok = "connected" in out and "cannot" not in out and "failed" not in out
    return ok, out.strip()


def screen_state(serial):
    """Return dict with keys: locked, awake, rotation, width, height (best effort)."""
    cmd = ("dumpsys window | grep -m1 -E 'isKeyguardShowing'; "
           "dumpsys power | grep -m1 -E 'mWakefulness='; "
           "dumpsys input | grep -m1 'Viewport INTERNAL'")
    code, out = shell(serial, cmd, timeout=8)
    state = {"locked": None, "awake": None, "rotation": None, "width": None, "height": None}
    if code != 0:
        return state
    m = re.search(r"isKeyguardShowing=(\w+)", out)
    if m:
        state["locked"] = m.group(1) == "true"
    m = re.search(r"mWakefulness=(\w+)", out)
    if m:
        state["awake"] = m.group(1) == "Awake"
    m = re.search(r"orientation=(\d)", out)
    if m:
        state["rotation"] = int(m.group(1))
    m = re.search(r"logicalFrame=\[\d+, \d+, (\d+), (\d+)\]", out)
    if m:
        state["width"], state["height"] = int(m.group(1)), int(m.group(2))
    return state


def quote(text):
    return shlex.quote(text)
