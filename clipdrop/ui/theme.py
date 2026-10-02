from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPixmap

BG = "#111214"
PANEL = "#18191c"
SURFACE = "#222328"
SURFACE_HI = "#2b2d33"
BORDER = "#2f3137"
TEXT = "#e9eaee"
MUTED = "#999ba3"
ACCENT = "#5865f2"
ACCENT_HI = "#6f7af5"
GOOD = "#3ba55d"
BAD = "#ed4245"

QSS = f"""
* {{ font-family: "Segoe UI"; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#Sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
QWidget#Browser {{ background: {BG}; border-right: 1px solid {BORDER}; }}
QWidget#Editor {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#AppTitle {{ font-size: 15pt; font-weight: 700; }}
QLabel#Muted, QLabel#Hint {{ color: {MUTED}; }}
QLabel#Section {{ color: {MUTED}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px; }}
QLabel#ClipTitle {{ font-size: 13pt; font-weight: 600; }}
QLabel#Big {{ font-size: 14pt; font-weight: 600; }}
QLabel#Good {{ color: {GOOD}; font-weight: 600; }}
QLabel#Bad {{ color: {BAD}; }}

QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ background: {SURFACE_HI}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #5c5e66; }}
QPushButton#Primary {{ background: {ACCENT}; border: none; font-weight: 600; padding: 9px 18px; }}
QPushButton#Primary:hover {{ background: {ACCENT_HI}; }}
QPushButton#Primary:disabled {{ background: #3a3f73; color: #a0a4c8; }}
QPushButton#Flat {{ background: transparent; border: none; color: {MUTED}; padding: 4px 6px; }}
QPushButton#Flat:hover {{ color: {TEXT}; }}
QPushButton#Icon {{ padding: 2px 6px 4px 6px; min-width: 34px; font-size: 14pt; }}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; outline: none; }}
QCheckBox {{ spacing: 7px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #4a4d55; background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: none; }}

QListWidget, QListView {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 7px 8px; border-radius: 6px; margin: 1px 6px; }}
QListWidget::item:hover {{ background: {SURFACE}; }}
QListWidget::item:selected {{ background: {SURFACE_HI}; color: {TEXT}; }}

QFrame#Card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#DropCard {{ background: #1d2140; border: 2px dashed {ACCENT}; border-radius: 10px; }}
QFrame#DropCard:hover {{ background: #232857; }}

QProgressBar {{ background: {SURFACE}; border: none; border-radius: 5px; height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_HI}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; margin: -5px 0; border-radius: 6px; background: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a3c43; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {BORDER}; }}
QToolTip {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
"""


def draw_logo(size=256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(ACCENT)))
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)
    p.setBrush(QBrush(QColor("white")))
    play = QPainterPath()
    play.moveTo(QPointF(98 * s, 62 * s))
    play.lineTo(QPointF(176 * s, 110 * s))
    play.lineTo(QPointF(98 * s, 158 * s))
    play.closeSubpath()
    p.drawPath(play)
    p.drawRoundedRect(QRectF(70 * s, 182 * s, 116 * s, 18 * s), 9 * s, 9 * s)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(draw_logo(sz))
    return icon
