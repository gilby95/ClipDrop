import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..finder import find_capture_folders
from ..library import norm
from ..media import GPU_NAMES, gpu_encoder
from ..settings import SIZE_PRESETS
from . import theme


def label(text="", name=None, wrap=False):
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def button(text, name=None, icon=None, icon_color=theme.TEXT):
    b = QPushButton(f" {text}" if icon and text else text)
    if name:
        b.setObjectName(name)
    if icon:
        b.setIcon(theme.icon(icon, icon_color, width=2.2 if name == "Primary" else 2.0))
        b.setIconSize(theme.ICON_SIZE)
    b.setMinimumHeight(38)
    b.setCursor(Qt.PointingHandCursor)
    return b


class Shell:
    """Dialog layout from the design: title + subtitle, body, darker footer with the buttons on the right."""

    def __init__(self, dlg, title, subtitle=None, divider=False, width=560):
        dlg.setMinimumWidth(width)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QWidget()
        if divider:
            head.setObjectName("DialogHeader")
            head.setAttribute(Qt.WA_StyledBackground)
        hl = QVBoxLayout(head)
        hl.setContentsMargins(24, 22, 24, 16 if divider else 0)
        hl.setSpacing(5)
        self.title = label(title, "DialogTitle", wrap=True)
        hl.addWidget(self.title)
        self.subtitle = label(subtitle or "", "Muted", wrap=True)
        self.subtitle.setVisible(bool(subtitle))
        hl.addWidget(self.subtitle)
        root.addWidget(head)
        body = QWidget()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(24, 16, 24, 20)
        self.body.setSpacing(12)
        root.addWidget(body, 1)
        foot = QWidget()
        foot.setObjectName("DialogFooter")
        foot.setAttribute(Qt.WA_StyledBackground)
        self.footer = QHBoxLayout(foot)
        self.footer.setContentsMargins(24, 14, 24, 14)
        self.footer.setSpacing(8)
        root.addWidget(foot)


def section(text):
    lab = label(text, "Section")
    return lab


class FolderRow(QFrame):
    """One found folder: checkbox, source tag, path and video count. The whole row toggles."""

    def __init__(self, path, source, count, watched=False, parent=None):
        super().__init__(parent)
        self.setObjectName("FolderRow")
        self.path = path
        self.box = QCheckBox()
        self.box.setFocusPolicy(Qt.NoFocus)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 14, 10)
        lay.setSpacing(12)
        lay.addWidget(self.box)
        col = QVBoxLayout()
        col.setSpacing(5)
        tag = label(source, "Tag")
        tag.setStyleSheet(f"color: {theme.FAINT if watched else theme.TEXT};")
        col.addWidget(tag, 0, Qt.AlignLeft)
        p = label(path, "Mono")
        p.setStyleSheet(f"color: {'#6b7079' if watched else theme.MUTED}; font-size: 12px;")
        p.setToolTip(path)
        col.addWidget(p)
        lay.addLayout(col, 1)
        n = "Already watching" if watched else f"{count if count < 500 else '500+'} videos"
        lay.addWidget(label(n, "Muted"))
        if watched:
            self.box.setChecked(True)
            self.box.setEnabled(False)
            self.setProperty("done", True)
        else:
            self.box.setChecked(count > 0)
            self.setCursor(Qt.PointingHandCursor)
        self.box.toggled.connect(self._sync)
        self._sync()

    def _sync(self, *_):
        self.setProperty("on", self.box.isChecked() and self.box.isEnabled())
        theme.repolish(self)

    def mousePressEvent(self, e):
        if self.box.isEnabled() and e.button() == Qt.LeftButton:
            self.box.toggle()

    def picked(self):
        return self.box.isEnabled() and self.box.isChecked()


def folder_rows(already):
    have = {norm(p) for p in already}
    rows = []
    for path, source, count in find_capture_folders():
        rows.append(FolderRow(path, source, count, watched=norm(path) in have))
    rows.sort(key=lambda r: not r.box.isEnabled())
    return rows


class FindFoldersDialog(QDialog):
    """Shows where capture programs save clips on this PC; tick the ones to watch."""

    def __init__(self, already, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find my clip folders")
        self.rows = folder_rows(already)
        self.extra = []
        new = [r for r in self.rows if r.box.isEnabled()]
        s = Shell(self, "Find my clip folders",
                  "These folders have videos in them. Tick the ones to watch." if new else None, width=600)
        if new:
            for r in self.rows:
                s.body.addWidget(r)
                r.box.toggled.connect(self._sync)
        else:
            s.body.addStretch()
            tile = QLabel()
            tile.setPixmap(_tile_pixmap("find", False))
            s.body.addWidget(tile, 0, Qt.AlignHCenter)
            t = label("Nothing new found.", "Heading")
            t.setAlignment(Qt.AlignCenter)
            s.body.addWidget(t)
            h = label("Use “Add folder” to pick a folder yourself.", "Muted")
            h.setAlignment(Qt.AlignCenter)
            s.body.addWidget(h)
            s.body.addStretch()
            self.setMinimumHeight(340)
        s.body.addStretch()
        if new:
            add = button("Add folder", "Flat", "plus", theme.TEXT_2)
            add.clicked.connect(self._pick)
            s.footer.addWidget(add)
            s.footer.addStretch()
            cancel = button("Cancel")
            cancel.clicked.connect(self.reject)
            s.footer.addWidget(cancel)
            self.ok = button("", "Primary")
            self.ok.clicked.connect(self.accept)
            self.ok.setDefault(True)
            s.footer.addWidget(self.ok)
            self._sync()
        else:
            s.footer.addStretch()
            close = button("Close")
            close.clicked.connect(self.reject)
            s.footer.addWidget(close)
            add = button("Add folder", "Primary", "plus", theme.ON_ACCENT)
            add.clicked.connect(self._pick)
            s.footer.addWidget(add)

    def _sync(self, *_):
        n = sum(r.picked() for r in self.rows)
        self.ok.setText(f"Add {n} folder{'s' if n != 1 else ''}")
        self.ok.setEnabled(n > 0)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Pick a folder where your clips are saved")
        if d:
            self.extra.append(os.path.normpath(d))
            self.accept()

    def selected(self):
        return [r.path for r in self.rows if r.picked()] + self.extra


def _tile_pixmap(icon_name, lime, size=52, dpr=2.0):
    from PySide6.QtGui import QPen, QPixmap
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(theme.ACCENT_LINE if lime else theme.BORDER), 1))
    p.setBrush(QColor(theme.ACCENT_SOFT if lime else theme.SURFACE))
    p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 14, 14)
    ic = int(size * 0.46)
    p.drawPixmap(QPointF((size - ic) / 2, (size - ic) / 2),
                 theme.icon_pixmap(icon_name, theme.ACCENT if lime else theme.MUTED, ic, 1.8))
    p.end()
    return pm


class Choice(QFrame):
    """A radio button dressed as a card (encoder, size limit)."""

    def __init__(self, title, desc, right=None, tag=None, group=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Choice")
        self.setCursor(Qt.PointingHandCursor)
        self.radio = QRadioButton()
        self.radio.setFocusPolicy(Qt.NoFocus)
        if group is not None:
            group.addButton(self.radio)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 16, 12)
        lay.setSpacing(12)
        lay.addWidget(self.radio, 0, Qt.AlignTop if not right else Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(8)
        t = label(title)
        t.setStyleSheet("font-weight: 600; font-size: 14px;")
        top.addWidget(t)
        if tag:
            tg = label(tag)
            tg.setStyleSheet(f"background: {theme.GOOD_SOFT}; color: {theme.GOOD}; border-radius: 9px; "
                             "font-size: 11px; font-weight: 600; padding: 1px 7px;")
            top.addWidget(tg)
        top.addStretch()
        col.addLayout(top)
        d = label(desc, "Muted", wrap=True)
        d.setStyleSheet("font-size: 12px;")
        col.addWidget(d)
        lay.addLayout(col, 1)
        self.right = None
        if right:
            self.right = label(right)
            lay.addWidget(self.right)
        self.radio.toggled.connect(self._sync)
        self._sync()

    def _sync(self, *_):
        on = self.radio.isChecked()
        self.setProperty("on", on)
        theme.repolish(self)
        if self.right:
            self.right.setStyleSheet(f"font-family: '{theme.MONO_FONT}'; font-size: 15px; font-weight: 600; "
                                     f"color: {theme.ACCENT if on else theme.TEXT_2};")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.radio.setChecked(True)


class StepDots(QWidget):
    def __init__(self, count, parent=None):
        super().__init__(parent)
        self.count, self.current = count, 0
        self.setFixedSize(count * 12 + 12, 10)

    def set_current(self, i):
        self.current = i
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        x = 0
        for i in range(self.count):
            w = 18 if i == self.current else 6
            p.setBrush(QColor(theme.ACCENT if i == self.current else
                              theme.ACCENT_LINE if i < self.current else theme.BORDER_HI))
            p.drawRoundedRect(QRectF(x, 2, w, 6), 3, 3)
            x += w + 6


class OnboardingDialog(QDialog):
    """First launch: welcome → find folders → size limit → your name."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Welcome to ClipDrop")
        self.setFixedSize(560, 540)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        foot = QWidget()
        foot.setObjectName("DialogFooter")
        foot.setAttribute(Qt.WA_StyledBackground)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(24, 14, 24, 14)
        fl.setSpacing(8)
        self.dots = StepDots(4)
        fl.addWidget(self.dots)
        fl.addStretch()
        self.back = button("Back", "Flat")
        self.back.clicked.connect(lambda: self._go(self.pages.currentIndex() - 1))
        fl.addWidget(self.back)
        self.next = button("", "Primary")
        self.next.clicked.connect(self._next)
        self.next.setDefault(True)
        fl.addWidget(self.next)
        root.addWidget(foot)

        self.pages.addWidget(self._welcome())
        self.pages.addWidget(self._folders())
        self.pages.addWidget(self._sizes())
        self.pages.addWidget(self._name())
        self._go(0)

    def _page(self, title=None, sub=None):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 28, 28, 16)
        lay.setSpacing(6)
        if title:
            lay.addWidget(label(title, "Big", wrap=True))
        if sub:
            s = label(sub, "Muted", wrap=True)
            lay.addWidget(s)
            lay.addSpacing(12)
        return w, lay

    def _welcome(self):
        w, lay = self._page()
        lay.addStretch()
        logo = QLabel()
        logo.setPixmap(theme.logo_label_pixmap(84))
        lay.addWidget(logo, 0, Qt.AlignHCenter)
        lay.addSpacing(18)
        t = label("Welcome to ClipDrop")
        t.setStyleSheet("font-size: 26px; font-weight: 700;")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        s = label("Trim your clips, shrink them to fit Discord, and drop them straight into chat. "
                  "Setup takes about 30 seconds.", "Muted", wrap=True)
        s.setStyleSheet("font-size: 14px;")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(s)
        lay.addSpacing(18)
        chips = QHBoxLayout()
        chips.addStretch()
        for text in ("1 · Find your clips", "2 · Pick a size", "3 · Your name"):
            c = label(text)
            c.setStyleSheet(f"background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 13px; "
                            f"padding: 4px 12px; color: {theme.TEXT_2}; font-size: 12px;")
            chips.addWidget(c)
        chips.addStretch()
        lay.addLayout(chips)
        lay.addStretch()
        return w

    def _folders(self):
        self.rows = [r for r in folder_rows(self.settings["folders"]) if r.box.isEnabled()][:5]
        n = len(self.rows)
        w, lay = self._page("Where do your clips go?",
                            f"Found {n} folder{'s' if n != 1 else ''} with videos in them. Tick the ones to watch."
                            if n else "Didn't find any clip folders on this PC. Pick yours below.")
        for r in self.rows:
            lay.addWidget(r)
            r.box.toggled.connect(self._sync_next)
        self.extra = []
        pick = QPushButton("Not here? Pick a folder yourself")
        pick.setObjectName("Link")
        pick.setCursor(Qt.PointingHandCursor)
        pick.clicked.connect(self._pick)
        lay.addSpacing(4)
        lay.addWidget(pick, 0, Qt.AlignLeft)
        self.picked_label = label("", "Mono")
        self.picked_label.setWordWrap(True)
        lay.addWidget(self.picked_label)
        lay.addStretch()
        return w

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Pick a folder where your clips are saved")
        if d:
            self.extra.append(os.path.normpath(d))
            self.picked_label.setText("Added: " + ", ".join(self.extra))
            self._sync_next()

    def _sizes(self):
        w, lay = self._page("How big can your uploads be?",
                            "This depends on your Discord plan. Not sure? Pick the first one. It works for everyone.")
        group = QButtonGroup(self)
        self.size_choices = {}
        descs = {"discord_free": "Everyone in the server can watch it", "nitro_basic": "Better quality for longer clips",
                 "nitro": "Barely needs compressing"}
        for key, lab, mb in SIZE_PRESETS:
            if not mb:
                continue
            c = Choice(lab.split(" - ")[0].replace("Discord Nitro", "Nitro"), descs.get(key, ""), f"{mb} MB",
                       group=group)
            c.radio.setChecked(key == self.settings["size_preset"])
            self.size_choices[key] = c
            lay.addWidget(c)
        if not any(c.radio.isChecked() for c in self.size_choices.values()):
            next(iter(self.size_choices.values())).radio.setChecked(True)
        lay.addSpacing(6)
        lay.addWidget(label("You can change this anytime, right above the Compress button.", "Faint"))
        lay.addStretch()
        return w

    def _name(self):
        from .share_dialog import default_name
        w, lay = self._page("What name should your clips be posted under?",
                            "When you press Share to Discord, your friends see this name on the post.")
        lay.addWidget(label("Your name", "Muted"))
        self.name = QLineEdit(self.settings["display_name"] or default_name())
        self.name.setMinimumHeight(40)
        self.name.setMaxLength(60)
        self.name.textChanged.connect(self._sync_preview)
        lay.addWidget(self.name)
        lay.addSpacing(14)
        lay.addWidget(section("HOW IT LOOKS"))
        card = QFrame()
        card.setObjectName("FolderRow")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(14, 14, 14, 14)
        cl.setSpacing(12)
        av = QLabel()
        av.setPixmap(theme.logo_label_pixmap(36))
        cl.addWidget(av, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.preview = label("")
        col.addWidget(self.preview)
        msg = label("bro look at this")
        msg.setStyleSheet(f"color: {theme.TEXT_2};")
        col.addWidget(msg)
        col.addStretch()
        cl.addLayout(col, 1)
        lay.addWidget(card)
        lay.addStretch()
        self._sync_preview()
        return w

    def _sync_preview(self, *_):
        n = self.name.text().strip() or "you"
        self.preview.setText(f"<b>{n}</b> <span style='color:{theme.FAINT}; font-size:12px'>via ClipDrop</span>")

    def _sync_next(self, *_):
        i = self.pages.currentIndex()
        if i == 1:
            n = sum(r.picked() for r in self.rows) + len(self.extra)
            self.next.setText(f"Watch {n} folder{'s' if n != 1 else ''}" if n else "Skip for now")

    def _go(self, i):
        i = max(0, min(3, i))
        self.pages.setCurrentIndex(i)
        self.dots.set_current(i)
        self.back.setVisible(i > 0)
        self.next.setText(("Let's set it up", "", "Next", "Start clipping")[i])
        self._sync_next()

    def _next(self):
        i = self.pages.currentIndex()
        if i < 3:
            self._go(i + 1)
            return
        for key, c in self.size_choices.items():
            if c.radio.isChecked():
                self.settings.data["size_preset"] = key
        name = self.name.text().strip()
        if name:
            self.settings.data["display_name"] = name
        self.settings.save()
        self.accept()

    def selected(self):
        return [r.path for r in self.rows if r.picked()] + self.extra


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        from .. import __version__
        self.setWindowTitle(f"ClipDrop settings  ·  version {__version__}")
        s = Shell(self, "Settings", divider=True, width=620)
        s.title.setText(f"Settings  <span style='font-family:\"{theme.MONO_FONT}\"; font-size:12px; "
                        f"font-weight:500; color:{theme.FAINT}'>ClipDrop {__version__}</span>")
        lay = s.body
        lay.setSpacing(8)

        lay.addWidget(section("SAVE COMPRESSED CLIPS TO"))
        row = QHBoxLayout()
        self.export_dir = QLineEdit(settings["export_dir"])
        self.export_dir.addAction(theme.icon("folder", theme.MUTED, 15), QLineEdit.LeadingPosition)
        row.addWidget(self.export_dir, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        lay.addLayout(row)

        lay.addSpacing(12)
        lay.addWidget(section("COMPRESSING"))
        g = gpu_encoder()
        group = QButtonGroup(self)
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self.fast = Choice("Fast", "Uses your NVIDIA, AMD or Intel GPU, or the CPU if there's none.",
                           tag=f"{GPU_NAMES[g]} found" if g else None, group=group)
        self.best = Choice("Best quality", "Uses the CPU, about 3× slower.", group=group)
        (self.best if settings["encoder"] == "quality" else self.fast).radio.setChecked(True)
        for c in (self.fast, self.best):
            c.setMinimumHeight(92)
        cards.addWidget(self.fast)
        cards.addWidget(self.best)
        lay.addLayout(cards)
        lay.addWidget(label("Works on any PC. If the GPU encoder fails, ClipDrop switches to the CPU on its own.",
                            "Faint", wrap=True))

        lay.addSpacing(12)
        lay.addWidget(section("FOLDERS"))
        self.recursive = QCheckBox("Include sub-folders (e.g. ShadowPlay's per-game folders)")
        self.recursive.setChecked(bool(settings["recursive"]))
        lay.addWidget(self.recursive)

        lay.addSpacing(12)
        lay.addWidget(section("DISCORD SHARING"))
        row = QHBoxLayout()
        row.addWidget(label("Post clips as", "Muted"))
        self.display_name = QLineEdit(settings["display_name"])
        self.display_name.setPlaceholderText("your name")
        row.addWidget(self.display_name, 1)
        lay.addLayout(row)
        self.channel_list = QListWidget()
        self.channel_list.setObjectName("Channels")
        self.channel_list.setMaximumHeight(130)
        self.channel_list.currentItemChanged.connect(self._sync_remove)
        lay.addWidget(self.channel_list)
        row = QHBoxLayout()
        add = QPushButton(" Add channel")
        add.setIcon(theme.icon("plus"))
        add.clicked.connect(self._add_channel)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("Danger")
        self.remove_btn.clicked.connect(self._remove_channel)
        row.addWidget(add)
        row.addWidget(self.remove_btn)
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(label("Channels added here are built into the installer when you run build.bat, "
                            "so friends get them automatically.", "Faint", wrap=True))
        self._channels = list(settings["channels"])
        self._fill_channels()

        lay.addStretch()
        s.footer.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        save = button("Save", "Primary")
        save.clicked.connect(self.accept)
        save.setDefault(True)
        s.footer.addWidget(cancel)
        s.footer.addWidget(save)

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
            it = QListWidgetItem(f"#  {ch['name']}      came with ClipDrop")
            it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
            it.setToolTip("Built into this install, so it can't be removed")
            self.channel_list.addItem(it)
        for ch in self._channels:
            it = QListWidgetItem(f"#  {ch['name']}")
            it.setData(Qt.UserRole, ch["url"])
            self.channel_list.addItem(it)
        if not self.channel_list.count():
            it = QListWidgetItem("No channels yet. Add one to get a Share button.")
            it.setFlags(Qt.NoItemFlags)
            self.channel_list.addItem(it)
        self._sync_remove()

    def _sync_remove(self, *_):
        it = self.channel_list.currentItem()
        self.remove_btn.setEnabled(bool(it and it.data(Qt.UserRole)))

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
        if url and confirm_remove(self, it.text().lstrip("# ").strip()):
            self._channels = [c for c in self._channels if c["url"] != url]
            self._fill_channels()

    def accept(self):
        s = self.settings
        s.data["channels"] = self._channels
        s.data["display_name"] = self.display_name.text().strip()
        s.data["export_dir"] = self.export_dir.text().strip() or s["export_dir"]
        s.data["encoder"] = "quality" if self.best.radio.isChecked() else "fast"
        s.data["recursive"] = self.recursive.isChecked()
        s.save()
        super().accept()
