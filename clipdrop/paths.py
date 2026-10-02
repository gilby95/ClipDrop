"""Where ClipDrop keeps its settings, cache and bundled tools."""
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "ClipDrop"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resource_dirs():
    dirs = [app_root()]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass))
    return dirs


def tool(name: str) -> str:
    """Path to ffmpeg / ffprobe: bundled copy first, then PATH."""
    exe = name + (".exe" if os.name == "nt" else "")
    for d in _resource_dirs():
        p = d / "bin" / exe
        if p.exists():
            return str(p)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"{name} wasn't found. Put {exe} in the 'bin' folder next to ClipDrop.")


def config_dir() -> Path:
    d = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _known_folder(guid: str):
    if os.name != "nt":
        return None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID(guid)
        g = GUID(u.time_low, u.time_mid, u.time_hi_version,
                 (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            return None
        value = out.value
        ctypes.windll.ole32.CoTaskMemFree(out)
        return value
    except Exception:
        return None


def videos_dir() -> Path:
    p = _known_folder("18989B1D-99B5-455B-841C-AB7C74E4DDFC")
    return Path(p) if p else Path.home() / "Videos"
