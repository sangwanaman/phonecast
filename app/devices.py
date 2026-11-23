"""Choosing which phone to connect to, and listing phones for the switcher.

Devices are dicts from ``adb.devices()``: serial, state ("device", "unauthorized", ...),
model and wifi. ``hardware(serial)`` returns a phone's hardware serial when known, which is
how one phone on both the cable and Wi-Fi is recognised as the same phone.
"""


def _no_hardware(serial):
    return ""


def choose(ready, last="", last_hw="", hardware=_no_hardware):
    """The phone picked last if it is here, on any connection; otherwise a cable before Wi-Fi."""
    for d in ready:
        if d["serial"] == last:
            return d
    if last_hw:
        same = [d for d in ready if hardware(d["serial"]) == last_hw or d["serial"] == last_hw]
        if same:
            return sorted(same, key=lambda d: d["wifi"])[0]
    return sorted(ready, key=lambda d: d["wifi"])[0]


def switcher_entries(devices, hardware=_no_hardware, name=lambda d: d["serial"]):
    """One entry per phone: serial to use, state, how it is connected ("USB", "Wi-Fi",
    "USB + Wi-Fi"), whether that is Wi-Fi only, display name, and the other serial if any."""
    groups = {}            # identity -> devices, in order of first appearance
    for d in devices:
        identity = hardware(d["serial"]) or d["serial"]
        groups.setdefault(identity, []).append(d)
    entries = []
    for members in groups.values():
        cable = [d for d in members if not d["wifi"]]
        air = [d for d in members if d["wifi"]]
        main = (cable or air)[0]
        other = air[0] if cable and air else None
        via = "USB + Wi-Fi" if other else ("Wi-Fi" if main["wifi"] else "USB")
        entries.append({"serial": main["serial"], "state": main["state"], "via": via,
                        "wifi": main["wifi"], "name": name(main),
                        "alt": other["serial"] if other else None})
    return entries
