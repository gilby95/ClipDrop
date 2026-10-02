import os
import subprocess
import time

from PySide6.QtCore import QByteArray, QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from ..library import Library, norm
from ..settings import Settings
from .cliplist import ClipDelegate, ClipModel, ClipRole
from .dialogs import FindFoldersDialog, SettingsDialog
from .editor import EditorPane, copy_file_to_clipboard, gpu_note, show_in_folder
from .theme import app_icon
from .update_dialog import UpdateChecker, UpdateDialog

SORTS = [("Newest first", "newest"), ("Oldest first", "oldest"), ("Name", "name"), ("Biggest", "size")]


class KeyFilter(QObject):
    """Space / I / O / arrows drive the player unless you're typing somewhere."""

    def __init__(self, window):
        super().__init__(window)
        self.w = window

    def eventFilter(self, obj, e):
        if e.type() != QEvent.KeyPress or not self.w.isActiveWindow():
            return False
        from PySide6.QtWidgets import QApplication
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QAbstractSpinBox)) or (isinstance(focus, QComboBox) and focus.isEditable()):
            return False
        if QApplication.activeModalWidget():
            return False
        ed = self.w.editor
        k, mods = e.key(), e.modifiers()
        shift = bool(mods & Qt.ShiftModifier)
        if k == Qt.Key_Space:
            ed.toggle_play()
        elif k in (Qt.Key_I, Qt.Key_BracketLeft):
            ed.set_in()
        elif k in (Qt.Key_O, Qt.Key_BracketRight):
            ed.set_out()
        elif k == Qt.Key_Left:
            ed.step(-5000 if shift else -1000)
        elif k == Qt.Key_Right:
            ed.step(5000 if shift else 1000)
        elif k == Qt.Key_Comma:
            ed.frame_step(-1)
        elif k == Qt.Key_Period:
            ed.frame_step(1)
        elif k in (Qt.Key_Return, Qt.Key_Enter) and mods & Qt.ControlModifier:
            ed.start_export()
        else:
            return False
        return True


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipDrop")
        self.setWindowIcon(app_icon())
        self.settings = Settings()
        self.library = Library(self.settings, self)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_sidebar())
        split.addWidget(self._build_browser())
        self.editor = EditorPane(self.settings)
        self.editor.status.connect(lambda s: self.statusBar().showMessage(s, 8000))
        self.editor.exported.connect(self.model.clip_changed)
        self.editor.wantChannels.connect(self._need_channels)
        split.addWidget(self.editor)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 0)
        split.setStretchFactor(2, 1)
        split.setSizes([220, 380, 900])
        self.split = split
        self.setCentralWidget(split)
        self.statusBar().showMessage(gpu_note(), 6000)

        self.library.changed.connect(self._on_library_changed)
        self.library.clipUpdated.connect(self._on_clip_updated)
        self.library.clipArrived.connect(self._on_clip_arrived)
        self._keys = KeyFilter(self)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self._keys)

        self.resize(1500, 900)
        geo = self.settings.get("window")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo["geometry"].encode()))
                self.split.restoreState(QByteArray.fromBase64(geo["split"].encode()))
            except (KeyError, TypeError, ValueError):
                pass

        self._refresh_folders()
        self._sync_empty()
        self.library.start()
        QTimer.singleShot(0, self.view.setFocus)
        if not self.settings["folders"]:
            QTimer.singleShot(400, self.find_folders)

        self._update_info = None
        self.updater = UpdateChecker(self)
        self.updater.found.connect(self._on_update_found)
        QTimer.singleShot(3000, self.updater.check)
        self._update_timer = QTimer(self, interval=6 * 3600 * 1000, timeout=self.updater.check)
        self._update_timer.start()

    # Sidebar ------------------------------------------------------------------

    def _build_sidebar(self):
        w = QWidget()
        w.setObjectName("Sidebar")
        w.setMinimumWidth(190)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.setSpacing(8)
        title = QLabel("ClipDrop")
        title.setObjectName("AppTitle")
        lay.addWidget(title)
        sub = QLabel("Clips → Discord, sized right.")
        sub.setObjectName("Muted")
        lay.addWidget(sub)
        lay.addSpacing(10)
        sec = QLabel("FOLDERS")
        sec.setObjectName("Section")
        lay.addWidget(sec)
        self.folder_list = QListWidget()
        self.folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self._folder_menu)
        self.folder_list.currentItemChanged.connect(self._on_folder_pick)
        self.folder_list.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.folder_list, 1)
        self.update_btn = QPushButton("")
        self.update_btn.setObjectName("Primary")
        self.update_btn.clicked.connect(self._open_update)
        self.update_btn.setFocusPolicy(Qt.NoFocus)
        self.update_btn.hide()
        lay.addWidget(self.update_btn)
        add = QPushButton("+  Add folder")
        add.clicked.connect(self.add_folder)
        find = QPushButton("Find my clip folders")
        find.clicked.connect(self.find_folders)
        lay.addWidget(add)
        lay.addWidget(find)
        lay.addSpacing(6)
        settings = QPushButton("Settings")
        settings.setObjectName("Flat")
        settings.clicked.connect(self.open_settings)
        lay.addWidget(settings, 0, Qt.AlignLeft)
        for b in (add, find, settings):
            b.setFocusPolicy(Qt.NoFocus)
        return w

    def _refresh_folders(self):
        current = self.model.folder if hasattr(self, "model") else None
        self.folder_list.blockSignals(True)
        self.folder_list.clear()
        counts = {}
        for c in self.library.clips.values():
            counts[norm(c.root)] = counts.get(norm(c.root), 0) + 1
        all_item = QListWidgetItem(f"All clips   {len(self.library.clips)}")
        all_item.setData(Qt.UserRole, None)
        self.folder_list.addItem(all_item)
        select = all_item
        for f in self.settings["folders"]:
            name = os.path.basename(os.path.normpath(f)) or f
            missing = "" if os.path.isdir(f) else "  (missing)"
            it = QListWidgetItem(f"{name}   {counts.get(norm(f), 0)}{missing}")
            it.setToolTip(f)
            it.setData(Qt.UserRole, f)
            self.folder_list.addItem(it)
            if current and norm(current) == norm(f):
                select = it
        self.folder_list.setCurrentItem(select)
        self.folder_list.blockSignals(False)

    def _on_folder_pick(self, item, _prev):
        self.model.folder = item.data(Qt.UserRole) if item else None
        self._reload_list()

    def _folder_menu(self, pos):
        item = self.folder_list.itemAt(pos)
        if not item or not item.data(Qt.UserRole):
            return
        path = item.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Open in Explorer", lambda: os.path.isdir(path) and os.startfile(path))
        m.addAction("Stop watching this folder", lambda: self.remove_folder(path))
        m.exec(self.folder_list.mapToGlobal(pos))

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Pick a folder where your clips are saved")
        if d:
            self._add_folders([os.path.normpath(d)])

    def find_folders(self):
        dlg = FindFoldersDialog(self.settings["folders"], self)
        if dlg.exec():
            self._add_folders(dlg.selected())

    def _add_folders(self, paths):
        folders = list(self.settings["folders"])
        have = {norm(f) for f in folders}
        for p in paths:
            if norm(p) not in have:
                folders.append(p)
                have.add(norm(p))
        self.settings["folders"] = folders
        self._refresh_folders()
        self._sync_empty()
        self.library.rescan()

    def remove_folder(self, path):
        self.settings["folders"] = [f for f in self.settings["folders"] if norm(f) != norm(path)]
        if self.model.folder and norm(self.model.folder) == norm(path):
            self.model.folder = None
        self._refresh_folders()
        self._sync_empty()
        self.library.rescan()

    def _on_update_found(self, info):
        self._update_info = info
        self.update_btn.setText(f"Update to {info['version']}")
        self.update_btn.show()
        self.statusBar().showMessage(f"ClipDrop {info['version']} is available", 15000)

    def _open_update(self):
        if self._update_info:
            UpdateDialog(self._update_info, busy=self.editor.busy(), parent=self).exec()

    def _need_channels(self):
        QMessageBox.information(self, "Add a Discord channel",
                                "To share straight into Discord, add a channel's webhook link first "
                                "(Settings → Discord sharing → Add channel).")
        self.open_settings()

    def open_settings(self):
        if SettingsDialog(self.settings, self).exec():
            self.library.rescan()

    # Clip browser -------------------------------------------------------------

    def _build_browser(self):
        w = QWidget()
        w.setObjectName("Browser")
        w.setMinimumWidth(320)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 12, 6, 6)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setContentsMargins(6, 0, 6, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search clips")
        self.search.setClearButtonEnabled(True)
        self.search.setFocusPolicy(Qt.ClickFocus)
        self.search.textChanged.connect(self._on_search)
        top.addWidget(self.search, 1)
        self.sort = QComboBox()
        for label, key in SORTS:
            self.sort.addItem(label, key)
        self.sort.setCurrentIndex(max(0, self.sort.findData(self.settings["sort"])))
        self.sort.currentIndexChanged.connect(self._on_sort)
        self.sort.setFocusPolicy(Qt.NoFocus)
        top.addWidget(self.sort)
        lay.addLayout(top)

        self.model = ClipModel(self.library, self.settings, self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(ClipDelegate(self.model, self.settings, self.view))
        self.view.setMouseTracking(True)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setDragEnabled(True)
        self.view.setDragDropMode(QAbstractItemView.DragOnly)
        self.view.setDefaultDropAction(Qt.CopyAction)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._clip_menu)
        self.view.selectionModel().currentChanged.connect(self._on_clip_pick)

        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.addStretch()
        self.empty_title = QLabel("")
        self.empty_title.setObjectName("Big")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_hint = QLabel("")
        self.empty_hint.setObjectName("Muted")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_btn = QPushButton("Find my clip folders")
        self.empty_btn.setObjectName("Primary")
        self.empty_btn.clicked.connect(self.find_folders)
        el.addWidget(self.empty_title)
        el.addWidget(self.empty_hint)
        el.addSpacing(8)
        el.addWidget(self.empty_btn, 0, Qt.AlignCenter)
        el.addStretch()

        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.view)
        self.list_stack.addWidget(self.empty)
        lay.addWidget(self.list_stack, 1)
        return w

    def _sync_empty(self):
        if not self.settings["folders"]:
            self.empty_title.setText("Where do your clips go?")
            self.empty_hint.setText("Point ClipDrop at the folders your capture app saves to "
                                    "(OBS, ShadowPlay, Medal…). New clips show up here on their own.")
            self.empty_btn.show()
            self.list_stack.setCurrentIndex(1)
        elif not self.model.clips():
            self.empty_title.setText("No clips here yet" if not self.search.text() else "No matches")
            self.empty_hint.setText("New recordings appear here as soon as they're saved."
                                    if not self.search.text() else "")
            self.empty_btn.hide()
            self.list_stack.setCurrentIndex(1)
        else:
            self.list_stack.setCurrentIndex(0)

    def _reload_list(self):
        cur = self.editor.clip.path if self.editor.clip else None
        self.model.refresh()
        self._sync_empty()
        if cur:
            row = self.model.row_of(cur)
            if row >= 0:
                self.view.selectionModel().blockSignals(True)
                self.view.setCurrentIndex(self.model.index(row))
                self.view.selectionModel().blockSignals(False)

    def _on_search(self, text):
        self.model.text = text.strip()
        self._reload_list()

    def _on_sort(self):
        self.settings["sort"] = self.sort.currentData()
        self._reload_list()

    def _on_library_changed(self):
        self._reload_list()
        self._refresh_folders()
        if self.editor.clip and self.editor.clip.path not in self.library.clips and not self.editor.busy():
            self.editor.load(None)

    def _on_clip_updated(self, path):
        self.model.clip_changed(path)
        if self.editor.clip and self.editor.clip.path == path:
            clip = self.library.clips.get(path)
            self.editor.load(clip, self.model.pixmap(clip))

    def _on_clip_arrived(self, path):
        self.statusBar().showMessage(f"New clip: {os.path.basename(path)}", 10000)

    def _on_clip_pick(self, current, _prev):
        clip = current.data(ClipRole) if current.isValid() else None
        if clip and clip.new:
            clip.new = False
            self.model.clip_changed(clip.path)
        self.editor.load(clip, self.model.pixmap(clip) if clip else None)

    def _clip_menu(self, pos):
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        clip = idx.data(ClipRole)
        e = self.settings.export_for(clip.path)
        m = QMenu(self)
        if e:
            m.addAction("Copy compressed clip (Ctrl+V in Discord)", lambda: copy_file_to_clipboard(e["path"]))
            m.addAction("Show compressed clip", lambda: show_in_folder(e["path"]))
            m.addAction("Delete compressed copy", lambda: self._delete_export(clip.path, e["path"]))
            m.addSeparator()
        m.addAction("Copy original file", lambda: copy_file_to_clipboard(clip.path))
        m.addAction("Show original in folder", lambda: show_in_folder(clip.path))
        m.exec(self.view.viewport().mapToGlobal(pos))

    def _delete_export(self, src, path):
        if src == path:
            self.settings.forget_export(src)
        else:
            ok = QMessageBox.question(self, "Delete compressed copy",
                                      f"Delete {os.path.basename(path)}?\nThe original recording isn't touched.")
            if ok != QMessageBox.Yes:
                return
            try:
                os.remove(path)
            except OSError as err:
                QMessageBox.warning(self, "Couldn't delete", str(err))
                return
            self.settings.forget_export(src)
        self.model.clip_changed(src)
        if self.editor.clip and self.editor.clip.path == src:
            self.editor.export_stack.setCurrentIndex(0)

    # Shutdown -----------------------------------------------------------------

    def closeEvent(self, e):
        if self.editor.busy() and not getattr(self, "updating", False):
            ok = QMessageBox.question(self, "Still compressing", "A clip is still compressing. Quit anyway?")
            if ok != QMessageBox.Yes:
                e.ignore()
                return
        self.editor.shutdown()
        self.library.shutdown()
        self.settings.data["window"] = {
            "geometry": bytes(self.saveGeometry().toBase64()).decode(),
            "split": bytes(self.split.saveState().toBase64()).decode(),
        }
        self.settings.data["last_session_end"] = time.time()
        self.settings.save()
        super().closeEvent(e)
