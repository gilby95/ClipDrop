"""Remembered choices: watched folders, size limit, export options."""
import json
import os
import time

from .paths import app_root, config_dir, videos_dir

# (key, label, megabytes). Discord free went from 10 MB to 20 MB in August 2026.
SIZE_PRESETS = [
    ("discord_free", "Discord (free) - 20 MB", 20),
    ("nitro_basic", "Discord Nitro Basic - 50 MB", 50),
    ("nitro", "Discord Nitro - 500 MB", 500),
    ("custom", "Custom size...", None),
]

DEFAULTS = {
    "folders": [],
    "recursive": True,
    "size_preset": "discord_free",
    "custom_mb": 25.0,
    "resolution": "auto",
    "fps": "auto",
    "mix_audio": True,
    "copy_when_done": True,
    "encoder": "fast",
    "export_dir": str(videos_dir() / "ClipDrop"),
    "sort": "newest",
    "volume": 0.8,
    "loop": True,
    "last_session_end": None,
    "exports": {},
    "trims": {},
    "window": None,
    "channels": [],            # [{"name": "clips", "url": webhook}] added on this PC
    "display_name": "",
    "last_channel": "",
}


class Settings:
    def __init__(self):
        self.path = config_dir() / "settings.json"
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    def limit_mb(self) -> float:
        for key, _label, mb in SIZE_PRESETS:
            if key == self.data["size_preset"] and mb:
                return float(mb)
        return max(1.0, float(self.data.get("custom_mb") or 25))

    # Per-clip memory -------------------------------------------------------

    def export_for(self, src):
        e = self.data["exports"].get(src)
        if e and os.path.exists(e["path"]):
            return e
        return None

    def remember_export(self, src, path, size, limit_mb):
        self.data["exports"][src] = {"path": path, "size": size, "limit_mb": limit_mb, "time": time.time()}
        self.save()

    def forget_export(self, src):
        if self.data["exports"].pop(src, None):
            self.save()

    def remember_share(self, src, channel):
        e = self.data["exports"].get(src)
        if e is not None:
            e.setdefault("shared", []).append({"channel": channel, "time": time.time()})
        self.data["last_channel"] = channel
        self.save()

    # Discord channels ------------------------------------------------------

    def channels(self):
        """Channels built into this install (share.json next to the exe) plus ones added here."""
        out, seen = [], set()
        for ch in bundled_channels():
            out.append({**ch, "bundled": True})
            seen.add(ch["url"])
        for ch in self.data["channels"]:
            if ch.get("url") and ch["url"] not in seen:
                out.append({"name": ch["name"], "url": ch["url"], "bundled": False})
                seen.add(ch["url"])
        return out


def bundled_channels():
    try:
        with open(app_root() / "share.json", encoding="utf-8") as f:
            data = json.load(f)
        return [{"name": c["name"], "url": c["url"]} for c in data.get("channels", []) if c.get("url")]
    except (OSError, ValueError, KeyError, TypeError):
        return []
