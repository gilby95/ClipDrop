"""Clip list: thumbnails, info, NEW / ready badges. Rows can be dragged straight
into Discord (drags the compressed copy if there is one, else the original)."""
import datetime
import os

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QPointF, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..library import norm
from ..media import fmt_size, fmt_time
from . import theme

ClipRole = Qt.UserRole + 1
HeaderRole = Qt.UserRole + 2
THUMB_W, THUMB_H = 128, 72


def when(ts):
    d = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    t = d.strftime("%I:%M %p").lstrip("0")
    if d.date() == today:
        return f"Today {t}"
    if d.date() == today - datetime.timedelta(days=1):
        return f"Yesterday {t}"
    if d.year == today.year:
        return d.strftime("%b %d ") + t
    return d.strftime("%b %d %Y")


def date_group(ts):
    """Today / Yesterday / This week / Last week / Earlier this month / March / March 2025."""
    d = datetime.date.fromtimestamp(ts)
    today = datetime.date.today()
    if d >= today:
        return "Today"
    if d == today - datetime.timedelta(days=1):
        return "Yesterday"
    week_start = today - datetime.timedelta(days=today.weekday())
    if d >= week_start:
        return "This week"
    if d >= week_start - datetime.timedelta(days=7):
        return "Last week"
    if (d.year, d.month) == (today.year, today.month):
        return "Earlier this month"
    return d.strftime("%B") if d.year == today.year else d.strftime("%B %Y")


class Header:
    """A 'Today · 3' divider row in the clip list."""
    __slots__ = ("title", "count")

    def __init__(self, title):
        self.title, self.count = title, 0


class ClipModel(QAbstractListModel):
    def __init__(self, library, settings, parent=None):
        super().__init__(parent)
        self.library = library
        self.settings = settings
        self.rows = []
        self.folder = None
        self.text = ""
        self.progress = {}          # path -> 0..1 while that clip is compressing
        self._pix = {}

    # Filtering / sorting ------------------------------------------------------

    def refresh(self):
        clips = list(self.library.clips.values())
        if self.folder:
            f = norm(self.folder)
            clips = [c for c in clips if norm(c.root) == f]
        if self.text:
            q = self.text.lower()
            clips = [c for c in clips if q in c.path.lower()]
        sort = self.settings["sort"]
        if sort == "oldest":
            clips.sort(key=lambda c: c.mtime)
        elif sort == "name":
            clips.sort(key=lambda c: c.name.lower())
        elif sort == "size":
            clips.sort(key=lambda c: -c.size)
        else:
            clips.sort(key=lambda c: -c.mtime)
        rows = clips
        if sort in ("newest", "oldest"):
            rows, header = [], None
            for c in clips:
                g = date_group(c.mtime)
                if header is None or header.title != g:
                    header = Header(g)
                    rows.append(header)
                header.count += 1
                rows.append(c)
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def clips(self):
        return [r for r in self.rows if not isinstance(r, Header)]

    def row_of(self, path):
        for i, c in enumerate(self.rows):
            if not isinstance(c, Header) and c.path == path:
                return i
        return -1

    def clip_changed(self, path):
        self._pix.pop(path, None)
        i = self.row_of(path)
        if i >= 0:
            idx = self.index(i)
            self.dataChanged.emit(idx, idx)

    def pixmap(self, clip):
        if not clip.thumb:
            return None
        pm = self._pix.get(clip.path)
        if pm is None:
            pm = QPixmap(clip.thumb)
            if not pm.isNull():
                pm = pm.scaled(THUMB_W * 2, THUMB_H * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self._pix[clip.path] = pm
        return pm if not pm.isNull() else None

    # Qt model -----------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        clip = self.rows[index.row()]
        if isinstance(clip, Header):
            return clip if role == HeaderRole else None
        if role == ClipRole:
            return clip
        if role == Qt.DisplayRole:
            return clip.name
        if role == Qt.ToolTipRole:
            what = "the compressed copy" if self.settings.export_for(clip.path) else "the original"
            return f"{clip.path}\n\nDrag into Discord ({what})"
        return None

    def flags(self, index):
        if index.isValid() and isinstance(self.rows[index.row()], Header):
            return Qt.NoItemFlags
        f = super().flags(index)
        return f | Qt.ItemIsDragEnabled if index.isValid() else f

    def mimeTypes(self):
        return ["text/uri-list"]

    def supportedDragActions(self):
        return Qt.CopyAction

    def mimeData(self, indexes):
        urls = []
        for idx in indexes:
            clip = self.rows[idx.row()]
            if isinstance(clip, Header):
                continue
            e = self.settings.export_for(clip.path)
            urls.append(QUrl.fromLocalFile(e["path"] if e else clip.path))
        m = QMimeData()
        m.setUrls(urls)
        return m


class ClipDelegate(QStyledItemDelegate):
    """Clip cards: 88 px tall, 128×72 thumbnail, name / game · size / time, NEW + ready pills,
    and a drag grip on hover so it's obvious the card can be dragged into Discord."""

    def __init__(self, model, settings, parent=None):
        super().__init__(parent)
        self.model = model
        self.settings = settings

    def sizeHint(self, option, index):
        if index.data(HeaderRole):
            return QSize(260, 36)
        return QSize(260, 90)

    def _paint_header(self, p, opt, h):
        r = QRectF(opt.rect).adjusted(18, 0, -18, 0)
        y = r.top() + 14
        f = theme.ui(11, QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.9)
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        title = h.title.upper()
        tw = QFontMetrics(f).horizontalAdvance(title)
        p.drawText(QRectF(r.left(), y, tw + 4, 18), Qt.AlignLeft | Qt.AlignVCenter, title)
        x = r.left() + tw + 8
        f = theme.mono(11)
        p.setFont(f)
        p.setPen(QColor(theme.FAINT))
        cw = QFontMetrics(f).horizontalAdvance(str(h.count))
        p.drawText(QRectF(x, y, cw + 4, 18), Qt.AlignLeft | Qt.AlignVCenter, str(h.count))
        x += cw + 10
        p.setPen(QColor(theme.BORDER))
        p.drawLine(QPointF(x, y + 9.5), QPointF(r.right(), y + 9.5))

    def _pill(self, p, right, cy, text, bg, fg, border=None, mono=False, check=False, bold=True):
        f = theme.mono(10.5, QFont.DemiBold) if mono else theme.ui(10.5, QFont.Bold if bold else QFont.DemiBold)
        if text == "NEW":
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        p.setFont(f)
        tw = QFontMetrics(f).horizontalAdvance(text)
        w = tw + 14 + (12 if check else 0)
        r = QRectF(right - w, cy - 9, w, 18)
        p.setPen(QPen(QColor(border), 1) if border else Qt.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
        x = r.left() + 7
        if check:
            pen = QPen(QColor(fg), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath(QPointF(x, cy))
            path.lineTo(x + 3, cy + 3)
            path.lineTo(x + 8, cy - 3)
            p.drawPath(path)
            x += 12
        p.setPen(QColor(fg))
        p.drawText(QRectF(x, r.top(), tw + 2, r.height()), Qt.AlignLeft | Qt.AlignVCenter, text)
        return w

    def paint(self, p, opt, index):
        h = index.data(HeaderRole)
        if h:
            p.save()
            p.setRenderHint(QPainter.Antialiasing)
            self._paint_header(p, opt, h)
            p.restore()
            return
        clip = index.data(ClipRole)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(opt.rect).adjusted(8, 1, -8, -1)
        selected = bool(opt.state & QStyle.State_Selected)
        hover = bool(opt.state & QStyle.State_MouseOver)
        if selected:
            p.setPen(QPen(QColor(theme.ACCENT_LINE), 1))
            p.setBrush(QColor(theme.CARD_SEL))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        elif hover:
            p.setPen(QPen(QColor(theme.BORDER), 1))
            p.setBrush(QColor("#1a1d21"))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        tr = QRectF(r.left() + 8, r.center().y() - THUMB_H / 2, THUMB_W, THUMB_H)
        if clip.error:
            p.setPen(QPen(QColor(theme.BAD_LINE), 1))
            p.setBrush(QColor("#1a1416"))
            p.drawRoundedRect(tr.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
            ic = theme.icon_pixmap("alert", theme.BAD, 22)
            p.drawPixmap(QPointF(tr.center().x() - 11, tr.center().y() - 11), ic)
        else:
            path = QPainterPath()
            path.addRoundedRect(tr, 6, 6)
            p.setClipPath(path)
            p.fillRect(tr, QColor("#0b0b0d"))
            pm = self.model.pixmap(clip)
            if pm:
                src = QRectF(0, 0, pm.width(), pm.height())
                scale = max(tr.width() / src.width(), tr.height() / src.height())
                sw, sh = tr.width() / scale, tr.height() / scale
                src = QRectF((src.width() - sw) / 2, (src.height() - sh) / 2, sw, sh)
                p.drawPixmap(tr, pm, src)
            p.setClipping(False)
            if clip.info:
                f = theme.mono(11)
                p.setFont(f)
                txt = fmt_time(clip.info["duration"], 0)
                w = QFontMetrics(f).horizontalAdvance(txt) + 10
                br = QRectF(tr.right() - w - 4, tr.bottom() - 20, w, 16)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 192))
                p.drawRoundedRect(br, 4, 4)
                p.setPen(QColor("white"))
                p.drawText(br, Qt.AlignCenter, txt)

        grip_w = 14
        x = tr.right() + 12
        right = r.right() - grip_w - 4
        w = right - x
        f = theme.ui(13, QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(theme.MUTED if clip.error else theme.TEXT))
        name = QFontMetrics(f).elidedText(os.path.splitext(clip.name)[0], Qt.ElideMiddle, int(w))
        top = r.center().y() - 33
        p.drawText(QRectF(x, top, w, 20), Qt.AlignLeft | Qt.AlignVCenter, name)

        f = theme.ui(12)
        p.setFont(f)
        fm = QFontMetrics(f)
        if clip.error:
            p.setPen(QColor(theme.BAD))
            line2 = "Can't read this file"
        else:
            p.setPen(QColor(theme.MUTED))
            line2 = f"{clip.group}  ·  {fmt_size(clip.size)}"
        p.drawText(QRectF(x, top + 21, w, 18), Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(line2, Qt.ElideMiddle, int(w)))
        p.setPen(QColor(theme.FAINT))
        line3 = when(clip.mtime)
        p.drawText(QRectF(x, top + 45, w, 18), Qt.AlignLeft | Qt.AlignVCenter, line3)

        cy = top + 54
        px = right
        prog = self.model.progress.get(clip.path)
        if prog is not None:
            px -= self._pill(p, px, cy, f"{int(prog * 100)}%", theme.ACCENT_SOFT, theme.ACCENT_HI,
                             theme.ACCENT_LINE, mono=True) + 6
        else:
            e = self.settings.export_for(clip.path)
            if e:
                px -= self._pill(p, px, cy, fmt_size(e["size"]), theme.GOOD_SOFT, theme.GOOD, theme.GOOD_LINE,
                                 check=True, bold=False) + 6
        if clip.new:
            self._pill(p, px, cy, "NEW", theme.ACCENT, theme.ON_ACCENT)

        if (selected or hover) and not clip.error:      # drag grip: "you can pull this out"
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.MUTED if selected else theme.FAINT))
            gx = r.right() - grip_w + 2
            for row in range(3):
                for col in range(2):
                    p.drawEllipse(QPointF(gx + col * 5, r.center().y() - 5 + row * 5), 1.5, 1.5)
        p.restore()
