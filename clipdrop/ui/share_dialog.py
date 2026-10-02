"""Share to Discord: pick a channel, optional message, send through the webhook."""
import os
import threading

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QProgressBar, QPushButton, QVBoxLayout)

from .. import share
from ..media import fmt_size


def default_name():
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USERNAME", "")


def ask_name(settings, parent, first_time=True):
    """Asks once for the name shown on posts. Returns it, or '' if cancelled."""
    if settings["display_name"] and first_time:
        return settings["display_name"]
    name, ok = QInputDialog.getText(parent, "Your name", "What name should your clips be posted under?",
                                    QLineEdit.Normal, settings["display_name"] or default_name())
    name = name.strip()
    if ok and name:
        settings["display_name"] = name
        return name
    return ""


class _Bridge(QObject):
    progress = Signal(float)
    done = Signal(object)
    failed = Signal(str, bool)
    cancelled = Signal()


class ShareDialog(QDialog):
    shared = Signal(str)        # channel name

    def __init__(self, settings, src, path, size, pixmap=None, parent=None):
        super().__init__(parent)
        self.settings, self.src, self.path = settings, src, path
        self.setWindowTitle("Share to Discord")
        self.setMinimumWidth(480)
        self._cancel = None
        self._sent = False

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        top = QHBoxLayout()
        thumb = QLabel()
        thumb.setFixedSize(112, 63)
        thumb.setStyleSheet("background:#0b0b0d; border-radius:6px;")
        if pixmap:
            thumb.setPixmap(pixmap.scaled(QSize(112, 63), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                            .copy(0, 0, 112, 63))
        top.addWidget(thumb)
        col = QVBoxLayout()
        t = QLabel("Share to Discord")
        t.setObjectName("Big")
        f = QLabel(f"{os.path.basename(path)}  ·  {fmt_size(size)}")
        f.setObjectName("Muted")
        col.addWidget(t)
        col.addWidget(f)
        top.addLayout(col, 1)
        lay.addLayout(top)

        lay.addWidget(QLabel("Channel"))
        self.channel = QComboBox()
        for ch in settings.channels():
            self.channel.addItem(f"#{ch['name']}", ch)
        last = settings["last_channel"]
        for i in range(self.channel.count()):
            if self.channel.itemData(i)["name"] == last:
                self.channel.setCurrentIndex(i)
        lay.addWidget(self.channel)

        lay.addWidget(QLabel("Message (optional)"))
        self.message = QLineEdit()
        self.message.setPlaceholderText("bro look at this")
        self.message.setMaxLength(1800)
        lay.addWidget(self.message)

        row = QHBoxLayout()
        self.as_label = QLabel()
        self.as_label.setObjectName("Muted")
        row.addWidget(self.as_label, 1)
        change = QPushButton("Change name")
        change.setObjectName("Flat")
        change.clicked.connect(self._change_name)
        row.addWidget(change)
        lay.addLayout(row)
        self._sync_name()

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.buttons = QDialogButtonBox()
        self.send_btn = self.buttons.addButton("Send", QDialogButtonBox.AcceptRole)
        self.send_btn.setObjectName("Primary")
        self.close_btn = self.buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.send_btn.clicked.connect(self._send)
        self.close_btn.clicked.connect(self._close)
        lay.addWidget(self.buttons)

        self.bridge = _Bridge()
        self.bridge.progress.connect(lambda f: self.progress.setValue(int(f * 1000)))
        self.bridge.done.connect(self._on_done)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.cancelled.connect(self._on_cancelled)
        self.message.setFocus()

    def _sync_name(self):
        self.as_label.setText(f"Posting as <b>{self.settings['display_name']}</b>")

    def _change_name(self):
        if ask_name(self.settings, self, first_time=False):
            self._sync_name()

    def _send(self):
        if self._sent:
            self.accept()
            return
        ch = self.channel.currentData()
        if not ch or self._cancel:
            return
        self._cancel = threading.Event()
        self.send_btn.setEnabled(False)
        self.channel.setEnabled(False)
        self.message.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText(f"Uploading to #{ch['name']}…")
        self.status.setStyleSheet("")
        cancel, bridge, path = self._cancel, self.bridge, self.path
        username = f"{self.settings['display_name']} via ClipDrop"
        content = self.message.text().strip()

        def job():
            try:
                bridge.done.emit(share.post_clip(ch["url"], path, username=username, content=content,
                                                 on_progress=bridge.progress.emit, cancel=cancel))
            except share.Cancelled:
                bridge.cancelled.emit()
            except share.ShareError as e:
                bridge.failed.emit(str(e), e.too_big)
            except Exception as e:
                bridge.failed.emit(f"Upload failed: {e}", False)

        threading.Thread(target=job, daemon=True).start()

    def _reset_controls(self):
        self._cancel = None
        self.send_btn.setEnabled(True)
        self.channel.setEnabled(True)
        self.message.setEnabled(True)
        self.progress.hide()

    def _on_done(self, _msg):
        ch = self.channel.currentData()
        self._reset_controls()
        self._sent = True
        self.settings.remember_share(self.src, ch["name"])
        self.status.setText(f"Posted to #{ch['name']} ✓")
        self.status.setObjectName("Good")
        self.status.setStyleSheet("color:#3ba55d; font-weight:600;")
        self.send_btn.setText("Done")
        self.close_btn.hide()
        self.channel.setEnabled(False)
        self.message.setEnabled(False)
        self.shared.emit(ch["name"])

    def _on_failed(self, msg, _too_big):
        self._reset_controls()
        self.status.setText(msg)
        self.status.setStyleSheet("color:#ed4245;")

    def _on_cancelled(self):
        self._reset_controls()
        self.status.setText("Cancelled.")
        self.status.setStyleSheet("")
        if self._closing:
            self.reject()

    _closing = False

    def _close(self):
        if self._cancel:
            self._closing = True
            self._cancel.set()
        else:
            self.reject()

    def reject(self):
        if self._cancel:
            self._closing = True
            self._cancel.set()
            return
        super().reject()


class AddChannelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a Discord channel")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        how = QLabel("In Discord: right-click the channel → <b>Edit Channel</b> → <b>Integrations</b> → "
                     "<b>Webhooks</b> → <b>New Webhook</b> → <b>Copy Webhook URL</b>. Paste it here.")
        how.setWordWrap(True)
        how.setObjectName("Muted")
        lay.addWidget(how)
        lay.addWidget(QLabel("Channel name (just a label, e.g. clips)"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("clips")
        lay.addWidget(self.name)
        lay.addWidget(QLabel("Webhook URL"))
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://discord.com/api/webhooks/…")
        lay.addWidget(self.url)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Check and add")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.accepted.connect(self._check)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _check(self):
        name = self.name.text().strip().lstrip("#")
        url = self.url.text().strip()
        if not name:
            self.status.setText("Give the channel a name.")
            return
        if not share.is_webhook_url(url):
            self.status.setText("That doesn't look like a Discord webhook URL. It starts with "
                                "https://discord.com/api/webhooks/")
            return
        self.status.setText("Checking with Discord…")
        self.repaint()
        try:
            share.webhook_info(url)
        except share.ShareError as e:
            self.status.setText(str(e))
            return
        self.result_channel = {"name": name, "url": url}
        self.accept()


def confirm_remove(parent, name):
    return QMessageBox.question(parent, "Remove channel", f"Stop sharing to #{name} from this PC?") == QMessageBox.Yes
