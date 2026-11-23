"""Which phone PhoneCast connects to, and how the phone switcher lists them."""

import unittest

import support  # noqa: F401  (puts the app on the import path)

from app.devices import choose, switcher_entries


def phone(serial, wifi=False, state="device", model=""):
    return {"serial": serial, "state": state, "model": model, "wifi": wifi}


HW = {"192.168.1.20:5555": "S21-HW", "S21-HW": "S21-HW", "REDMI": "REDMI"}


def hardware(serial):
    return HW.get(serial, "")


class ChoosingAPhone(unittest.TestCase):
    def test_with_no_history_a_cable_beats_wifi(self):
        ready = [phone("192.168.1.99:5555", wifi=True), phone("REDMI")]
        self.assertEqual(choose(ready)["serial"], "REDMI")

    def test_the_phone_picked_last_wins(self):
        ready = [phone("S21-HW"), phone("REDMI")]
        self.assertEqual(choose(ready, last="REDMI")["serial"], "REDMI")

    def test_the_phone_picked_last_is_found_on_wifi(self):
        # picked over the cable yesterday, only on Wi-Fi today
        ready = [phone("REDMI"), phone("192.168.1.20:5555", wifi=True)]
        chosen = choose(ready, last="S21-HW", last_hw="S21-HW", hardware=hardware)
        self.assertEqual(chosen["serial"], "192.168.1.20:5555")

    def test_when_the_last_phone_is_gone_a_cable_still_wins(self):
        ready = [phone("10.0.0.5:5555", wifi=True), phone("REDMI")]
        self.assertEqual(choose(ready, last="S21-HW", last_hw="S21-HW", hardware=hardware)["serial"], "REDMI")


class ListingPhones(unittest.TestCase):
    def test_one_phone_on_cable_and_wifi_is_listed_once(self):
        devices = [phone("192.168.1.20:5555", wifi=True), phone("S21-HW"), phone("REDMI")]
        entries = switcher_entries(devices, hardware=hardware, name=lambda d: d["serial"])
        self.assertEqual([(e["serial"], e["via"]) for e in entries],
                         [("S21-HW", "USB + Wi-Fi"), ("REDMI", "USB")])

    def test_phones_waiting_for_permission_are_still_listed(self):
        devices = [phone("S21-HW"), phone("NEWPHONE", state="unauthorized")]
        entries = switcher_entries(devices, hardware=hardware, name=lambda d: d["serial"])
        self.assertEqual([(e["serial"], e["state"]) for e in entries],
                         [("S21-HW", "device"), ("NEWPHONE", "unauthorized")])


if __name__ == "__main__":
    unittest.main()
