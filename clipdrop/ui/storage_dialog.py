"""Compressed clips: where they live, how much space they take, and cleaning them out."""
import datetime
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox,
                               QStackedWidget, QTreeWidget, QTreeWidgetItem)

from .. import storage
from ..media import fmt_size
from . import theme
from .dialogs import Shell, button, label
from .editor import show_in_folder


def _when(ts):
    d = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    t = d.strftime("%I:%M %p").lstrip("0")
    if d.date() == today:
        return f"Today {t}"
    if d.date() == today - datetime.timedelta(days=1):
        return f"Yesterday {t}"
    return d.strftime("%b %d") + ("" if d.year == today.year else d.strftime(" %Y"))


class _SizeItem(QTreeWidgetItem):
    """Sorts the Size and Made columns by their real values, not the text."""

    def __lt__(self, other):
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if col in (1, 2):
            return self.data(col, Qt.UserRole) < other.data(col, Qt.UserRole)
        return self.text(col).lower() < other.text(col).lower()


class StorageDialog(QDialog):
    changed = Signal()          # files were deleted or the folder moved

    def __init__(self, settings, busy=False, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.busy = busy
        self.setWindowTitle("Compressed clips")
        self.resize(680, 560)
        shell = Shell(self, "Compressed clips",
                      "The smaller copies ClipDrop made for Discord. Your original recordings are never touched.",
                      width=640)
        body = shell.body

        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_label = label("", "Mono")
        self.path_label.setStyleSheet(f"color: {theme.TEXT_2}; font-size: 12px;")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.path_label, 1)
        open_btn = button("Open folder", icon="folder")
        open_btn.clicked.connect(self._open)
        change_btn = button("Change…", "Flat")
        change_btn.clicked.connect(self._change)
        row.addWidget(open_btn)
        row.addWidget(change_btn)
        body.addLayout(row)

        top = QHBoxLayout()
        self.summary = label("", "Big")
        top.addWidget(self.summary, 1)
        top.addWidget(label("Auto-delete clips older than", "Muted"))
        self.auto = QComboBox()
        for text, days in (("Never", 0), ("7 days", 7), ("14 days", 14), ("30 days", 30), ("60 days", 60),
                           ("90 days", 90)):
            self.auto.addItem(text, days)
        self.auto.setCurrentIndex(max(0, self.auto.findData(int(settings.get("cleanup_days", 30) or 0))))
        self.auto.setToolTip("Old compressed copies go to the Recycle Bin automatically.\n"
                             "Your original recordings are never touched.")
        self.auto.currentIndexChanged.connect(lambda _i: self.settings.__setitem__("cleanup_days", self.auto.currentData()))
        top.addWidget(self.auto)
        body.addLayout(top)

        self.stack = QStackedWidget()
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Clip", "Size", "Made"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSortingEnabled(True)
        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 8px;"
            f" outline: none; padding: 4px; }}"
            f"QTreeWidget::item {{ height: 30px; padding: 0 6px; color: {theme.TEXT}; }}"
            f"QTreeWidget::item:selected {{ background: {theme.ACCENT_SOFT}; color: {theme.TEXT}; }}"
            f"QTreeWidget::item:hover:!selected {{ background: {theme.SURFACE_HI}; }}"
            f"QHeaderView::section {{ background: {theme.SURFACE}; color: {theme.MUTED}; border: none;"
            f" border-bottom: 1px solid {theme.BORDER}; padding: 6px; font-weight: 600; }}")
        self.tree.itemSelectionChanged.connect(self._sync_buttons)
        self.tree.itemDoubleClicked.connect(lambda it, _c: show_in_folder(it.data(0, Qt.UserRole)))
        self.stack.addWidget(self.tree)
        empty = label("No compressed clips here. They show up after you press Compress for Discord.", "Muted", wrap=True)
        empty.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(empty)
        body.addWidget(self.stack, 1)
        hint = label("Deleted clips go to the Recycle Bin, so you can get them back.", "Faint", wrap=True)
        body.addWidget(hint)

        self.del_btn = button("Delete selected", "Danger", icon="trash", icon_color=theme.BAD)
        self.del_btn.clicked.connect(self._delete_selected)
        self.empty_btn = button("Empty folder", "Danger", icon="trash", icon_color=theme.BAD)
        self.empty_btn.clicked.connect(self._empty)
        done = button("Done", "Primary")
        done.clicked.connect(self.accept)
        shell.footer.addWidget(self.del_btn)
        shell.footer.addWidget(self.empty_btn)
        shell.footer.addStretch()
        shell.footer.addWidget(done)
        self.refresh()

    # Data ---------------------------------------------------------------------

    def refresh(self):
        folder = self.settings["export_dir"]
        fm = QFontMetrics(self.path_label.font())
        self.path_label.setText(fm.elidedText(folder, Qt.ElideMiddle, 340))
        self.path_label.setToolTip(folder)
        files = storage.list_exports(folder)
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for path, size, mtime in files:
            it = _SizeItem([os.path.basename(path), fmt_size(size), _when(mtime)])
            it.setData(0, Qt.UserRole, path)
            it.setData(1, Qt.UserRole, size)
            it.setData(2, Qt.UserRole, mtime)
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            it.setForeground(1, theme.QColor(theme.TEXT_2))
            it.setForeground(2, theme.QColor(theme.MUTED))
            it.setToolTip(0, path)
            self.tree.addTopLevelItem(it)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(2, Qt.DescendingOrder)
        total = sum(f[1] for f in files)
        n = len(files)
        self.summary.setText(f"{n} clip{'s' if n != 1 else ''}  ·  {fmt_size(total) if n else '0 MB'}")
        self.stack.setCurrentIndex(0 if files else 1)
        self._sync_buttons()

    def _sync_buttons(self):
        self.del_btn.setEnabled(bool(self.tree.selectedItems()))
        self.empty_btn.setEnabled(self.tree.topLevelItemCount() > 0)

    # Actions ------------------------------------------------------------------

    def _open(self):
        folder = self.settings["export_dir"]
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder) if os.name == "nt" else show_in_folder(folder)

    def _change(self):
        d = QFileDialog.getExistingDirectory(self, "Save compressed clips to", self.settings["export_dir"])
        if d:
            self.settings["export_dir"] = os.path.normpath(d)
            self.refresh()
            self.changed.emit()

    def _delete(self, paths, what):
        size = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
        if QMessageBox.question(
                self, "Delete compressed clips",
                f"Move {what} ({fmt_size(size)}) to the Recycle Bin?\n\n"
                "Only ClipDrop's smaller copies are removed. Your original recordings stay where they are."
        ) != QMessageBox.Yes:
            return
        failed = storage.recycle(paths)
        self.refresh()
        self.changed.emit()
        if failed:
            QMessageBox.warning(self, "Some clips weren't deleted",
                                f"{len(failed)} file(s) couldn't be removed. They may be open in another program.")

    def _delete_selected(self):
        paths = [it.data(0, Qt.UserRole) for it in self.tree.selectedItems()]
        if paths:
            self._delete(paths, f"{len(paths)} clip{'s' if len(paths) != 1 else ''}")

    def _empty(self):
        paths = [p for p, _s, _m in storage.list_exports(self.settings["export_dir"])]
        if paths:
            self._delete(paths, f"all {len(paths)} compressed clip{'s' if len(paths) != 1 else ''}")
