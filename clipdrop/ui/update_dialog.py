import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel, QMessageBox, QProgressBar,
                               QVBoxLayout)

from .. import __version__, update


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
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        t = QLabel(f"ClipDrop {info['version']} is out")
        t.setObjectName("Big")
        lay.addWidget(t)
        sub = QLabel(f"You have {__version__}. Updating takes about a minute; your clips, folders and "
                     "settings stay as they are.")
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        if info["notes"]:
            notes = QLabel(info["notes"])
            notes.setWordWrap(True)
            notes.setStyleSheet("background:#222328; border-radius:6px; padding:8px;")
            lay.addWidget(notes)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        bb = QDialogButtonBox()
        self.go = bb.addButton("Update now", QDialogButtonBox.AcceptRole)
        self.go.setObjectName("Primary")
        later = bb.addButton("Later", QDialogButtonBox.RejectRole)
        self.go.clicked.connect(self._start)
        later.clicked.connect(self.reject)
        lay.addWidget(bb)
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
        self.go.setEnabled(False)
        self.progress.show()
        self.status.setText("Downloading…")
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
        self.status.setText("Installing… ClipDrop will reopen by itself.")
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
        self.go.setEnabled(True)
        self.progress.hide()
        self.status.setText(f"Update failed: {msg}")
        self.status.setStyleSheet("color:#ed4245;")

    def reject(self):
        self._cancel.set()
        super().reject()
