"""Right-hand pane: preview + trim + compress + drag the result into Discord."""
import os
import re
import subprocess
import threading
import time

from PySide6.QtCore import QObject, QPoint, QPointF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QFontMetrics, QGuiApplication, QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QProgressBar, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from .. import compress
from ..media import GPU_NAMES, fmt_size, fmt_time, gpu_encoder
from ..settings import SIZE_PRESETS
from . import theme
from .timeline import Timeline

RESOLUTIONS = [("Auto", "auto"), ("Original", "source"), ("1440p", "1440"), ("1080p", "1080"),
               ("720p", "720"), ("480p", "480")]
FRAME_RATES = [("Auto", "auto"), ("60 fps", "60"), ("30 fps", "30"), ("Original", "source")]
FPS_TIPS = ("Auto picks the sharpest result: 60 fps when there's room, otherwise 30 fps.\n"
            "60 fps = smoothest motion, but blurrier when the clip is long.\n30 fps = sharpest picture.")
SHORTCUTS = [("Play / pause", "Space"), ("Set start / end", "I  O  or  [  ]"), ("Jump 1 s (Shift: 5 s)", "←  →"),
             ("One frame", ",  ."), ("Zoom timeline", "Wheel"), ("Reset zoom", "Double-click"),
             ("Compress", "Ctrl+Enter")]


def copy_file_to_clipboard(path):
    """Puts the file itself on the clipboard: Ctrl+V in Discord attaches it."""
    from PySide6.QtCore import QMimeData
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(path)])
    QGuiApplication.clipboard().setMimeData(m)


def show_in_folder(path):
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def _label(text="", name=None, wrap=False):
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def _button(text, name=None, icon=None, icon_color=theme.TEXT, tip=None):
    b = QPushButton(f" {text}" if icon and text else text)
    if name:
        b.setObjectName(name)
    if icon:
        b.setIcon(theme.icon(icon, icon_color))
        b.setIconSize(theme.ICON_SIZE)
    if tip:
        b.setToolTip(tip)
    b.setFocusPolicy(Qt.NoFocus)
    return b


def _hairline():
    f = QFrame()
    f.setObjectName("Hairline")
    return f


def _icon_label(name, color, size=16):
    lab = QLabel()
    lab.setPixmap(theme.icon_pixmap(name, color, size))
    lab.setFixedSize(size, size)
    return lab


def _grip_pixmap(color, dot=2.0, gap=5, dpr=2.0):
    pm = QPixmap(int(12 * dpr), int(16 * dpr))
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    for row in range(3):
        for col in range(2):
            p.drawEllipse(QPointF(3 + col * gap, 3 + row * gap), dot, dot)
    p.end()
    return pm


def _step_tile(icon_name, text, lime=False):
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    tile = QLabel()
    tile.setObjectName("TileLime" if lime else "Tile")
    tile.setFixedSize(56, 56)
    tile.setAlignment(Qt.AlignCenter)
    tile.setPixmap(theme.icon_pixmap(icon_name, theme.ACCENT if lime else theme.TEXT, 24, 1.8))
    lay.addWidget(tile, 0, Qt.AlignHCenter)
    cap = _label(text, "Muted")
    cap.setAlignment(Qt.AlignCenter)
    lay.addWidget(cap)
    w.setFixedWidth(120)
    return w


class DropCard(QFrame):
    """The finished file. Drag it out and drop it in Discord."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropCard")
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Drag into a Discord chat")
        self.path = None
        self._press = None
        self._pix = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 14, 18, 14)
        lay.setSpacing(16)
        grip = QLabel()
        grip.setPixmap(_grip_pixmap(theme.ACCENT))
        lay.addWidget(grip)
        self.thumb = QLabel()
        self.thumb.setFixedSize(128, 72)
        self.thumb.setStyleSheet("background:#0b0b0d; border-radius:8px;")
        lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(4)
        title = _label("Drag me into Discord")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        col.addWidget(title)
        self.file_label = _label("")
        self.file_label.setStyleSheet(f"color: {theme.TEXT_2}; font-size: 12px;")
        col.addWidget(self.file_label)
        col.addWidget(_label("…or press Copy, then Ctrl+V in any Discord chat.", "Faint"))
        lay.addLayout(col, 1)
        lay.addWidget(_icon_label("arrow", theme.ACCENT, 32))

    def set_file(self, path, size, pixmap):
        self.path = path
        self._pix = pixmap
        name = self.file_label.fontMetrics().elidedText(os.path.basename(path), Qt.ElideMiddle, 360)
        self.file_label.setText(f"{name}  <span style='color:{theme.FAINT}'>·</span>  "
                                f"<b style='color:{theme.ACCENT}'>{fmt_size(size)}</b>")
        if pixmap:
            self.thumb.setPixmap(pixmap.scaled(QSize(128, 72), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                                 .copy(0, 0, 128, 72))
        else:
            self.thumb.clear()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if not self._press or not self.path:
            return
        if (e.position().toPoint() - self._press).manhattanLength() < QApplication.startDragDistance():
            return
        self._press = None
        from PySide6.QtCore import QMimeData
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(self.path)])
        drag = QDrag(self)
        drag.setMimeData(m)
        if self._pix:
            drag.setPixmap(self._pix.scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            drag.setHotSpot(QPoint(80, 45))
        drag.exec(Qt.CopyAction)
        self.setCursor(Qt.OpenHandCursor)

    def mouseReleaseEvent(self, _):
        self._press = None
        self.setCursor(Qt.OpenHandCursor)


class ShortcutsPopover(QFrame):
    """The "?" list of keys. Opens downward from its button, never over the video."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QWidget()
        box.setObjectName("Popover")
        box.setAttribute(Qt.WA_StyledBackground)
        outer.addWidget(box)
        lay = QGridLayout(box)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setHorizontalSpacing(24)
        lay.setVerticalSpacing(9)
        head = _label("Keyboard shortcuts")
        head.setStyleSheet("font-weight: 600;")
        lay.addWidget(head, 0, 0, 1, 2)
        for i, (what, key) in enumerate(SHORTCUTS, 1):
            w = _label(what)
            w.setStyleSheet(f"color: {theme.TEXT_2};")
            lay.addWidget(w, i, 0)
            lay.addWidget(_label(key, "Kbd"), i, 1, Qt.AlignRight)

    def show_under(self, button):
        self.adjustSize()
        g = button.mapToGlobal(QPoint(button.width(), button.height() + 6))
        self.move(g.x() - self.width(), g.y())
        self.show()


class _Bridge(QObject):
    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class EditorPane(QWidget):
    exported = Signal(str)          # source path
    status = Signal(str)
    wantChannels = Signal()
    sharedClip = Signal(str)        # source path that was just posted
    jobProgress = Signal(str, float)  # source path, 0..1 (or -1 when the job ends)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("Editor")
        self.setAttribute(Qt.WA_StyledBackground)
        self.settings = settings
        self.clip = None
        self.thumb_pix = None
        self.a = 0
        self.b = 0
        self._play_in_sel = False
        self._cancel = None
        self._job_src = None
        self._started = 0
        self._trim_save = QTimer(self, singleShot=True, interval=600, timeout=self._save_trim)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(float(settings["volume"]))
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)

        self.pages = QStackedWidget(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.pages)
        self.pages.addWidget(self._build_empty())
        self.pages.addWidget(self._build_editor())

        self.bridge = _Bridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.done.connect(self._on_done)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.cancelled.connect(self._on_cancelled)

    # Layout -------------------------------------------------------------------

    def _build_empty(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addStretch()
        steps = QHBoxLayout()
        steps.setSpacing(14)
        steps.addStretch()
        for i, (ic, text) in enumerate((("video", "Pick a clip"), ("trim", "Trim + shrink"), ("drop", "Drop in Discord"))):
            if i:
                steps.addWidget(_icon_label("arrow", theme.BORDER_HI, 20), 0, Qt.AlignTop)
            steps.addWidget(_step_tile(ic, text, lime=i == 2))
        steps.addStretch()
        lay.addLayout(steps)
        lay.addSpacing(26)
        t = _label("Pick a clip on the left", "Display")
        t.setAlignment(Qt.AlignCenter)
        h = _label("Trim it, shrink it to fit Discord, then drag it straight into your chat.", "Muted")
        h.setStyleSheet("font-size: 14px;")
        h.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addSpacing(6)
        lay.addWidget(h)
        lay.addStretch()
        lay.addSpacing(40)
        return w

    def _build_editor(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(3)
        self.title = _label("", "ClipTitle")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.subtitle = _label("", "Muted")
        self.subtitle.setStyleSheet("font-size: 12px;")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        head.addLayout(col, 1)
        open_btn = _button("Show in folder", icon="folder")
        open_btn.clicked.connect(lambda: self.clip and show_in_folder(self.clip.path))
        head.addWidget(open_btn, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.video_stack = QStackedWidget()
        self.video = QVideoWidget()
        self.video.setStyleSheet("background: black;")
        self.video.setMinimumHeight(220)
        self.player.setVideoOutput(self.video)
        self.video_stack.addWidget(self.video)
        self.video_msg = _label("", wrap=True)
        self.video_msg.setAlignment(Qt.AlignCenter)
        self.video_msg.setStyleSheet(f"background:{theme.LIST}; border:1px dashed {theme.BORDER_HI}; "
                                     f"border-radius:10px; color:{theme.MUTED}; padding:30px; font-size:13px;")
        self.video_stack.addWidget(self.video_msg)
        lay.addWidget(self.video_stack, 1)

        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self._seek)
        self.timeline.rangeChanged.connect(self._range_from_timeline)
        lay.addWidget(self.timeline)

        ctl = QHBoxLayout()
        ctl.setSpacing(6)
        self.play_btn = _button("", "Play", tip="Play / pause (Space)")
        self.play_btn.setIconSize(QSize(16, 16))
        self._play_icons = (theme.icon("play", theme.BG), theme.icon("pause", theme.BG))
        self.play_btn.setIcon(self._play_icons[0])
        self.play_btn.clicked.connect(self.toggle_play)
        ctl.addWidget(self.play_btn)
        self.time_label = _label("0:00.0 / 0:00.0", "Time")
        self.time_label.setMinimumWidth(QFontMetrics(theme.mono(14)).horizontalAdvance("0:00.0 / 0:00.0") + 10)
        ctl.addWidget(self.time_label)
        b_in = _button("[  Start here", tip="Start the clip at the playhead (I or [)")
        b_in.clicked.connect(self.set_in)
        b_out = _button("End here  ]", tip="End the clip at the playhead (O or ])")
        b_out.clicked.connect(self.set_out)
        b_reset = _button("Reset", "Flat", "reset", theme.MUTED, "Keep the whole video")
        b_reset.clicked.connect(self.reset_trim)
        for b in (b_in, b_out, b_reset):
            ctl.addWidget(b)
        ctl.addStretch()
        self.sel_label = _label("", "ClipPill")
        self.sel_label.setToolTip("Length of the part you're keeping")
        ctl.addWidget(self.sel_label)
        self.loop_box = _button("", "Icon", tip="Loop the selected part while previewing")
        self.loop_box.setCheckable(True)
        loop_ic = theme.icon("loop", theme.MUTED)
        loop_ic.addPixmap(theme.icon_pixmap("loop", theme.ACCENT, 16), theme.QIcon.Normal, theme.QIcon.On)
        self.loop_box.setIcon(loop_ic)
        self.loop_box.setIconSize(theme.ICON_SIZE)
        self.loop_box.setChecked(bool(self.settings["loop"]))
        self.loop_box.toggled.connect(lambda v: self.settings.__setitem__("loop", v))
        ctl.addWidget(self.loop_box)
        ctl.addSpacing(4)
        ctl.addWidget(_icon_label("volume", theme.MUTED))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setFixedWidth(76)
        self.vol.setRange(0, 100)
        self.vol.setValue(int(float(self.settings["volume"]) * 100))
        self.vol.valueChanged.connect(self._on_volume)
        self.vol.setToolTip("Volume")
        self.vol.setFocusPolicy(Qt.NoFocus)
        ctl.addWidget(self.vol)
        keys = _button("?", "Icon", tip="Keyboard shortcuts")
        self._keys_pop = None
        keys.clicked.connect(lambda: self._show_keys(keys))
        ctl.addWidget(keys)
        lay.addLayout(ctl)

        self.card = QFrame()
        self.card.setObjectName("Card")
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(18, 16, 18, 16)
        self.export_stack = QStackedWidget()
        self.export_stack.addWidget(self._build_options())
        self.export_stack.addWidget(self._build_progress())
        self.export_stack.addWidget(self._build_ready())
        self.export_stack.currentChanged.connect(self._sync_card)
        cl.addWidget(self.export_stack)
        lay.addWidget(self.card)
        return w

    def _show_keys(self, btn):
        if self._keys_pop is None:
            self._keys_pop = ShortcutsPopover(self)
        self._keys_pop.show_under(btn)

    def _sync_card(self, *_):
        """The ready page is its own drop card, so the outer card disappears there."""
        from PySide6.QtWidgets import QSizePolicy
        cur = self.export_stack.currentIndex()
        for i in range(self.export_stack.count()):     # size the card to the page that's showing
            pol = QSizePolicy.Preferred if i == cur else QSizePolicy.Ignored
            self.export_stack.widget(i).setSizePolicy(pol, pol)
        self.export_stack.adjustSize()
        ready = cur == 2
        self.card.setStyleSheet("QFrame#Card { background: transparent; border: none; }" if ready else "")
        self.card.layout().setContentsMargins(*((0, 0, 0, 0) if ready else (18, 16, 18, 16)))

    def _set_card_bad(self, bad):
        if self.card.property("bad") != bad:
            self.card.setProperty("bad", bad)
            theme.repolish(self.card)

    def _build_options(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        row = QHBoxLayout()
        row.setSpacing(12)
        fit = QVBoxLayout()
        fit.setSpacing(6)
        fit.addWidget(_label("Fit under", "Muted"))
        fit_row = QHBoxLayout()
        fit_row.setSpacing(8)
        self.size_combo = QComboBox()
        for key, label, _mb in SIZE_PRESETS:
            self.size_combo.addItem(label.replace(" - ", " · ").replace("Custom size...", "Custom…"), key)
        self.size_combo.setMinimumWidth(220)
        self.size_combo.setCurrentIndex(max(0, self.size_combo.findData(self.settings["size_preset"])))
        self.size_combo.currentIndexChanged.connect(self._on_preset)
        fit_row.addWidget(self.size_combo)
        self.custom_mb = QDoubleSpinBox()
        self.custom_mb.setRange(1, 10000)
        self.custom_mb.setDecimals(0)
        self.custom_mb.setSuffix(" MB")
        self.custom_mb.setFixedWidth(100)
        self.custom_mb.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.custom_mb.setValue(float(self.settings["custom_mb"]))
        self.custom_mb.valueChanged.connect(self._on_custom_mb)
        fit_row.addWidget(self.custom_mb)
        fit.addLayout(fit_row)
        row.addLayout(fit)

        self.adv = QWidget()
        adv = QHBoxLayout(self.adv)
        adv.setContentsMargins(0, 0, 0, 0)
        adv.setSpacing(12)
        for title, items, key in (("Resolution", RESOLUTIONS, "resolution"), ("Frame rate", FRAME_RATES, "fps")):
            c = QVBoxLayout()
            c.setSpacing(6)
            c.addWidget(_label(title, "Muted"))
            combo = self._combo(items, key)
            combo.setMinimumWidth(110)
            c.addWidget(combo)
            adv.addLayout(c)
            if key == "resolution":
                self.res_combo = combo
            else:
                self.fps_combo = combo
                combo.setToolTip(FPS_TIPS)
        row.addWidget(self.adv, 0, Qt.AlignBottom)
        self.adv_btn = _button("", "Flat")
        self.adv_btn.setLayoutDirection(Qt.RightToLeft)
        self.adv_btn.clicked.connect(self._toggle_advanced)
        row.addWidget(self.adv_btn, 0, Qt.AlignBottom)
        row.addStretch()

        boxes = QVBoxLayout()
        boxes.setSpacing(8)
        self.mix_box = QCheckBox("Mix all audio tracks")
        self.mix_box.setToolTip("Recordings from OBS can have several audio tracks (game, mic, Discord).\n"
                                "On: everything ends up in the clip. Off: only the first track.")
        self.mix_box.setChecked(bool(self.settings["mix_audio"]))
        self.mix_box.toggled.connect(lambda v: (self.settings.__setitem__("mix_audio", v)))
        boxes.addWidget(self.mix_box)
        self.copy_box = QCheckBox("Copy to clipboard when done")
        self.copy_box.setToolTip("Then just press Ctrl+V in Discord")
        self.copy_box.setChecked(bool(self.settings["copy_when_done"]))
        self.copy_box.toggled.connect(lambda v: self.settings.__setitem__("copy_when_done", v))
        boxes.addWidget(self.copy_box)
        row.addLayout(boxes)
        lay.addLayout(row)
        lay.addWidget(_hairline())

        row3 = QHBoxLayout()
        row3.setSpacing(20)
        plan = QVBoxLayout()
        plan.setSpacing(8)
        self.plan_label = _label("", wrap=True)
        self.plan_label.setStyleSheet("font-size: 14px;")
        plan.addWidget(self.plan_label)
        self.plan_detail = _label("", "Mono")
        plan.addWidget(self.plan_detail)
        self.low_res = QFrame()
        self.low_res.setStyleSheet(f"QFrame {{ background: #2b2312; border: 1px solid #5a4418; border-radius: 8px; }}"
                                   f"QLabel {{ border: none; background: transparent; color: {theme.WARN}; }}")
        lr = QHBoxLayout(self.low_res)
        lr.setContentsMargins(12, 8, 8, 8)
        lr.setSpacing(10)
        self.low_res_label = _label("", wrap=True)
        lr.addWidget(self.low_res_label, 1)
        self.shorten_btn = _button("", tip="Keeps the start where it is and moves the end in")
        self.shorten_btn.setFocusPolicy(Qt.NoFocus)
        self.shorten_btn.clicked.connect(self._shorten_to_720)
        lr.addWidget(self.shorten_btn, 0, Qt.AlignVCenter)
        self.low_res.hide()
        self._shorten_ms = 0
        plan.addWidget(self.low_res)
        meter = QHBoxLayout()
        meter.setSpacing(10)
        self.meter = QProgressBar()
        self.meter.setProperty("thin", True)
        self.meter.setRange(0, 1000)
        meter.addWidget(self.meter, 1)
        self.meter_label = _label("", "Mono")
        meter.addWidget(self.meter_label)
        self.meter_row = QWidget()
        self.meter_row.setLayout(meter)
        meter.setContentsMargins(0, 0, 0, 0)
        plan.addWidget(self.meter_row)
        row3.addLayout(plan, 1)
        self.go_btn = _button("Compress for Discord", "Primary", tip="Compress for Discord (Ctrl+Enter)")
        self.go_btn.setProperty("big", True)
        self.go_btn.clicked.connect(self.start_export)
        row3.addWidget(self.go_btn, 0, Qt.AlignVCenter)
        lay.addLayout(row3)
        for wdg in (self.size_combo, self.res_combo, self.fps_combo, self.mix_box, self.copy_box, self.go_btn):
            wdg.setFocusPolicy(Qt.NoFocus)
        self._advanced = self.settings["resolution"] != "auto" or self.settings["fps"] != "auto"
        self._sync_advanced()
        self._sync_custom()
        return w

    def _toggle_advanced(self):
        self._advanced = not self._advanced
        self._sync_advanced()
        self._update_plan()

    def _sync_advanced(self):
        self.adv.setVisible(self._advanced)
        if self._advanced:
            self.adv_btn.setText("Hide")
            self.adv_btn.setIcon(theme.icon("chevron-up", theme.MUTED))
        else:
            self.adv_btn.setText(f"Advanced  ·  {self.res_combo.currentText()} size, {self.fps_combo.currentText()}"
                                 f"{' fps' if self.fps_combo.currentData() in ('auto', 'source') else ''}")
            self.adv_btn.setIcon(theme.icon("chevron", theme.MUTED))
        self.plan_detail.setVisible(self._advanced and bool(self.plan_detail.text()))

    def _combo(self, items, key):
        c = QComboBox()
        for label, value in items:
            c.addItem(label, value)
        c.setCurrentIndex(max(0, c.findData(self.settings[key])))
        c.currentIndexChanged.connect(lambda _i, c=c, key=key: (self.settings.__setitem__(key, c.currentData()),
                                                               self._update_plan()))
        return c

    def _build_progress(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.prog_label = _label("Starting…", "Heading")
        row.addWidget(self.prog_label, 1)
        self.eta_label = _label("", "Muted")
        row.addWidget(self.eta_label)
        cancel = _button("Cancel")
        cancel.clicked.connect(self.cancel_export)
        row.addWidget(cancel)
        lay.addLayout(row)
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        lay.addWidget(self.prog)
        row = QHBoxLayout()
        self.prog_plan = _label("", "Faint")
        row.addWidget(self.prog_plan, 1)
        row.addWidget(_label("You can keep browsing clips while this runs.", "Faint"))
        lay.addLayout(row)
        return w

    def _build_ready(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.drop = DropCard()
        lay.addWidget(self.drop)
        info = QHBoxLayout()
        info.setSpacing(10)
        self.ready_meter = QProgressBar()
        self.ready_meter.setProperty("thin", True)
        self.ready_meter.setProperty("kind", "good")
        self.ready_meter.setRange(0, 1000)
        self.ready_meter.setFixedWidth(90)
        info.addWidget(self.ready_meter)
        self.ready_info = _label("", "Muted", wrap=True)
        info.addWidget(self.ready_info, 1)
        lay.addLayout(info)
        row = QHBoxLayout()
        row.setSpacing(8)
        share_btn = _button("Share to Discord", "Primary", "share", theme.ON_ACCENT,
                            "Post it straight into one of your Discord channels")
        share_btn.clicked.connect(self._share)
        copy = _button("Copy", icon="copy", tip="Copies the video file. Click Discord's message box and press Ctrl+V.")
        copy.clicked.connect(self._copy_ready)
        folder = _button("Show file", icon="folder")
        folder.clicked.connect(lambda: self.drop.path and show_in_folder(self.drop.path))
        again = _button("Make another version", "Flat", "reset", theme.MUTED)
        again.clicked.connect(lambda: self.export_stack.setCurrentIndex(0))
        for b in (share_btn, copy, folder):
            b.setMinimumHeight(40)
            row.addWidget(b)
        row.addStretch()
        row.addWidget(again)
        lay.addLayout(row)
        return w

    # Loading a clip -----------------------------------------------------------

    def load(self, clip, thumb_pix=None):
        same = self.clip is not None and clip is not None and self.clip.path == clip.path
        if same:
            self.clip = clip
            self.thumb_pix = thumb_pix or self.thumb_pix
            self._refresh_header()
            self._update_plan()
            return
        self._save_trim()
        self.player.stop()
        self.clip = clip
        self.thumb_pix = thumb_pix
        if clip is None:
            self.player.setSource(QUrl())
            self.pages.setCurrentIndex(0)
            return
        self.pages.setCurrentIndex(1)
        self.video_stack.setCurrentIndex(0)
        dur_ms = int((clip.info or {}).get("duration", 0) * 1000)
        self.timeline.set_duration(dur_ms)
        saved = self.settings["trims"].get(clip.path)
        if saved and dur_ms and saved[1] <= dur_ms:
            self.a, self.b = saved
        else:
            self.a, self.b = 0, dur_ms
        self.timeline.set_range(self.a, self.b)
        self.player.setSource(QUrl.fromLocalFile(clip.path))
        self.player.setPosition(self.a)
        self.player.pause()
        self._refresh_header()
        self._update_plan()
        if self._cancel and self._job_src == clip.path:
            self.export_stack.setCurrentIndex(1)
        elif self.settings.export_for(clip.path):
            self._show_ready(self.settings.export_for(clip.path), note="Made earlier. " + self._posted_note(clip.path))
        else:
            self.export_stack.setCurrentIndex(0)

    def _refresh_header(self):
        c = self.clip
        self.title.setText(os.path.splitext(c.name)[0])
        bits = [c.group]
        if c.info:
            i = c.info
            bits += [f"{i['height']}p{round(i['fps'])}", fmt_time(i["duration"], 0), fmt_size(c.size)]
            if i["audio_tracks"] > 1:
                bits.append(f"{i['audio_tracks']} audio tracks")
            self.mix_box.setVisible(i["audio_tracks"] > 1)
            if self.timeline.dur <= 1 and i["duration"]:
                self.timeline.set_duration(int(i["duration"] * 1000))
                if self.b == 0:
                    self.a, self.b = 0, int(i["duration"] * 1000)
                self.timeline.set_range(self.a, self.b)
        elif c.error:
            bits.append(c.error)
        else:
            bits.append("reading…")
        self.subtitle.setText("  <span style='color:#4a5058'>·</span>  ".join(bits))

    # Player -------------------------------------------------------------------

    def _on_duration(self, ms):
        if ms > 0 and self.timeline.dur <= 1:
            self.timeline.set_duration(ms)
            if self.b == 0:
                self.a, self.b = 0, ms
            self.timeline.set_range(self.a, self.b)
            self._update_plan()

    def _on_position(self, ms):
        if self.player.playbackState() == QMediaPlayer.PlayingState and self._play_in_sel and ms >= self.b:
            if self.loop_box.isChecked():
                self.player.setPosition(self.a)
                return
            self.player.pause()
            self.player.setPosition(self.b)
            ms = self.b
        self.timeline.set_position(ms)
        self.time_label.setText(f"{fmt_time(ms / 1000)}<span style='color:{theme.FAINT}'> / "
                                f"{fmt_time(self.timeline.dur / 1000)}</span>")

    def _on_state(self, state):
        self.play_btn.setIcon(self._play_icons[state == QMediaPlayer.PlayingState])

    def _on_error(self, _err, msg):
        if self.clip:
            self.video_msg.setText("<b style='color:#eceef1'>Can't preview this video here</b>" +
                                   (f" ({msg})" if msg else "") + ".<br>You can still trim by time and compress it.")
            self.video_stack.setCurrentIndex(1)

    def _on_volume(self, v):
        self.audio.setVolume(v / 100)
        self.settings.data["volume"] = v / 100
        self._trim_save.start()

    def _seek(self, ms):
        self.player.setPosition(int(ms))

    def toggle_play(self):
        if not self.clip:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            return
        pos = self.player.position()
        if pos >= self.b - 30 or pos < self.a - 30:
            if pos >= self.b - 30:
                self.player.setPosition(self.a)
            self._play_in_sel = pos >= self.b - 30
        else:
            self._play_in_sel = True
        self.player.play()

    def step(self, ms):
        if self.clip:
            self.player.setPosition(max(0, min(self.timeline.dur, self.player.position() + ms)))

    def frame_step(self, direction):
        fps = (self.clip.info or {}).get("fps", 30) if self.clip else 30
        self.player.pause()
        self.step(int(direction * 1000 / max(1, fps)))

    # Trimming -----------------------------------------------------------------

    def _range_from_timeline(self, a, b):
        self.a, self.b = a, b
        self._range_changed()

    def _range_changed(self):
        self.timeline.set_range(self.a, self.b)
        self._update_plan()
        self._trim_save.start()
        if self.export_stack.currentIndex() == 2:
            self.export_stack.setCurrentIndex(0)

    def set_in(self):
        if self.clip:
            self.a = min(self.player.position(), self.b - 500)
            self.a = max(0, self.a)
            self._range_changed()

    def set_out(self):
        if self.clip:
            self.b = max(self.player.position(), self.a + 500)
            self.b = min(self.timeline.dur, self.b)
            self._range_changed()

    def reset_trim(self):
        if self.clip:
            self.a, self.b = 0, self.timeline.dur
            self._range_changed()

    def _save_trim(self):
        if self.clip and self.timeline.dur > 1:
            trims = self.settings.data["trims"]
            if self.a <= 0 and self.b >= self.timeline.dur:
                trims.pop(self.clip.path, None)
            else:
                trims[self.clip.path] = [self.a, self.b]
        self.settings.save()

    # Export options -----------------------------------------------------------

    def _on_preset(self):
        self.settings["size_preset"] = self.size_combo.currentData()
        self._sync_custom()
        self._update_plan()
        if self.export_stack.currentIndex() == 2:
            self.export_stack.setCurrentIndex(0)

    def _on_custom_mb(self, v):
        self.settings["custom_mb"] = v
        self._update_plan()

    def _sync_custom(self):
        self.custom_mb.setVisible(self.size_combo.currentData() == "custom")

    def _limit_label(self):
        return f"{self.settings.limit_mb():g} MB"

    def _set_pill(self, text, bad=False):
        self.sel_label.setText(text)
        if self.sel_label.property("bad") != bad:
            self.sel_label.setProperty("bad", bad)
            theme.repolish(self.sel_label)

    def _plan_text(self, html, bad=False, meter=None):
        self.plan_label.setText(f"<span style='color:{theme.BAD}'>{html}</span>" if bad else html)
        self._set_card_bad(bad)
        self.meter_row.setVisible(meter is not None)
        if meter is not None:
            est, limit = meter
            self.meter.setValue(int(min(1.0, est / limit) * 1000))
            self.meter_label.setText(f"{est:.1f} / {limit:g} MB")

    def _update_plan(self):
        c = self.clip
        self.plan_detail.setText("")
        self.plan_detail.hide()
        self.low_res.hide()
        if hasattr(self, "adv_btn") and not self._advanced:
            self._sync_advanced()
        if not c or not c.info:
            self._plan_text(f"<span style='color:{theme.MUTED}'>Reading the video…</span>" if c and not c.error else "")
            self._set_pill("")
            self.go_btn.setEnabled(False)
            return
        start, end = self.a / 1000, self.b / 1000
        limit = self.settings.limit_mb()
        length = fmt_time(end - start, 0)
        sel = f"<b style='font-family:\"{theme.MONO_FONT}\"'>{length}</b> selected"
        self._set_pill(fmt_time(end - start) + " clip")
        self.go_btn.setText("Compress for Discord")
        if compress.shareable_as_is(c.path, c.info, start, end, limit):
            self._plan_text(f"{sel}. Already under {self._limit_label()}, so no compressing needed.")
            self.go_btn.setText("Use as is")
            self.go_btn.setEnabled(True)
            return
        try:
            plan = compress.make_plan(c.info, end - start, limit, self.settings["resolution"], self.settings["fps"],
                                      has_audio=c.info["audio_tracks"] > 0)
        except compress.TooLong as e:
            self._plan_text(f"{sel}: too long to fit in {self._limit_label()}. "
                            f"Trim it to under {fmt_time(e.max_seconds, 0)}.", bad=True)
            self._set_pill(fmt_time(end - start) + " clip · too long", bad=True)
            self.go_btn.setEnabled(False)
            return
        except ValueError as e:
            self._plan_text(str(e))
            self.go_btn.setEnabled(False)
            return
        est = min(plan.est_mb, limit)
        self._plan_text(f"{sel}  <span style='color:{theme.FAINT}'>→</span>  "
                        f"<b>{plan.height}p{round(plan.fps)}</b>  <span style='color:{theme.FAINT}'>·</span>  "
                        f"about <b>{est:.1f} MB</b>", meter=(est, limit))
        self.plan_detail.setText(f"{plan.video_kbps / 1000:.1f} Mbps video · {plan.audio_kbps} kbps audio")
        self.plan_detail.setVisible(self._advanced)
        self._sync_low_res(plan, end - start, limit)
        self.go_btn.setEnabled(self._cancel is None)

    def _sync_low_res(self, plan, length, limit):
        """Warns when the clip is too long to stay at 720p, and offers to shorten it."""
        info = self.clip.info
        if (self.settings["resolution"] != "auto" or plan.height >= 720 or (info.get("height") or 0) < 720):
            self.low_res.hide()
            return
        max_s = compress.max_seconds_at(info, limit, 720, self.settings["fps"], info["audio_tracks"] > 0)
        self._shorten_ms = int(max_s * 1000) - 100
        if self._shorten_ms < 1000:
            self.low_res.hide()
            return
        blurry = "will look pretty blurry" if plan.height <= 480 else "will look a bit soft"
        self.low_res_label.setText(f"At this length it drops to <b>{plan.height}p</b> and {blurry}. "
                                   f"Keep it under <b>{fmt_time(max_s, 0)}</b> to stay at 720p.")
        self.shorten_btn.setText(f"Shorten to {fmt_time(self._shorten_ms / 1000, 0)}")
        self.low_res.show()

    def _shorten_to_720(self):
        if not self.clip or self._shorten_ms <= 0:
            return
        self.b = min(self.timeline.dur, self.a + self._shorten_ms)
        self._range_changed()
        if self.player.position() > self.b:
            self.player.setPosition(self.a)

    # Exporting ----------------------------------------------------------------

    def _out_path(self, limit_mb=None):
        stem = os.path.splitext(self.clip.name)[0]
        stem = re.sub(r'[<>:"/\\|?*]+', "_", stem)
        tag = f"{limit_mb or self.settings.limit_mb():g}MB"
        if self.a > 0 or self.b < self.timeline.dur - 50:
            s = int(self.a / 1000)
            stem += f"_{s // 60:02d}m{s % 60:02d}s"
        return os.path.join(self.settings["export_dir"], f"{stem}_{tag}.mp4")

    def start_export(self):
        c = self.clip
        if not c or not c.info or self._cancel is not None or not self.go_btn.isEnabled():
            return
        start, end = self.a / 1000, self.b / 1000
        limit = self.settings.limit_mb()
        if compress.shareable_as_is(c.path, c.info, start, end, limit):
            self._finish(c.path, {"path": c.path, "size": c.size, "plan": None, "encoder": None}, limit)
            return
        self.player.pause()
        self._cancel = threading.Event()
        self._job_src = c.path
        self._started = time.time()
        self.prog.setValue(0)
        self.prog_label.setText("Starting…")
        self.eta_label.setText("")
        self.prog_plan.setText(re.sub(r"<[^>]+>", "", self.plan_label.text()).replace("selected  →", "→"))
        self.export_stack.setCurrentIndex(1)
        self.jobProgress.emit(c.path, 0.0)
        out = self._out_path()
        info = dict(c.info)
        opts = dict(resolution=self.settings["resolution"], fps_pref=self.settings["fps"],
                    mix_audio=self.settings["mix_audio"], encoder=self.settings["encoder"])
        cancel, bridge, src = self._cancel, self.bridge, c.path

        def job():
            try:
                r = compress.compress(src, out, start, end, info, limit, cancel=cancel,
                                      on_progress=lambda f, s: bridge.progress.emit(f, s),
                                      log=lambda s: bridge.progress.emit(-1, s), **opts)
                r["src"], r["limit"] = src, limit
                bridge.done.emit(r)
            except compress.Cancelled:
                bridge.cancelled.emit()
            except Exception as e:
                bridge.failed.emit(str(e))

        threading.Thread(target=job, daemon=True).start()

    def cancel_export(self):
        if self._cancel:
            self._cancel.set()

    def _on_progress(self, frac, label):
        if frac < 0:                     # log line
            self.status.emit(label)
            return
        if self._job_src:
            self.jobProgress.emit(self._job_src, frac)
        if self.clip and self.clip.path != self._job_src:
            return
        self.prog.setValue(int(frac * 1000))
        self.prog_label.setText(f"{label}…  <span style='color:{theme.ACCENT}; font-family:\"{theme.MONO_FONT}\"'>"
                                f"{int(frac * 100)}%</span>")
        elapsed = time.time() - self._started
        if frac > 0.03 and elapsed > 2:
            left = elapsed / frac - elapsed
            self.eta_label.setText(f"about {int(left) + 1}s left")

    def _job_over(self):
        self._cancel = None
        src, self._job_src = self._job_src, None
        if src:
            self.jobProgress.emit(src, -1.0)
        return src

    def _on_done(self, r):
        src = self._job_over()
        self._finish(src, r, r["limit"])

    def _finish(self, src, r, limit):
        if src != r["path"]:
            self.settings.remember_export(src, r["path"], r["size"], limit)
        else:
            self.settings.remember_export(src, src, r["size"], limit)
        self.exported.emit(src)
        took = ""
        if r.get("plan"):
            enc = "GPU (" + GPU_NAMES.get(r["encoder"], "") + ")" if r["encoder"] not in (None, "cpu") else "CPU"
            p = r["plan"]
            took = f"{p.height}p{round(p.fps)} · {enc} · took {int(time.time() - self._started)}s. "
        if self.copy_box.isChecked():
            copy_file_to_clipboard(r["path"])
            note = took + f"<span style='color:{theme.GOOD}'>✓ Copied. Click Discord's message box and press Ctrl+V.</span>"
        else:
            note = took
        e = {"path": r["path"], "size": r["size"], "limit_mb": limit}
        if self.clip and self.clip.path == src:
            self._show_ready(e, note=note)
        self.status.emit(f"Ready: {os.path.basename(r['path'])} ({fmt_size(r['size'])})")
        self._update_plan()

    def _posted_note(self, src):
        shares = self.settings.shares_for(src)
        if not shares:
            return ""
        from .cliplist import when
        last = shares[-1]
        more = f" ({len(shares)} times)" if len(shares) > 1 else ""
        return (f"<span style='color:{theme.GOOD}'>Posted to #{last['channel']} "
                f"{when(last['time']).replace('Today', 'today').replace('Yesterday', 'yesterday')}{more}.</span>")

    def _show_ready(self, e, note=""):
        self.drop.set_file(e["path"], e["size"], self.thumb_pix)
        self.ready_meter.setValue(int(min(1.0, e["size"] / (e["limit_mb"] * 1e6)) * 1000))
        self.ready_info.setText(f"<b style='color:{theme.TEXT}'>{fmt_size(e['size'])}</b> of {e['limit_mb']:g} MB. "
                                f"{note}")
        self.export_stack.setCurrentIndex(2)

    def _share(self):
        from .share_dialog import ShareDialog, ask_name
        if not self.drop.path or not os.path.exists(self.drop.path):
            return
        if not self.settings.channels():
            self.wantChannels.emit()
            return
        if not ask_name(self.settings, self):
            return
        src = self.clip.path if self.clip else self.drop.path
        shrink = None
        if self.clip and self.clip.info:       # lets Share make a smaller copy if the channel's limit is lower
            shrink = dict(src=self.clip.path, start=self.a / 1000, end=self.b / 1000, info=dict(self.clip.info),
                          out_for=self._out_path,
                          opts=dict(resolution=self.settings["resolution"], fps_pref=self.settings["fps"],
                                    mix_audio=self.settings["mix_audio"], encoder=self.settings["encoder"]))
        dlg = ShareDialog(self.settings, src, self.drop.path, os.path.getsize(self.drop.path), self.thumb_pix, self,
                          shrink=shrink)
        dlg.shared.connect(lambda ch: (self.ready_info.setText(
            f"<span style='color:{theme.GOOD}; font-weight:600'>Posted to #{ch} ✓</span>"),
            self.status.emit(f"Posted to #{ch}"), self.sharedClip.emit(src)))
        dlg.exec()

    def _copy_ready(self):
        if self.drop.path:
            copy_file_to_clipboard(self.drop.path)
            self.ready_info.setText(f"<span style='color:{theme.GOOD}'>✓ Copied.</span> "
                                    "Click Discord's message box and press Ctrl+V.")

    def _on_failed(self, msg):
        src = self._job_over()
        self.status.emit("Compressing failed: " + msg.splitlines()[-1] if msg else "Compressing failed")
        if self.clip and self.clip.path == src:
            self.export_stack.setCurrentIndex(0)
            self._plan_text(f"Compressing failed: {msg.splitlines()[-1] if msg else ''}", bad=True)
        self._update_plan_soon()

    def _on_cancelled(self):
        self._job_over()
        self.export_stack.setCurrentIndex(0)
        self.status.emit("Cancelled")
        self._update_plan()

    def _update_plan_soon(self):
        self.go_btn.setEnabled(True)

    def busy(self):
        return self._cancel is not None

    def shutdown(self):
        self._save_trim()
        if self._cancel:
            self._cancel.set()
        self.player.stop()


def gpu_note():
    g = gpu_encoder()
    return f"{GPU_NAMES[g]} GPU encoder found" if g else "No GPU encoder found, using the CPU"
