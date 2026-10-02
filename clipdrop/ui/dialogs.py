import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from ..finder import find_capture_folders
from ..library import norm
from ..media import GPU_NAMES, gpu_encoder


class FindFoldersDialog(QDialog):
    """Shows where capture programs save clips on this PC; tick the ones to watch."""

    def __init__(self, already, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find my clip folders")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        t = QLabel("Clip folders found on this PC")
        t.setObjectName("Big")
        lay.addWidget(t)
        h = QLabel("ClipDrop looked for OBS, NVIDIA ShadowPlay / NVIDIA App, AMD ReLive, Medal, Xbox Game Bar "
                   "and Outplayed. Tick the ones you use. Sub-folders are included.")
        h.setObjectName("Muted")
        h.setWordWrap(True)
        lay.addWidget(h)
        self.boxes = []
        have = {norm(p) for p in already}
        found = find_capture_folders()
        for path, label, count in found:
            if norm(path) in have:
                continue
            cb = QCheckBox(f"{path}\n{label} · {count if count < 500 else '500+'} videos")
            cb.setChecked(count > 0)
            cb.setProperty("path", path)
            lay.addWidget(cb)
            self.boxes.append(cb)
        if not self.boxes:
            n = QLabel("Nothing new found. Use “Add folder” to pick a folder yourself.")
            n.setObjectName("Muted")
            lay.addWidget(n)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Add selected")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected(self):
        return [cb.property("path") for cb in self.boxes if cb.isChecked()]


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        from .. import __version__
        self.setWindowTitle(f"ClipDrop settings  ·  version {__version__}")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        lay.addWidget(self._section("SAVE COMPRESSED CLIPS TO"))
        row = QHBoxLayout()
        self.export_dir = QLineEdit(settings["export_dir"])
        row.addWidget(self.export_dir, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        lay.addLayout(row)

        lay.addSpacing(8)
        lay.addWidget(self._section("COMPRESSING"))
        self.encoder = QComboBox()
        g = gpu_encoder()
        gpu_txt = f"use your {GPU_NAMES[g]} GPU" if g else "no GPU encoder on this PC, so it uses the CPU"
        self.encoder.addItem(f"Fast ({gpu_txt})", "fast")
        self.encoder.addItem("Best quality (CPU, about 3x slower)", "quality")
        self.encoder.setCurrentIndex(max(0, self.encoder.findData(settings["encoder"])))
        lay.addWidget(self.encoder)
        note = QLabel("Works on any PC. If the GPU encoder fails, ClipDrop switches to the CPU on its own.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        lay.addSpacing(8)
        lay.addWidget(self._section("FOLDERS"))
        self.recursive = QCheckBox("Include sub-folders (e.g. ShadowPlay's per-game folders)")
        self.recursive.setChecked(bool(settings["recursive"]))
        lay.addWidget(self.recursive)

        lay.addSpacing(8)
        lay.addWidget(self._section("DISCORD SHARING"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Post clips as"))
        self.display_name = QLineEdit(settings["display_name"])
        self.display_name.setPlaceholderText("your name")
        row.addWidget(self.display_name, 1)
        lay.addLayout(row)
        self.channel_list = QListWidget()
        self.channel_list.setMaximumHeight(110)
        self.channel_list.setStyleSheet("QListWidget { background: #222328; border-radius: 6px; }")
        lay.addWidget(self.channel_list)
        row = QHBoxLayout()
        add = QPushButton("+  Add channel")
        add.clicked.connect(self._add_channel)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_channel)
        row.addWidget(add)
        row.addWidget(self.remove_btn)
        row.addStretch()
        lay.addLayout(row)
        hint = QLabel("Channels added here are built into the installer when you run build.bat, "
                      "so friends get them automatically.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self._channels = list(settings["channels"])
        self._fill_channels()

        lay.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _section(self, text):
        lab = QLabel(text)
        lab.setObjectName("Section")
        return lab

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save compressed clips to", self.export_dir.text())
        if d:
            self.export_dir.setText(os.path.normpath(d))

    def _fill_channels(self):
        from ..settings import bundled_channels
        self.channel_list.clear()
        mine = {c["url"] for c in self._channels}
        for ch in bundled_channels():
            if ch["url"] in mine:
                continue
            it = QListWidgetItem(f"#{ch['name']}   (came with ClipDrop)")
            it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
            self.channel_list.addItem(it)
        for ch in self._channels:
            it = QListWidgetItem(f"#{ch['name']}")
            it.setData(Qt.UserRole, ch["url"])
            self.channel_list.addItem(it)
        if not self.channel_list.count():
            it = QListWidgetItem("No channels yet. Add one to get a Share button.")
            it.setFlags(Qt.NoItemFlags)
            self.channel_list.addItem(it)

    def _add_channel(self):
        from .share_dialog import AddChannelDialog
        dlg = AddChannelDialog(self)
        if dlg.exec():
            ch = dlg.result_channel
            self._channels = [c for c in self._channels if c["url"] != ch["url"]] + [ch]
            self._fill_channels()

    def _remove_channel(self):
        from .share_dialog import confirm_remove
        it = self.channel_list.currentItem()
        url = it.data(Qt.UserRole) if it else None
        if url and confirm_remove(self, it.text().lstrip("#")):
            self._channels = [c for c in self._channels if c["url"] != url]
            self._fill_channels()

    def accept(self):
        s = self.settings
        s.data["channels"] = self._channels
        s.data["display_name"] = self.display_name.text().strip()
        s.data["export_dir"] = self.export_dir.text().strip() or s["export_dir"]
        s.data["encoder"] = self.encoder.currentData()
        s.data["recursive"] = self.recursive.isChecked()
        s.save()
        super().accept()
