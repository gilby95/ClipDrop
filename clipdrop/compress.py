"""Trim + shrink a clip so it fits under a size limit (e.g. Discord's 20 MB).

Works on any PC: "quality" mode uses the CPU (x264 two-pass, the most accurate
way to hit a size). "fast" mode uses the GPU encoder if this PC has one
(NVIDIA / AMD / Intel) and falls back to the CPU if it doesn't or if it fails.
"""
import collections
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass

from .media import NO_WINDOW, gpu_encoder, tool

SAFETY = 0.97          # leave room for the MP4 container; overshoots are re-encoded
MIN_VIDEO_KBPS = 150
LADDER = [1440, 1080, 720, 540, 480, 360]

# Minimum bits per pixel for each choice, from the quality lab (tools/quality_lab.py) at 20 MB:
# 30 fps beat 60 fps by 3-7 VMAF points at the same size, so 60 fps is only kept with plenty of room.
BPP_60 = 0.085         # full-resolution 60 fps
BPP_30 = {1440: 0.09, 1080: 0.09, 720: 0.08, 540: 0.06, 480: 0.05}
BPP_FIXED_FPS = 0.045  # when the frame rate is chosen by hand, only resolution adapts


class Cancelled(Exception):
    pass


class TooLong(Exception):
    def __init__(self, max_seconds):
        self.max_seconds = max_seconds
        super().__init__(f"Too long for this size. Trim it to about {int(max_seconds)} seconds or less.")


@dataclass
class Plan:
    width: int
    height: int
    fps: float
    video_kbps: int
    audio_kbps: int
    duration: float
    scaled: bool
    fps_changed: bool

    @property
    def est_mb(self):
        return (self.video_kbps + self.audio_kbps) * self.duration / 8000 / SAFETY * 0.98

    def describe(self):
        return f"{self.height}p{round(self.fps)} · {self.video_kbps / 1000:.1f} Mbps"


def make_plan(info, duration, limit_mb, resolution="auto", fps_pref="auto", has_audio=True) -> Plan:
    if duration <= 0.05:
        raise ValueError("The selection is empty.")
    total = limit_mb * 8000 * SAFETY / duration           # kbps for video + audio
    audio = 0
    if has_audio:   # game audio sounds fine at 96k; give the video the bits when space is tight
        audio = 160 if total > 15000 else 128 if total > 8000 else 96 if total > 600 else 64
    video = total - audio
    if video < MIN_VIDEO_KBPS:
        raise TooLong(limit_mb * 8000 * SAFETY / (MIN_VIDEO_KBPS + (64 if has_audio else 0)))

    sw, sh = info.get("width") or 1920, info.get("height") or 1080
    src_fps = min(info.get("fps") or 30, 60)

    heights = [sh] + [h for h in LADDER if h < sh]
    if resolution == "source":
        heights = [sh]
    elif resolution != "auto":
        heights = [min(int(resolution), sh)]
    low_fps = 30 if src_fps > 31 else src_fps

    def bpp30(h):
        return BPP_30.get(h, 0.09 if h > 1080 else 0.0)

    # (height, fps, minimum bits per pixel), best first; the last one is the fallback.
    if fps_pref in ("source", "60") or (fps_pref != "auto" and float(fps_pref) > 31):
        f = src_fps if fps_pref == "source" else min(float(fps_pref), src_fps)
        order = [(h, f, BPP_FIXED_FPS) for h in heights]
    elif fps_pref == "30" or src_fps <= 31:
        order = [(h, low_fps, bpp30(h)) for h in heights]
    else:   # auto: full-res 60 fps when there's room, otherwise the sharper 30 fps
        order = [(heights[0], src_fps, BPP_60)] + [(h, low_fps, bpp30(h)) for h in heights]

    def width_for(h):
        return max(2, int(round(sw * h / sh / 2)) * 2)

    pick = order[-1][:2]
    for h, f, need in order:
        if video * 1000 / (width_for(h) * h * f) >= need:
            pick = (h, f)
            break
    h, f = pick
    w = width_for(h)

    # Big limits (Nitro): don't waste space past what looks good / what the source has.
    cap = w * h * f * (0.2 if f <= 31 else 0.12) / 1000
    src_kbps = (info.get("bitrate") or 0) / 1000
    if src_kbps > 0:
        cap = min(cap, max(src_kbps, 1500))
    video = min(video, cap)

    return Plan(width=w, height=h, fps=f, video_kbps=int(video), audio_kbps=audio, duration=duration,
                scaled=(h != sh), fps_changed=abs(f - (info.get("fps") or f)) > 0.5)


def max_seconds_at(info, limit_mb, min_height=720, fps_pref="auto", has_audio=True):
    """Longest clip that still comes out at min_height or better (auto resolution), in seconds."""
    target = min(min_height, info.get("height") or min_height)

    def ok(d):
        try:
            return make_plan(info, d, limit_mb, "auto", fps_pref, has_audio).height >= target
        except (TooLong, ValueError):
            return False

    lo, hi = 0.5, 4 * 3600.0
    if not ok(lo):
        return 0.0
    if ok(hi):
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo


def shareable_as_is(path, info, start, end, limit_mb) -> bool:
    """Untrimmed MP4/H.264 already under the limit: no need to re-encode."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    full = start <= 0.05 and end >= info["duration"] - 0.05
    return (full and size <= limit_mb * 1_000_000 and path.lower().endswith(".mp4")
            and info.get("vcodec") == "h264")


# --- ffmpeg command building --------------------------------------------------

def _graph(plan, n_audio, mix, pix_fmt, with_audio=True):
    vf = []
    if plan.scaled:
        vf.append(f"scale={plan.width}:{plan.height}:flags=lanczos")
    if plan.fps_changed:
        vf.append(f"fps={plan.fps:g}")
    vf.append(f"format={pix_fmt}")
    parts = [f"[0:v:0]{','.join(vf)}[v]"]
    maps = ["-map", "[v]"]
    if with_audio and n_audio:
        if mix and n_audio > 1:
            ins = "".join(f"[0:a:{i}]" for i in range(n_audio))
            parts.append(f"{ins}amix=inputs={n_audio}:duration=longest:normalize=0[a]")
            maps += ["-map", "[a]"]
        else:
            maps += ["-map", "0:a:0"]
    return ["-filter_complex", ";".join(parts), *maps]


def _gpu_args(kind, v, tuned=True):
    rate = ["-b:v", f"{v}k", "-maxrate", f"{int(v * 1.5)}k", "-bufsize", f"{int(v * 2)}k"]
    if kind == "nvenc" and tuned:
        # Quality-lab winner for NVIDIA: much better on dark / grainy games at the same size and speed.
        # b_ref_mode needs an RTX (Turing+) card; older cards fall back to the plain settings below.
        return ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-multipass", "fullres",
                "-rc-lookahead", "32", "-spatial-aq", "1", "-temporal-aq", "1", "-aq-strength", "8",
                "-bf", "3", "-b_ref_mode", "middle", "-profile:v", "high", *rate]
    if kind == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-multipass", "fullres",
                "-spatial-aq", "1", "-profile:v", "high", *rate]
    if kind == "amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", "-profile:v", "high", *rate]
    return ["-c:v", "h264_qsv", "-preset", "slower", "-profile:v", "high", *rate]


def _run(args, duration, on_progress, cancel, lo, hi, label):
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                         text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    err = collections.deque(maxlen=30)
    t = threading.Thread(target=lambda: err.extend(p.stderr), daemon=True)
    t.start()
    try:
        for line in p.stdout:
            if cancel.is_set():
                break
            if line.startswith("out_time_us="):
                try:
                    secs = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                on_progress(lo + (hi - lo) * min(1.0, max(0.0, secs / duration)), label)
        if cancel.is_set():
            p.kill()
        p.wait()
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    t.join(timeout=2)
    if cancel.is_set():
        raise Cancelled()
    if p.returncode != 0:
        raise RuntimeError("".join(err).strip()[-1500:] or f"ffmpeg failed ({p.returncode})")
    on_progress(hi, label)


def compress(src, out, start, end, info, limit_mb, *, resolution="auto", fps_pref="auto", mix_audio=True,
             encoder="fast", on_progress=lambda f, s: None, cancel=None, log=lambda s: None) -> dict:
    cancel = cancel or threading.Event()
    duration = end - start
    n_audio = info.get("audio_tracks", 0)
    plan = make_plan(info, duration, limit_mb, resolution, fps_pref, has_audio=n_audio > 0)
    limit_bytes = limit_mb * 1_000_000
    tmp = os.path.splitext(out)[0] + ".part.mp4"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    ff = tool("ffmpeg")
    head = [ff, "-hide_banner", "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", src]
    tail = ["-progress", "pipe:1", "-nostats"]
    audio_args = (["-c:a", "aac", "-b:a", f"{plan.audio_kbps}k", "-ac", "2", "-ar", "48000"] if n_audio else [])
    log(f"Plan: {plan.width}x{plan.height} @ {plan.fps:g} fps, video {plan.video_kbps} kbps, audio {plan.audio_kbps} kbps")

    def finish(kind):
        size = os.path.getsize(tmp)
        os.replace(tmp, out)
        return {"path": out, "size": size, "plan": plan, "encoder": kind}

    v = plan.video_kbps
    gpu = gpu_encoder() if encoder == "fast" else None
    try:
        if gpu:
            v = int(v * 0.98)        # hardware encoders overshoot a little more than x264
            tuned = True
            attempt = 0
            while attempt < 3:
                label = "Compressing on GPU" + (" (retry)" if attempt else "")
                pix = "nv12" if gpu == "qsv" else "yuv420p"
                try:
                    _run([*head, *_graph(plan, n_audio, mix_audio, pix), *_gpu_args(gpu, v, tuned), *audio_args,
                          "-movflags", "+faststart", *tail, tmp], duration, on_progress, cancel, 0, 1, label)
                except RuntimeError as e:
                    if gpu == "nvenc" and tuned:
                        log(f"Tuned NVIDIA settings not supported here, using basic ones: {e}")
                        tuned = False
                        continue
                    log(f"GPU encoder failed, using CPU instead: {e}")
                    break
                attempt += 1
                size = os.path.getsize(tmp)
                if size <= limit_bytes:
                    return finish(gpu)
                log(f"GPU result {size / 1e6:.1f} MB was over the limit; lowering bitrate")
                v = int(v * limit_bytes * 0.95 / size)

        passlog_dir = tempfile.mkdtemp(prefix="clipdrop_")
        passlog = os.path.join(passlog_dir, "pass")
        try:
            for attempt in range(3):
                x264 = ["-c:v", "libx264", "-preset", "slow" if duration <= 90 else "medium", "-profile:v", "high",
                        "-b:v", f"{v}k",
                        "-passlogfile", passlog]
                note = " (retry)" if attempt else ""
                _run([*head, *_graph(plan, n_audio, mix_audio, "yuv420p", with_audio=False), *x264,
                      "-pass", "1", "-an", "-f", "null", *tail, os.devnull],
                     duration, on_progress, cancel, 0, 0.4, "Analyzing" + note)
                _run([*head, *_graph(plan, n_audio, mix_audio, "yuv420p"), *x264, "-pass", "2", *audio_args,
                      "-movflags", "+faststart", *tail, tmp],
                     duration, on_progress, cancel, 0.4, 1, "Compressing" + note)
                size = os.path.getsize(tmp)
                if size <= limit_bytes:
                    return finish("cpu")
                log(f"Result {size / 1e6:.1f} MB was over the limit; lowering bitrate")
                v = int(v * limit_bytes * 0.95 / size)
        finally:
            shutil.rmtree(passlog_dir, ignore_errors=True)
        raise RuntimeError("Couldn't get the clip under the size limit. Try trimming it shorter.")
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
