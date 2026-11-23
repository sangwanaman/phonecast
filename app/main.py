"""PhoneCast: your phone's screen on the computer, controlled with mouse and keyboard."""

import ctypes
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QPoint, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLayout, QMainWindow, QMenu, QScrollArea, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from . import adb, devices, outline, settings, tasks, theme
from . import protocol as P
from .capture import CaptureSource
from .dialogs import (CaptureDialog, CommandPalette, ConnectDialog, HelpDialog, PairDialog,
                      SettingsDialog, TypePinDialog, UnlockDialog, remembered_pin)
from .session import Session
from .tasks import run_async
from .theme import G
from .widgets import Battery, ScreenView, SideButton

INSTANCE_KEY = "PhoneCast-single-instance"
RESTART_KEYS = ("max_size", "max_fps", "bitrate_mbps", "codec", "audio", "audio_dup",
                "show_touches", "keep_awake", "wake_on_connect")


def _user_dir(location, *parts):
    base = Path(QStandardPaths.writableLocation(location))
    path = base.joinpath("PhoneCast", *parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def pictures_dir(*parts):
    return _user_dir(QStandardPaths.PicturesLocation, *parts)


def videos_dir():
    return _user_dir(QStandardPaths.MoviesLocation)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = settings.load()
        self.setWindowTitle("PhoneCast")
        self.setWindowIcon(theme.app_icon())

        self.mode = "usb"            # "usb" (mirror over USB/Wi-Fi) or "capture" (HDMI card)
        self.session = None
        self.capture = None
        self.connected = False
        self.connecting = False
        self.serial = None
        self.phone_name = ""
        self.phone_state = {}
        self.dark = False
        self.retry_after = 0.0
        self.devices = []            # latest `adb devices` list
        self._info = {}              # serial -> device_info() (name, hardware serial, battery)
        self._info_busy = set()
        self._pending_switch = None  # Wi-Fi serial to switch to once it shows up
        self._going_wireless = False
        self._devices_busy = False
        self._state_busy = False
        self._orientation = None
        self._was_maximized = False
        self._last_blocked_hint = 0.0
        self._outline_busy = False
        self._outline_again = False
        self._status = ("idle", "")
        self.compact = False
        self._compact_geo = None

        self.view = ScreenView()
        self.view.mouse_enabled = self.cfg["mouse"]
        self.view.keyboard_enabled = self.cfg["keyboard"]
        self.view.right_click_back = self.cfg["right_click_back"]
        self.view.box_changed.connect(self._on_box)
        self.view.blocked.connect(self._on_blocked)
        self.view.files_dropped.connect(self.send_files)
        self.view.edge_reached.connect(self._reveal_sidebar)
        self.view.wake_requested.connect(self.act_wake)
        self.view.input_sent.connect(self._on_user_input)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        left = QWidget()
        col = QVBoxLayout(left)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self.view, 1)
        self.statusbar = self._build_status()
        col.addWidget(self.statusbar)
        row.addWidget(left, 1)
        self.sidebar = self._build_sidebar()
        row.addWidget(self.sidebar)
        self.setCentralWidget(central)

        self._shortcuts()
        self._restore_geometry()
        self._set_controls_enabled(False)
        self._update_chips()
        self._set_status("idle", "Looking for your phone…")
        self.view.set_message(G["usb"], "Looking for your phone…")

        self.devices_timer = QTimer(self, interval=1500, timeout=self._check_devices)
        self.devices_timer.start()
        self.state_timer = QTimer(self, interval=2000, timeout=self._poll_state)
        self.state_timer.start()
        self.stats_timer = QTimer(self, interval=1000, timeout=self._update_stats)
        self.stats_timer.start()
        self.battery_timer = QTimer(self, interval=30000, timeout=self._poll_battery)
        self.battery_timer.start()
        self.rec_timer = QTimer(self, interval=500, timeout=self._update_rec)
        self.hide_sidebar_timer = QTimer(self, interval=700, timeout=self._maybe_hide_sidebar)
        self.outline_timer = QTimer(self, singleShot=True, timeout=self._outline_tick)
        QTimer.singleShot(0, self._check_devices)

    # ================================================================== layout

    def _build_sidebar(self):
        dock = QFrame(objectName="Dock")
        dock.setFixedWidth(52)
        outer = QVBoxLayout(dock)
        outer.setContentsMargins(0, 6, 8, 6)
        panel = QFrame(objectName="DockPanel")
        outer.addWidget(panel)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 2, 0, 2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget(objectName="DockInner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.side_buttons = []
        self.side_seps = 0

        def add(glyph, tip, slot, checkable=False, checked=False):
            b = SideButton(glyph, tip, checkable)
            self.side_buttons.append(b)
            if checkable:
                b.setChecked(checked)
                b.toggled.connect(slot)
            else:
                b.clicked.connect(slot)
            lay.addWidget(b, 0, Qt.AlignHCenter)
            return b

        def sep():
            self.side_seps += 1
            lay.addWidget(QFrame(objectName="SideSep"))

        self.control_buttons = [
            add(G["back"], "Back   (right-click, Esc, Ctrl+Alt+B)", self.act_back),
            add(G["home"], "Home   (middle-click, Ctrl+Alt+H)", self.act_home),
            add(G["recents"], "Recent apps   (Ctrl+Alt+R)", self.act_recents),
        ]
        sep()
        self.control_buttons += [
            add(G["notifications"], "Open notifications", self.act_notifications),
            add(G["quick"], "Open quick settings", self.act_quick_settings),
        ]
        sep()
        self.control_buttons += [
            add(G["vol_up"], "Volume up", self.act_volume_up),
            add(G["vol_down"], "Volume down", self.act_volume_down),
            add(G["power"], "Power button (lock / wake)", self.act_power),
            add(G["rotate"], "Rotate the phone", self.act_rotate),
        ]
        self.b_unlock = add(G["unlock"], "", self.act_unlock)
        self.control_buttons.append(self.b_unlock)
        self._update_unlock_tip()
        sep()
        self.b_mouse = add(G["mouse"], "Mouse / touchpad controls the phone   (Ctrl+Alt+M)",
                           self.act_mouse, True, self.cfg["mouse"])
        self.b_keyboard = add(G["keyboard"], "Keyboard types on the phone   (Ctrl+Alt+K)",
                              self.act_keyboard, True, self.cfg["keyboard"])
        sep()
        self.b_sound = add(G["volume"], "Play the phone's sound here", self.act_sound,
                           True, not self.cfg["muted"])
        self.b_screen_off = add(G["screen_off"], "Turn the phone's own screen off (the picture here keeps working)",
                                self.act_screen_off, True, self.cfg["screen_off"])
        self.b_outline = add(G["eye"], "Outline of protected (black) screens, so you can click their buttons"
                             "   (Ctrl+Alt+O)", self.act_outline, True, self.cfg["outline"])
        self.b_shot = add(G["camera"], "Screenshot to Pictures\\PhoneCast   (Ctrl+Alt+S)\n"
                          "Shift+click copies it to the clipboard   (Ctrl+Alt+C)", self.act_screenshot)
        self.b_record = add(G["record"], "Record the screen to Videos\\PhoneCast   (Ctrl+Alt+V)", self.act_record)
        self.control_buttons += [self.b_screen_off, self.b_shot, self.b_record]
        lay.addStretch(1)
        self.b_capture = add(G["hdmi"], "HDMI capture mode: see PIN and protected screens too",
                             self.act_capture, True, False)
        self.b_capture.toggled.disconnect()
        self.b_capture.clicked.connect(self.act_capture)
        self.b_top = add(G["pin"], "Keep this window on top", self.act_on_top, True,
                         self.cfg["always_on_top"])
        self.b_compact = add(G["compact"], "Compact window: small, on top, no buttons   (Ctrl+Alt+I)",
                             self.act_compact)
        self.b_full = add(G["fullscreen"], "Full screen   (F11)", self.act_fullscreen)
        add(G["settings"], "Settings", self.act_settings)
        self.b_more = add(G["more"], "More   (Ctrl+K searches every action)", self.act_more)

        scroll.setWidget(inner)
        pv.addWidget(scroll)
        self.dock_panel = panel
        dock.installEventFilter(self)
        if self.cfg["always_on_top"]:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        return dock

    def _build_status(self):
        bar = QFrame(objectName="StatusBar")
        bar.setFixedHeight(32)
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 0, 12, 4)
        h.setSpacing(10)
        self.pill = QToolButton(objectName="DevicePill")
        self.pill.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.pill.setCursor(Qt.PointingHandCursor)
        self.pill.setFocusPolicy(Qt.NoFocus)
        self.pill.clicked.connect(self.act_devices)
        self.via_icon = QLabel()
        self.via_icon.setFont(theme.icon_font(13))
        self.via_icon.hide()
        self.st_text = QLabel()
        self.st_info = QLabel()
        # Let the bar shrink to the phone picture's width instead of widening the window
        for label in (self.st_text, self.st_info):
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.st_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.rec_pill = QLabel(objectName="RecPill")
        self.rec_pill.hide()
        for label in (self.rec_pill, self.st_info):
            label.setFont(theme.tabular(label.font()))
        self.battery = Battery()
        self.chip_lock = QLabel(G["lock"], objectName="Chip")   # only shown while the phone is locked
        self.chip_lock.setToolTip("The phone is locked")
        self.chip_lock.setAccessibleName("The phone is locked")
        h.addWidget(self.pill)
        h.addWidget(self.via_icon)
        h.addWidget(self.st_text, 3)
        h.addWidget(self.rec_pill)
        h.addWidget(self.st_info, 2)
        h.addWidget(self.battery)
        h.addWidget(self.chip_lock)
        # The bar must never widen the window past the phone's shape: it drops its least
        # important items instead when space runs out (see _fit_statusbar).
        h.setSizeConstraint(QLayout.SetNoConstraint)
        bar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        bar.setMinimumWidth(0)
        bar.installEventFilter(self)
        self.pill.setMaximumWidth(230)
        return bar

    def _fit_statusbar(self):
        """Hide the bar's extras, least important first, until everything fits."""
        bar = self.statusbar
        width = bar.width() - 22
        optional = [self.st_info, self.battery, self.via_icon]
        wanted = {
            self.st_info: bool(self.st_info.text()),
            self.battery: self.battery.level is not None,
            self.via_icon: self.connected and self.mode == "usb",
        }
        fixed = self.pill.sizeHint().width() + (self.rec_pill.sizeHint().width() + 10 if self.rec_pill.isVisible() else 0)
        if self.chip_lock.isVisible():
            fixed += self.chip_lock.sizeHint().width() + 10
        sizes = {w: (w.sizeHint().width() if w is not self.st_info else 56) + 10 for w in optional}
        used = fixed + sum(sizes[w] for w in optional if wanted[w])
        for w in optional:
            show = wanted[w] and used <= width
            if wanted[w] and not show:
                used -= sizes[w]
            w.setVisible(show and wanted[w])
        # second pass: things hidden early may fit again once later ones were dropped
        for w in reversed(optional):
            if wanted[w] and not w.isVisible() and used + sizes[w] <= width:
                w.setVisible(True)
                used += sizes[w]

    def _shortcuts(self):
        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)
        sc("F11", self.act_fullscreen)
        sc("F1", self.act_help)
        sc("Ctrl+K", self.act_palette)
        sc("Ctrl+Alt+D", self.act_devices)
        sc("Ctrl+Alt+I", self.act_compact)
        sc("Ctrl+Alt+V", self.act_record)
        sc("Ctrl+Alt+C", self.act_copy_screenshot)
        sc("Ctrl+Alt+M", self.b_mouse.toggle)
        sc("Ctrl+Alt+K", self.b_keyboard.toggle)
        sc("Ctrl+Alt+O", self.b_outline.toggle)
        sc("Ctrl+Alt+U", self.act_unlock)
        sc("Ctrl+Alt+P", self.act_type_pin)
        sc("Ctrl+Alt+H", self.act_home)
        sc("Ctrl+Alt+B", self.act_back)
        sc("Ctrl+Alt+R", self.act_recents)
        sc("Ctrl+Alt+S", self.act_screenshot)

    def _restore_geometry(self):
        geo = self.cfg.get("geometry")
        if geo and self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii"))):
            return
        self._fit_window(1080, 2340)

    def _chrome_size(self):
        side = self.sidebar.width() if self.sidebar.isVisible() or not self.isVisible() else 0
        bar = self.statusbar.height() if self.statusbar.isVisible() or not self.isVisible() else 0
        return side, bar

    def _fit_window(self, w, h):
        if self.isFullScreen() or self.isMaximized():
            return
        if self.compact:
            self._compact_resize(w, h)
            return
        avail = self.screen().availableGeometry()
        side, bar = self._chrome_size()
        title = 32
        scale = min((avail.width() * 0.94 - side) / w, (avail.height() * 0.94 - bar - title) / h)
        new_w, new_h = int(w * scale + side), int(h * scale + bar)
        center = self.frameGeometry().center() if self.isVisible() else avail.center()
        self.resize(new_w, new_h)
        geo = self.frameGeometry()
        geo.moveCenter(center)
        geo.moveLeft(max(avail.left(), min(geo.left(), avail.right() - geo.width())))
        geo.moveTop(max(avail.top(), min(geo.top(), avail.bottom() - geo.height())))
        self.move(geo.topLeft())

    # ============================================================== devices

    def _device_name(self, dev):
        info = self._info.get(dev["serial"], {})
        return info.get("name") or dev.get("model") or dev["serial"]

    def _hw(self, serial):
        return self._info.get(serial, {}).get("hw") or ""

    def _check_devices(self):
        if self._devices_busy:
            return
        self._devices_busy = True
        run_async(adb.devices, self._on_devices)

    def _on_devices(self, devs):
        self._devices_busy = False
        if isinstance(devs, Exception):
            devs = []
        self.devices = devs
        self._fetch_infos(devs)
        ready = [d for d in devs if d["state"] == "device"]
        if self._pending_switch and any(d["serial"] == self._pending_switch for d in ready):
            target, self._pending_switch = self._pending_switch, None
            self._going_wireless = False
            self.switch_device(target)
        self._update_pill()
        if self.mode != "usb" or self.session is not None or self.connecting or self._going_wireless:
            return
        if time.monotonic() < self.retry_after:
            return
        if ready:
            self._start_session(self._pick_device(ready))
            return
        states = {d["state"] for d in devs}
        if "unauthorized" in states:
            self._set_status("warn", "Waiting for USB debugging permission")
            self.view.set_message(
                G["lock"], "Your phone is asking for permission",
                "The phone shows an “Allow USB debugging?” question. Tap Allow on the phone. On a "
                "phone with a broken screen, unplug and re-plug the cable, or see Help (F1).")
        elif devs:
            self._set_status("warn", "Phone found, waiting for it…")
            self.view.set_message(G["phone"], "Phone found, waiting for it to respond…")
        else:
            self._set_status("idle", "No phone connected")
            self.view.set_message(
                G["usb"], "Connect your phone",
                "Plug an Android phone into this computer with a USB cable. USB debugging must be "
                "on (Settings → Developer options). It connects by itself.")

    def _pick_device(self, ready):
        return devices.choose(ready, self.cfg.get("last_device", ""), self.cfg.get("last_device_hw", ""),
                              self._hw)

    def _fetch_infos(self, devs):
        for d in devs:
            s = d["serial"]
            if d["state"] != "device" or s in self._info or s in self._info_busy:
                continue
            self._info_busy.add(s)
            run_async(lambda s=s: adb.device_info(s), lambda info, s=s: self._on_info(s, info))

    def _on_info(self, serial, info):
        self._info_busy.discard(serial)
        if isinstance(info, Exception):
            return
        self._info[serial] = info
        if serial == self.serial and self.mode == "usb":
            if info.get("name"):
                self.phone_name = info["name"]
                self.setWindowTitle(f"PhoneCast · {self.phone_name}")
            if info.get("battery") and self.connected:
                b = info["battery"]
                self.battery.set_level(b["level"], b["charging"])
        self._update_pill()

    def _device_entries(self):
        """Phones for the switcher, with one phone on both USB and Wi-Fi shown once."""
        return devices.switcher_entries(self.devices, self._hw, self._device_name)

    def _ready_count(self):
        return sum(1 for e in self._device_entries() if e["state"] == "device")

    def _update_pill(self):
        level = self._status[0]
        color = {"ok": theme.GOOD, "busy": theme.WARN, "warn": theme.WARN, "bad": theme.BAD}.get(level, theme.FAINT)
        if self.mode == "capture":
            name = self.phone_name or "HDMI capture"
        elif (self.connected or self.connecting) and self.phone_name:
            name = self.phone_name
        else:
            name = "No phone" if not self._ready_count() else "Phones"
        count = self._ready_count()
        extra = f"   +{count - 1}" if count > 1 and (self.connected or self.connecting) else ""
        name = self.pill.fontMetrics().elidedText(name, Qt.ElideRight, 150)
        self.pill.setIcon(theme.dot_icon(color, 16))
        self.pill.setText(f"{name}{extra}  ▾")
        tip = f"{count} phones connected. Click to switch   (Ctrl+Alt+D)" if count > 1 else \
              "Phones and Wi-Fi connections   (Ctrl+Alt+D)"
        self.pill.setToolTip(tip)

    def act_devices(self):
        menu = QMenu(self)
        title = menu.addAction("Phones")
        title.setEnabled(False)
        entries = self._device_entries()
        current = {self.serial} if (self.connected or self.connecting) else set()
        for e in entries:
            serial = e["serial"]
            is_current = serial in current or (e["alt"] and e["alt"] in current)
            if e["state"] == "device":
                detail = e["via"]
                batt = self._info.get(serial, {}).get("battery")
                if is_current and self.battery.level is not None:
                    detail += f"  ·  {self.battery.level}%"
                elif batt:
                    detail += f"  ·  {batt['level']}%"
            elif e["state"] == "unauthorized":
                detail = "waiting for permission"
            else:
                detail = e["state"]
            glyph = G["check"] if is_current else (G["wifi"] if e["wifi"] else G["usb"])
            act = menu.addAction(theme.glyph_icon(glyph, theme.TEXT if is_current else theme.MUTED),
                                 f"{e['name']}	{detail}")
            act.setEnabled(e["state"] == "device" and self.mode == "usb")
            if is_current:
                f = act.font()
                f.setWeight(f.Weight.DemiBold)
                act.setFont(f)
            act.triggered.connect(lambda _=False, s=serial: self.switch_device(s))
        if not entries:
            menu.addAction("No phones found").setEnabled(False)
        menu.addSeparator()
        cur_usb = self.connected and self.mode == "usb" and self.serial and ":" not in self.serial \
            and "_adb-tls" not in self.serial
        cur_wifi = self.connected and self.mode == "usb" and self.serial and not cur_usb
        a = menu.addAction(theme.glyph_icon(G["wifi"], theme.MUTED), "Continue over Wi-Fi", self.act_go_wireless)
        a.setEnabled(bool(cur_usb))
        a.setToolTip("Lets you unplug the cable and keep going wirelessly")
        menu.addAction(theme.glyph_icon(G["link"], theme.MUTED), "Connect over Wi-Fi…", self.act_connect_wifi)
        menu.addAction(theme.glyph_icon(G["add"], theme.MUTED), "Pair a phone over Wi-Fi…",
                       lambda: PairDialog(self).exec())
        if cur_wifi:
            menu.addAction(theme.glyph_icon(G["close"], theme.MUTED), "Disconnect this Wi-Fi phone",
                           self.act_disconnect_wifi)
        menu.setToolTipsVisible(True)
        if self.statusbar.isVisible():
            hint = menu.sizeHint()
            corner = self.pill.mapToGlobal(QPoint(0, 0))
            menu.exec(QPoint(corner.x(), corner.y() - hint.height() - 6))
        else:
            menu.exec(self.mapToGlobal(QPoint(16, 16)))

    def switch_device(self, serial):
        if self.mode != "usb":
            self.view.toast.show_text("Leave HDMI capture mode to switch phones")
            return
        dev = next((d for d in self.devices if d["serial"] == serial and d["state"] == "device"), None)
        if dev is None:
            self.view.toast.show_text("That phone is not ready")
            return
        self.cfg["last_device"] = serial
        self.cfg["last_device_hw"] = self._hw(serial) or ("" if dev["wifi"] else serial)
        settings.save(self.cfg)
        if serial == self.serial and (self.connected or self.connecting):
            return
        self._stop_session()
        self.view.clear_frame()
        self._orientation = None
        self.phone_name = ""
        self.phone_state = {}
        self.battery.set_level(None, False)
        self.retry_after = 0
        self._start_session(dev)

    def act_go_wireless(self):
        serial = self.serial
        if not (self.connected and serial):
            return
        self._going_wireless = True
        self.view.toast.show_text("Switching to Wi-Fi…", 20000)

        def done(result):
            if isinstance(result, Exception):
                result = (False, str(result), None)
            ok, message, target = result
            if not ok:
                self._going_wireless = False
                self.retry_after = 0
                self.view.toast.show_text(message, 6000)
                return
            self.cfg["wifi_target"] = target
            self.view.toast.show_text("Wi-Fi is ready. You can unplug the cable.", 4000)
            self._pending_switch = target
            self._check_devices()
        run_async(lambda: adb.enable_wifi(serial), done)

    def act_connect_wifi(self):
        dlg = ConnectDialog(self, self.cfg.get("wifi_target", ""))
        if dlg.exec() and dlg.target:
            self.cfg["wifi_target"] = dlg.target
            self._pending_switch = dlg.target if self.mode == "usb" else None
            self._check_devices()

    def act_disconnect_wifi(self):
        serial = self.serial
        self._stop_session()
        self.retry_after = time.monotonic() + 2
        run_async(lambda: adb.run(["disconnect", serial], timeout=6),
                  lambda _r: (self.view.toast.show_text("Wi-Fi phone disconnected"), self._check_devices()))

    # ============================================================== connecting

    def _session_opts(self):
        return dict(self.cfg)

    def _start_session(self, dev):
        self.connecting = True
        self.serial = dev["serial"]
        self.phone_name = self.phone_name or self._device_name(dev) or "phone"
        via = "Wi-Fi" if dev["wifi"] else "USB"
        self._set_status("busy", f"Connecting over {via}…")
        self.view.set_message(G["phone"], f"Connecting to {self.phone_name}…", "Starting the screen stream")
        s = Session(self.serial, self._session_opts(), video=True, audio=self.cfg["audio"])
        self._wire_session(s)
        self.view.session = s
        self.view.mode = "video"
        self.view.banner.dismissed.clear()
        s.set_box(*self.view.box_size())
        s.start()

    def _wire_session(self, s):
        self.session = s
        s.connected.connect(self._on_connected)
        s.failed.connect(self._on_failed)
        s.stopped.connect(self._on_stopped)
        s.frame_ready.connect(self._on_frame)
        s.video_size_changed.connect(self._on_video_size)
        s.clipboard_changed.connect(self._on_phone_clipboard)
        s.dark_changed.connect(self._on_dark)
        s.recording_finished.connect(self._on_recording_finished)

    def _stop_session(self):
        s, self.session = self.session, None
        self.view.release_all()
        self.view.session = None
        if s is not None:
            s.stop()
        self.connected = False
        self.connecting = False
        self.dark = False
        self.via_icon.hide()
        self._set_controls_enabled(False)
        self.view.banner.clear()
        self._clear_outline()
        self._update_pill()

    def _on_connected(self, name):
        if self.sender() is not self.session:
            return
        self.connecting = False
        self.connected = True
        self._set_controls_enabled(True)
        if self.mode == "usb":
            self.view.clear_message()
            wifi = ":" in (self.serial or "") or "_adb-tls" in (self.serial or "")
            self.via_icon.setText(G["wifi"] if wifi else G["usb"])
            self.via_icon.setStyleSheet(f"color: {theme.MUTED};")
            self.via_icon.setToolTip("Connected over Wi-Fi" if wifi else "Connected with the USB cable")
            self.via_icon.show()
            self._set_status("ok", "")
            self.setWindowTitle(f"PhoneCast · {self.phone_name}")
        else:
            self._set_status("ok", "HDMI picture · control over Wi-Fi")
            self.view.banner.clear("control")
        self.view.toast.show_text(f"Connected to {self.phone_name}")
        if self.session.player is None and self.cfg["audio"] and self.session.want_video:
            self.view.toast.show_text("Connected (phone sound is not available right now)", 3500)
        serial = self.serial
        self._info.pop(serial, None)       # refresh name and battery for this phone
        self._fetch_infos([{"serial": serial, "state": "device"}])
        self._poll_state()
        self.view.setFocus()

    def _on_failed(self, message):
        if self.sender() is not self.session:
            return
        self._stop_session()
        if self.mode == "capture":
            self._control_problem(message)
            return
        self.retry_after = time.monotonic() + 4
        self.view.clear_frame()
        self._set_status("bad", "Could not start mirroring")
        self.view.set_message(G["info"], "Couldn't start mirroring",
                              message + "\n\nTrying again in a few seconds…")

    def _on_stopped(self, reason):
        if self.sender() is not self.session:
            return
        self._stop_session()
        self.battery.set_level(None, False)
        if self.mode == "capture":
            self._control_problem("The Wi-Fi connection to the phone was lost.")
            return
        self.retry_after = time.monotonic() + 1
        if self._going_wireless:
            self._set_status("busy", "Switching to Wi-Fi…")
            self.view.set_message(G["wifi"], "Switching to Wi-Fi…", "Keep the cable in until it says you can unplug it.")
            return
        self._set_status("bad", "Disconnected")
        self.view.set_message(G["usb"], "Phone disconnected",
                              "Reconnect the USB cable. PhoneCast will pick it up by itself.")

    # ================================================================ picture

    def _on_box(self, w, h):
        source = self.capture if self.mode == "capture" else self.session
        if source is not None:
            source.set_box(w, h)

    def _on_frame(self):
        source = self.sender()
        if source is not self.session and source is not self.capture:
            return
        frame = source.take_frame()
        if frame is None:
            return
        if source is self.capture:
            self.view.capture_size = self.capture.frame_size
            if self.view.message is not None and self.view.message[1].startswith("Waiting for the HDMI"):
                self.view.clear_message()
        self.view.set_frame(frame)

    def _on_video_size(self, w, h):
        if self.sender() is not self.session:
            return
        portrait = h >= w
        if self._orientation != portrait:
            first = self._orientation is None
            self._orientation = portrait
            if first and not self.compact:
                self._snap_to_aspect(w, h)
            else:
                self._fit_window(w, h)

    def _snap_to_aspect(self, w, h):
        """Keep the window's size but trim it to the phone's shape (no empty side bands)."""
        if self.isFullScreen() or self.isMaximized():
            return
        vw, vh = self.view.width(), self.view.height()
        if h >= w:
            new_vw, new_vh = vh * w / h, vh
        else:
            new_vw, new_vh = vw, vw * h / w
        extra_w, extra_h = self.width() - vw, self.height() - vh
        avail = self.screen().availableGeometry()
        if new_vw + extra_w > avail.width() or new_vh + extra_h > avail.height():
            self._fit_window(w, h)
            return
        self.resize(int(round(new_vw + extra_w)), int(round(new_vh + extra_h)))

    def _update_stats(self):
        if self.mode == "capture" and self.capture is not None:
            cw, ch = self.capture.frame_size
            self.st_info.setText(f"HDMI {cw}×{ch}" if cw else "")
        elif self.view.outline is not None:
            self.st_info.setText("outline…" if self._outline_busy else "outline")
            self.st_info.setToolTip("The phone hides this screen's picture; this is an outline of it")
        elif self.connected and self.session is not None and self.session.want_video:
            w, h = self.session.video_size
            fps = self.session.current_fps()
            self.st_info.setText(f"{fps:.0f} fps" if fps >= 1 else "")
            self.st_info.setToolTip(f"Picture: {w}×{h} pixels")
        else:
            self.st_info.setText("")
        self._fit_statusbar()

    # ============================================================ phone state

    def _poll_state(self):
        if self._state_busy or not self.connected or not self.serial:
            return
        self._state_busy = True
        serial = self.serial
        run_async(lambda: adb.screen_state(serial), self._on_state)

    def _on_state(self, st):
        self._state_busy = False
        if isinstance(st, Exception) or not self.connected:
            return
        self._apply_state(st)

    def _apply_state(self, st):
        self.phone_state = st
        self.view.asleep = st.get("awake") is False
        if st.get("width"):
            self.view.phone_size = (st["width"], st["height"])
        if st.get("awake") is False:
            self._clear_outline()
        self._update_banner()
        self._update_chips()

    def _poll_battery(self):
        if not self.connected or not self.serial:
            return
        serial = self.serial

        def done(b):
            if isinstance(b, Exception) or b is None or serial != self.serial or not self.connected:
                return
            self.battery.set_level(b["level"], b["charging"])
            self._info.setdefault(serial, {})["battery"] = b
        run_async(lambda: adb.battery(serial), done)

    def _on_dark(self, dark):
        if self.sender() is not self.session:
            return
        self.dark = dark
        if dark:
            self.outline_timer.start(300)
        else:
            self._clear_outline()
        self._update_banner()
        self._poll_state()

    # ======================================================= protected screens

    def _outline_wanted(self):
        return (self.cfg["outline"] and self.connected and self.mode == "usb" and self.dark
                and self.phone_state.get("awake") is not False)

    def _screen_size(self):
        """The phone's screen size in the current orientation (what layout positions refer to)."""
        vw, vh = self.session.video_size if self.session else (0, 0)
        w, h = self.phone_state.get("width") or vw, self.phone_state.get("height") or vh
        if vw and (w > h) != (vw > vh):
            w, h = h, w
        return w, h

    def _outline_tick(self):
        if not self._outline_wanted():
            self._clear_outline()
            return
        if self._outline_busy:
            self._outline_again = True
            return
        w, h = self._screen_size()
        if not (w and h):
            self.outline_timer.start(1000)
            return
        self._outline_busy = True
        serial = self.serial
        run_async(lambda: outline.dump(serial, w, h), self._on_outline)

    def _on_outline(self, result):
        self._outline_busy = False
        if not self._outline_wanted():
            self._clear_outline()
            return
        if isinstance(result, outline.Outline):
            self.view.set_outline(result)
        self.outline_timer.start(200 if self._outline_again else 1500)
        self._outline_again = False

    def _on_user_input(self):
        # after a tap or key on a protected screen, refresh the outline soon
        if self.view.outline is not None:
            self._outline_again = True
            if not self._outline_busy:
                self.outline_timer.start(600)

    def _clear_outline(self):
        self.outline_timer.stop()
        self._outline_again = False
        if self.view.outline is not None:
            self.view.set_outline(None)

    def act_outline(self, on):
        self.cfg["outline"] = on
        if on and self.dark:
            self.outline_timer.start(0)
        elif not on:
            self._clear_outline()
        self.view.banner.clear("secure")
        self._update_banner()
        self.view.toast.show_text("Outline of protected screens on" if on else "Outline of protected screens off")

    def _update_banner(self):
        b = self.view.banner
        if not self.connected:
            return
        st = self.phone_state
        if st.get("awake") is False:
            b.show_banner("asleep", G["power"],
                          "<b>The phone's screen is off.</b> Click the picture or press a key to wake it.",
                          [("Wake up", self.act_wake)])
        elif self.mode == "usb" and self.dark and st.get("locked"):
            b.show_banner("locked", G["lock"],
                          "<b>Your phone is locked.</b> Android hides the lock screen from USB "
                          "mirroring, so it looks black here. Typing into it still works.",
                          [("Unlock with PIN", self.act_unlock)])
        elif self.mode == "usb" and self.dark and self.cfg["outline"]:
            b.show_banner("secure", G["eye"],
                          "<b>Protected screen.</b> Android hides its picture, so PhoneCast draws an "
                          "outline of its buttons and text. Click them as usual.",
                          [("Type my PIN", self.act_type_pin), ("Why?", self.act_help)], top=True)
        elif self.mode == "usb" and self.dark:
            b.show_banner("secure", G["hide"],
                          "<b>Black screen?</b> This screen may be protected by Android (passwords, "
                          "banking or payment apps, some video apps). Taps and typing still work.",
                          [("Show outline", lambda: self.b_outline.setChecked(True)), ("Why?", self.act_help)])
        elif b.kind in ("asleep", "locked", "secure"):
            b.clear()

    def _control_problem(self, message):
        self.view.banner.dismissed.discard("control")
        self.view.banner.show_banner(
            "control", G["wifi"],
            f"<b>No control over Wi-Fi.</b> The picture still works, but mouse and keyboard can't "
            f"reach the phone.<br><span style='color:{theme.MUTED}'>{message}</span>",
            [("Retry", self._retry_control), ("Back to USB", self.exit_capture)])
        self._set_status("warn", "HDMI picture · no control")

    # ================================================================ actions

    def _ctrl(self):
        s = self.session
        return s if s is not None and s.has_control and self.connected else None

    def _key(self, code):
        s = self._ctrl()
        if s:
            s.press_key(code)

    def _send(self, data):
        s = self._ctrl()
        if s:
            s.send(data)

    def act_back(self):
        self._key(P.KEYCODE_BACK)

    def act_home(self):
        self._key(P.KEYCODE_HOME)

    def act_recents(self):
        self._key(P.KEYCODE_APP_SWITCH)

    def act_notifications(self):
        self._send(P.simple(P.EXPAND_NOTIFICATION_PANEL))

    def act_quick_settings(self):
        self._send(P.simple(P.EXPAND_SETTINGS_PANEL))

    def act_volume_up(self):
        self._key(P.KEYCODE_VOLUME_UP)

    def act_volume_down(self):
        self._key(P.KEYCODE_VOLUME_DOWN)

    def act_power(self):
        self._key(P.KEYCODE_POWER)
        QTimer.singleShot(900, self._poll_state)

    def act_rotate(self):
        self._send(P.simple(P.ROTATE_DEVICE))

    def act_wake(self):
        self._key(P.KEYCODE_WAKEUP)
        self.view.asleep = False
        self.phone_state["awake"] = None
        self.view.banner.clear("asleep")
        QTimer.singleShot(800, self._poll_state)

    def _update_unlock_tip(self):
        extra = "\nOn an unlocked phone: types your PIN into a protected PIN box (bank, UPI, Verify it's you)"
        if self.cfg.get("pin_blob"):
            self.b_unlock.setToolTip("Unlock with your saved PIN   (Ctrl+Alt+U)" + extra +
                                     "\nShift+click to change the saved PIN")
        else:
            self.b_unlock.setToolTip("Unlock with PIN   (Ctrl+Alt+U)" + extra)

    def act_unlock(self):
        if not self.connected:
            return
        if self.phone_state.get("locked") is False and not (QGuiApplication.keyboardModifiers() & Qt.ShiftModifier):
            self.act_type_pin()
            return
        pin = remembered_pin(self.cfg)
        shift = QGuiApplication.keyboardModifiers() & Qt.ShiftModifier
        if not pin or shift:
            dlg = UnlockDialog(self, pin)
            if not dlg.exec():
                return
            pin = dlg.pin.text()
            self.cfg["pin_blob"] = settings.protect(pin) if dlg.remember.isChecked() else ""
            settings.save(self.cfg)
            self._update_unlock_tip()
        if pin:
            self._do_unlock(pin)

    def _do_unlock(self, pin):
        serial, session = self.serial, self._ctrl()
        self.view.toast.show_text("Unlocking…", 5000)

        def work():
            st = adb.screen_state(serial)
            adb.shell(serial, "input keyevent 224")       # wake up
            if st.get("locked") is False:
                # never type the PIN into an unlocked phone (it would land in some app)
                return "already", st
            time.sleep(0.4)
            adb.shell(serial, "wm dismiss-keyguard")       # brings up the PIN pad
            time.sleep(0.9)
            if session is not None:
                session.type_text(pin)
                time.sleep(0.25)
                session.press_key(P.KEYCODE_ENTER)
            else:
                adb.shell(serial, "input text " + adb.quote(pin))
                adb.shell(serial, "input keyevent 66")
            time.sleep(1.4)
            return "typed", adb.screen_state(serial)
        run_async(work, self._unlock_done)

    def _unlock_done(self, result):
        if isinstance(result, Exception):
            self.view.toast.show_text(f"Could not unlock: {result}", 4000)
            return
        what, st = result
        if what == "already":
            self.view.toast.show_text("The phone is already unlocked")
        elif st.get("locked") is False:
            self.view.toast.show_text("Unlocked")
        else:
            self.view.toast.show_text("Still locked. Check the PIN, or type it yourself and press Enter.", 5000)
        if self.connected:
            self._apply_state(st)

    def act_type_pin(self):
        """Type a PIN into a protected PIN box, or tap it on an on-screen number pad."""
        session = self._ctrl()
        if session is None or not session.want_video:
            return
        if self.phone_state.get("locked"):
            self.act_unlock()
            return
        dlg = TypePinDialog(self, remembered_pin(self.cfg))
        if not dlg.exec():
            return
        pin, press_enter = dlg.pin.text(), dlg.press_enter.isChecked()
        serial = self.serial
        (vw, vh), (w, h) = session.video_size, self._screen_size()
        self.view.toast.show_text("Looking for the PIN box…", 8000)

        def tap(node):
            x, y = int(node.center[0] * vw / w), int(node.center[1] * vh / h)
            session.send(P.inject_touch(P.ACTION_DOWN, P.POINTER_FINGER, x, y, vw, vh, 1.0))
            time.sleep(0.05)
            session.send(P.inject_touch(P.ACTION_UP, P.POINTER_FINGER, x, y, vw, vh, 0.0))

        def work():
            target = outline.pin_target(outline.dump(serial, w, h, attempts=2), pin)
            if target is None:
                return "none"
            kind, where = target
            if kind == "field":
                if not where.focused:
                    tap(where)
                    time.sleep(0.4)
                session.type_text(pin)
                if press_enter:
                    time.sleep(0.2)
                    session.press_key(P.KEYCODE_ENTER)
                return "typed"
            for digit in pin:
                tap(where[digit])
                time.sleep(0.15)
            return "tapped"

        def done(result):
            messages = {
                "typed": "PIN typed into the PIN box",
                "tapped": "PIN entered on the on-screen number keys",
                "none": "No PIN box or number keys found on this screen. Click “Use PIN” or the "
                        "PIN box first, or just type the PIN on your keyboard.",
            }
            text = messages.get(result, f"Could not type the PIN: {result}")
            self.view.toast.show_text(text, 5000 if result == "none" else 2500)
            self._on_user_input()
        run_async(work, done)

    def act_mouse(self, on):
        self.view.mouse_enabled = on
        if not on:
            self.view.release_all()
        self.cfg["mouse"] = on
        self._update_chips()
        self.view.toast.show_text("Mouse control on" if on else "Mouse control off   (Ctrl+Alt+M to turn on)")

    def act_keyboard(self, on):
        self.view.keyboard_enabled = on
        if not on:
            self.view.release_all()
        self.cfg["keyboard"] = on
        self._update_chips()
        self.view.toast.show_text("Keyboard control on" if on else "Keyboard control off   (Ctrl+Alt+K to turn on)")

    def _on_blocked(self, kind):
        now = time.monotonic()
        if now - self._last_blocked_hint < 3:
            return
        self._last_blocked_hint = now
        if kind == "mouse":
            self.view.toast.show_text("Mouse control is off. Press Ctrl+Alt+M to turn it on", 2600)
        else:
            self.view.toast.show_text("Keyboard control is off. Press Ctrl+Alt+K to turn it on", 2600)

    def act_sound(self, on):
        self.cfg["muted"] = not on
        if self.session is not None:
            self.session.set_muted(not on)
        if self.capture is not None:
            self.capture.set_muted(not on)
        self.view.toast.show_text("Sound on" if on else "Sound muted")

    def act_screen_off(self, on):
        self.cfg["screen_off"] = on
        self._send(P.set_display_power(not on))
        self.view.toast.show_text("Phone's own screen turned off" if on else "Phone's own screen turned on")

    # ------------------------------------------------------------ screenshots

    def _grab_image(self):
        if self.mode == "capture" and self.capture is not None and self.capture.last_image is not None:
            return self.capture.last_image.copy()
        if self.session is not None:
            return self.session.snapshot()
        return None

    def act_screenshot(self):
        if QGuiApplication.keyboardModifiers() & Qt.ShiftModifier:
            self.act_copy_screenshot()
            return
        img = self._grab_image()
        if img is None:
            self.view.toast.show_text("Nothing to capture yet")
            return
        path = pictures_dir() / f"Screenshot {datetime.now():%Y-%m-%d %H-%M-%S}.png"
        run_async(lambda: img.save(str(path)),
                  lambda ok: self.view.toast.show_text(
                      "Screenshot saved in Pictures › PhoneCast" if ok is True else "Could not save the screenshot"))

    def act_copy_screenshot(self):
        img = self._grab_image()
        if img is None:
            self.view.toast.show_text("Nothing to capture yet")
            return
        QGuiApplication.clipboard().setImage(img)
        self.view.toast.show_text("Screenshot copied to the clipboard")

    # -------------------------------------------------------------- recording

    def act_record(self):
        s = self.session
        if self.mode == "capture":
            self.view.toast.show_text("Recording works over USB or Wi-Fi mirroring, not in HDMI mode")
            return
        if s is None or not self.connected or not s.want_video:
            self.view.toast.show_text("Connect the phone first")
            return
        if s.recorder is not None:
            s.stop_recording("user")
            return
        path = videos_dir() / f"Recording {datetime.now():%Y-%m-%d %H-%M-%S}.mp4"
        error = s.start_recording(path)
        if error:
            self.view.toast.show_text(error)
            return
        self._set_recording(True)
        self.view.toast.show_text("Recording the screen. Press Ctrl+Alt+V again to stop")

    def _set_recording(self, on):
        self.b_record.set_flag("recording", on)
        self.b_record.setText(G["stop"] if on else G["record"])
        self.b_record.setToolTip("Stop recording   (Ctrl+Alt+V)" if on else
                                 "Record the screen to Videos\\PhoneCast   (Ctrl+Alt+V)")
        self.rec_pill.setVisible(on)
        if on:
            self._update_rec()
            self.rec_timer.start()
        else:
            self.rec_timer.stop()
        self._fit_statusbar()

    def _update_rec(self):
        rec = self.session.recorder if self.session is not None else None
        if rec is None:
            return
        secs = int(rec.elapsed)
        self.rec_pill.setText(f"● {secs // 60:02d}:{secs % 60:02d}")
        self.rec_pill.setToolTip("Recording the screen. Ctrl+Alt+V stops it")

    def _on_recording_finished(self, path, saved, reason):
        self._set_recording(False)
        if saved:
            first = "Recording stopped because the picture changed size. " if reason == "resized" else ""
            self.view.toast.show_text(first + "Recording saved in Videos › PhoneCast", 4000)
        elif reason.startswith("error"):
            self.view.toast.show_text("Recording failed: " + reason[7:], 5000)
        else:
            self.view.toast.show_text("Recording stopped: nothing was recorded", 3000)

    def open_folder(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ----------------------------------------------------------------- window

    def act_on_top(self, on):
        self.cfg["always_on_top"] = on
        if not self.compact:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
            self.show()
            theme.dark_titlebar(self)

    def _set_chrome(self, visible):
        """Show or hide the dock and bottom bar (full screen and compact mode hide them)."""
        self.hide_sidebar_timer.stop()
        self.sidebar.setVisible(visible)
        self.statusbar.setVisible(visible)
        self.view.edge_reveal = not visible

    def act_fullscreen(self):
        if self.isFullScreen():
            self._set_chrome(not self.compact)
            if self.compact:
                self.showNormal()
            else:
                self.showMaximized() if self._was_maximized else self.showNormal()
            self.b_full.setText(G["fullscreen"])
        else:
            if self.compact:
                self.act_compact()
            self._was_maximized = self.isMaximized()
            self._set_chrome(False)
            self.showFullScreen()
            self.b_full.setText(G["exit_fullscreen"])
            self.view.toast.show_text("Full screen. Press F11 to exit; move the mouse to the right edge for buttons", 3500)
        self.view.setFocus()

    def act_compact(self):
        if self.isFullScreen():
            self.act_fullscreen()
        if not self.compact:
            self._compact_geo = self.saveGeometry()
            self.compact = True
            if self.isMaximized():
                self.showNormal()
            self._set_chrome(False)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.show()
            theme.dark_titlebar(self)
            w, h = self.session.video_size if self.session and self.session.video_size[0] else (1080, 2340)
            self._compact_resize(w, h, corner=True)
            # Windows re-creates the window when the on-top flag changes; size it again once that settled
            QTimer.singleShot(60, lambda: self.compact and self._compact_resize(w, h, corner=True))
            self.b_compact.setText(G["expand"])
            self.view.toast.show_text("Compact window · Ctrl+Alt+I to exit", 3000)
        else:
            self.compact = False
            self._set_chrome(True)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, self.cfg["always_on_top"])
            self.show()
            theme.dark_titlebar(self)
            if self._compact_geo is not None:
                self.restoreGeometry(self._compact_geo)
            self.b_compact.setText(G["compact"])
        self.view.setFocus()

    def _compact_resize(self, w, h, corner=False):
        avail = self.screen().availableGeometry()
        if h >= w:
            vh = int(avail.height() * 0.46)
            vw = int(vh * w / h)
        else:
            vw = int(avail.width() * 0.34)
            vh = int(vw * h / w)
        self.resize(vw, vh)
        if corner:
            geo = self.frameGeometry()
            self.move(avail.right() - geo.width() - 24, avail.bottom() - geo.height() - 24)

    def _reveal_sidebar(self):
        if (self.isFullScreen() or self.compact) and not self.sidebar.isVisible():
            self.sidebar.show()
            self.hide_sidebar_timer.start()

    def _maybe_hide_sidebar(self):
        if not (self.isFullScreen() or self.compact):
            self.hide_sidebar_timer.stop()
        elif not self.sidebar.underMouse() and not QApplication.activePopupWidget():
            self.sidebar.hide()
            self.hide_sidebar_timer.stop()

    def act_settings(self):
        dlg = SettingsDialog(self, self.cfg, bool(self.cfg.get("pin_blob")))
        if not dlg.exec():
            self._restyle()
            return
        old = dict(self.cfg)
        new = dlg.values()
        if dlg.forget_pin:
            new["pin_blob"] = ""
        self.cfg.update(new)
        settings.save(self.cfg)
        self._update_unlock_tip()
        self.view.right_click_back = self.cfg["right_click_back"]
        theme.set_accent(self.cfg.get("accent"))
        theme.apply(QApplication.instance())
        self._restyle()
        if old["screen_off"] != self.cfg["screen_off"]:
            self.b_screen_off.setChecked(self.cfg["screen_off"])
        if old["outline"] != self.cfg["outline"]:
            self.b_outline.setChecked(self.cfg["outline"])
        if self.mode == "usb" and self.session is not None and any(old[k] != self.cfg[k] for k in RESTART_KEYS):
            self._stop_session()
            self.retry_after = 0
            self.view.set_message(G["refresh"], "Applying settings…")
            self._check_devices()

    def _restyle(self):
        """Repaint the pieces that hold colours themselves after an accent change."""
        self._update_chips()
        self._update_pill()
        self.view.update()

    def act_help(self):
        HelpDialog(self).exec()

    def act_more(self):
        menu = QMenu(self)
        c = self.connected
        recording = self.session is not None and self.session.recorder is not None
        menu.addAction(theme.glyph_icon(G["search"], theme.MUTED), "Search actions…	Ctrl+K", self.act_palette)
        menu.addAction(theme.glyph_icon(G["devices"], theme.MUTED), "Phones…	Ctrl+Alt+D", self.act_devices)
        menu.addSeparator()
        menu.addAction(theme.glyph_icon(G["download"], theme.MUTED), "Send files to the phone…",
                       self.pick_files).setEnabled(c)
        menu.addAction(theme.glyph_icon(G["photo"], theme.MUTED), "Copy phone photos && videos here",
                       self.copy_photos).setEnabled(c)
        menu.addAction(theme.glyph_icon(G["stop"] if recording else G["record"], theme.MUTED),
                       "Stop recording" if recording else "Record the screen", self.act_record).setEnabled(c)
        menu.addAction(theme.glyph_icon(G["copy"], theme.MUTED), "Copy a screenshot",
                       self.act_copy_screenshot).setEnabled(c)
        menu.addSeparator()
        menu.addAction(theme.glyph_icon(G["open_folder"], theme.MUTED), "Open screenshots folder",
                       lambda: self.open_folder(pictures_dir()))
        menu.addAction(theme.glyph_icon(G["open_folder"], theme.MUTED), "Open recordings folder",
                       lambda: self.open_folder(videos_dir()))
        menu.addSeparator()
        menu.addAction(theme.glyph_icon(G["refresh"], theme.MUTED), "Reconnect", self.reconnect)
        menu.addAction(theme.glyph_icon(G["help"], theme.MUTED), "Help && shortcuts	F1", self.act_help)
        hint = menu.sizeHint()
        corner = self.b_more.mapToGlobal(QPoint(0, self.b_more.height()))
        menu.exec(QPoint(corner.x() - hint.width() - 6, corner.y() - hint.height()))

    def _commands(self):
        c = self.connected
        rec = self.session is not None and self.session.recorder is not None
        usb_now = c and self.mode == "usb" and self.serial and ":" not in self.serial and "_adb-tls" not in self.serial
        return [
            ("Switch phone…", "Ctrl+Alt+D", self.act_devices, True, "devices phones switch change"),
            ("Back", "Ctrl+Alt+B", self.act_back, c, ""),
            ("Home", "Ctrl+Alt+H", self.act_home, c, ""),
            ("Recent apps", "Ctrl+Alt+R", self.act_recents, c, "app switcher multitask"),
            ("Open notifications", "", self.act_notifications, c, ""),
            ("Open quick settings", "", self.act_quick_settings, c, "toggles"),
            ("Volume up", "", self.act_volume_up, c, "louder"),
            ("Volume down", "", self.act_volume_down, c, "quieter"),
            ("Power button", "", self.act_power, c, "lock wake sleep"),
            ("Rotate the phone", "", self.act_rotate, c, "landscape portrait"),
            ("Unlock with PIN", "Ctrl+Alt+U", self.act_unlock, c, "password"),
            ("Type my PIN", "Ctrl+Alt+P", self.act_type_pin, c, "bank upi verify"),
            ("Stop recording" if rec else "Record the screen", "Ctrl+Alt+V", self.act_record, c,
             "video capture mp4"),
            ("Take a screenshot", "Ctrl+Alt+S", self.act_screenshot, c, "picture capture png"),
            ("Copy a screenshot", "Ctrl+Alt+C", self.act_copy_screenshot, c, "clipboard picture"),
            ("Mouse control on / off", "Ctrl+Alt+M", self.b_mouse.toggle, True, "touchpad"),
            ("Keyboard control on / off", "Ctrl+Alt+K", self.b_keyboard.toggle, True, "typing"),
            ("Sound on / off", "", self.b_sound.toggle, True, "mute audio"),
            ("Phone's own screen off / on", "", self.b_screen_off.toggle, c, "battery display"),
            ("Outline of protected screens on / off", "Ctrl+Alt+O", self.b_outline.toggle, True, "black secure"),
            ("Full screen", "F11", self.act_fullscreen, True, ""),
            ("Compact window", "Ctrl+Alt+I", self.act_compact, True, "mini small picture in picture"),
            ("Keep the window on top", "", self.b_top.toggle, True, "pin always"),
            ("Send files to the phone…", "", self.pick_files, c, "upload push apk install"),
            ("Copy phone photos & videos here", "", self.copy_photos, c, "dcim pull gallery"),
            ("Open screenshots folder", "", lambda: self.open_folder(pictures_dir()), True, "pictures"),
            ("Open recordings folder", "", lambda: self.open_folder(videos_dir()), True, "videos"),
            ("Continue over Wi-Fi", "", self.act_go_wireless, bool(usb_now), "wireless unplug"),
            ("Connect over Wi-Fi…", "", self.act_connect_wifi, True, "wireless address ip"),
            ("Pair over Wi-Fi…", "", lambda: PairDialog(self).exec(), True, "wireless debugging code"),
            ("HDMI capture mode", "", self.act_capture, True, "capture card tv"),
            ("Reconnect", "", self.reconnect, True, "restart"),
            ("Settings", "", self.act_settings, True, "preferences options accent colour color quality"),
            ("Help & shortcuts", "F1", self.act_help, True, "keyboard"),
        ]

    def act_palette(self):
        commands = [(t, h, (lambda cb=cb: QTimer.singleShot(0, cb)), e, k)
                    for t, h, cb, e, k in self._commands()]
        CommandPalette(self, commands).exec()
        self.view.setFocus()

    def reconnect(self):
        if self.mode == "capture":
            self._retry_control()
            return
        self._stop_session()
        self.retry_after = 0
        self.view.set_message(G["refresh"], "Reconnecting…")
        self._check_devices()

    # ======================================================== files & photos

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Send files to the phone")
        if paths:
            self.send_files(paths)

    def send_files(self, paths):
        if not self.connected or not self.serial:
            self.view.toast.show_text("Connect the phone first")
            return
        serial, session = self.serial, self._ctrl()
        self.view.toast.show_text(f"Sending {len(paths)} file(s) to the phone…", 60000)

        def work():
            done, failed = [], []
            for p in paths:
                name = Path(p).name
                if p.lower().endswith(".apk"):
                    code, out = adb.run(["install", "-r", p], serial=serial, timeout=600)
                    (done if "Success" in out else failed).append(name)
                elif Path(p).is_file():
                    dest = "/sdcard/Download/" + name
                    code, out = adb.run(["push", p, dest], serial=serial, timeout=1800)
                    if code == 0:
                        done.append(name)
                        if session is not None:
                            session.send(P.scan_file(dest))
                    else:
                        failed.append(name)
                else:
                    failed.append(name)
            return done, failed

        def finished(result):
            if isinstance(result, Exception):
                self.view.toast.show_text(f"Sending failed: {result}", 4000)
                return
            done, failed = result
            msg = f"Sent {len(done)} file(s) to the phone's Download folder" if done else ""
            if failed:
                msg += ("  ·  " if msg else "") + "Failed: " + ", ".join(failed)
            self.view.toast.show_text(msg, 4000)
        run_async(work, finished)

    def copy_photos(self):
        serial = self.serial
        dest = pictures_dir("Phone photos")
        self.view.toast.show_text("Copying photos and videos from the phone… this can take a while", 3_600_000)
        previous = self._status
        self._set_status("busy", "Copying photos to Pictures › PhoneCast › Phone photos…")

        def finished(result):
            ok = not isinstance(result, Exception) and result[0] == 0
            self.view.toast.show_text("Photos and videos copied" if ok else "Copying stopped with an error", 4000)
            if self.connected:
                self._set_status(*previous)
            self.open_folder(dest)
        run_async(lambda: adb.run(["pull", "-a", "/sdcard/DCIM/", str(dest)], serial=serial, timeout=None), finished)

    def _on_phone_clipboard(self, text):
        if self.sender() is self.session and text:
            QGuiApplication.clipboard().setText(text)
            self.view.toast.show_text("Copied from the phone")

    # =========================================================== HDMI capture

    def act_capture(self):
        if self.mode == "capture":
            self.exit_capture()
            return
        self.b_capture.setChecked(False)
        usb = self.serial if self.connected and self.serial and ":" not in self.serial else None
        if usb is None:
            usb = next((d["serial"] for d in adb.devices() if d["state"] == "device" and not d["wifi"]), None)
        dlg = CaptureDialog(self, self.cfg, usb)
        if not dlg.exec():
            return
        vals = dlg.result_values()
        if vals["video"] is None or not vals["target"]:
            return
        self.cfg["capture_video"] = vals["video_name"]
        self.cfg["capture_audio"] = vals["audio_name"]
        settings.save(self.cfg)
        self.enter_capture(vals)

    def enter_capture(self, vals):
        self._stop_session()
        self.mode = "capture"
        self.b_capture.setChecked(True)
        self.view.mode = "capture"
        self.view.clear_frame()
        self.view.set_message(G["hdmi"], "Waiting for the HDMI picture…",
                              "Check: phone → HDMI adapter → capture card → computer.")
        self._set_status("busy", "HDMI capture mode")
        cap = CaptureSource(vals["video"], vals["audio"])
        cap.frame_ready.connect(self._on_frame)
        cap.error.connect(self._on_capture_error)
        cap.set_muted(self.cfg["muted"])
        cap.set_box(*self.view.box_size())
        self.capture = cap
        cap.start()
        self.serial = vals["target"]
        self._retry_control()

    def _retry_control(self):
        if self.mode != "capture":
            return
        self._stop_session()
        self.view.banner.clear("control")
        target = self.serial
        self._set_status("busy", "HDMI picture · connecting control over Wi-Fi…")

        def prepare():
            if any(d["serial"] == target and d["state"] == "device" for d in adb.devices()):
                return True, ""
            return adb.connect_wifi(target)

        def go(result):
            if self.mode != "capture" or target != self.serial:
                return
            if isinstance(result, Exception) or not result[0]:
                self._control_problem(str(result if isinstance(result, Exception) else result[1]))
                return
            s = Session(target, self._session_opts(), video=False, audio=False, control=True)
            self._wire_session(s)
            self.view.session = s
            self.connecting = True
            s.start()
        run_async(prepare, go)

    def _on_capture_error(self, text):
        self.view.set_message(G["hdmi"], "The capture card stopped", text)

    def exit_capture(self):
        if self.capture is not None:
            self.capture.stop()
            self.capture.deleteLater()
            self.capture = None
        self._stop_session()
        self.mode = "usb"
        self.b_capture.setChecked(False)
        self.view.mode = "video"
        self.view.clear_frame()
        self.view.set_message(G["usb"], "Looking for your phone…")
        self.retry_after = 0
        self._check_devices()

    # ================================================================ status

    def _set_controls_enabled(self, on):
        for b in self.control_buttons:
            b.setEnabled(on)

    def _set_status(self, level, text):
        self._status = (level, text)
        self.st_text.setText(text)
        self.st_text.setVisible(bool(text))     # an empty label would still take the fps counter's room
        self._update_pill()
        self._fit_statusbar()

    def _update_chips(self):
        locked = self.connected and self.phone_state.get("locked")
        self.chip_lock.setVisible(bool(locked))

    # ================================================================ window

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, e):
        super().showEvent(e)
        theme.dark_titlebar(self)

    def eventFilter(self, obj, e):
        if obj is getattr(self, "statusbar", None) and e.type() == QEvent.Resize:
            QTimer.singleShot(0, self._fit_statusbar)
        if obj is getattr(self, "sidebar", None):
            if e.type() == QEvent.Leave and (self.isFullScreen() or self.compact):
                self.hide_sidebar_timer.start()
            elif e.type() == QEvent.Resize:
                self._size_side_buttons(e.size().height())
        return False

    def _size_side_buttons(self, height):
        """Shrink the dock buttons a little on short windows so all of them stay visible."""
        n = len(self.side_buttons)
        fixed = 12 + 4 + self.side_seps * 12 + (n + self.side_seps) * 2
        h = max(24, min(34, (height - fixed) // n))
        for b in self.side_buttons:
            b.setFixedHeight(h)

    def closeEvent(self, e):
        if self.compact and self._compact_geo is not None:
            self.cfg["geometry"] = bytes(self._compact_geo.toBase64()).decode("ascii")
        elif not self.isFullScreen():
            self.cfg["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
        settings.save(self.cfg)
        if self.capture is not None:
            self.capture.stop()
        self._stop_session()
        super().closeEvent(e)


class _DarkDialogs(QObject):
    """Gives every dialog a dark title bar."""

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Show and isinstance(obj, QDialog):
            theme.dark_titlebar(obj)
        return False


def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PhoneCast.App")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("PhoneCast")
    app.setStyle("Fusion")
    theme.set_accent(settings.load().get("accent"))
    theme.apply(app)
    app.setWindowIcon(theme.app_icon())

    # One window only: a second launch just brings the first one forward
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE_KEY)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    tasks.init()
    dark = _DarkDialogs()
    app.installEventFilter(dark)
    win = MainWindow()
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.bring_to_front()))
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
