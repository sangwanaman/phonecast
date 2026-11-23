"""The phone screen view (with mouse/keyboard forwarding) and small UI pieces."""

from PySide6.QtCore import (QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QAccessible, QAccessibleAnnouncementEvent, QColor, QFont,
                           QGuiApplication, QPainter, QPen)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QCheckBox, QFrame,
                               QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from . import protocol as P
from . import theme
from .theme import G


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_done)
        self._timer = QTimer(self, singleShot=True, timeout=self._fade)
        self.hide()

    def show_text(self, text, ms=2200):
        self.setText(text)
        # fit narrow windows (compact mode) by wrapping instead of running off the edges
        limit = max(120, self.parentWidget().width() - 24)
        self.setWordWrap(self.fontMetrics().horizontalAdvance(text) + 40 > limit)
        self.setMaximumWidth(limit)
        self.setAlignment(Qt.AlignCenter)
        self.adjustSize()
        self.reposition()
        was_visible = self.isVisible() and self._effect.opacity() > 0.5
        self._anim.stop()
        self.show()
        self.raise_()
        # screen readers announce it, like an aria-live region
        QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self, text))
        if was_visible or theme.reduce_motion():
            self._effect.setOpacity(1.0)
        else:
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        self._timer.start(ms)

    def reposition(self):
        p = self.parentWidget()
        self.move(max(8, (p.width() - self.width()) // 2), 16)

    def _fade(self):
        if theme.reduce_motion():
            self.hide()
            return
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_done(self):
        if self._effect.opacity() < 0.05:
            self.hide()


class Banner(QFrame):
    """A dismissible hint card shown at the bottom of the screen view."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.kind = None
        self._top = False
        self.dismissed = set()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 8, 10)
        outer.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.icon = QLabel(objectName="BannerIcon")
        self.icon.setAlignment(Qt.AlignTop)
        self.text = QLabel(wordWrap=True)
        self.text.setTextFormat(Qt.RichText)
        close = QPushButton(G["close"], objectName="Flat")
        close.setFont(theme.icon_font(11))
        close.setCursor(Qt.PointingHandCursor)
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(self._dismiss)
        top.addWidget(self.icon)
        top.addWidget(self.text, 1)
        top.addWidget(close, 0, Qt.AlignTop)
        # buttons get their own row so they never squeeze the text on a narrow window
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(6)
        self.buttons.setContentsMargins(0, 0, 6, 0)
        outer.addLayout(top)
        outer.addLayout(self.buttons)
        self.hide()

    def show_banner(self, kind, glyph, html, actions=(), top=False):
        if kind in self.dismissed:
            self.hide()
            return
        if kind == self.kind and self.isVisible():
            return
        self.kind = kind
        self._top = top
        self.icon.setText(glyph)
        self.text.setText(html)
        while self.buttons.count():
            w = self.buttons.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.buttons.addStretch(1)
        for i, (label, callback) in enumerate(actions):
            b = QPushButton(label, objectName="Primary" if i == 0 else "")
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(callback)
            self.buttons.addWidget(b)
        self.show()
        self.raise_()
        self.reposition()

    def clear(self, kind=None):
        if kind is None or self.kind == kind:
            self.kind = None
            self.hide()

    def _dismiss(self):
        if self.kind:
            self.dismissed.add(self.kind)
        self.clear()

    def reposition(self):
        p = self.parentWidget()
        w = min(p.width() - 24, 560)
        self.setFixedWidth(max(220, w))
        self.adjustSize()
        y = 12 if self._top else p.height() - self.height() - 16
        self.move((p.width() - self.width()) // 2, y)


class SideButton(QToolButton):
    def __init__(self, glyph, tip, checkable=False, parent=None):
        super().__init__(parent)
        self.setObjectName("SideButton")
        self.setFixedSize(40, 34)
        self.setText(glyph)
        self.setToolTip(tip)
        self.setCheckable(checkable)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)

    def setToolTip(self, tip):
        super().setToolTip(tip)
        # the button shows only an icon: screen readers get the tooltip's first phrase as its name
        self.setAccessibleName(tip.split("\n")[0].split("   (")[0].strip())

    def set_flag(self, name, on):
        """Toggle a stylesheet property (e.g. recording) and restyle."""
        self.setProperty(name, "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class Switch(QCheckBox):
    """An iOS-style toggle. Text (and an optional muted detail line) on the left, switch on the right.

    It is a QCheckBox underneath, so isChecked / setChecked / toggled all work as usual.
    """

    TRACK_W, TRACK_H = 40, 24

    def __init__(self, text="", detail="", parent=None):
        super().__init__(text, parent)
        self.detail = detail
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on):
        if not self.isVisible() or theme.reduce_motion():
            self._set_pos(1.0 if on else 0.0)
            return
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def showEvent(self, e):
        self._pos = 1.0 if self.isChecked() else 0.0
        super().showEvent(e)

    def _fonts(self):
        main = QFont(self.font())
        small = QFont(self.font())
        small.setPointSizeF(max(7.5, main.pointSizeF() - 1.2))
        return main, small

    def sizeHint(self):
        main, small = self._fonts()
        from PySide6.QtGui import QFontMetrics
        fm, fs = QFontMetrics(main), QFontMetrics(small)
        w = max(fm.horizontalAdvance(self.text()), fs.horizontalAdvance(self.detail) if self.detail else 0)
        h = fm.height() + (fs.height() + 2 if self.detail else 0)
        return QSize(w + 18 + self.TRACK_W, max(self.TRACK_H + 8, h + 10))

    def minimumSizeHint(self):
        return QSize(self.TRACK_W + 120, self.sizeHint().height())

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        r = self.rect()
        main, small = self._fonts()
        text_w = r.width() - self.TRACK_W - 16
        fm = p.fontMetrics()
        p.setFont(main)
        fm = p.fontMetrics()
        if self.detail:
            p.setFont(small)
            fs = p.fontMetrics()
            total = fm.height() + 2 + fs.height()
            top = (r.height() - total) / 2
            p.setFont(main)
            p.setPen(QColor(theme.TEXT))
            p.drawText(QRectF(0, top, text_w, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(self.text(), Qt.ElideRight, text_w))
            p.setFont(small)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, top + fm.height() + 2, text_w, fs.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fs.elidedText(self.detail, Qt.ElideRight, text_w))
        else:
            p.setPen(QColor(theme.TEXT))
            p.drawText(QRectF(0, 0, text_w, r.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(self.text(), Qt.ElideRight, text_w))
        # track
        tw, th = self.TRACK_W, self.TRACK_H
        track = QRectF(r.width() - tw - 1, (r.height() - th) / 2, tw, th)
        off, on = QColor("#3a3a3f"), QColor(theme.ACCENT)
        t = self._pos
        color = QColor(round(off.red() + (on.red() - off.red()) * t),
                       round(off.green() + (on.green() - off.green()) * t),
                       round(off.blue() + (on.blue() - off.blue()) * t))
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(track, th / 2, th / 2)
        # knob, with a soft drop shadow
        d = th - 4
        x = track.x() + 2 + (tw - d - 4) * t
        knob = QRectF(x, track.y() + 2, d, d)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(knob.translated(0, 1))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(knob)
        if self.hasFocus():
            pen = QPen(QColor(theme.ACCENT))
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(track.adjusted(-2, -2, 2, 2), th / 2 + 2, th / 2 + 2)
        p.end()


class Battery(QWidget):
    """Phone battery: percentage and a small battery shape, green while charging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = None
        self.charging = False
        self.setFixedHeight(18)
        self.hide()

    def set_level(self, level, charging):
        self.level, self.charging = level, charging
        self.setVisible(level is not None)
        if level is not None:
            state = "charging" if charging else "on battery"
            self.setToolTip(f"Phone battery: {level}% ({state})")
            fm = self.fontMetrics()
            self.setFixedWidth(fm.horizontalAdvance("100%") + 34)
        self.update()

    def paintEvent(self, e):
        if self.level is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = theme.tabular(QFont(self.font()))
        f.setPointSizeF(9)
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        body = QRectF(self.width() - 28, (self.height() - 12) / 2, 24, 12)
        p.drawText(QRectF(0, 0, body.x() - 5, self.height()), Qt.AlignRight | Qt.AlignVCenter, f"{self.level}%")
        pen = QPen(QColor(theme.MUTED))
        pen.setWidthF(1.1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body, 3.5, 3.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.MUTED))
        p.drawRoundedRect(QRectF(body.right() + 1, body.center().y() - 2.5, 2, 5), 1, 1)
        fill = QColor(theme.GOOD if self.charging else (theme.BAD if self.level <= 15 else theme.TEXT))
        inner = body.adjusted(2, 2, -2, -2)
        inner.setWidth(max(1.5, inner.width() * max(0, min(100, self.level)) / 100))
        p.setBrush(fill)
        p.drawRoundedRect(inner, 2, 2)
        p.end()


class _Swatch(QAbstractButton):
    def __init__(self, name, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setToolTip(name)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(30, 30)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(5, 5, -5, -5)
        if self.isChecked():
            pen = QPen(QColor(self.color))
            pen.setWidthF(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(r)
        if self.isChecked():
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(r.center().x() - 3, r.center().y() - 3, 6, 6))
        p.end()


class AccentPicker(QWidget):
    """A row of colour dots, like macOS's accent colour setting."""

    changed = Signal(str)

    def __init__(self, current, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for name, color in theme.ACCENTS:
            s = _Swatch(name, color)
            s.setChecked(color.lower() == (current or "").lower())
            s.clicked.connect(lambda _=False, c=color: self.changed.emit(c))
            self.group.addButton(s)
            row.addWidget(s)
        row.addStretch(1)
        if self.group.checkedButton() is None:
            self.group.buttons()[0].setChecked(True)

    def value(self):
        b = self.group.checkedButton()
        return b.color if b else theme.ACCENTS[0][1]


class ScreenView(QWidget):
    """Shows the phone picture and turns mouse/keyboard input into phone input."""

    box_changed = Signal(int, int)       # drawable size in device pixels
    blocked = Signal(str)                # "mouse" / "keyboard" input was ignored (control off)
    files_dropped = Signal(list)
    edge_reached = Signal()              # mouse touched the right edge (full screen)
    wake_requested = Signal()
    input_sent = Signal()                # a tap or key went to the phone

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_InputMethodEnabled)
        self.setMinimumSize(160, 160)

        self.session = None          # anything with .send() and .video_size
        self.mode = "video"          # "video" (USB/Wi-Fi mirror) or "capture" (HDMI card)
        self.capture_size = (0, 0)   # capture frame size, in capture mode
        self.phone_size = (0, 0)     # phone logical screen size, in capture mode
        self.frame = None
        self.image_rect = QRectF()
        self.message = None
        self.mouse_enabled = True
        self.keyboard_enabled = True
        self.right_click_back = True
        self.asleep = False
        self.outline = None          # outline of a protected (black) screen, see outline.py
        self._hover = None
        self.edge_reveal = False     # report the mouse touching the right edge (chrome hidden)

        self._pressed = False
        self._pinch = False
        self._down_keys = {}
        self._repeat = {}

        self.toast = Toast(self)
        self.banner = Banner(self)

    # ---------------------------------------------------------------- display

    def set_frame(self, frame):
        self.frame = frame
        self.update()

    def clear_frame(self):
        self.frame = None
        self.update()

    def set_outline(self, outline):
        self.outline = outline
        self._hover = None
        self.update()

    def set_message(self, glyph, title, subtitle=""):
        self.message = (glyph, title, subtitle)
        self.update()

    def clear_message(self):
        if self.message is not None:
            self.message = None
            self.update()

    def box_size(self):
        """Drawable size for the picture, in device pixels: the whole view, edge to edge."""
        dpr = self.devicePixelRatioF()
        return int(max(2, self.width()) * dpr), int(max(2, self.height()) * dpr)

    def resizeEvent(self, e):
        self.box_changed.emit(*self.box_size())
        self.banner.reposition()
        self.toast.reposition()
        super().resizeEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        if self.frame is not None:
            img = self.frame[0]
            dpr = self.devicePixelRatioF()
            w, h = img.width() / dpr, img.height() / dpr
            x = round((self.width() - w) / 2 * dpr) / dpr
            y = round((self.height() - h) / 2 * dpr) / dpr
            self.image_rect = QRectF(x, y, w, h)
            p.drawImage(self.image_rect, img)
        else:
            self.image_rect = QRectF()
        if self.outline is not None and not self.image_rect.isEmpty():
            self._paint_outline(p)
        if self.message is not None:
            self._paint_message(p)
        p.end()

    def _outline_rect(self, node):
        r, o = self.image_rect, self.outline
        sx, sy = r.width() / o.width, r.height() / o.height
        return QRectF(r.x() + node.left * sx, r.y() + node.top * sy,
                      (node.right - node.left) * sx, (node.bottom - node.top) * sy)

    def _paint_outline(self, p):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.image_rect, QColor(theme.SURFACE))
        accent = QColor(theme.ACCENT)
        font = QFont(theme.UI_FONT)
        nodes = self.outline.nodes
        # boxes first (big ones underneath), then all the text on top
        for n in sorted((n for n in nodes if n.kind != "text"), key=lambda n: -n.area):
            rect = self._outline_rect(n)
            fill = QColor(accent if n.kind == "button" else theme.PANEL_2)
            fill.setAlpha(110 if n is self._hover else (34 if n.kind == "button" else 200))
            border = QColor(accent if (n.kind == "button" or n.focused) else theme.MUTED)
            border.setAlpha(220)
            p.setPen(border)
            p.setBrush(fill)
            radius = min(10.0, rect.height() / 3)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
        for n in nodes:
            if not n.label:
                continue
            rect = self._outline_rect(n)
            font.setPixelSize(int(max(9, min(20, rect.height() * 0.5))))
            font.setWeight(QFont.DemiBold if n.kind == "button" else QFont.Normal)
            p.setFont(font)
            p.setPen(QColor(theme.TEXT))
            text_rect = rect.adjusted(6, 0, -6, 0)
            text = p.fontMetrics().elidedText(n.label, Qt.ElideRight, int(text_rect.width()))
            align = Qt.AlignCenter if n.kind == "button" else Qt.AlignLeft | Qt.AlignVCenter
            p.drawText(text_rect, align, text)
        p.restore()

    def _node_at(self, pos):
        if self.outline is None or self.image_rect.isEmpty():
            return None
        r, o = self.image_rect, self.outline
        x = (pos.x() - r.x()) / r.width() * o.width
        y = (pos.y() - r.y()) / r.height() * o.height
        hits = [n for n in o.nodes if n.kind != "text" and n.contains(x, y)]
        return min(hits, key=lambda n: n.area) if hits else None

    def _paint_message(self, p):
        glyph, title, subtitle = self.message
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if self.frame is not None:
            bg = QColor(theme.BG)
            bg.setAlpha(215)
            p.fillRect(self.rect(), bg)
        r = self.rect()
        cx, cy = r.width() / 2, r.height() / 2 - 64
        # the icon sits in a softly tinted circle
        tint = QColor(theme.ACCENT)
        tint.setAlpha(36)
        p.setPen(Qt.NoPen)
        p.setBrush(tint)
        p.drawEllipse(QPointF(cx, cy), 46, 46)
        p.setPen(QColor(theme.ACCENT))
        p.setFont(theme.icon_font(38))
        p.drawText(QRectF(cx - 46, cy - 46, 92, 92), Qt.AlignCenter, glyph)
        width = min(r.width() - 32, 380)
        left = (r.width() - width) / 2
        p.setFont(theme.display_font(15))
        p.setPen(QColor(theme.TEXT))
        title_rect = p.boundingRect(QRectF(left, 0, width, 400), Qt.AlignHCenter | Qt.TextWordWrap, title)
        top = cy + 68
        p.drawText(QRectF(left, top, width, title_rect.height()),
                   Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, title)
        if subtitle:
            f = QFont(theme.UI_FONT)
            f.setPointSizeF(10)
            p.setFont(f)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(left, top + title_rect.height() + 8, width, r.height() - top - 20),
                       Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, subtitle)
        p.restore()

    # ---------------------------------------------------------------- mapping

    def map_point(self, pos, clamp):
        """Widget position -> (x, y, width, height) in phone/video coordinates."""
        r = self.image_rect
        if r.isEmpty() or self.session is None:
            return None
        fx = (pos.x() - r.x()) / r.width()
        fy = (pos.y() - r.y()) / r.height()
        if self.mode == "video":
            w, h = self.session.video_size
        else:
            # The phone picture sits letterboxed inside the HDMI frame
            w, h = self.phone_size
            cw, ch = self.capture_size
            if not (w and h and cw and ch):
                return None
            s = min(cw / w, ch / h)
            ox, oy = (cw - w * s) / 2, (ch - h * s) / 2
            fx = (fx * cw - ox) / (w * s)
            fy = (fy * ch - oy) / (h * s)
        if not (w and h):
            return None
        if not clamp and not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        fx = min(max(fx, 0.0), 1.0)
        fy = min(max(fy, 0.0), 1.0)
        return min(int(fx * w), w - 1), min(int(fy * h), h - 1), w, h

    # ------------------------------------------------------------------ mouse

    def _can_send(self):
        return self.session is not None and self.session.has_control

    def _send(self, data):
        if self.session is not None:
            self.session.send(data)

    def _key(self, action, code, repeat=0, meta=0):
        self._send(P.inject_keycode(action, code, repeat, meta))

    def _touch(self, action, point):
        x, y, w, h = point
        pressure = 0.0 if action == P.ACTION_UP else 1.0
        if self._pinch:
            # Ctrl+drag: a second, mirrored finger to pinch-zoom or rotate
            mx = min(max(w - 1 - x, 0), w - 1)
            my = min(max(h - 1 - y, 0), h - 1)
            self._send(P.inject_touch(action, P.POINTER_FINGER, x, y, w, h, pressure))
            self._send(P.inject_touch(action, P.POINTER_VIRTUAL_FINGER, mx, my, w, h, pressure))
        else:
            buttons = 0 if action == P.ACTION_UP else P.BUTTON_PRIMARY
            action_button = 0 if action == P.ACTION_MOVE else P.BUTTON_PRIMARY
            self._send(P.inject_touch(action, P.POINTER_MOUSE, x, y, w, h, pressure,
                                      action_button, buttons))

    def _input_allowed(self, kind):
        if not self._can_send():
            return False
        enabled = self.mouse_enabled if kind == "mouse" else self.keyboard_enabled
        if not enabled:
            self.blocked.emit(kind)
            return False
        if self.asleep:
            self.wake_requested.emit()
            return False
        return True

    def mousePressEvent(self, e):
        self.setFocus()
        if not self._input_allowed("mouse"):
            return
        b = e.button()
        if b == Qt.LeftButton:
            point = self.map_point(e.position(), clamp=False)
            if point is None:
                return
            self._pressed = True
            self._pinch = bool(e.modifiers() & Qt.ControlModifier)
            self._touch(P.ACTION_DOWN, point)
        elif b == Qt.RightButton and self.right_click_back:
            self._send(P.back_or_screen_on(P.ACTION_DOWN))
        elif b == Qt.MiddleButton:
            self._key(P.ACTION_DOWN, P.KEYCODE_HOME)
        elif b == Qt.BackButton:
            self._key(P.ACTION_DOWN, P.KEYCODE_APP_SWITCH)
        elif b == Qt.ForwardButton:
            self._send(P.simple(P.EXPAND_NOTIFICATION_PANEL))

    def mouseMoveEvent(self, e):
        if self._pressed:
            point = self.map_point(e.position(), clamp=True)
            if point is not None:
                self._touch(P.ACTION_MOVE, point)
        else:
            if self.outline is not None:
                hover = self._node_at(e.position())
                if hover is not self._hover:
                    self._hover = hover
                    self.update()
            if self.edge_reveal and e.position().x() >= self.width() - 3:
                self.edge_reached.emit()

    def mouseReleaseEvent(self, e):
        b = e.button()
        if b == Qt.LeftButton and self._pressed:
            point = self.map_point(e.position(), clamp=True)
            if point is not None:
                self._touch(P.ACTION_UP, point)
            self._pressed = False
            self._pinch = False
            self.input_sent.emit()
        elif not self._can_send() or not self.mouse_enabled:
            return
        elif b == Qt.RightButton and self.right_click_back:
            self._send(P.back_or_screen_on(P.ACTION_UP))
        elif b == Qt.MiddleButton:
            self._key(P.ACTION_UP, P.KEYCODE_HOME)
        elif b == Qt.BackButton:
            self._key(P.ACTION_UP, P.KEYCODE_APP_SWITCH)

    def mouseDoubleClickEvent(self, e):
        # Qt replaces the second press of a double click by this event
        self.mousePressEvent(e)

    def wheelEvent(self, e):
        if not self._input_allowed("mouse"):
            return
        point = self.map_point(e.position(), clamp=False)
        if point is None:
            return
        d = e.angleDelta()
        x, y, w, h = point
        self._send(P.inject_scroll(x, y, w, h, -d.x() / 120, d.y() / 120))

    # --------------------------------------------------------------- keyboard

    def event(self, e):
        # Let Tab reach the phone instead of moving the laptop's focus
        if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(e)
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        key, mods = e.key(), e.modifiers()
        if key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr):
            return
        if e.isAutoRepeat():
            # no "control is off" hint or wake-up for auto-repeated keys
            if not (self._can_send() and self.keyboard_enabled):
                return
        elif not self._input_allowed("keyboard"):
            return
        ctrl = bool(mods & Qt.ControlModifier)
        alt = bool(mods & Qt.AltModifier)
        text = e.text()
        altgr_text = ctrl and alt and text and text.isprintable()

        if ctrl and not alt and key == Qt.Key_V:
            clip = QGuiApplication.clipboard().text()
            if clip:
                self.session.paste_text(clip)
            return
        code = P.SPECIAL_KEYS.get(key)
        if code is None and (ctrl or alt) and not altgr_text:
            code = P.CHORD_KEYS.get(key)
        if code is not None:
            repeat = self._repeat.get(key, -1) + 1 if e.isAutoRepeat() else 0
            self._repeat[key] = repeat
            self._down_keys[key] = code
            self._key(P.ACTION_DOWN, code, repeat, P.meta_state(mods))
            self.input_sent.emit()
            return
        if text and text.isprintable():
            self.session.type_text(text)
            self.input_sent.emit()

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        code = self._down_keys.pop(e.key(), None)
        self._repeat.pop(e.key(), None)
        if code is not None:
            self._key(P.ACTION_UP, code, 0, P.meta_state(e.modifiers()))

    def inputMethodEvent(self, e):
        # IME / emoji panel (Win + .) input
        if e.commitString() and self._can_send() and self.keyboard_enabled:
            self.session.type_text(e.commitString())
        e.accept()

    def focusOutEvent(self, e):
        self.release_all()
        super().focusOutEvent(e)

    def release_all(self):
        """Never leave a key or finger stuck down on the phone."""
        for key, code in list(self._down_keys.items()):
            self._key(P.ACTION_UP, code)
        self._down_keys.clear()
        self._repeat.clear()
        if self._pressed:
            r = self.image_rect
            point = self.map_point(QPointF(r.center()), clamp=True)
            if point is not None:
                self._touch(P.ACTION_UP, point)
            self._pressed = False
            self._pinch = False

    # ------------------------------------------------------------ drag & drop

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            e.acceptProposedAction()
