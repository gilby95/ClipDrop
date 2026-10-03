"""Builds your Discord channels into the release so friends get them preinstalled.

Takes the channels you added in ClipDrop's Settings on this PC (plus share_channels.json
in the project folder, if you made one) and writes release/ClipDrop/share.json.
"""
import json
import os
import sys

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
channels, seen = [], set()


def take(items):
    for c in items or []:
        if c.get("url") and c.get("name") and c["url"] not in seen:
            channels.append({"name": c["name"], "url": c["url"], "limit_mb": c.get("limit_mb", 20)})
            seen.add(c["url"])


for path in (os.path.join(root, "share_channels.json"),
             os.path.join(os.environ.get("APPDATA", ""), "ClipDrop", "settings.json")):
    try:
        with open(path, encoding="utf-8") as f:
            take(json.load(f).get("channels"))
    except (OSError, ValueError, AttributeError):
        pass

out = os.path.join(root, "release", "ClipDrop", "share.json")
if not os.path.isdir(os.path.dirname(out)):
    sys.exit("release\\ClipDrop doesn't exist yet")
if channels:
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"channels": channels}, f, indent=2)
    print("Built in Discord channels: " + ", ".join("#" + c["name"] for c in channels))
else:
    if os.path.exists(out):
        os.remove(out)
    print("No Discord channels to build in (add some in ClipDrop > Settings first).")
