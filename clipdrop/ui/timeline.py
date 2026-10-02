"""Trim timeline: drag the two handles to pick the part to keep, click to seek,
mouse wheel to zoom in on long recordings."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..media import fmt_time
from . import theme

MIN_SEL_MS = 500
HANDLE_W = 14
TOP = 24            # room above the track for the time bubble / zoom map
TRACK_H = 56
STEPS_S = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]


def _label(ms, step_s):
    s = ms / 1000
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    sec_txt = f"{sec:04.1f}" if step_s < 1 else f"{int(round(sec)):02d}"
    return f"{int(h)}:{int(m):02d}:{sec_txt}" if h else f"{int(m)}:{sec_txt}"


class Timeline(QWidget):
    seekRequested = Signal(int)
    rangeChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TOP + TRACK_H + 30)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.dur = 0
        self.a = 0
        self.b = 0
        self.pos = 0
        self.v0 = 0
        self.v1 = 1
        self._drag = None
        self._hover = None
        self.setToolTip("Drag the handles to trim. Click to jump. Scroll to zoom.")

    # API ----------------------------------------------------------------------

    def set_duration(self, ms):
        self.dur = max(1, int(ms))
        self.v0, self.v1 = 0, self.dur
        self.update()

    def set_range(self, a, b):
        self.a, self.b = int(a), int(b)
        self.update()

    def set_position(self, ms):
        self.pos = int(ms)
        if self._drag is None and not (self.v0 <= self.pos <= self.v1):
            span = self.v1 - self.v0
            self.v0 = max(0, min(self.dur - span, self.pos - span // 10))
            self.v1 = self.v0 + span
        self.update()

    # Geometry -----------------------------------------------------------------

    def _track(self):
        return QRectF(HANDLE_W + 2, TOP, self.width() - 2 * HANDLE_W - 4, TRACK_H)

    def _x(self, ms):
        t = self._track()
        return t.left() + (ms - self.v0) / max(1, self.v1 - self.v0) * t.width()

    def _ms(self, x):
        t = self._track()
        ms = self.v0 + (x - t.left()) / max(1.0, t.width()) * (self.v1 - self.v0)
        return int(max(0, min(self.dur, ms)))

    def _hit(self, x):
        da, db = abs(x - (self._x(self.a) - HANDLE_W / 2)), abs(x - (self._x(self.b) + HANDLE_W / 2))
        if min(da, db) <= HANDLE_W:
            if abs(da - db) < 1:
                return "a" if x < self._x(self.a) else "b"
            return "a" if da < db else "b"
        return None

    def zoomed(self):
        return self.v1 - self.v0 < self.dur

    # Painting -----------------------------------------------------------------

    def _bubble(self, p, cx, text, lime):
        f = theme.mono(11.5, QFont.DemiBold)
        p.setFont(f)
        w = QFontMetrics(f).horizontalAdvance(text) + 18
        r = QRectF(cx - w / 2, 0, w, 20)
        r.moveLeft(max(0, min(self.width() - w, r.left())))
        p.setPen(QPen(QColor(theme.ACCENT if lime else theme.BORDER_HI), 1))
        p.setBrush(QColor(theme.ACCENT if lime else theme.SURFACE_HI))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.setPen(QColor(theme.ON_ACCENT if lime else theme.TEXT))
        p.drawText(r, Qt.AlignCenter, text)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._track()
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor("#1a1d21"))
        p.drawRoundedRect(t.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        if self.dur <= 1:
            return

        # zoom map: where the visible window sits in the whole clip
        if self.zoomed():
            m = QRectF(t.left(), 8, t.width(), 6)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURFACE))
            p.drawRoundedRect(m, 3, 3)
            sa, sb = m.left() + self.a / self.dur * m.width(), m.left() + self.b / self.dur * m.width()
            p.setBrush(QColor(theme.ACCENT_LINE))
            p.drawRoundedRect(QRectF(sa, m.top(), max(2, sb - sa), m.height()), 3, 3)
            va, vb = m.left() + self.v0 / self.dur * m.width(), m.left() + self.v1 / self.dur * m.width()
            p.setPen(QPen(QColor(theme.TEXT), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(va, m.top() - 2, max(4, vb - va), m.height() + 4), 4, 4)

        xa, xb = self._x(self.a), self._x(self.b)
        clip = QPainterPath()
        clip.addRoundedRect(t, 8, 8)
        p.save()
        p.setClipPath(clip)
        p.setPen(Qt.NoPen)
        dim = QColor(8, 9, 11, 158)
        if xa > t.left():
            p.fillRect(QRectF(t.left(), t.top(), xa - t.left(), t.height()), dim)
        if xb < t.right():
            p.fillRect(QRectF(xb, t.top(), t.right() - xb, t.height()), dim)
        sa, sb = max(t.left(), xa), min(t.right(), xb)
        if sb > sa:
            fill = QColor(theme.ACCENT)
            fill.setAlpha(34 if self._drag in ("a", "b") else 20)
            p.fillRect(QRectF(sa, t.top(), sb - sa, t.height()), fill)
        p.restore()
        if sb > sa:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawLine(QPointF(sa, t.top() + 1), QPointF(sb, t.top() + 1))
            p.drawLine(QPointF(sa, t.bottom() - 1), QPointF(sb, t.bottom() - 1))

        for which, x in (("a", xa), ("b", xb)):
            if not (t.left() - HANDLE_W <= x <= t.right() + HANDLE_W):
                continue
            active = self._drag == which
            hot = active or self._hover == which
            hw = HANDLE_W + (2 if hot else 0)
            r = QRectF(x - hw if which == "a" else x, t.top() - 5, hw, t.height() + 10)
            if active:
                ring = QColor(theme.ACCENT)
                ring.setAlpha(72)
                p.setPen(QPen(ring, 3))
            else:
                p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT_HI if hot else theme.ACCENT))
            p.drawRoundedRect(r, 5, 5)
            p.setPen(QPen(QColor(theme.ON_ACCENT), 1.5))
            cx = r.center().x()
            for dx in (-2, 2):
                p.drawLine(QPointF(cx + dx, r.center().y() - 8), QPointF(cx + dx, r.center().y() + 8))

        # ticks
        span_s = (self.v1 - self.v0) / 1000
        step = next((s for s in STEPS_S if t.width() / max(span_s / s, 1e-6) >= 80), STEPS_S[-1])
        p.setFont(theme.mono(11, QFont.Normal))
        first = int(self.v0 / 1000 // step) * step
        s = first
        while s * 1000 <= self.v1:
            x = self._x(s * 1000)
            if x >= t.left() - 1:
                p.setPen(QColor(theme.FAINT))
                p.drawText(QRectF(x - 40, t.bottom() + 8, 80, 16), Qt.AlignHCenter | Qt.AlignTop,
                           _label(s * 1000, step))
            s += step

        # playhead
        if self.v0 <= self.pos <= self.v1:
            x = self._x(self.pos)
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(QPointF(x, t.top() - 6), QPointF(x, t.bottom() + 4))
            p.setPen(QPen(QColor(theme.BG), 2))
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(x, t.top() - 6), 6, 6)

        if self.zoomed():
            f = theme.ui(11.5)
            p.setFont(f)
            text = "Zoomed · double-click to reset"
            w = QFontMetrics(f).horizontalAdvance(text) + 20
            r = QRectF(t.right() - w, t.bottom() + 6, w, 20)
            p.setPen(QPen(QColor(theme.BORDER), 1))
            p.setBrush(QColor(theme.SURFACE))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
            p.setPen(QColor(theme.TEXT_2))
            p.drawText(r, Qt.AlignCenter, text)

        # time bubble over the handle you're touching
        which = self._drag if self._drag in ("a", "b") else self._hover
        if which:
            ms = self.a if which == "a" else self.b
            if self._drag:
                text = f"{fmt_time(ms / 1000)} · {fmt_time((self.b - self.a) / 1000)} clip"
            else:
                text = f"{'Start' if which == 'a' else 'End'} {fmt_time(ms / 1000)}"
            self._bubble(p, xa - HANDLE_W / 2 if which == "a" else xb + HANDLE_W / 2, text, bool(self._drag))

    # Mouse --------------------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self.dur <= 1:
            return
        x = e.position().x()
        self._drag = self._hit(x) or "pos"
        if self._drag == "pos":
            self.pos = self._ms(x)
            self.seekRequested.emit(self.pos)
        self.update()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            hit = self._hit(x) if self.dur > 1 else None
            if hit != self._hover:
                self._hover = hit
                self.update()
            self.setCursor(Qt.SizeHorCursor if hit else Qt.PointingHandCursor)
            return
        ms = self._ms(x)
        if self._drag == "a":
            self.a = max(0, min(ms, self.b - MIN_SEL_MS))
            self.rangeChanged.emit(self.a, self.b)
            self.seekRequested.emit(self.a)
        elif self._drag == "b":
            self.b = min(self.dur, max(ms, self.a + MIN_SEL_MS))
            self.rangeChanged.emit(self.a, self.b)
            self.seekRequested.emit(self.b)
        else:
            self.pos = ms
            self.seekRequested.emit(ms)
        self.update()

    def mouseReleaseEvent(self, _):
        self._drag = None
        self.update()

    def leaveEvent(self, _):
        if self._hover:
            self._hover = None
            self.update()

    def mouseDoubleClickEvent(self, _):
        self.v0, self.v1 = 0, self.dur
        self.update()

    def wheelEvent(self, e):
        if self.dur <= 1:
            return
        steps = e.angleDelta().y() / 120 or e.angleDelta().x() / 120
        if e.modifiers() & Qt.ShiftModifier:            # pan
            span = self.v1 - self.v0
            shift = -steps * span * 0.15
            self.v0 = int(max(0, min(self.dur - span, self.v0 + shift)))
            self.v1 = self.v0 + span
        else:                                           # zoom around the cursor
            anchor = self._ms(e.position().x())
            span = (self.v1 - self.v0) * (0.8 ** steps)
            span = max(2000, min(self.dur, span))
            frac = (anchor - self.v0) / max(1, self.v1 - self.v0)
            v0 = anchor - frac * span
            v0 = max(0, min(self.dur - span, v0))
            self.v0, self.v1 = int(v0), int(v0 + span)
        self.update()
