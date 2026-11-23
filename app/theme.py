"""Design tokens, icon glyphs (Segoe Fluent Icons, built into Windows 11) and the stylesheet.

The look follows Apple's dark appearance: layered charcoal surfaces instead of
borders, one accent colour the user can pick, soft rounded shapes and quiet
secondary text. Colours are module attributes so ``set_accent`` can restyle the
running app; always read them as ``theme.ACCENT`` (not ``from .theme import``).
"""

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPixmap)

ICON_FONT = "Segoe Fluent Icons"
UI_FONT = "Segoe UI Variable Text"
DISPLAY_FONT = "Segoe UI Variable Display"

# Surfaces, darkest to lightest
BG = "#141416"            # window and phone backdrop
SURFACE = "#1d1d20"       # dock and bottom bar
ELEVATED = "#28282c"      # menus, inputs, cards
RAISED = "#333338"        # hover on elevated things
BORDER = "#2f2f34"        # hairlines
TEXT = "#f5f5f7"
MUTED = "#8e8e93"
FAINT = "#5a5a60"

GOOD = "#30d158"
WARN = "#ff9f0a"
BAD = "#ff453a"
RECORD = "#ff3b30"

# Accent colours offered in Settings → Appearance (name, colour)
ACCENTS = [
    ("Blue", "#0a84ff"),
    ("Coral", "#d97757"),
    ("Purple", "#bf5af2"),
    ("Pink", "#ff375f"),
    ("Green", "#30d158"),
    ("Yellow", "#ffd60a"),
    ("Graphite", "#98989d"),
]
ACCENT = ACCENTS[0][1]
ACCENT_SOFT = "#3a2a24"   # accent at low strength over a surface
ON_ACCENT = "#1a0f0a"     # text drawn on an accent fill
ACCENT_HOVER = "#e58a6c"

PANEL = SURFACE           # older names, still used in a few places
PANEL_2 = ELEVATED

G = {
    "back": "", "home": "", "recents": "", "power": "",
    "vol_up": "", "vol_down": "", "mute": "", "volume": "",
    "mouse": "", "keyboard": "", "fullscreen": "", "exit_fullscreen": "",
    "pin": "", "settings": "", "camera": "", "rotate": "",
    "lock": "", "unlock": "", "notifications": "", "quick": "",
    "tv": "", "phone": "", "hdmi": "", "webcam": "", "wifi": "",
    "usb": "", "info": "", "refresh": "", "screen_off": "",
    "more": "", "help": "", "close": "", "download": "",
    "photo": "", "folder": "", "touch": "", "hide": "", "eye": "",
    "record": "", "stop": "", "search": "", "chevron_down": "",
    "chevron_up": "", "check": "", "copy": "", "devices": "",
    "add": "", "video": "", "color": "", "link": "",
    "compact": "", "expand": "", "open_folder": "", "speaker": "",
}


def _mix(a, b, t):
    """Blend colour a towards b by t (0..1); returns #rrggbb."""
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def _luminance(color):
    c = QColor(color)
    return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()


def set_accent(color):
    """Switch the accent colour; call ``apply(app)`` afterwards to restyle."""
    global ACCENT, ACCENT_SOFT, ON_ACCENT, ACCENT_HOVER
    if not QColor(color).isValid():
        color = ACCENTS[0][1]
    ACCENT = QColor(color).name()
    ACCENT_SOFT = _mix(SURFACE, ACCENT, 0.22)
    ACCENT_HOVER = _mix(ACCENT, "#ffffff", 0.14)
    ON_ACCENT = "#ffffff" if _luminance(ACCENT) < 0.55 else "#1a1206"


def rgba(color, alpha):
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def style():
    return f"""
* {{ font-family: "{UI_FONT}", "Segoe UI"; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {ELEVATED}; color: {TEXT}; border: none; padding: 6px 9px; border-radius: 8px; }}

/* Flat chrome: icons and text sit on the window's own background. Surfaces are told apart by
   tone, never by outlines; a fill appears only under the pointer. */

/* button column on the right */
#Dock, #DockPanel, #DockPanel QScrollArea, #DockPanel QWidget#DockInner {{ background: {BG}; border: none; }}
#SideButton {{ font-family: "{ICON_FONT}"; font-size: 15px; background: transparent; border: none;
    border-radius: 8px; color: {MUTED}; }}
#SideButton:hover {{ background: {SURFACE}; color: {TEXT}; }}
#SideButton:pressed {{ background: {ELEVATED}; }}
#SideButton:checked {{ color: {ACCENT}; }}
#SideButton:disabled {{ color: {FAINT}; }}
#SideButton[recording="true"] {{ color: {RECORD}; }}
#SideSep {{ background: transparent; min-height: 10px; max-height: 10px; }}

/* bottom bar */
#StatusBar {{ background: {BG}; }}
#StatusBar QLabel {{ color: {MUTED}; font-size: 9pt; }}
#DevicePill {{ background: transparent; border: none; border-radius: 8px; padding: 3px 8px 3px 4px;
    color: {TEXT}; font-size: 9pt; text-align: left; }}
#DevicePill:hover {{ background: {SURFACE}; }}
#DevicePill:pressed {{ background: {ELEVATED}; }}
#DevicePill::menu-indicator {{ image: none; width: 0; }}
#RecPill {{ background: transparent; color: {RECORD}; font-size: 9pt; font-weight: 600; }}
#Chip {{ background: transparent; font-family: "{ICON_FONT}"; font-size: 12px; color: {WARN}; }}

/* overlays on the phone picture */
#Banner {{ background: {rgba(ELEVATED, 245)}; border: none; border-radius: 14px; }}
#Banner QLabel {{ color: {TEXT}; }}
#BannerIcon {{ font-family: "{ICON_FONT}"; font-size: 20px; color: {WARN}; }}
#Toast {{ background: {rgba(ELEVATED, 240)}; border: none; border-radius: 16px; padding: 8px 18px;
    color: {TEXT}; }}

/* buttons */
QPushButton {{ background: {ELEVATED}; border: none; border-radius: 8px; padding: 7px 16px; }}
QPushButton:hover {{ background: {RAISED}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {FAINT}; }}
QPushButton#Primary {{ background: {ACCENT}; color: {ON_ACCENT}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Primary:disabled {{ background: {ACCENT_SOFT}; color: {MUTED}; }}
QPushButton#Flat {{ background: transparent; padding: 4px 8px; color: {MUTED}; }}
QPushButton#Flat:hover {{ color: {TEXT}; }}
QPushButton#Link {{ background: transparent; padding: 4px 2px; color: {ACCENT}; }}
QPushButton#Link:hover {{ color: {ACCENT_HOVER}; }}

/* inputs: a tone, and an accent line only while typing */
QLineEdit, QComboBox, QSpinBox {{ background: {ELEVATED}; border: 1px solid {ELEVATED}; border-radius: 8px;
    padding: 6px 9px; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {ELEVATED}; border: none; outline: none;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; padding: 4px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: none; background: {RAISED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; }}

/* grouped settings: a slightly lighter tone, no outline */
QGroupBox {{ background: {SURFACE}; border: none; border-radius: 12px; margin-top: 22px;
    padding: 10px 12px 8px 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 4px; top: 2px;
    padding: 0 2px; color: {MUTED}; font-size: 9pt; font-weight: 600; }}
#Card {{ background: {SURFACE}; border: none; border-radius: 12px; }}
#RowSep {{ background: {BORDER}; min-height: 1px; max-height: 1px; }}

/* settings tabs */
#TabButton {{ background: transparent; border: none; border-radius: 9px; padding: 6px 10px; color: {MUTED};
    font-size: 9pt; }}
#TabButton:hover {{ color: {TEXT}; }}
#TabButton:checked {{ background: {SURFACE}; color: {ACCENT}; }}

/* menus */
QMenu {{ background: {ELEVATED}; border: none; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 7px; }}
QMenu::item:selected {{ background: {ACCENT}; color: {ON_ACCENT}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {RAISED}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

/* command palette */
#Palette {{ background: {ELEVATED}; border: none; border-radius: 16px; }}
#PaletteSearch {{ background: transparent; border: none; border-radius: 0; padding: 12px 6px;
    font-size: 13pt; font-family: "{DISPLAY_FONT}"; }}
#PaletteList {{ background: transparent; border: none; outline: none; padding: 6px; }}
#PaletteList::item {{ padding: 8px 10px; border-radius: 8px; color: {TEXT}; }}
#PaletteList::item:selected {{ background: {ACCENT}; color: {ON_ACCENT}; }}

QScrollBar:vertical {{ width: 0px; }}
QListWidget {{ background: {ELEVATED}; border: none; border-radius: 10px; outline: none; }}
QListWidget::item {{ padding: 8px; border-radius: 7px; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QLabel#H1 {{ font-family: "{DISPLAY_FONT}"; font-size: 16pt; font-weight: 600; }}
QLabel#H2 {{ font-family: "{DISPLAY_FONT}"; font-size: 12pt; font-weight: 600; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Step {{ font-weight: 600; color: {ACCENT}; }}
QTextBrowser {{ background: {SURFACE}; border: none; border-radius: 12px; padding: 10px; }}
"""


def dark_palette():
    from PySide6.QtGui import QPalette
    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: ELEVATED,
        QPalette.AlternateBase: SURFACE, QPalette.Text: TEXT, QPalette.Button: ELEVATED,
        QPalette.ButtonText: TEXT, QPalette.Highlight: ACCENT, QPalette.HighlightedText: ON_ACCENT,
        QPalette.ToolTipBase: ELEVATED, QPalette.ToolTipText: TEXT, QPalette.PlaceholderText: MUTED,
        QPalette.Link: ACCENT, QPalette.Mid: BORDER, QPalette.Dark: BG, QPalette.Light: RAISED,
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    return pal


def apply(app):
    """(Re)style the whole application with the current tokens."""
    app.setPalette(dark_palette())
    app.setStyleSheet(style())


def dark_titlebar(widget):
    """Windows 11: dark title bar matching the app, even when Windows uses light mode."""
    try:
        import ctypes
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))  # immersive dark mode
        c = QColor(BG)
        color = ctypes.c_int(c.red() | (c.green() << 8) | (c.blue() << 16))  # COLORREF 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))  # caption colour
        corners = ctypes.c_int(2)  # rounded corners, also for dialogs
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corners), ctypes.sizeof(corners))
    except Exception:
        pass


def reduce_motion():
    """True when Windows' "Animation effects" setting is off: then nothing fades or slides."""
    try:
        import ctypes
        on = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0)  # SPI_GETCLIENTAREAANIMATION
        return not on.value
    except Exception:
        return False


def tabular(font):
    """Same-width digits, so counters (timer, fps, battery) don't jitter as they change."""
    font.setFeature(QFont.Tag("tnum"), 1)
    return font


def icon_font(px):
    f = QFont(ICON_FONT)
    f.setPixelSize(px)
    return f


def display_font(pt, weight=QFont.DemiBold):
    f = QFont(DISPLAY_FONT)
    f.setPointSizeF(pt)
    f.setWeight(weight)
    return f


def glyph_icon(glyph, color, size=32):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(color))
    p.setFont(icon_font(int(size * 0.7)))
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, glyph)
    p.end()
    return QIcon(pm)


def dot_icon(color, size=16, ring=None):
    """A filled circle (accent swatches, status dots in menus)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen if ring is None else QColor(ring))
    p.setBrush(QColor(color))
    m = size * 0.2
    p.drawEllipse(QRectF(m, m, size - 2 * m, size - 2 * m))
    p.end()
    return QIcon(pm)


BRAND = "#0a84ff"         # the app icon stays PhoneCast blue whatever the accent


def paint_logo(p, rect, small=False):
    """The PhoneCast mark (docs/logo.svg): a phone outline casting out to the side, on a blue tile.

    Drawn on a 512-unit grid scaled into rect. Small sizes drop the outer arc, which would blur.
    """
    from PySide6.QtGui import QPen
    s = rect.width() / 512.0
    p.save()
    p.translate(rect.x(), rect.y())
    p.scale(s, s)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, 512, 512), 116, 116)
    grad = QLinearGradient(0, 0, 0, 512)
    grad.setColorAt(0.0, QColor("#3a9dff"))
    grad.setColorAt(1.0, QColor("#0866d6"))
    p.fillPath(tile, grad)
    width = 34 if small else 28
    pen = QPen(QColor("#ffffff"), width)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(112, 100, 172, 312), 38, 38)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    if not small:
        p.drawRoundedRect(QRectF(172, 138, 52, 14), 7, 7)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # arcs centred on the phone's right edge; Qt angles are in 1/16 degree, counter-clockwise from 3 o'clock
    p.drawArc(QRectF(277 - 62, 256 - 62, 124, 124), -54 * 16, 108 * 16)
    if not small:
        c = QColor("#ffffff")
        c.setAlphaF(0.75)
        pen.setColor(c)
        p.setPen(pen)
        p.drawArc(QRectF(273 - 128, 256 - 128, 256, 256), -54 * 16, 108 * 16)
    p.restore()


def app_icon():
    """Window/taskbar icon: the PhoneCast mark at every size Windows asks for."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        inset = 0 if size <= 32 else size * 0.04
        paint_logo(p, QRectF(inset, inset, size - 2 * inset, size - 2 * inset), small=size <= 24)
        p.end()
        icon.addPixmap(pm)
    return icon


set_accent(ACCENT)
