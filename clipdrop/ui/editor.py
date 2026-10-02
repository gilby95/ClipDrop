"""Right-hand pane: preview + trim + compress + drag the result into Discord."""
import os
import re
import subprocess
import threading
import time

from PySide6.QtCore import QObject, QPoint, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag, QGuiApplication, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from .. import compress
from ..media import GPU_NAMES, fmt_size, fmt_time, gpu_encoder
from ..settings import SIZE_PRESETS
from .timeline import Timeline

RESOLUTIONS = [("Auto", "auto"), ("Original", "source"), ("1440p", "1440"), ("1080p", "1080"),
               ("720p", "720"), ("480p", "480")]
FRAME_RATES = [("Auto", "auto"), ("Original", "source"), ("60 fps", "60"), ("30 fps", "30")]


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


class DropCard(QFrame):
    """The finished file. Drag it out and drop it in Discord."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropCard")
        self.setCursor(Qt.OpenHandCursor)
        self.path = None
        self._press = None
        self._pix = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(14)
        self.thumb = QLabel()
        self.thumb.setFixedSize(128, 72)
        self.thumb.setStyleSheet("background:#0b0b0d; border-radius:6px;")
        lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(_label("Drag me into Discord", "Big"))
        self.file_label = _label("", "Muted")
        col.addWidget(self.file_label)
        col.addWidget(_label("…or press Copy below, then Ctrl+V in any Discord chat.", "Hint"))
        lay.addLayout(col, 1)

    def set_file(self, path, size, pixmap):
        self.path = path
        self._pix = pixmap
        self.file_label.setText(f"{os.path.basename(path)}  ·  {fmt_size(size)}")
        if pixmap:
            self.thumb.setPixmap(pixmap.scaled(QSize(128, 72), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                                 .copy(0, 0, 128, 72))
        else:
            self.thumb.clear()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()

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

    def mouseReleaseEvent(self, _):
        self._press = None


class _Bridge(QObject):
    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class EditorPane(QWidget):
    exported = Signal(str)          # source path
    status = Signal(str)
    wantChannels = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("Editor")
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
        t = _label("Pick a clip on the left", "Big")
        t.setAlignment(Qt.AlignCenter)
        h = _label("Trim it, shrink it to fit Discord, then drag it straight into your chat.", "Muted")
        h.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(h)
        lay.addStretch()
        return w

    def _build_editor(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = _label("", "ClipTitle")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.subtitle = _label("", "Muted")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        head.addLayout(col, 1)
        open_btn = QPushButton("Show in folder")
        open_btn.clicked.connect(lambda: self.clip and show_in_folder(self.clip.path))
        head.addWidget(open_btn, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.video_stack = QStackedWidget()
        self.video = QVideoWidget()
        self.video.setStyleSheet("background: black;")
        self.video.setMinimumHeight(220)
        self.player.setVideoOutput(self.video)
        self.video_stack.addWidget(self.video)
        self.video_msg = _label("", "Muted", wrap=True)
        self.video_msg.setAlignment(Qt.AlignCenter)
        self.video_msg.setStyleSheet("background:black; padding:30px;")
        self.video_stack.addWidget(self.video_msg)
        lay.addWidget(self.video_stack, 1)

        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self._seek)
        self.timeline.rangeChanged.connect(self._range_from_timeline)
        lay.addWidget(self.timeline)

        ctl = QHBoxLayout()
        ctl.setSpacing(6)
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("Icon")
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.clicked.connect(self.toggle_play)
        ctl.addWidget(self.play_btn)
        self.time_label = _label("0:00.0 / 0:00.0", "Muted")
        self.time_label.setMinimumWidth(130)
        ctl.addWidget(self.time_label)
        ctl.addStretch()
        b_in = QPushButton("[  Start here")
        b_in.setToolTip("Start the clip at the playhead (I or [)")
        b_in.clicked.connect(self.set_in)
        b_out = QPushButton("End here  ]")
        b_out.setToolTip("End the clip at the playhead (O or ])")
        b_out.clicked.connect(self.set_out)
        b_reset = QPushButton("Reset")
        b_reset.setObjectName("Flat")
        b_reset.setToolTip("Keep the whole video")
        b_reset.clicked.connect(self.reset_trim)
        for b in (b_in, b_out, b_reset):
            b.setFocusPolicy(Qt.NoFocus)
            ctl.addWidget(b)
        self.sel_label = _label("", "Muted")
        self.sel_label.setMinimumWidth(110)
        ctl.addWidget(self.sel_label)
        ctl.addStretch()
        self.loop_box = QCheckBox("Loop")
        self.loop_box.setToolTip("Loop the selected part while previewing")
        self.loop_box.setChecked(bool(self.settings["loop"]))
        self.loop_box.toggled.connect(lambda v: self.settings.__setitem__("loop", v))
        ctl.addWidget(self.loop_box)
        ctl.addWidget(_label("🔊"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setFixedWidth(90)
        self.vol.setRange(0, 100)
        self.vol.setValue(int(float(self.settings["volume"]) * 100))
        self.vol.valueChanged.connect(self._on_volume)
        ctl.addWidget(self.vol)
        for wdg in (self.play_btn, self.loop_box, self.vol):
            wdg.setFocusPolicy(Qt.NoFocus)
        lay.addLayout(ctl)

        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        self.export_stack = QStackedWidget()
        self.export_stack.addWidget(self._build_options())
        self.export_stack.addWidget(self._build_progress())
        self.export_stack.addWidget(self._build_ready())
        cl.addWidget(self.export_stack)
        lay.addWidget(card)
        return w

    def _build_options(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_label("Fit under"))
        self.size_combo = QComboBox()
        for key, label, _mb in SIZE_PRESETS:
            self.size_combo.addItem(label, key)
        self.size_combo.setCurrentIndex(max(0, self.size_combo.findData(self.settings["size_preset"])))
        self.size_combo.currentIndexChanged.connect(self._on_preset)
        row.addWidget(self.size_combo)
        self.custom_mb = QDoubleSpinBox()
        self.custom_mb.setRange(1, 10000)
        self.custom_mb.setDecimals(0)
        self.custom_mb.setSuffix(" MB")
        self.custom_mb.setValue(float(self.settings["custom_mb"]))
        self.custom_mb.valueChanged.connect(self._on_custom_mb)
        row.addWidget(self.custom_mb)
        row.addSpacing(10)
        row.addWidget(_label("Resolution"))
        self.res_combo = self._combo(RESOLUTIONS, "resolution")
        row.addWidget(self.res_combo)
        row.addWidget(_label("Frame rate"))
        self.fps_combo = self._combo(FRAME_RATES, "fps")
        row.addWidget(self.fps_combo)
        row.addStretch()
        lay.addLayout(row)

        row2 = QHBoxLayout()
        self.mix_box = QCheckBox("Mix all audio tracks")
        self.mix_box.setToolTip("Recordings from OBS can have several audio tracks (game, mic, Discord).\n"
                                "On: everything ends up in the clip. Off: only the first track.")
        self.mix_box.setChecked(bool(self.settings["mix_audio"]))
        self.mix_box.toggled.connect(lambda v: (self.settings.__setitem__("mix_audio", v)))
        row2.addWidget(self.mix_box)
        self.copy_box = QCheckBox("Copy to clipboard when done")
        self.copy_box.setToolTip("Then just press Ctrl+V in Discord")
        self.copy_box.setChecked(bool(self.settings["copy_when_done"]))
        self.copy_box.toggled.connect(lambda v: self.settings.__setitem__("copy_when_done", v))
        row2.addWidget(self.copy_box)
        row2.addStretch()
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        self.plan_label = _label("", "Muted", wrap=True)
        row3.addWidget(self.plan_label, 1)
        self.go_btn = QPushButton("Compress for Discord")
        self.go_btn.setObjectName("Primary")
        self.go_btn.setToolTip("Ctrl+Enter")
        self.go_btn.clicked.connect(self.start_export)
        row3.addWidget(self.go_btn)
        lay.addLayout(row3)
        for wdg in (self.size_combo, self.res_combo, self.fps_combo, self.mix_box, self.copy_box, self.go_btn):
            wdg.setFocusPolicy(Qt.NoFocus)
        self._sync_custom()
        return w

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
        row = QHBoxLayout()
        self.prog_label = _label("Starting…")
        row.addWidget(self.prog_label, 1)
        self.eta_label = _label("", "Muted")
        row.addWidget(self.eta_label)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        row.addWidget(self.prog, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancel_export)
        row.addWidget(cancel)
        lay.addLayout(row)
        return w

    def _build_ready(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.drop = DropCard()
        lay.addWidget(self.drop)
        row = QHBoxLayout()
        self.ready_info = _label("", "Muted", wrap=True)
        row.addWidget(self.ready_info, 1)
        share_btn = QPushButton("Share to Discord")
        share_btn.setObjectName("Primary")
        share_btn.setToolTip("Post it straight into one of your Discord channels")
        share_btn.clicked.connect(self._share)
        copy = QPushButton("Copy")
        copy.setToolTip("Copies the video file. Click Discord's message box and press Ctrl+V.")
        copy.clicked.connect(self._copy_ready)
        folder = QPushButton("Show file")
        folder.clicked.connect(lambda: self.drop.path and show_in_folder(self.drop.path))
        again = QPushButton("Make another version")
        again.clicked.connect(lambda: self.export_stack.setCurrentIndex(0))
        for b in (share_btn, copy, folder, again):
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
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
            self._show_ready(self.settings.export_for(clip.path), note="Made earlier.")
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
        self.subtitle.setText("  ·  ".join(bits))

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
        self.time_label.setText(f"{fmt_time(ms / 1000)} / {fmt_time(self.timeline.dur / 1000)}")

    def _on_state(self, state):
        self.play_btn.setText("❚❚" if state == QMediaPlayer.PlayingState else "▶")

    def _on_error(self, _err, msg):
        if self.clip:
            self.video_msg.setText("Can't preview this video here" + (f" ({msg})" if msg else "") +
                                   ".\nYou can still trim by time and compress it.")
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

    def _update_plan(self):
        c = self.clip
        if not c or not c.info:
            self.plan_label.setText("Reading the video…" if c and not c.error else "")
            self.go_btn.setEnabled(False)
            return
        start, end = self.a / 1000, self.b / 1000
        limit = self.settings.limit_mb()
        sel = f"{fmt_time(end - start)} selected"
        self.sel_label.setText(fmt_time(end - start) + " clip")
        self.go_btn.setText("Compress for Discord")
        if compress.shareable_as_is(c.path, c.info, start, end, limit):
            self.plan_label.setText(f"{sel}. Already under {self._limit_label()}, so no compressing needed.")
            self.go_btn.setText("Use as is")
            self.go_btn.setEnabled(True)
            return
        try:
            plan = compress.make_plan(c.info, end - start, limit, self.settings["resolution"], self.settings["fps"],
                                      has_audio=c.info["audio_tracks"] > 0)
        except compress.TooLong as e:
            self.plan_label.setText(f"<span style='color:#ed4245'>{sel}: too long to fit in {self._limit_label()}. "
                                    f"Trim it to under {fmt_time(e.max_seconds, 0)}.</span>")
            self.go_btn.setEnabled(False)
            return
        except ValueError as e:
            self.plan_label.setText(str(e))
            self.go_btn.setEnabled(False)
            return
        self.plan_label.setText(f"{sel}  →  {plan.describe()}, about {min(plan.est_mb, limit):.1f} MB")
        self.go_btn.setEnabled(self._cancel is None)

    # Exporting ----------------------------------------------------------------

    def _out_path(self):
        stem = os.path.splitext(self.clip.name)[0]
        stem = re.sub(r'[<>:"/\\|?*]+', "_", stem)
        tag = f"{self.settings.limit_mb():g}MB"
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
        self.export_stack.setCurrentIndex(1)
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
        if self.clip and self.clip.path != self._job_src:
            return
        self.prog.setValue(int(frac * 1000))
        self.prog_label.setText(f"{label}…  {int(frac * 100)}%")
        elapsed = time.time() - self._started
        if frac > 0.03 and elapsed > 2:
            left = elapsed / frac - elapsed
            self.eta_label.setText(f"about {int(left) + 1}s left")

    def _job_over(self):
        self._cancel = None
        src, self._job_src = self._job_src, None
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
            took = f"{r['plan'].describe()} · {enc} · took {int(time.time() - self._started)}s. "
        if self.copy_box.isChecked():
            copy_file_to_clipboard(r["path"])
            note = took + "Copied. Click Discord's message box and press Ctrl+V."
        else:
            note = took
        e = {"path": r["path"], "size": r["size"], "limit_mb": limit}
        if self.clip and self.clip.path == src:
            self._show_ready(e, note=note)
        self.status.emit(f"Ready: {os.path.basename(r['path'])} ({fmt_size(r['size'])})")
        self._update_plan()

    def _show_ready(self, e, note=""):
        self.drop.set_file(e["path"], e["size"], self.thumb_pix)
        self.ready_info.setText(f"{fmt_size(e['size'])} of {e['limit_mb']:g} MB. {note}")
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
        dlg = ShareDialog(self.settings, src, self.drop.path, os.path.getsize(self.drop.path), self.thumb_pix, self)
        dlg.shared.connect(lambda ch: (self.ready_info.setText(f"Posted to #{ch} ✓"),
                                       self.status.emit(f"Posted to #{ch}")))
        dlg.exec()

    def _copy_ready(self):
        if self.drop.path:
            copy_file_to_clipboard(self.drop.path)
            self.ready_info.setText("Copied. Click Discord's message box and press Ctrl+V.")

    def _on_failed(self, msg):
        src = self._job_over()
        self.status.emit("Compressing failed: " + msg.splitlines()[-1] if msg else "Compressing failed")
        if self.clip and self.clip.path == src:
            self.export_stack.setCurrentIndex(0)
            self.plan_label.setText(f"<span style='color:#ed4245'>Compressing failed: {msg.splitlines()[-1] if msg else ''}</span>")
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
