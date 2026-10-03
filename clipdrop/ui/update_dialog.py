import html
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QVBoxLayout)

from .. import __version__, update
from . import theme
from .dialogs import Shell, button


class UpdateChecker(QObject):
    found = Signal(object)

    def check(self):
        if not update.can_update():
            return

        def job():
            try:
                info = update.latest()
            except Exception:
                return          # offline, GitHub down, etc.: try again later
            if info:
                self.found.emit(info)

        threading.Thread(target=job, daemon=True).start()


class _Bridge(QObject):
    progress = Signal(float)
    done = Signal(str)
    failed = Signal(str)


class UpdateDialog(QDialog):
    def __init__(self, info, busy=False, parent=None):
        super().__init__(parent)
        self.info, self.busy = info, busy
        self.setWindowTitle("Update ClipDrop")
        s = Shell(self, f"ClipDrop {info['version']} is out",
                  f"You have {__version__}. Updating takes about a minute; your clips, folders and "
                  "settings stay as they are.")
        head = s.title.parentWidget().layout()
        head.removeWidget(s.title)
        head.removeWidget(s.subtitle)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(s.title)
        col.addWidget(s.subtitle)
        top = QHBoxLayout()
        top.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(theme.logo_label_pixmap(48))
        top.addWidget(logo, 0, Qt.AlignTop)
        top.addLayout(col, 1)
        head.addLayout(top)
        lay = s.body
        if info["notes"]:
            notes = QLabel(f"<span style='color:{theme.FAINT}; font-size:11px; font-weight:600'>WHAT'S NEW</span>"
                           "<br>" + html.escape(info["notes"]).replace("\n", "<br>"))
            notes.setWordWrap(True)
            notes.setTextFormat(Qt.RichText)
            notes.setStyleSheet(f"background:{theme.LIST}; border:1px solid {theme.BORDER}; border-radius:10px; "
                                f"padding:12px 14px; color:{theme.TEXT_2};")
            lay.addWidget(notes)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("Muted")
        self.progress_label.hide()
        lay.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch()
        s.footer.addStretch()
        self.later = button("Skip")
        self.later.setToolTip("Not now. You'll be asked again next time you open ClipDrop,"
                              " or update any time from the button in the sidebar.")
        self.go = button("Update now", "Primary", "update", theme.ON_ACCENT)
        self.go.setDefault(True)
        self.go.clicked.connect(self._start)
        self.later.clicked.connect(self.reject)
        s.footer.addWidget(self.later)
        s.footer.addWidget(self.go)
        self._cancel = threading.Event()
        self.bridge = _Bridge()
        self.bridge.progress.connect(lambda f: self.progress.setValue(int(f * 1000)))
        self.bridge.done.connect(self._install)
        self.bridge.failed.connect(self._failed)

    def _start(self):
        if self.busy and QMessageBox.question(
                self, "Still compressing", "A clip is still compressing and will be stopped. Update anyway?"
        ) != QMessageBox.Yes:
            return
        self.go.hide()
        self.later.setText("Cancel")
        self.progress.show()
        self.progress_label.setText("Downloading…")
        self.progress_label.show()
        self.status.setText("")
        self.status.setStyleSheet("")
        info, bridge, cancel = self.info, self.bridge, self._cancel

        def job():
            try:
                bridge.done.emit(update.download(info, bridge.progress.emit, cancel))
            except InterruptedError:
                pass
            except Exception as e:
                bridge.failed.emit(str(e))

        threading.Thread(target=job, daemon=True).start()

    def _install(self, path):
        self.progress.hide()
        self.progress_label.hide()
        self.later.hide()
        self.status.setText(f"<b>Installing…</b> <span style='color:{theme.MUTED}'>ClipDrop will reopen by itself.</span>")
        self.repaint()
        try:
            update.run_installer(path)
        except OSError as e:
            self._failed(str(e))
            return
        if self.parent() is not None:
            self.parent().updating = True
        QApplication.instance().closeAllWindows()
        QApplication.instance().quit()

    def _failed(self, msg):
        self.go.show()
        self.go.setText("Try again")
        self.later.show()
        self.later.setText("Skip")
        self.progress.hide()
        self.progress_label.hide()
        self.status.setText(f"Couldn't update: {msg}")
        self.status.setObjectName("Banner")
        self.status.setProperty("kind", "bad")
        theme.repolish(self.status)

    def reject(self):
        self._cancel.set()
        super().reject()
