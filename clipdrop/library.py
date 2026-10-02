"""Watches the clip folders and keeps a list of clips with info + thumbnails."""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal

from .media import VIDEO_EXTS, probe, thumbnail
from .paths import cache_dir

SCAN_EVERY_MS = 4000


def norm(p):
    return os.path.normcase(os.path.normpath(p))


class Clip:
    __slots__ = ("path", "root", "size", "mtime", "info", "thumb", "error", "new")

    def __init__(self, path, root, size, mtime, new=False):
        self.path, self.root, self.size, self.mtime = path, root, size, mtime
        self.info = None
        self.thumb = None
        self.error = None
        self.new = new

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def group(self):
        """Sub-folder label, e.g. the game folder ShadowPlay/OBS sorted it into."""
        parent = os.path.dirname(self.path)
        if norm(parent) == norm(self.root):
            return os.path.basename(os.path.normpath(self.root)) or self.root
        return os.path.relpath(parent, self.root)


def walk(folders, recursive, exclude):
    found = {}
    for root in folders:
        if not os.path.isdir(root):
            continue
        stack = [root]
        while stack:
            d = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if recursive and not e.name.startswith((".", "$")) and norm(e.path) not in exclude:
                                stack.append(e.path)
                        elif os.path.splitext(e.name)[1].lower() in VIDEO_EXTS and ".part." not in e.name.lower():
                            key = norm(e.path)
                            if key not in found:
                                st = e.stat()
                                found[key] = (e.path, root, st.st_size, st.st_mtime)
                    except OSError:
                        pass
    return list(found.values())


class Library(QObject):
    changed = Signal()
    clipUpdated = Signal(str)
    clipArrived = Signal(str)
    _scanned = Signal(object)
    _probed = Signal(str, object, object, object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.clips = {}             # path -> Clip
        self._pending = {}          # path -> (size, mtime) while a file may still be recording
        self._scanning = False
        self._first_scan = True
        self._since = settings.get("last_session_end") or time.time()
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._cache_path = cache_dir() / "probe.json"
        self._thumb_dir = cache_dir() / "thumbs"
        self._thumb_dir.mkdir(exist_ok=True)
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                self._cache = json.load(f)
        except (OSError, ValueError):
            self._cache = {}
        self._cache_lock = threading.Lock()
        self._save_timer = QTimer(self, singleShot=True, interval=2000, timeout=self._save_cache)
        self._scanned.connect(self._on_scanned)
        self._probed.connect(self._on_probed)
        self._timer = QTimer(self, interval=SCAN_EVERY_MS, timeout=self.rescan)

    def start(self):
        self.rescan()
        self._timer.start()

    def shutdown(self):
        self._timer.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._save_cache()

    # Scanning -----------------------------------------------------------------

    def rescan(self):
        if self._scanning:
            return
        self._scanning = True
        folders = list(self.settings["folders"])
        recursive = self.settings["recursive"]
        exclude = {norm(self.settings["export_dir"])}

        def job():
            try:
                entries = walk(folders, recursive, exclude)
            except Exception:
                entries = None
            self._scanned.emit(entries)

        threading.Thread(target=job, daemon=True).start()

    def _on_scanned(self, entries):
        self._scanning = False
        if entries is None:
            return
        now = time.time()
        seen = set()
        changed = False
        for path, root, size, mtime in entries:
            seen.add(path)
            clip = self.clips.get(path)
            if clip:
                if clip.size != size or clip.mtime != mtime:
                    clip.size, clip.mtime = size, mtime
                    self._queue(clip)
                continue
            prev = self._pending.get(path)
            if prev is None:
                ready = now - mtime > 10
            else:
                ready = prev == (size, mtime) and now - mtime > 3
            if not ready:                       # still being recorded / saved
                self._pending[path] = (size, mtime)
                continue
            self._pending.pop(path, None)
            clip = Clip(path, root, size, mtime, new=mtime > self._since)
            self.clips[path] = clip
            self._queue(clip)
            changed = True
            if not self._first_scan:
                self.clipArrived.emit(path)
        for path in [p for p in self.clips if p not in seen]:
            del self.clips[path]
            changed = True
        self._pending = {p: v for p, v in self._pending.items() if p in seen}
        self._first_scan = False
        if changed:
            self.changed.emit()

    # Probing ------------------------------------------------------------------

    def _queue(self, clip):
        path, size, mtime = clip.path, clip.size, clip.mtime
        key = f"{path}|{size}|{int(mtime)}"
        with self._cache_lock:
            cached = self._cache.get(key)
        thumb = str(self._thumb_dir / (hashlib.sha1(key.encode()).hexdigest()[:20] + ".jpg"))
        if cached and os.path.exists(thumb):
            clip.info, clip.thumb = cached, thumb
            return

        def job():
            try:
                info = cached or probe(path)
                with self._cache_lock:
                    self._cache[key] = info
                if not os.path.exists(thumb):
                    thumbnail(path, min(2.0, info["duration"] * 0.3), thumb)
                self._probed.emit(path, info, thumb if os.path.exists(thumb) else None, None)
            except Exception as e:
                self._probed.emit(path, None, None, str(e))

        self._pool.submit(job)

    def _on_probed(self, path, info, thumb, error):
        clip = self.clips.get(path)
        if not clip:
            return
        clip.info, clip.thumb, clip.error = info, thumb, error
        self.clipUpdated.emit(path)
        self._save_timer.start()

    def _save_cache(self):
        with self._cache_lock:
            data = dict(self._cache)
        try:
            tmp = self._cache_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self._cache_path)
        except OSError:
            pass
