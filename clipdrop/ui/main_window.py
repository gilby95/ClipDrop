import os
import subprocess
import time

from PySide6.QtCore import QByteArray, QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QSizePolicy, QSpacerItem, QSplitter, QStackedWidget, QStyle,
                               QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from ..library import Library, norm
from .. import storage
from ..media import fmt_size
from ..settings import Settings
from . import theme
from .cliplist import ClipDelegate, ClipModel, ClipRole
from .dialogs import FindFoldersDialog, OnboardingDialog, SettingsDialog
from .editor import EditorPane, copy_file_to_clipboard, gpu_note, show_in_folder
from .theme import app_icon
from .storage_dialog import StorageDialog
from .update_dialog import UpdateChecker, UpdateDialog

SORTS = [("Newest first", "newest"), ("Oldest first", "oldest"), ("Name", "name"), ("Biggest", "size")]


class FolderDelegate(QStyledItemDelegate):
    """Sidebar folder row: icon, name, count on the right; missing folders in red."""
    COUNT = Qt.UserRole + 1
    MISSING = Qt.UserRole + 2

    def sizeHint(self, option, index):
        return QSize(180, 36)

    def paint(self, p, opt, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(opt.rect).adjusted(0, 1, 0, -1)
        selected = bool(opt.state & QStyle.State_Selected)
        if selected or opt.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURFACE_HI if selected else theme.SURFACE))
            p.drawRoundedRect(r, 8, 8)
        is_all = index.data(Qt.UserRole) is None
        missing = bool(index.data(self.MISSING))
        name = "grid" if is_all else ("folder-alert" if missing else "folder")
        color = theme.BAD if missing else (theme.ACCENT if selected else theme.MUTED)
        p.drawPixmap(QPointF(r.left() + 10, r.center().y() - 8), theme.icon_pixmap(name, color, 16))
        count = str(index.data(self.COUNT) or 0)
        f = theme.mono(12)
        p.setFont(f)
        cw = QFontMetrics(f).horizontalAdvance(count)
        p.setPen(QColor(theme.TEXT if selected else theme.FAINT))
        p.drawText(QRectF(r.right() - 10 - cw, r.top(), cw + 2, r.height()), Qt.AlignVCenter | Qt.AlignLeft, count)
        f = theme.ui(13, QFont.DemiBold if selected else QFont.Normal)
        p.setFont(f)
        fm = QFontMetrics(f)
        x = r.left() + 36
        avail = r.right() - 18 - cw - x
        text = index.data(Qt.DisplayRole)
        suffix = "  (missing)" if missing else ""
        p.setPen(QColor(theme.MUTED if missing else (theme.TEXT if selected else "#d4d7dc")))
        shown = fm.elidedText(text, Qt.ElideMiddle, int(avail - fm.horizontalAdvance(suffix)))
        p.drawText(QRectF(x, r.top(), avail, r.height()), Qt.AlignVCenter | Qt.AlignLeft, shown)
        if missing:
            p.setPen(QColor(theme.BAD))
            p.setFont(theme.ui(12))
            p.drawText(QRectF(x + fm.horizontalAdvance(shown), r.top(), avail, r.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, suffix)
        p.restore()


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
        self.editor.exported.connect(lambda _src: self._refresh_storage())
        self.editor.wantChannels.connect(self._need_channels)
        self.editor.jobProgress.connect(self._on_job_progress)
        split.addWidget(self.editor)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 0)
        split.setStretchFactor(2, 1)
        split.setSizes([220, 360, 920])
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
            QTimer.singleShot(400, self.onboard)

        self._update_info = None
        self.updater = UpdateChecker(self)
        self.updater.found.connect(self._on_update_found)
        QTimer.singleShot(3000, self.updater.check)
        self._refresh_storage()
        self._storage_timer = QTimer(self, interval=15000, timeout=self._refresh_storage)
        self._storage_timer.start()
        self._update_timer = QTimer(self, interval=6 * 3600 * 1000, timeout=self.updater.check)
        self._update_timer.start()

    # Sidebar ------------------------------------------------------------------

    def _build_sidebar(self):
        w = QWidget()
        w.setObjectName("Sidebar")
        w.setAttribute(Qt.WA_StyledBackground)
        w.setMinimumWidth(200)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 18, 12, 10)
        lay.setSpacing(6)
        brand = QHBoxLayout()
        brand.setContentsMargins(4, 0, 0, 0)
        brand.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(theme.logo_label_pixmap(32))
        logo.setFixedSize(32, 32)
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(1)
        title = QLabel("ClipDrop")
        title.setObjectName("AppTitle")
        col.addWidget(title)
        sub = QLabel("Clips → Discord, sized right.")
        sub.setObjectName("Tagline")
        col.addWidget(sub)
        brand.addLayout(col, 1)
        lay.addLayout(brand)
        lay.addSpacing(22)
        sec = QLabel("FOLDERS")
        sec.setObjectName("Section")
        sec.setContentsMargins(10, 0, 0, 2)
        lay.addWidget(sec)
        self.folder_list = QListWidget()
        self.folder_list.setItemDelegate(FolderDelegate(self.folder_list))
        self.folder_list.setMouseTracking(True)
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self._folder_menu)
        self.folder_list.currentItemChanged.connect(self._on_folder_pick)
        self.folder_list.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.folder_list, 1)
        self.no_folders = QLabel("No folders yet. Add the one your capture app saves to.")
        self.no_folders.setObjectName("Faint")
        self.no_folders.setWordWrap(True)
        self.no_folders.setContentsMargins(10, 0, 6, 0)
        lay.addWidget(self.no_folders)
        self._side_stretch = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Minimum)
        lay.addItem(self._side_stretch)
        self.update_btn = QPushButton("")
        self.update_btn.setObjectName("Primary")
        self.update_btn.setIcon(theme.icon("update", theme.ON_ACCENT, width=2.2))
        self.update_btn.setMinimumHeight(36)
        self.update_btn.clicked.connect(self._open_update)
        self.update_btn.setFocusPolicy(Qt.NoFocus)
        self.update_btn.hide()
        lay.addWidget(self.update_btn)
        lay.addSpacing(2)
        add = QPushButton(" Add folder")
        add.setIcon(theme.icon("plus"))
        add.setStyleSheet("text-align: left; padding-left: 12px;")
        add.clicked.connect(self.add_folder)
        find = QPushButton(" Find my clip folders")
        find.setObjectName("SideNav")
        find.setIcon(theme.icon("find", theme.TEXT_2))
        find.clicked.connect(self.find_folders)
        lay.addWidget(add)
        lay.addWidget(find)
        srow = QHBoxLayout()
        srow.setContentsMargins(0, 0, 6, 0)
        self.storage_btn = QPushButton(" Compressed clips")
        self.storage_btn.setObjectName("SideNav")
        self.storage_btn.setIcon(theme.icon("storage", theme.TEXT_2))
        self.storage_btn.setToolTip("See, open and clean out the smaller copies ClipDrop made")
        self.storage_btn.clicked.connect(self.open_storage)
        srow.addWidget(self.storage_btn, 1)
        self.storage_size = QLabel("")
        self.storage_size.setObjectName("Mono")
        self.storage_size.setStyleSheet(f"color: {theme.FAINT}; font-size: 11px;")
        srow.addWidget(self.storage_size)
        lay.addLayout(srow)
        line = QFrame()
        line.setObjectName("Hairline")
        lay.addSpacing(4)
        lay.addWidget(line)
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 6, 0)
        settings = QPushButton(" Settings")
        settings.setObjectName("SideNav")
        settings.setIcon(theme.icon("settings", theme.TEXT_2))
        settings.clicked.connect(self.open_settings)
        row.addWidget(settings, 1)
        from .. import __version__
        ver = QLabel(__version__)
        ver.setObjectName("Mono")
        ver.setStyleSheet(f"color: {theme.FAINT}; font-size: 11px;")
        row.addWidget(ver)
        lay.addLayout(row)
        for b in (add, find, settings, self.storage_btn):
            b.setFocusPolicy(Qt.NoFocus)
            b.setIconSize(theme.ICON_SIZE)
            b.setMinimumHeight(34)
        return w

    def _refresh_folders(self):
        current = self.model.folder if hasattr(self, "model") else None
        self.folder_list.blockSignals(True)
        self.folder_list.clear()
        counts = {}
        for c in self.library.clips.values():
            counts[norm(c.root)] = counts.get(norm(c.root), 0) + 1
        all_item = QListWidgetItem("All clips")
        all_item.setData(Qt.UserRole, None)
        all_item.setData(FolderDelegate.COUNT, len(self.library.clips))
        self.folder_list.addItem(all_item)
        select = all_item
        for f in self.settings["folders"]:
            name = os.path.basename(os.path.normpath(f)) or f
            it = QListWidgetItem(name)
            it.setToolTip(f)
            it.setData(Qt.UserRole, f)
            it.setData(FolderDelegate.COUNT, counts.get(norm(f), 0))
            it.setData(FolderDelegate.MISSING, not os.path.isdir(f))
            self.folder_list.addItem(it)
            if current and norm(current) == norm(f):
                select = it
        self.folder_list.setCurrentItem(select)
        self.folder_list.blockSignals(False)
        empty = not self.settings["folders"]
        self.no_folders.setVisible(empty)
        self.folder_list.setMaximumHeight(40 if empty else 16777215)
        self._side_stretch.changeSize(0, 0, QSizePolicy.Minimum,
                                      QSizePolicy.Expanding if empty else QSizePolicy.Minimum)
        self.folder_list.parentWidget().layout().invalidate()

    def _on_folder_pick(self, item, _prev):
        self.model.folder = item.data(Qt.UserRole) if item else None
        self._reload_list()

    def _folder_menu(self, pos):
        item = self.folder_list.itemAt(pos)
        if not item or not item.data(Qt.UserRole):
            return
        path = item.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction(theme.icon("folder", theme.MUTED), "Open in Explorer",
                    lambda: os.path.isdir(path) and os.startfile(path))
        m.addAction(theme.icon("close", theme.MUTED), "Stop watching this folder", lambda: self.remove_folder(path))
        m.exec(self.folder_list.mapToGlobal(pos))

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Pick a folder where your clips are saved")
        if d:
            self._add_folders([os.path.normpath(d)])

    def onboard(self):
        dlg = OnboardingDialog(self.settings, self)
        if dlg.exec():
            self.editor.size_combo.setCurrentIndex(max(0, self.editor.size_combo.findData(self.settings["size_preset"])))
            self._add_folders(dlg.selected())

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
        w.setAttribute(Qt.WA_StyledBackground)
        w.setMinimumWidth(340)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 14, 0, 6)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(14, 0, 14, 0)
        top.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search clips")
        self.search.addAction(theme.icon("search", theme.FAINT, 15), QLineEdit.LeadingPosition)
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
        el.setContentsMargins(34, 0, 34, 50)
        el.setSpacing(0)
        el.addStretch()
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignCenter)
        el.addWidget(self.empty_icon, 0, Qt.AlignHCenter)
        el.addSpacing(16)
        self.empty_title = QLabel("")
        self.empty_title.setObjectName("Big")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_hint = QLabel("")
        self.empty_hint.setObjectName("Muted")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_btn = QPushButton(" Find my clip folders")
        self.empty_btn.setObjectName("Primary")
        self.empty_btn.setIcon(theme.icon("find", theme.ON_ACCENT, width=2.2))
        self.empty_btn.setIconSize(theme.ICON_SIZE)
        self.empty_btn.clicked.connect(self.find_folders)
        self.empty_link = QPushButton("Or pick a folder yourself")
        self.empty_link.setObjectName("Link")
        self.empty_link.clicked.connect(self.add_folder)
        self.empty_clear = QPushButton("Clear search")
        self.empty_clear.setObjectName("Link")
        self.empty_clear.clicked.connect(self.search.clear)
        el.addWidget(self.empty_title)
        el.addSpacing(8)
        el.addWidget(self.empty_hint)
        el.addSpacing(18)
        for b in (self.empty_btn, self.empty_link, self.empty_clear):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            el.addWidget(b, 0, Qt.AlignCenter)
        el.addSpacing(4)
        el.addStretch()

        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.view)
        self.list_stack.addWidget(self.empty)
        lay.addWidget(self.list_stack, 1)
        return w

    def _empty_tile(self, name, lime):
        size, dpr = 64 if lime else 52, 2.0
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.ACCENT_LINE if lime else theme.BORDER), 1))
        p.setBrush(QColor(theme.ACCENT_SOFT if lime else theme.SURFACE))
        p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 16 if lime else 13, 16 if lime else 13)
        ic = 30 if lime else 22
        p.drawPixmap(QPointF((size - ic) / 2, (size - ic) / 2),
                     theme.icon_pixmap(name, theme.ACCENT if lime else theme.MUTED, ic, 1.8))
        p.end()
        self.empty_icon.setPixmap(pm)

    def _sync_empty(self):
        searching = bool(self.search.text())
        if not self.settings["folders"]:
            self._empty_tile("find", True)
            self.empty_title.setText("Where do your clips go?")
            self.empty_hint.setText("ClipDrop watches the folders your recording app saves to (OBS, NVIDIA, Medal, "
                                    "Xbox Game Bar, AMD) and puts every clip in one list.")
            self.empty_btn.show()
            self.empty_link.show()
            self.empty_clear.hide()
            self.list_stack.setCurrentIndex(1)
        elif not self.model.clips():
            self._empty_tile("search" if searching else "video", False)
            self.empty_title.setText("No matches" if searching else "No clips here yet")
            self.empty_hint.setText(f"Nothing called “{self.search.text()}”." if searching else
                                    "Go save a clip. It'll pop up here right away.")
            self.empty_btn.hide()
            self.empty_link.hide()
            self.empty_clear.setVisible(searching)
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

    def _refresh_storage(self):
        total, n = storage.usage(self.settings["export_dir"])
        self.storage_size.setText(fmt_size(total) if n else "")
        self.storage_btn.setToolTip(f"{n} compressed clip{'s' if n != 1 else ''} in {self.settings['export_dir']}"
                                    "\nClick to open, delete or empty them")

    def open_storage(self):
        dlg = StorageDialog(self.settings, busy=self.editor.busy(), parent=self)
        dlg.changed.connect(self._after_storage_change)
        dlg.exec()
        self._after_storage_change()

    def _after_storage_change(self):
        # forget compressed copies that are gone, so the green "ready" badges and card go away
        gone = [src for src, e in list(self.settings.data["exports"].items())
                if e.get("path") != src and not os.path.exists(e.get("path", ""))]
        for src in gone:
            self.settings.data["exports"].pop(src, None)
        if gone:
            self.settings.save()
        for src in gone:
            self.model.clip_changed(src)
        ed = self.editor
        if ed.export_stack.currentIndex() == 2 and ed.drop.path and not os.path.exists(ed.drop.path):
            ed.export_stack.setCurrentIndex(0)
        self._refresh_storage()
        self.library.rescan()

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

    def _on_job_progress(self, path, frac):
        if frac < 0:
            self.model.progress.pop(path, None)
        else:
            self.model.progress[path] = frac
        self.model.clip_changed(path)

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
            m.addAction(theme.icon("copy"), "Copy compressed clip (Ctrl+V in Discord)",
                        lambda: copy_file_to_clipboard(e["path"]))
            m.addAction(theme.icon("folder", theme.MUTED), "Show compressed clip", lambda: show_in_folder(e["path"]))
            m.addAction(theme.icon("close", theme.BAD), "Delete compressed copy",
                        lambda: self._delete_export(clip.path, e["path"]))
            m.addSeparator()
        m.addAction(theme.icon("copy", theme.MUTED), "Copy original file", lambda: copy_file_to_clipboard(clip.path))
        m.addAction(theme.icon("folder", theme.MUTED), "Show original in folder", lambda: show_in_folder(clip.path))
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
