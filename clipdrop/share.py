"""Post a clip into a Discord channel through a webhook (no bot needed)."""
import http.client
import json
import os
import re
import time
import uuid
from urllib.parse import urlsplit

from . import __version__

WEBHOOK_RE = re.compile(
    r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/\d+/[\w-]+/?$")
CHUNK = 256 * 1024


class ShareError(Exception):
    def __init__(self, message, too_big=False):
        super().__init__(message)
        self.too_big = too_big


class Cancelled(Exception):
    pass


def is_webhook_url(url):
    return bool(WEBHOOK_RE.match((url or "").strip()))


def _connect(url, timeout=120):
    parts = urlsplit(url)
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    return cls(parts.hostname, parts.port, timeout=timeout), target


def _error_text(body):
    try:
        return json.loads(body).get("message") or body[:200].decode(errors="replace")
    except (ValueError, AttributeError):
        return body[:200].decode(errors="replace")


def webhook_info(url):
    """Checks a webhook link still works. Returns Discord's info about it."""
    conn, target = _connect(url.strip(), timeout=15)
    try:
        conn.request("GET", target, headers={"User-Agent": f"ClipDrop/{__version__}"})
        resp = conn.getresponse()
        body = resp.read()
    except OSError as e:
        raise ShareError(f"Couldn't reach Discord: {e}")
    finally:
        conn.close()
    if resp.status in (401, 403, 404):
        raise ShareError("That webhook link doesn't work (it may have been deleted).")
    if resp.status >= 300:
        raise ShareError(f"Discord said {resp.status}: {_error_text(body)}")
    return json.loads(body or b"{}")


def post_clip(url, path, *, username, content="", on_progress=lambda f: None, cancel=None):
    """Uploads the video to the channel. Returns Discord's message JSON."""
    size = os.path.getsize(path)
    name = os.path.basename(path).replace('"', "'")
    payload = {"content": content[:2000], "username": username[:80], "allowed_mentions": {"parse": []}}
    target_url = url.strip().rstrip("/") + "?wait=true"

    for _attempt in range(3):
        b = uuid.uuid4().hex
        head = (f"--{b}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
                f"Content-Type: application/json\r\n\r\n{json.dumps(payload)}\r\n"
                f"--{b}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{name}\"\r\n"
                f"Content-Type: video/mp4\r\n\r\n").encode("utf-8")
        tail = f"\r\n--{b}--\r\n".encode()
        conn, target = _connect(target_url)
        try:
            try:
                conn.putrequest("POST", target)
                conn.putheader("Content-Type", f"multipart/form-data; boundary={b}")
                conn.putheader("Content-Length", str(len(head) + size + len(tail)))
                conn.putheader("User-Agent", f"ClipDrop/{__version__}")
                conn.endheaders()
                conn.send(head)
                sent = 0
                with open(path, "rb") as f:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise Cancelled()
                        chunk = f.read(CHUNK)
                        if not chunk:
                            break
                        conn.send(chunk)
                        sent += len(chunk)
                        on_progress(sent / size)
                conn.send(tail)
            except OSError:
                pass        # Discord may hang up early (e.g. file too big); its answer explains why
            try:
                resp = conn.getresponse()
                body = resp.read()
            except OSError as e:
                raise ShareError("The upload was cut off. The clip may be too big for this server, "
                                 f"or the connection dropped ({e}).", too_big=True)
        finally:
            conn.close()

        if 200 <= resp.status < 300:
            return json.loads(body or b"{}")
        if resp.status == 429:
            try:
                wait = float(json.loads(body).get("retry_after", 2))
            except ValueError:
                wait = 2
            time.sleep(min(wait, 15))
            continue
        if resp.status == 413:
            raise ShareError("Too big for this Discord server. Pick a smaller “Fit under” size and try again.",
                             too_big=True)
        if resp.status in (401, 403, 404):
            raise ShareError("This channel's webhook link doesn't work anymore. Make a new one in Discord.")
        raise ShareError(f"Discord said {resp.status}: {_error_text(body)}")
    raise ShareError("Discord is busy (rate limited). Try again in a minute.")
