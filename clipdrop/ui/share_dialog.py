"""Share to Discord: pick a channel, optional message, send through the webhook."""
import os
import threading

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QProgressBar, QPushButton, QVBoxLayout)

from .. import share
from ..media import fmt_size
from . import theme
from .dialogs import Shell, button, label


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
        self._cancel = None
        self._sent = False

        s = Shell(self, "Share to Discord", f"{os.path.basename(path)}  ·  {fmt_size(size)}", divider=True)
        thumb = QLabel()
        thumb.setFixedSize(96, 54)
        thumb.setStyleSheet("background:#0b0b0d; border-radius:6px;")
        if pixmap:
            thumb.setPixmap(pixmap.scaled(QSize(96, 54), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                            .copy(0, 0, 96, 54))
        head = s.title.parentWidget().layout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        head.removeWidget(s.title)
        head.removeWidget(s.subtitle)
        title_box.addWidget(s.title)
        title_box.addWidget(s.subtitle)
        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(thumb)
        top.addLayout(title_box, 1)
        head.addLayout(top)
        lay = s.body
        lay.setSpacing(6)

        lay.addWidget(label("Channel", "Muted"))
        self.channel = QComboBox()
        self.channel.setMinimumHeight(38)
        for ch in settings.channels():
            self.channel.addItem(f"#  {ch['name']}", ch)
        last = settings["last_channel"]
        for i in range(self.channel.count()):
            if self.channel.itemData(i)["name"] == last:
                self.channel.setCurrentIndex(i)
        lay.addWidget(self.channel)

        lay.addSpacing(8)
        lay.addWidget(label("Message <span style='color:#80868f'>(optional)</span>", "Muted"))
        self.message = QLineEdit()
        self.message.setPlaceholderText("bro look at this")
        self.message.setMaxLength(1800)
        self.message.setMinimumHeight(38)
        lay.addWidget(self.message)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.as_label = label("", "Muted")
        row.addWidget(self.as_label)
        change = QPushButton("Change name")
        change.setObjectName("Link")
        change.setCursor(Qt.PointingHandCursor)
        change.clicked.connect(self._change_name)
        row.addWidget(change)
        row.addStretch()
        lay.addSpacing(4)
        lay.addLayout(row)
        self._sync_name()

        self.progress_label = label("", "Muted")
        self.progress_label.hide()
        lay.addSpacing(6)
        lay.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setProperty("thin", True)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = label("", "Banner", wrap=True)
        self.status.hide()
        lay.addWidget(self.status)

        s.footer.addStretch()
        self.close_btn = button("Cancel")
        self.send_btn = button("Send", "Primary", "share", theme.ON_ACCENT)
        self.send_btn.setMinimumWidth(110)
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._send)
        self.close_btn.clicked.connect(self._close)
        s.footer.addWidget(self.close_btn)
        s.footer.addWidget(self.send_btn)

        self.bridge = _Bridge()
        self.bridge.progress.connect(lambda f: self.progress.setValue(int(f * 1000)))
        self.bridge.done.connect(self._on_done)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.cancelled.connect(self._on_cancelled)
        self.channel.currentIndexChanged.connect(self._warn_repost)
        self._warn_repost()
        self.message.setFocus()

    def _warn_repost(self, *_):
        """Heads-up when this clip already went to the chosen channel."""
        ch = self.channel.currentData()
        if not ch:
            return
        from .cliplist import when
        before = [x for x in self.settings.shares_for(self.src) if x["channel"] == ch["name"]]
        if before:
            t = when(before[-1]["time"]).replace("Today", "today").replace("Yesterday", "yesterday")
            self._banner(f"You already posted this clip to #{ch['name']} {t}. Send it again?", "warn")
        elif self.status.property("kind") == "warn":
            self._banner("")

    def _sync_name(self):
        self.as_label.setText(f"Posting as <b style='color:{theme.TEXT}'>{self.settings['display_name']}</b>  ·")

    def _banner(self, text, kind=None):
        self.status.setVisible(bool(text))
        self.status.setText(text)
        self.status.setProperty("kind", kind or "info")
        theme.repolish(self.status)

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
        self.progress_label.setText(f"Uploading to #{ch['name']}…")
        self.progress_label.show()
        self.send_btn.setText("Sending…")
        self.send_btn.setIcon(QIcon())
        self._banner("")
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
        self.send_btn.setText("Send")
        self.send_btn.setIcon(theme.icon("share", theme.ON_ACCENT, width=2.2))
        self.channel.setEnabled(True)
        self.message.setEnabled(True)
        self.progress.hide()
        self.progress_label.hide()

    def _on_done(self, _msg):
        ch = self.channel.currentData()
        self._reset_controls()
        self._sent = True
        self.settings.remember_share(self.src, ch["name"])
        self._banner(f"✓  Posted to #{ch['name']}", "good")
        self.send_btn.setText("Done")
        self.send_btn.setIcon(QIcon())
        self.close_btn.hide()
        self.channel.setEnabled(False)
        self.message.setEnabled(False)
        self.shared.emit(ch["name"])

    def _on_failed(self, msg, _too_big):
        self._reset_controls()
        self.send_btn.setText("Try again")
        self._banner(msg, "warn" if "rate limit" in msg.lower() or "busy" in msg.lower() else "bad")

    def _on_cancelled(self):
        self._reset_controls()
        self._banner("Cancelled.")
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
        s = Shell(self, "Add a Discord channel",
                  "You need a webhook link from the channel. Anyone who can edit the channel can make one.", width=590)
        lay = s.body
        lay.setSpacing(6)
        steps = ["Edit Channel", "Integrations", "Webhooks", "New Webhook", "Copy Webhook URL"]
        how = label("In Discord, right-click the channel:<br>" + f"  <span style='color:{theme.FAINT}'>→</span>  ".join(
            f"<b style='color:{theme.ACCENT}; font-family:\"{theme.MONO_FONT}\"'>{i}</b> {t}"
            for i, t in enumerate(steps, 1)), "Steps", wrap=True)
        lay.addWidget(how)
        lay.addSpacing(10)
        lay.addWidget(label("Channel name (just a label, e.g. clips)", "Muted"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("clips")
        self.name.setMinimumHeight(36)
        lay.addWidget(self.name)
        lay.addSpacing(8)
        lay.addWidget(label("Webhook URL", "Muted"))
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://discord.com/api/webhooks/…")
        self.url.setMinimumHeight(36)
        self.url.setStyleSheet(f"font-family: '{theme.MONO_FONT}'; font-size: 12px;")
        lay.addWidget(self.url)
        lay.addSpacing(6)
        self.status = label("", wrap=True)
        lay.addWidget(self.status)
        s.footer.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        self.ok = button("Check and add", "Primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._check)
        s.footer.addWidget(cancel)
        s.footer.addWidget(self.ok)

    def _say(self, text, bad=False, field=None):
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {theme.BAD if bad else theme.MUTED};")
        for f in (self.name, self.url):
            on = f is field
            if bool(f.property("error")) != on:
                f.setProperty("error", on)
                theme.repolish(f)

    def _check(self):
        name = self.name.text().strip().lstrip("#")
        url = self.url.text().strip()
        if not name:
            self._say("Give the channel a name.", True, self.name)
            return
        if not share.is_webhook_url(url):
            self._say("That doesn't look like a Discord webhook URL. It starts with "
                      "https://discord.com/api/webhooks/", True, self.url)
            return
        self._say("Checking with Discord…")
        self.ok.setEnabled(False)
        self.repaint()
        try:
            share.webhook_info(url)
        except share.ShareError as e:
            self.ok.setEnabled(True)
            self._say(str(e), True, self.url)
            return
        self.ok.setEnabled(True)
        self.result_channel = {"name": name, "url": url}
        self.accept()


def confirm_remove(parent, name):
    return QMessageBox.question(parent, "Remove channel", f"Stop sharing to #{name} from this PC?") == QMessageBox.Yes
