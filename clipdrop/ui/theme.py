"""Colors, fonts, icons and the app-wide stylesheet ("Graphite + Lime")."""
from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..paths import _resource_dirs, cache_dir

BG = "#0e0f11"            # window, editor column
LIST = "#111316"          # clip list column
PANEL = "#15171a"         # sidebar, cards, dialogs, status bar
SURFACE = "#1d2024"       # inputs, secondary buttons
SURFACE_HI = "#262a30"    # hover, tracks, kbd keys
CARD_SEL = "#23272d"      # selected clip card
BORDER = "#2a2e34"
BORDER_HI = "#3a3f47"
TEXT = "#eceef1"
TEXT_2 = "#c4c8ce"
MUTED = "#a1a7b0"
FAINT = "#80868f"
ACCENT = "#b6f23d"
ACCENT_HI = "#c8f76b"
ACCENT_PRESSED = "#9ed628"
ON_ACCENT = "#10140a"
ACCENT_SOFT = "#232b14"
ACCENT_LINE = "#4c6320"
GOOD = "#57d98b"
GOOD_SOFT = "#15291d"
GOOD_LINE = "#24543a"
BAD = "#ff7a7e"
BAD_SOFT = "#2e1617"
BAD_LINE = "#4a2326"
WARN = "#ffb547"
DISABLED_FG = "#5b6068"

UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"

# 24px stroke icons; "currentColor" is swapped for the requested color.
_STROKE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
           'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
_FILL = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">{body}</svg>'
ICONS = {
    "play": (_FILL, '<path d="M7 4.5v15l12-7.5z"/>'),
    "pause": (_FILL, '<rect x="6" y="4.5" width="4" height="15" rx="1"/><rect x="14" y="4.5" width="4" height="15" rx="1"/>'),
    "volume": (_STROKE, '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/>'),
    "mute": (_STROKE, '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="m16 9 5 6"/><path d="m21 9-5 6"/>'),
    "folder": (_STROKE, '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
    "folder-alert": (_STROKE, '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
                              '<path d="M12 10.5v3"/><path d="M12 16.2v.01"/>'),
    "grid": (_STROKE, '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
                      '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
    "share": (_STROKE, '<path d="M21 3 10 14"/><path d="m21 3-7 18-4-7-7-4z"/>'),
    "copy": (_STROKE, '<rect x="9" y="9" width="12" height="12" rx="2"/>'
                      '<path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>'),
    "settings": (_STROKE, '<path d="M4 6h9"/><path d="M17 6h3"/><path d="M4 12h3"/><path d="M11 12h9"/><path d="M4 18h11"/>'
                          '<path d="M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/>'
                          '<circle cx="17" cy="18" r="2"/>'),
    "update": (_STROKE, '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>'),
    "find": (_STROKE, '<path d="M4 8V5a1 1 0 0 1 1-1h3"/><path d="M16 4h3a1 1 0 0 1 1 1v3"/>'
                      '<path d="M20 16v3a1 1 0 0 1-1 1h-3"/><path d="M8 20H5a1 1 0 0 1-1-1v-3"/><circle cx="12" cy="12" r="3"/>'),
    "loop": (_STROKE, '<path d="m17 2 4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="m7 22-4-4 4-4"/>'
                      '<path d="M21 13v2a3 3 0 0 1-3 3H3"/>'),
    "reset": (_STROKE, '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>'),
    "search": (_STROKE, '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
    "plus": (_STROKE, '<path d="M12 5v14"/><path d="M5 12h14"/>'),
    "check": (_STROKE, '<path d="m5 12.5 4.5 4.5L19 7.5"/>'),
    "close": (_STROKE, '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>'),
    "alert": (_STROKE, '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5"/><path d="M12 16.5v.01"/>'),
    "chevron": (_STROKE, '<path d="m6 9 6 6 6-6"/>'),
    "chevron-up": (_STROKE, '<path d="m18 15-6-6-6 6"/>'),
    "arrow": (_STROKE, '<path d="M5 12h12"/><path d="m12 6 6 6-6 6"/>'),
    "keyboard": (_STROKE, '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01"/><path d="M10 10h.01"/>'
                          '<path d="M14 10h.01"/><path d="M18 10h.01"/><path d="M7 14h10"/>'),
    "video": (_STROKE, '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9.5 4.5 2.5-4.5 2.5z"/>'),
    "trim": (_STROKE, '<path d="M4 12h16"/><path d="M7 7v10"/><path d="M17 7v10"/>'),
    "drop": (_FILL, '<path d="M7.5 6.75h9L12 13.5z" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>'
                    '<rect x="6.75" y="16.1" width="10.5" height="2.6" rx="1.3"/>'),
}


def icon_svg(name, color=TEXT, width=2.0):
    tpl, body = ICONS[name]
    return tpl.format(w=width, body=body).replace("currentColor", color)


def icon_pixmap(name, color=TEXT, size=16, width=2.0, dpr=2.0):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(icon_svg(name, color, width).encode())).render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name, color=TEXT, size=16, width=2.0, disabled=DISABLED_FG):
    ic = QIcon()
    ic.addPixmap(icon_pixmap(name, color, size, width), QIcon.Normal)
    ic.addPixmap(icon_pixmap(name, disabled, size, width), QIcon.Disabled)
    return ic


def _icon_file(name, color, width=2.0):
    """Writes an SVG for stylesheet url() use (combo arrows, checkmarks)."""
    d = cache_dir().parent / "ui"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}-{color.lstrip('#')}.svg"
    if not f.exists():
        f.write_text(icon_svg(name, color, width), encoding="utf-8")
    return f.as_posix()


def init_fonts():
    """Loads bundled fonts (assets/fonts/*.ttf, e.g. Geist + Geist Mono) and picks the best available."""
    global UI_FONT, MONO_FONT
    for d in _resource_dirs():
        fonts = d / "assets" / "fonts"
        if fonts.is_dir():
            for f in sorted(fonts.glob("*.[ot]tf")):
                QFontDatabase.addApplicationFont(str(f))
    have = set(QFontDatabase.families())
    UI_FONT = next((f for f in ("Geist", "Segoe UI Variable Text", "Segoe UI") if f in have), UI_FONT)
    MONO_FONT = next((f for f in ("Geist Mono", "Cascadia Mono", "Consolas") if f in have), MONO_FONT)


def mono(px=12, weight=QFont.Medium):
    f = QFont(MONO_FONT)
    f.setPixelSize(int(px + 0.5))
    f.setWeight(weight)
    f.setStyleHint(QFont.Monospace)
    return f


def ui(px=13, weight=QFont.Normal):
    f = QFont(UI_FONT)
    f.setPixelSize(int(px + 0.5))
    f.setWeight(weight)
    return f


def qss():
    chevron = _icon_file("chevron", MUTED)
    check = _icon_file("check", ON_ACCENT, 3.2)
    check_off = _icon_file("check", "#6b7a4a", 3.2)
    return f"""
* {{ font-family: "{UI_FONT}"; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {PANEL}; }}
QMainWindow > QWidget {{ background: {BG}; }}
QWidget#Sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
QWidget#Browser {{ background: {LIST}; border-right: 1px solid {BORDER}; }}
QWidget#Editor {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#AppTitle {{ font-size: 16px; font-weight: 700; }}
QLabel#Tagline {{ color: {MUTED}; font-size: 11px; }}
QLabel#Muted, QLabel#Hint {{ color: {MUTED}; }}
QLabel#Faint {{ color: {FAINT}; font-size: 12px; }}
QLabel#Section {{ color: {FAINT}; font-size: 11px; font-weight: 600; letter-spacing: 0.9px; }}
QLabel#ClipTitle {{ font-size: 18px; font-weight: 600; }}
QLabel#Big {{ font-size: 18px; font-weight: 600; }}
QLabel#Display {{ font-size: 22px; font-weight: 600; }}
QLabel#Heading {{ font-size: 15px; font-weight: 600; }}
QLabel#DialogTitle {{ font-size: 18px; font-weight: 600; }}
QLabel#Good {{ color: {GOOD}; font-weight: 600; }}
QLabel#Bad {{ color: {BAD}; }}
QLabel#Time {{ font-family: "{MONO_FONT}"; font-size: 14px; font-weight: 500; }}
QLabel#Mono {{ font-family: "{MONO_FONT}"; color: {MUTED}; font-size: 12px; }}
QLabel#ClipPill {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT_LINE}; border-radius: 13px; color: {ACCENT_HI};
    font-family: "{MONO_FONT}"; font-size: 12px; font-weight: 600; padding: 0 10px; min-height: 24px; max-height: 24px; }}
QLabel#ClipPill[bad="true"] {{ background: {BAD_SOFT}; border-color: {BAD_LINE}; color: {BAD}; }}
QLabel#Kbd {{ font-family: "{MONO_FONT}"; font-size: 11px; color: {TEXT}; background: {SURFACE_HI};
    border: 1px solid {BORDER_HI}; border-bottom-width: 2px; border-radius: 4px; padding: 1px 6px; }}
QLabel#Tag {{ background: {SURFACE_HI}; color: {MUTED}; border-radius: 9px; font-size: 11px; padding: 2px 8px; }}
QLabel#Tile {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
QLabel#TileLime {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT_LINE}; border-radius: 16px; }}
QLabel#Banner {{ border-radius: 10px; padding: 10px 12px; font-size: 13px; }}
QLabel#Banner[kind="good"] {{ background: {GOOD_SOFT}; border: 1px solid {GOOD_LINE}; color: {GOOD}; font-weight: 600; }}
QLabel#Banner[kind="bad"] {{ background: {BAD_SOFT}; border: 1px solid {BAD_LINE}; color: #ffb3b5; }}
QLabel#Banner[kind="warn"] {{ background: #2b2111; border: 1px solid #4f3b17; color: #ffd08a; }}
QLabel#Banner[kind="info"] {{ background: {SURFACE}; border: 1px solid {BORDER}; color: {MUTED}; }}
QLabel#Steps {{ background: {LIST}; border: 1px solid {BORDER}; border-radius: 10px; padding: 10px 12px; color: {TEXT_2}; }}

QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 0 14px;
    min-height: 32px; font-weight: 500; }}
QPushButton:hover {{ background: {SURFACE_HI}; border-color: {BORDER_HI}; }}
QPushButton:pressed {{ background: #17191c; }}
QPushButton:disabled {{ color: {DISABLED_FG}; background: #17191c; border-color: #22252a; }}
QPushButton#Primary {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; font-weight: 700; padding: 0 18px;
    min-height: 38px; border-radius: 10px; }}
QPushButton#Primary:hover {{ background: {ACCENT_HI}; }}
QPushButton#Primary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#Primary:disabled {{ background: #2c3320; color: #6b7a4a; }}
QPushButton#Primary[big="true"] {{ min-height: 44px; font-size: 14px; padding: 0 20px; }}
QPushButton#Flat {{ background: transparent; border: none; color: {TEXT_2}; padding: 0 10px; }}
QPushButton#Flat:hover {{ background: {SURFACE}; color: {TEXT}; }}
QPushButton#Flat:pressed {{ background: #17191c; }}
QPushButton#Flat:disabled {{ color: {DISABLED_FG}; background: transparent; }}
QPushButton#Danger {{ color: {BAD}; }}
QPushButton#Danger:hover {{ background: {BAD_SOFT}; border-color: {BAD_LINE}; }}
QPushButton#Icon {{ background: transparent; border: 1px solid transparent; padding: 0; min-width: 32px; max-width: 32px;
    min-height: 32px; max-height: 32px; color: {MUTED}; font-size: 14px; font-weight: 600; }}
QPushButton#Icon:hover {{ background: {SURFACE}; border-color: {BORDER}; color: {TEXT}; }}
QPushButton#Icon:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT_LINE}; }}
QPushButton#Play {{ background: {TEXT}; border: none; border-radius: 19px; padding: 0; min-width: 38px; max-width: 38px;
    min-height: 38px; max-height: 38px; }}
QPushButton#Play:hover {{ background: #ffffff; }}
QPushButton#Play:pressed {{ background: #c9ccd1; }}
QPushButton#SideNav {{ background: transparent; border: none; color: {TEXT_2}; text-align: left; padding: 0 10px; }}
QPushButton#SideNav:hover {{ background: {SURFACE}; color: {TEXT}; }}
QPushButton#Link {{ background: transparent; border: none; color: {MUTED}; padding: 0; min-height: 20px;
    text-decoration: underline; }}
QPushButton#Link:hover {{ color: {ACCENT}; }}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QPlainTextEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 0 10px; min-height: 32px;
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT};
}}
QPlainTextEdit {{ padding: 8px 10px; }}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover {{ border-color: {BORDER_HI}; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus, QComboBox:on {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled {{ background: #17191c; border-color: #22252a;
    color: #6b7079; }}
QLineEdit[error="true"] {{ border-color: {BAD}; }}
QLineEdit#Search {{ padding-left: 30px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER_HI}; border-radius: 8px; padding: 4px;
    outline: none; selection-background-color: #2d323a; selection-color: {TEXT}; }}
QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 8px; border-radius: 6px; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox, QRadioButton {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1.5px solid {BORDER_HI};
    background: {SURFACE}; }}
QCheckBox::indicator:hover {{ border-color: {MUTED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{check}"); }}
QCheckBox::indicator:checked:disabled {{ background: #2c3320; border-color: #2c3320; image: url("{check_off}"); }}
QCheckBox:disabled {{ color: #6b7079; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 1.5px solid {BORDER_HI};
    background: transparent; }}
QRadioButton::indicator:checked {{ border: 5px solid {ACCENT}; background: {ON_ACCENT}; width: 8px; height: 8px; }}

QFrame#Choice {{ background: {SURFACE}; border: 1.5px solid {BORDER}; border-radius: 12px; }}
QFrame#Choice:hover {{ border-color: {BORDER_HI}; }}
QFrame#Choice[on="true"] {{ background: #1b2210; border-color: {ACCENT}; }}
QFrame#FolderRow {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#FolderRow[on="true"] {{ border-color: {ACCENT_LINE}; }}
QFrame#FolderRow[done="true"] {{ background: transparent; border-color: #22252a; }}

QListWidget, QListView {{ background: transparent; border: none; outline: none; }}
QListWidget#Channels {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px; }}
QListWidget#Channels::item {{ min-height: 34px; padding: 0 8px; border-radius: 6px; }}
QListWidget#Channels::item:hover {{ background: {SURFACE_HI}; }}
QListWidget#Channels::item:selected {{ background: {CARD_SEL}; color: {TEXT}; }}

QFrame#Card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Card[bad="true"] {{ border-color: {BAD_LINE}; }}
QFrame#DropCard {{ background: #1b2210; border: 2px dashed #8dbb2c; border-radius: 14px; }}
QFrame#DropCard:hover {{ background: #202a12; border-color: {ACCENT}; }}
QFrame#Hairline {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}
QWidget#DialogFooter {{ background: #121417; border-top: 1px solid {BORDER}; }}
QWidget#DialogHeader {{ border-bottom: 1px solid {BORDER}; }}
QWidget#Popover {{ background: {SURFACE}; border: 1px solid {BORDER_HI}; border-radius: 12px; }}

QProgressBar {{ background: {SURFACE_HI}; border: none; border-radius: 4px; min-height: 8px; max-height: 8px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QProgressBar[thin="true"] {{ min-height: 6px; max-height: 6px; border-radius: 3px; }}
QProgressBar[thin="true"]::chunk {{ border-radius: 3px; }}
QProgressBar[kind="good"]::chunk {{ background: {GOOD}; }}
QProgressBar[kind="warn"]::chunk {{ background: {WARN}; }}
QSlider {{ background: transparent; min-height: 16px; }}
QSlider::groove:horizontal {{ height: 4px; background: #2f343b; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {TEXT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #33373e; border-radius: 3px; min-height: 30px; margin: 2px 3px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_HI}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #33373e; border-radius: 3px; min-width: 30px; margin: 3px 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QSplitter::handle {{ background: {BORDER}; }}
QToolTip {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER_HI}; border-radius: 6px; padding: 5px 8px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER_HI}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 14px 8px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2d323a; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::separator {{ height: 1px; background: #2f343b; margin: 6px 4px; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; font-size: 12px; min-height: 26px; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {MUTED}; font-size: 12px; }}
QDialogButtonBox QPushButton {{ min-width: 72px; }}
"""


def repolish(w):
    """Re-applies the stylesheet after a dynamic property change."""
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def draw_logo(size=256) -> QPixmap:
    """Lime tile with a down-pointing triangle dropping onto a bar ("the drop")."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(ACCENT)))
    dark = QColor(ON_ACCENT)
    if size <= 20:                              # squarer and simpler so it stays crisp at 16 px
        s = size / 16
        p.drawRoundedRect(QRectF(0, 0, 16 * s, 16 * s), 3 * s, 3 * s)
        p.setBrush(dark)
        tri = QPainterPath()
        tri.moveTo(4 * s, 4 * s)
        tri.lineTo(12 * s, 4 * s)
        tri.lineTo(8 * s, 9 * s)
        tri.closeSubpath()
        p.drawPath(tri)
        p.drawRect(QRectF(4 * s, 11 * s, 8 * s, 2 * s))
        p.end()
        return pm
    p.drawRoundedRect(QRectF(0, 0, 64 * s, 64 * s), 15 * s, 15 * s)
    from PySide6.QtGui import QPen
    p.setBrush(dark)
    p.setPen(QPen(dark, 5 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    tri = QPainterPath()
    tri.moveTo(QPointF(20 * s, 18 * s))
    tri.lineTo(QPointF(44 * s, 18 * s))
    tri.lineTo(QPointF(32 * s, 36 * s))
    tri.closeSubpath()
    p.drawPath(tri)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(18 * s, 43 * s, 28 * s, 7 * s), 3.5 * s, 3.5 * s)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(draw_logo(sz))
    return icon


def logo_label_pixmap(size, dpr=2.0):
    pm = draw_logo(int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    return pm


ICON_SIZE = QSize(16, 16)
