"""Settings, unlock, HDMI capture setup, Wi-Fi, command palette and help dialogs."""

from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QStackedWidget, QStyle,
                               QStyledItemDelegate, QTextBrowser, QToolButton, QVBoxLayout,
                               QWidget)

from . import adb, capture, settings, theme
from .tasks import run_async
from .theme import G, glyph_icon
from .widgets import AccentPicker, Switch


def _buttons(dialog, ok_text, ok_slot=None):
    row = QHBoxLayout()
    row.addStretch(1)
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text, objectName="Primary")
    ok.setDefault(True)
    ok.clicked.connect(ok_slot or dialog.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row, ok


def _heading(text, sub=None):
    box = QVBoxLayout()
    box.setSpacing(6)
    box.addWidget(QLabel(text, objectName="H1"))
    if sub:
        s = QLabel(sub, objectName="Muted", wordWrap=True)
        s.setTextFormat(Qt.RichText)
        box.addWidget(s)
    return box


def _status_html(ok, text):
    return f"<span style='color:{theme.GOOD if ok else theme.BAD}'>{text}</span>"


class Card(QFrame):
    """A rounded group of rows with hairlines between them (an inset list)."""

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(14, 4, 14, 4)
        self._lay.setSpacing(0)
        self._rows = 0
        self.title = title

    def add(self, widget_or_layout):
        if self._rows:
            self._lay.addWidget(QFrame(objectName="RowSep"))
        holder = QWidget()
        h = QVBoxLayout(holder)
        h.setContentsMargins(0, 7, 0, 7)
        if isinstance(widget_or_layout, QWidget):
            h.addWidget(widget_or_layout)
        else:
            h.addLayout(widget_or_layout)
        self._lay.addWidget(holder)
        self._rows += 1
        return widget_or_layout

    def add_field(self, label, widget, detail=""):
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(QLabel(label))
        if detail:
            col.addWidget(QLabel(detail, objectName="Muted"))
        row.addLayout(col, 1)
        widget.setMinimumWidth(230)
        row.addWidget(widget)
        return self.add(row)


def _section(layout, title, card):
    if title:
        lab = QLabel(title, objectName="Muted")
        lab.setStyleSheet("font-size: 9pt; font-weight: 600; padding: 10px 4px 4px 4px;")
        layout.addWidget(lab)
    layout.addWidget(card)


# ======================================================================= PIN dialogs

class PinDialog(QDialog):
    def __init__(self, parent, title, heading, text, prefill, ok_text, remember_box, enter_box):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)
        lay.addLayout(_heading(heading, text))
        self.pin = QLineEdit(placeholderText="PIN or password…")
        self.pin.setEchoMode(QLineEdit.Password)
        show = self.pin.addAction(glyph_icon(G["eye"], theme.MUTED), QLineEdit.TrailingPosition)
        show.setToolTip("Show / hide")
        show.triggered.connect(lambda: self.pin.setEchoMode(
            QLineEdit.Normal if self.pin.echoMode() == QLineEdit.Password else QLineEdit.Password))
        self.pin.setText(prefill)
        lay.addWidget(self.pin)
        self.remember = self.press_enter = None
        if remember_box or enter_box:
            card = Card()
            if remember_box:
                self.remember = card.add(Switch("Remember on this computer",
                                                "Encrypted with your Windows login"))
                self.remember.setChecked(bool(prefill))
            if enter_box:
                self.press_enter = card.add(Switch("Press Enter after typing", "Confirms most PIN screens"))
                self.press_enter.setChecked(True)
            lay.addWidget(card)
        row, ok = _buttons(self, ok_text)
        self.pin.textChanged.connect(lambda t: ok.setEnabled(bool(t)))
        ok.setEnabled(bool(prefill))
        lay.addLayout(row)


class UnlockDialog(PinDialog):
    def __init__(self, parent, remembered):
        super().__init__(
            parent, "Unlock phone", "Unlock your phone",
            "Type your PIN or password. PhoneCast wakes the phone, opens the lock screen and "
            "types it for you.<br><br>The lock screen itself stays black over USB: Android "
            "hides it from any screen capture for your privacy. Typing into it still works.",
            remembered, "Unlock", remember_box=True, enter_box=False)


class TypePinDialog(PinDialog):
    def __init__(self, parent, remembered):
        saved = ("Your saved phone PIN is filled in. For a bank or UPI PIN, type that one "
                 "instead: it is not saved." if remembered else
                 "Type your phone PIN, or a bank or UPI PIN. It is not saved.")
        super().__init__(
            parent, "Type my PIN", "Type a PIN into this screen",
            "PhoneCast types it into the PIN box on the phone's screen, or taps the on-screen "
            "number keys. It never types into ordinary text boxes, so a PIN can't land in a "
            "chat by mistake.<br><br>" + saved,
            remembered, "Type it", remember_box=False, enter_box=True)


# ========================================================================== Settings

class SettingsDialog(QDialog):
    RESOLUTIONS = [("Phone's full resolution (sharpest)", 0), ("1920 pixels", 1920),
                   ("1600 pixels", 1600), ("1280 pixels (lighter on the computer)", 1280),
                   ("1024 pixels", 1024)]
    FPS = [("30 fps", 30), ("60 fps (smooth)", 60), ("90 fps", 90), ("120 fps (smoothest)", 120)]
    BITRATES = [("Standard, 8 Mbps", 8), ("High, 12 Mbps", 12), ("Very high, 20 Mbps", 20),
                ("Maximum, 32 Mbps", 32)]
    CODECS = [("H.264 (most compatible)", "h264"), ("H.265 (sharper, a bit more CPU)", "h265")]
    TABS = [("General", G["settings"]), ("Picture", G["video"]), ("Sound", G["speaker"]),
            ("Appearance", G["color"])]

    def __init__(self, parent, cfg, has_pin):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        self.cfg = dict(cfg)
        self._orig_accent = theme.ACCENT
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(10)

        # macOS-style tab strip: an icon over a label
        strip = QHBoxLayout()
        strip.setSpacing(4)
        strip.addStretch(1)
        self.stack = QStackedWidget()
        self.tab_group = QButtonGroup(self)
        for i, (name, glyph) in enumerate(self.TABS):
            b = QToolButton(objectName="TabButton")
            b.setText(name)
            b.setIcon(glyph_icon(glyph, theme.TEXT, 40))
            b.setIconSize(QSize(20, 20))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setMinimumWidth(78)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self.stack.setCurrentIndex(i))
            self.tab_group.addButton(b, i)
            strip.addWidget(b)
        strip.addStretch(1)
        lay.addLayout(strip)
        lay.addWidget(self.stack, 1)

        self.stack.addWidget(self._general(cfg, has_pin))
        self.stack.addWidget(self._picture(cfg))
        self.stack.addWidget(self._sound(cfg))
        self.stack.addWidget(self._appearance(cfg))
        self.tab_group.button(0).setChecked(True)

        row, _ = _buttons(self, "Save")
        lay.addLayout(row)

    @staticmethod
    def _page():
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        return page, v

    def _general(self, cfg, has_pin):
        page, v = self._page()
        phone = Card()
        self.keep_awake = phone.add(Switch("Keep the phone awake", "While it is connected"))
        self.wake = phone.add(Switch("Wake the screen when connecting"))
        self.screen_off = phone.add(Switch("Turn the phone's own screen off", "Saves battery; the picture here keeps working"))
        self.touches = phone.add(Switch("Show taps", "A dot where you click, on the picture"))
        _section(v, "Phone", phone)

        other = Card()
        self.outline = other.add(Switch("Outline protected screens", "Draws buttons and text over black (secure) screens"))
        self.rclick = other.add(Switch("Right-click goes Back", "Middle-click goes Home"))
        _section(v, "Controls", other)

        self.keep_awake.setChecked(cfg["keep_awake"])
        self.wake.setChecked(cfg["wake_on_connect"])
        self.screen_off.setChecked(cfg["screen_off"])
        self.touches.setChecked(cfg["show_touches"])
        self.outline.setChecked(cfg["outline"])
        self.rclick.setChecked(cfg["right_click_back"])

        self.forget_pin = False
        if has_pin:
            pin = Card()
            row = QHBoxLayout()
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(QLabel("Saved PIN"))
            col.addWidget(QLabel("Used for one-click unlock", objectName="Muted"))
            row.addLayout(col, 1)
            b = QPushButton("Forget")
            b.clicked.connect(lambda: (setattr(self, "forget_pin", True), b.setEnabled(False),
                                       b.setText("Will be forgotten")))
            row.addWidget(b)
            pin.add(row)
            _section(v, "Privacy", pin)
        v.addStretch(1)
        return page

    def _picture(self, cfg):
        page, v = self._page()
        card = Card()
        self.res = self._combo(self.RESOLUTIONS, cfg["max_size"])
        self.fps = self._combo(self.FPS, cfg["max_fps"])
        self.bitrate = self._combo(self.BITRATES, cfg["bitrate_mbps"])
        self.codec = self._combo(self.CODECS, cfg["codec"])
        card.add_field("Resolution", self.res)
        card.add_field("Smoothness", self.fps)
        card.add_field("Quality", self.bitrate)
        card.add_field("Video format", self.codec)
        _section(v, "Picture", card)
        note = QLabel("Screen recordings use the same quality: they save the phone's own video "
                      "stream without re-encoding it.", objectName="Muted", wordWrap=True)
        note.setContentsMargins(4, 8, 4, 0)
        v.addWidget(note)
        v.addStretch(1)
        return page

    def _sound(self, cfg):
        page, v = self._page()
        card = Card()
        self.audio = card.add(Switch("Play the phone's sound here"))
        self.audio_dup = card.add(Switch("Keep playing on the phone's speaker too"))
        self.audio.setChecked(cfg["audio"])
        self.audio_dup.setChecked(cfg["audio_dup"])
        _section(v, "Sound", card)
        v.addStretch(1)
        return page

    def _appearance(self, cfg):
        page, v = self._page()
        card = Card()
        row = QHBoxLayout()
        row.addWidget(QLabel("Accent colour"), 1)
        self.accent = AccentPicker(cfg.get("accent") or theme.ACCENTS[0][1])
        self.accent.changed.connect(self._preview_accent)
        row.addWidget(self.accent)
        card.add(row)
        _section(v, "Appearance", card)
        v.addStretch(1)
        return page

    def _preview_accent(self, color):
        theme.set_accent(color)
        theme.apply(QApplication.instance())

    def reject(self):
        if theme.ACCENT != self._orig_accent:
            self._preview_accent(self._orig_accent)
        super().reject()

    @staticmethod
    def _combo(items, current):
        c = QComboBox()
        for label, value in items:
            c.addItem(label, value)
        i = c.findData(current)
        c.setCurrentIndex(i if i >= 0 else 0)
        return c

    def values(self):
        c = self.cfg
        c["max_size"] = self.res.currentData()
        c["max_fps"] = self.fps.currentData()
        c["bitrate_mbps"] = self.bitrate.currentData()
        c["codec"] = self.codec.currentData()
        c["audio"] = self.audio.isChecked()
        c["audio_dup"] = self.audio_dup.isChecked()
        c["keep_awake"] = self.keep_awake.isChecked()
        c["wake_on_connect"] = self.wake.isChecked()
        c["screen_off"] = self.screen_off.isChecked()
        c["show_touches"] = self.touches.isChecked()
        c["right_click_back"] = self.rclick.isChecked()
        c["outline"] = self.outline.isChecked()
        c["accent"] = self.accent.value()
        return c


# ======================================================================= HDMI capture

class CaptureDialog(QDialog):
    """Setup for HDMI capture card mode."""

    def __init__(self, parent, cfg, usb_serial):
        super().__init__(parent)
        self.setWindowTitle("HDMI capture mode")
        self.setMinimumWidth(580)
        self.cfg = cfg
        self.usb_serial = usb_serial
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        lay.addLayout(_heading(
            "HDMI capture mode",
            "Your phone shows <b>everything</b> on HDMI (PIN pad, password boxes, banking apps…). "
            "A cheap <b>USB HDMI capture card</b> lets this computer receive that HDMI signal, so "
            "the picture is identical to what a TV gets. Your mouse and keyboard still control the "
            "phone, over Wi-Fi."))

        lay.addWidget(QLabel("1  Wi-Fi control (do this while the USB cable is still plugged in)",
                             objectName="Step"))
        row = QHBoxLayout()
        self.target = QComboBox()
        self.target.setEditable(True)
        self.target.setMinimumWidth(240)
        self.target.lineEdit().setPlaceholderText("192.168.1.20:5555…")
        row.addWidget(self.target, 1)
        self.enable_btn = QPushButton("Enable Wi-Fi control")
        self.enable_btn.setIcon(glyph_icon(G["wifi"], theme.TEXT))
        self.enable_btn.clicked.connect(self._enable_wifi)
        self.enable_btn.setEnabled(bool(usb_serial))
        row.addWidget(self.enable_btn)
        lay.addLayout(row)
        self.wifi_status = QLabel(objectName="Muted", wordWrap=True)
        lay.addWidget(self.wifi_status)

        lay.addWidget(QLabel("2  Connect the cables", objectName="Step"))
        lay.addWidget(QLabel(
            "Phone  →  USB-C to HDMI adapter  →  HDMI cable  →  capture card  →  computer USB port.\n"
            "Tip: an adapter with a USB-C charging port keeps the phone charged.",
            objectName="Muted", wordWrap=True))

        lay.addWidget(QLabel("3  Choose the capture card", objectName="Step"))
        form = QFormLayout()
        self.video = QComboBox()
        self.audio = QComboBox()
        form.addRow("Picture from", self.video)
        form.addRow("Sound from", self.audio)
        lay.addLayout(form)
        refresh = QPushButton("Refresh list", objectName="Link")
        refresh.clicked.connect(self._fill_devices)
        lay.addWidget(refresh, 0, Qt.AlignLeft)

        lay.addSpacing(4)
        row, self.ok = _buttons(self, "Start HDMI mode")
        lay.addLayout(row)

        self._fill_targets()
        self._fill_devices()

    def _fill_targets(self):
        saved = self.cfg.get("wifi_target", "")
        items = []
        if saved:
            items.append(saved)
        for d in adb.devices():
            if d["state"] == "device" and d["serial"] not in items:
                items.append(d["serial"])
        self.target.clear()
        self.target.addItems(items)
        self.wifi_status.setText(
            "Click “Enable Wi-Fi control” once while the USB cable is plugged in. It lasts until the "
            "phone restarts. The computer must be on the same Wi-Fi as the phone, or on its hotspot.")

    def _fill_devices(self):
        self.video.clear()
        self.audio.clear()
        cams = capture.video_inputs()
        for cam in cams:
            self.video.addItem(cam.description(), cam)
        self.audio.addItem("No sound", None)
        for mic in capture.audio_inputs():
            self.audio.addItem(mic.description(), mic)
        self._select(self.video, self.cfg.get("capture_video", ""), ("capture", "hdmi", "usb video", "cam link"))
        self._select(self.audio, self.cfg.get("capture_audio", ""), ("capture", "hdmi", "usb digital", "cam link"))
        self.ok.setEnabled(bool(cams))
        if not cams:
            self.video.addItem("No capture card found: plug it in, then Refresh")

    @staticmethod
    def _select(combo, saved, hints):
        for i in range(combo.count()):
            if saved and combo.itemText(i) == saved:
                combo.setCurrentIndex(i)
                return
        for i in range(combo.count()):
            if any(h in combo.itemText(i).lower() for h in hints):
                combo.setCurrentIndex(i)
                return

    def _enable_wifi(self):
        self.enable_btn.setEnabled(False)
        self.wifi_status.setText("Switching the phone to Wi-Fi debugging…")
        run_async(lambda: adb.enable_wifi(self.usb_serial), self._wifi_done)

    def _wifi_done(self, result):
        self.enable_btn.setEnabled(True)
        if isinstance(result, Exception):
            self.wifi_status.setText(_status_html(False, f"Failed: {result}"))
            return
        ok, message, target = result
        self.wifi_status.setText(_status_html(ok, message))
        if ok:
            self.cfg["wifi_target"] = target
            if self.target.findText(target) < 0:
                self.target.insertItem(0, target)
            self.target.setCurrentText(target)

    def result_values(self):
        return {
            "target": self.target.currentText().strip(),
            "video": self.video.currentData(),
            "audio": self.audio.currentData(),
            "video_name": self.video.currentText(),
            "audio_name": self.audio.currentText() if self.audio.currentData() is not None else "",
        }


# ============================================================================ Wi-Fi

class PairDialog(QDialog):
    """Wireless debugging pairing, for when USB permission is lost."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Pair over Wi-Fi")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        lay.addLayout(_heading(
            "Pair over Wi-Fi",
            "On the phone: Developer options → Wireless debugging → "
            "<b>Pair device with pairing code</b>. Type what it shows here. The phone and this "
            "computer must be on the same Wi-Fi."))
        form = QFormLayout()
        form.setSpacing(8)
        self.pair_addr = QLineEdit(placeholderText="192.168.1.20:37099…")
        self.code = QLineEdit(placeholderText="6-digit code…")
        self.connect_addr = QLineEdit(placeholderText="192.168.1.20:41237…")
        form.addRow("Pairing address", self.pair_addr)
        form.addRow("Pairing code", self.code)
        form.addRow("Connect address", self.connect_addr)
        lay.addLayout(form)
        self.status = QLabel(objectName="Muted", wordWrap=True)
        lay.addWidget(self.status)
        row, self.ok = _buttons(self, "Pair", self._pair)
        lay.addLayout(row)

    def _pair(self):
        pair, code, conn = (self.pair_addr.text().strip(), self.code.text().strip(),
                            self.connect_addr.text().strip())
        if not (pair and code):
            self.status.setText("Fill in the pairing address and code.")
            return
        self.ok.setEnabled(False)
        self.status.setText("Pairing…")

        def work():
            rc, out = adb.run(["pair", pair, code], timeout=20)
            if "Successfully paired" not in out:
                return False, out.strip() or "Pairing failed"
            if conn:
                ok, msg = adb.connect_wifi(conn)
                return ok, msg
            return True, out.strip()
        run_async(work, self._done)

    def _done(self, result):
        self.ok.setEnabled(True)
        if isinstance(result, Exception):
            result = (False, str(result))
        ok, msg = result
        self.status.setText(_status_html(ok, msg))
        if ok:
            self.ok.setText("Done")
            self.ok.clicked.disconnect()
            self.ok.clicked.connect(self.accept)


class ConnectDialog(QDialog):
    """Connect to a phone that already has Wi-Fi debugging on, by its address."""

    def __init__(self, parent, suggestion=""):
        super().__init__(parent)
        self.setWindowTitle("Connect over Wi-Fi")
        self.setMinimumWidth(440)
        self.target = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        lay.addLayout(_heading(
            "Connect over Wi-Fi",
            "Type the phone's address. Use this for a phone that already has Wi-Fi debugging on "
            "(for example after <b>Continue over Wi-Fi</b>, or one paired before)."))
        self.addr = QLineEdit(placeholderText="192.168.1.20:5555…")
        self.addr.setText(suggestion)
        lay.addWidget(self.addr)
        self.status = QLabel(objectName="Muted", wordWrap=True)
        lay.addWidget(self.status)
        row, self.ok = _buttons(self, "Connect", self._connect)
        lay.addLayout(row)

    def _connect(self):
        target = self.addr.text().strip()
        if not target:
            return
        if ":" not in target:
            target += f":{adb.WIFI_PORT}"
        self.ok.setEnabled(False)
        self.status.setText(f"Connecting to {target}…")

        def done(result):
            self.ok.setEnabled(True)
            if isinstance(result, Exception):
                result = (False, str(result))
            ok, msg = result
            self.status.setText(_status_html(ok, msg))
            if ok:
                self.target = target
                self.accept()
        run_async(lambda: adb.connect_wifi(target), done)


# =================================================================== command palette

class _PaletteDelegate(QStyledItemDelegate):
    """Draws a palette row: the action on the left, its shortcut right-aligned and muted."""

    ROW_H = 38

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, p, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(2, 1, -2, -1)
        enabled = bool(index.flags() & Qt.ItemIsEnabled)
        selected = bool(option.state & QStyle.State_Selected) and enabled
        if selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT))
            p.drawRoundedRect(r, 8, 8)
        title = index.data(Qt.DisplayRole)
        hint = index.data(Qt.UserRole + 1) or ""
        fg = QColor(theme.ON_ACCENT if selected else (theme.TEXT if enabled else theme.FAINT))
        p.setPen(fg)
        p.setFont(option.font)
        text_r = r.adjusted(12, 0, -12, 0)
        p.drawText(text_r, Qt.AlignLeft | Qt.AlignVCenter, title)
        if hint:
            hc = QColor(fg)
            hc.setAlpha(170 if selected else 255)
            p.setPen(hc if selected else QColor(theme.MUTED if enabled else theme.FAINT))
            p.drawText(text_r, Qt.AlignRight | Qt.AlignVCenter, hint)
        p.restore()


class CommandPalette(QDialog):
    """Ctrl+K: search every action by name and run it with Enter, like Spotlight."""

    def __init__(self, parent, commands):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.commands = commands      # list of (title, hint, callback, enabled, keywords)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame(objectName="Palette")
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 4, 10, 10)
        lay.setSpacing(4)
        top = QHBoxLayout()
        icon = QLabel(G["search"])
        icon.setFont(theme.icon_font(16))
        icon.setStyleSheet(f"color: {theme.MUTED}; padding-left: 6px;")
        top.addWidget(icon)
        self.search = QLineEdit(objectName="PaletteSearch", placeholderText="Search actions…")
        top.addWidget(self.search, 1)
        lay.addLayout(top)
        self.list = QListWidget(objectName="PaletteList")
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(_PaletteDelegate(self.list))
        self.list.itemActivated.connect(self._run)
        self.list.itemClicked.connect(self._run)
        lay.addWidget(self.list)
        self.empty = QLabel("No matching actions", objectName="Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setMinimumHeight(60)
        lay.addWidget(self.empty)
        self.search.textChanged.connect(self._filter)
        self.search.installEventFilter(self)
        self._width = min(560, max(360, parent.width() - 40))
        self._anchor = parent
        self._filter("")

    def _filter(self, text):
        words = text.lower().split()
        self.list.clear()
        for title, hint, callback, enabled, keywords in self.commands:
            hay = (title + " " + keywords).lower()
            if not all(w in hay for w in words):
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, callback)
            item.setData(Qt.UserRole + 1, hint)
            if not enabled:
                item.setFlags(Qt.NoItemFlags)
            self.list.addItem(item)
        for i in range(self.list.count()):
            if self.list.item(i).flags() & Qt.ItemIsEnabled:
                self.list.setCurrentRow(i)
                break
        # grow with the results, up to nine rows
        rows = min(self.list.count(), 9)
        self.list.setVisible(rows > 0)
        self.empty.setVisible(rows == 0)
        self.list.setFixedHeight(rows * _PaletteDelegate.ROW_H + 14)
        height = 64 + (rows * _PaletteDelegate.ROW_H + 14 if rows else 64)
        self.layout().activate()          # let the new list height count before shrinking
        self.setFixedHeight(height)
        self.setFixedWidth(self._width)
        parent = self._anchor
        top_left = parent.mapToGlobal(parent.rect().topLeft())
        self.move(top_left.x() + (parent.width() - self._width) // 2, top_left.y() + 60)

    def _run(self, item):
        if item is None or not (item.flags() & Qt.ItemIsEnabled):
            return
        callback = item.data(Qt.UserRole)
        self.accept()
        callback()

    def eventFilter(self, obj, e):
        if obj is self.search and e.type() == QEvent.KeyPress:
            k = e.key()
            if k in (Qt.Key_Down, Qt.Key_Up):
                step = 1 if k == Qt.Key_Down else -1
                row = self.list.currentRow()
                for _ in range(self.list.count()):
                    row = (row + step) % max(1, self.list.count())
                    if self.list.item(row) and self.list.item(row).flags() & Qt.ItemIsEnabled:
                        self.list.setCurrentRow(row)
                        break
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._run(self.list.currentItem())
                return True
            if k == Qt.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, e)


# ============================================================================== Help

def help_html():
    a, m = theme.ACCENT, theme.MUTED
    return f"""
<h2 style="color:{a}">PhoneCast</h2>
<p>Shows your Android phone on this computer and lets you use it with the touchpad, mouse and
keyboard. Plug the phone in with a USB cable and it connects by itself.</p>

<h3>Mouse &amp; touchpad</h3>
<table cellspacing="4">
<tr><td><b>Click / drag</b></td><td>Tap / swipe</td></tr>
<tr><td><b>Scroll</b></td><td>Scroll</td></tr>
<tr><td><b>Right-click</b></td><td>Back (wakes the screen if it is off)</td></tr>
<tr><td><b>Middle-click</b></td><td>Home</td></tr>
<tr><td><b>Ctrl + drag</b></td><td>Pinch to zoom / rotate</td></tr>
</table>

<h3>Keyboard</h3>
<p>Typing goes straight to the phone. <b>Ctrl+V</b> pastes this computer's clipboard into the phone;
text you copy on the phone lands in this computer's clipboard. <b>Esc</b> = Back.</p>
<table cellspacing="4">
<tr><td><b>Ctrl+K</b></td><td>Search all actions</td></tr>
<tr><td><b>Ctrl+Alt+D</b></td><td>Switch phones (when several are connected)</td></tr>
<tr><td><b>F11</b></td><td>Full screen (move the mouse to the right edge for the buttons)</td></tr>
<tr><td><b>Ctrl+Alt+I</b></td><td>Compact window: small, always on top, no buttons</td></tr>
<tr><td><b>Ctrl+Alt+V</b></td><td>Start / stop screen recording (saved in Videos\\PhoneCast)</td></tr>
<tr><td><b>Ctrl+Alt+S</b></td><td>Screenshot (saved in Pictures\\PhoneCast)</td></tr>
<tr><td><b>Ctrl+Alt+C</b></td><td>Copy a screenshot to the clipboard</td></tr>
<tr><td><b>Ctrl+Alt+M</b></td><td>Turn mouse control on/off</td></tr>
<tr><td><b>Ctrl+Alt+K</b></td><td>Turn keyboard control on/off</td></tr>
<tr><td><b>Ctrl+Alt+U</b></td><td>Unlock with PIN, or type your PIN into a protected PIN box</td></tr>
<tr><td><b>Ctrl+Alt+O</b></td><td>Outline of protected (black) screens on/off</td></tr>
<tr><td><b>Ctrl+Alt+H / B / R</b></td><td>Home / Back / Recent apps</td></tr>
</table>
<p>Drop a file on the window to send it to the phone's Download folder (an .apk gets installed).</p>

<h3>Several phones</h3>
<p>Click the phone's name at the bottom left (or press <b>Ctrl+Alt+D</b>) to see every connected phone
and switch between them. PhoneCast remembers the last one you picked. <b>Continue over Wi-Fi</b>
in that menu lets you unplug the cable and keep going wirelessly.</p>

<h3>Why are some screens black over USB?</h3>
<p>Android marks some screens as <i>secure</i>: the lock-screen PIN pad, password boxes, banking and
payment apps, and some video apps. Android refuses to hand these to <b>any</b> screen-capture program
(scrcpy, Phone Link, screen recorders, this app), so they come out black. An HDMI cable to a TV is
different: the phone treats a TV as a real, trusted screen.</p>
<ul>
<li><b>Outline view</b> (eye icon, on by default): Android still tells screen readers what is on a
protected screen, so PhoneCast draws an outline of its buttons and text where the black picture is.
Click them as usual, for example <b>Use PIN</b> on a fingerprint prompt.</li>
<li><b>Unlock button</b> (lock icon, Ctrl+Alt+U): on the lock screen it unlocks the phone with your PIN.
On a "Verify it's you", banking or UPI PIN screen it types the PIN into the PIN box, or taps the
on-screen number keys. It never types into ordinary text boxes.</li>
<li>Fingerprint can't be done from a computer: choose <b>Use PIN</b> instead.</li>
<li>Black screens still respond: typing and Enter work as normal.</li>
<li><b>HDMI capture mode</b> (projector icon): with a cheap USB HDMI capture card, the computer
receives the phone's real HDMI signal, so you see <b>everything</b>, exactly like on a TV.</li>
</ul>

<h3>"USB debugging permission" problems</h3>
<p>Android forgets a computer's permission after 7 days without connecting, and on a phone with a
broken screen the "Allow USB debugging?" question can't be answered. To prevent it, open
<b>Settings → Developer options</b> on the phone (here in PhoneCast) and turn on
<b>Disable adb authorization timeout</b>.</p>
<p>If it happens anyway: put the phone and the computer on the same Wi-Fi, show the phone on a TV with
an HDMI adapter, open <b>Developer options → Wireless debugging → Pair device with pairing code</b>,
then use <b>Pair over Wi-Fi</b> in PhoneCast with the address and code shown.</p>

<p style="color:{m}">Built on the open-source scrcpy {adb.SERVER_VERSION} server (Apache 2.0).</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(600, 680)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(help_html())
        lay.addWidget(view)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close", objectName="Primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)


def remembered_pin(cfg):
    return settings.unprotect(cfg.get("pin_blob", ""))
