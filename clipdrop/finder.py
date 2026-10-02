"""Finds where common capture programs save clips on this PC."""
import configparser
import glob
import os
from pathlib import Path

from .media import VIDEO_EXTS
from .paths import videos_dir


def _obs_paths():
    out = []
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return out
    for ini in glob.glob(os.path.join(appdata, "obs-studio", "basic", "profiles", "*", "basic.ini")):
        cp = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            cp.read(ini, encoding="utf-8-sig")
        except (configparser.Error, OSError, UnicodeDecodeError):
            continue
        for section, key in (("SimpleOutput", "FilePath"), ("AdvOut", "RecFilePath"), ("AdvOut", "FFFilePath")):
            v = cp.get(section, key, fallback=None)
            if v:
                out.append(v)
    return out


def _shadowplay_paths():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS") as k:
            raw, _ = winreg.QueryValueEx(k, "DefaultPathW")
        return [raw.decode("utf-16-le").split("\x00")[0]]
    except (OSError, ImportError, UnicodeDecodeError, AttributeError):
        return []


def _count_videos(folder, limit=500):
    n = 0
    for _root, _dirs, files in os.walk(folder):
        n += sum(1 for f in files if os.path.splitext(f)[1].lower() in VIDEO_EXTS)
        if n >= limit:
            break
    return n


def find_capture_folders():
    """[(path, source label, video count)] for folders that exist."""
    vids = videos_dir()
    home = Path.home()
    candidates = []
    candidates += [(p, "OBS") for p in _obs_paths()]
    candidates += [(p, "NVIDIA ShadowPlay / NVIDIA App") for p in _shadowplay_paths()]
    candidates += [
        (vids, "Videos folder (OBS / NVIDIA default)"),
        (vids / "Captures", "Xbox Game Bar"),
        (vids / "Radeon ReLive", "AMD ReLive / Adrenalin"),
        (vids / "Medal", "Medal"),
        (Path("C:/Medal"), "Medal"),
        (vids / "Outplayed", "Outplayed"),
        (vids / "Overwolf" / "Outplayed", "Outplayed"),
        (vids / "Insights Capture", "Insights Capture"),
        (vids / "SteelSeries Moments", "SteelSeries Moments"),
        (home / "Videos" / "Captures", "Xbox Game Bar"),
    ]
    seen, out = set(), []
    for path, label in candidates:
        p = os.path.normpath(str(path))
        key = os.path.normcase(p)
        if key in seen or not os.path.isdir(p):
            continue
        seen.add(key)
        out.append((p, label, _count_videos(p)))
    return out
