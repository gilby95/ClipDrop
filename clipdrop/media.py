"""ffprobe / ffmpeg helpers: video info, thumbnails, encoder detection."""
import json
import os
import subprocess
import threading

from .paths import tool

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv", ".ts", ".m4v", ".wmv"}


def run(args, timeout=None):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=timeout)


def _fps(stream):
    for key in ("avg_frame_rate", "r_frame_rate"):
        num, _, den = (stream.get(key) or "0/1").partition("/")
        try:
            f = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            continue
        if 0 < f < 1000:
            return f
    return 30.0


def probe(path) -> dict:
    r = run([tool("ffprobe"), "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path], timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "Couldn't read this video")
    d = json.loads(r.stdout or "{}")
    streams = d.get("streams", [])
    fmt = d.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if not video:
        raise RuntimeError("No video stream")
    duration = float(fmt.get("duration") or video.get("duration") or 0)
    return {
        "duration": duration,
        "bitrate": int(fmt.get("bit_rate") or 0),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": round(_fps(video), 3),
        "vcodec": video.get("codec_name"),
        "audio_tracks": len(audio),
        "format": fmt.get("format_name", ""),
    }


def thumbnail(src, t, out_path, width=384) -> bool:
    r = run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, t):.2f}",
             "-i", src, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", out_path], timeout=60)
    return r.returncode == 0 and os.path.exists(out_path)


_gpu = None
_gpu_lock = threading.Lock()


def gpu_encoder():
    """'nvenc' / 'amf' / 'qsv' if this PC has a working hardware H.264 encoder, else None."""
    global _gpu
    with _gpu_lock:
        if _gpu is None:
            _gpu = ""
            for key, name in (("nvenc", "h264_nvenc"), ("amf", "h264_amf"), ("qsv", "h264_qsv")):
                try:
                    r = run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                             "-i", "color=black:s=256x256:d=0.2", "-c:v", name, "-f", "null", "-"], timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                if r.returncode == 0:
                    _gpu = key
                    break
        return _gpu or None


GPU_NAMES = {"nvenc": "NVIDIA", "amf": "AMD", "qsv": "Intel"}


def fmt_time(seconds, decimals=1):
    seconds = max(0.0, seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    s_txt = f"{s:0{3 + decimals if decimals else 2}.{decimals}f}"
    if h:
        return f"{int(h)}:{int(m):02d}:{s_txt}"
    return f"{int(m)}:{s_txt}"


def fmt_size(n):
    if n >= 1e9:
        return f"{n / 1e9:.2f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.1f} MB"
    return f"{n / 1e3:.0f} KB"
