"""Trim timeline: drag the two handles to pick the part to keep, click to seek,
mouse wheel to zoom in on long recordings."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme

MIN_SEL_MS = 500
HANDLE_W = 10
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
        self.setMinimumHeight(72)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.dur = 0
        self.a = 0
        self.b = 0
        self.pos = 0
        self.v0 = 0
        self.v1 = 1
        self._drag = None
        self.setToolTip("Drag the blue handles to trim. Click to jump. Scroll to zoom.")

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
        return QRectF(HANDLE_W + 2, 6, self.width() - 2 * HANDLE_W - 4, 38)

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

    # Painting -----------------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._track()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.SURFACE))
        p.drawRoundedRect(t, 6, 6)
        if self.dur <= 1:
            return

        xa, xb = max(t.left(), self._x(self.a)), min(t.right(), self._x(self.b))
        if xb > xa:
            sel = QRectF(xa, t.top(), xb - xa, t.height())
            c = QColor(theme.ACCENT)
            c.setAlpha(70)
            p.setBrush(c)
            p.drawRect(sel)
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawLine(QPointF(xa, t.top() + 1), QPointF(xb, t.top() + 1))
            p.drawLine(QPointF(xa, t.bottom() - 1), QPointF(xb, t.bottom() - 1))
            p.setPen(Qt.NoPen)

        for which, x in (("a", self._x(self.a)), ("b", self._x(self.b))):
            if t.left() - HANDLE_W <= x <= t.right() + HANDLE_W:
                r = QRectF(x - HANDLE_W if which == "a" else x, t.top() - 3, HANDLE_W, t.height() + 6)
                p.setBrush(QColor(theme.ACCENT_HI if self._drag == which else theme.ACCENT))
                p.drawRoundedRect(r, 3, 3)
                p.setPen(QPen(QColor(255, 255, 255, 200), 1.2))
                cx = r.center().x()
                for dx in (-1.5, 1.5):
                    p.drawLine(QPointF(cx + dx, r.center().y() - 6), QPointF(cx + dx, r.center().y() + 6))
                p.setPen(Qt.NoPen)

        # ticks
        span_s = (self.v1 - self.v0) / 1000
        step = next((s for s in STEPS_S if t.width() / max(span_s / s, 1e-6) >= 80), STEPS_S[-1])
        f = QFont(self.font())
        f.setPointSizeF(8)
        p.setFont(f)
        first = int(self.v0 / 1000 // step) * step
        s = first
        while s * 1000 <= self.v1:
            x = self._x(s * 1000)
            if x >= t.left() - 1:
                p.setPen(QPen(QColor(theme.BORDER), 1))
                p.drawLine(QPointF(x, t.bottom() + 3), QPointF(x, t.bottom() + 8))
                p.setPen(QColor(theme.MUTED))
                p.drawText(QRectF(x - 40, t.bottom() + 8, 80, 16), Qt.AlignHCenter | Qt.AlignTop,
                           _label(s * 1000, step))
            s += step

        # playhead
        if self.v0 <= self.pos <= self.v1:
            x = self._x(self.pos)
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(QPointF(x, t.top() - 4), QPointF(x, t.bottom() + 2))
            knob = QPainterPath()
            knob.moveTo(x - 6, t.top() - 6)
            knob.lineTo(x + 6, t.top() - 6)
            knob.lineTo(x, t.top() + 2)
            knob.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("white"))
            p.drawPath(knob)

        if self.v1 - self.v0 < self.dur:
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(t.right() - 160, t.bottom() + 8, 160, 16), Qt.AlignRight,
                       "zoomed · double-click to reset")

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
            self.setCursor(Qt.SizeHorCursor if self._hit(x) else Qt.PointingHandCursor)
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
