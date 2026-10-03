"""The compressed copies ClipDrop has made: find them, add them up, clean them out.

Only files ClipDrop itself names (…_20MB.mp4, …_00m05s_50MB.mp4, leftover .part.mp4) are ever
listed or deleted, so pointing the save folder at e.g. Videos can't touch anyone's recordings.
"""
import os
import re
import time

MADE_BY_US = re.compile(r"(_\d+(?:\.\d+)?MB\.mp4|\.part\.mp4)$", re.IGNORECASE)


def is_ours(name):
    return bool(MADE_BY_US.search(name))


def list_exports(folder, skip_recent_parts=True):
    """[(path, size, mtime)] newest first. Unfinished .part files from a running job are left out."""
    out = []
    try:
        with os.scandir(folder) as it:
            for e in it:
                if not e.is_file() or not is_ours(e.name):
                    continue
                st = e.stat()
                if skip_recent_parts and e.name.lower().endswith(".part.mp4") and time.time() - st.st_mtime < 120:
                    continue
                out.append((e.path, st.st_size, st.st_mtime))
    except OSError:
        pass
    out.sort(key=lambda x: -x[2])
    return out


def usage(folder):
    """(total bytes, number of files)."""
    files = list_exports(folder)
    return sum(f[1] for f in files), len(files)


def cleanup(folder, days, keep=()):
    """Recycles compressed copies older than `days`. Returns (count, bytes) removed."""
    if not days or days <= 0:
        return 0, 0
    cutoff = time.time() - days * 86400
    keep = {os.path.normcase(os.path.abspath(k)) for k in keep if k}
    old = [(p, s) for p, s, m in list_exports(folder) if m < cutoff and os.path.normcase(os.path.abspath(p)) not in keep]
    if not old:
        return 0, 0
    failed = set(recycle([p for p, _s in old]))
    gone = [(p, s) for p, s in old if p not in failed]
    return len(gone), sum(s for _p, s in gone)


def recycle(paths):
    """Moves files to the Recycle Bin (Windows), or deletes them elsewhere. Returns the ones that failed."""
    paths = [os.path.abspath(p) for p in paths if is_ours(os.path.basename(p)) and os.path.exists(p)]
    if not paths:
        return []
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", ctypes.c_void_p),
                        ("pTo", ctypes.c_void_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

        FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
        buf = ctypes.create_unicode_buffer("\0".join(paths) + "\0\0")
        op = SHFILEOPSTRUCTW(None, FO_DELETE, ctypes.cast(buf, ctypes.c_void_p), None,
                             FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI, False, None, None)
        ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    else:
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass
    return [p for p in paths if os.path.exists(p)]
