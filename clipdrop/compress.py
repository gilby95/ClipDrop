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

SAFETY = 0.94          # leave room for the MP4 container and encoder wobble
BPP_MIN = 0.045        # bits per pixel below which gameplay turns to mush
MIN_VIDEO_KBPS = 150
LADDER = [1440, 1080, 720, 540, 480, 360]


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
    if has_audio:
        audio = 160 if total > 4000 else 128 if total > 1500 else 96 if total > 600 else 64
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
    fps_opts = [src_fps] + ([30] if src_fps > 31 else [])
    if fps_pref == "source":
        fps_opts = [src_fps]
    elif fps_pref != "auto":
        fps_opts = [min(float(fps_pref), src_fps)]

    # Keep 60 fps down to 720p (smooth gameplay reads better than extra pixels),
    # then drop to 30 fps, and only then go below 720p.
    order = [(h, fps_opts[0]) for h in heights if h >= 720 or len(fps_opts) == 1]
    order += [(h, f) for f in fps_opts[1:] for h in heights]
    order += [(h, fps_opts[0]) for h in heights if (h, fps_opts[0]) not in order]

    def width_for(h):
        return max(2, int(round(sw * h / sh / 2)) * 2)

    pick = order[-1]
    for h, f in order:
        if video * 1000 / (width_for(h) * h * f) >= BPP_MIN:
            pick = (h, f)
            break
    h, f = pick
    w = width_for(h)

    # Big limits (Nitro): don't waste space past what looks good / what the source has.
    cap = w * h * f * 0.12 / 1000
    src_kbps = (info.get("bitrate") or 0) / 1000
    if src_kbps > 0:
        cap = min(cap, max(src_kbps, 1500))
    video = min(video, cap)

    return Plan(width=w, height=h, fps=f, video_kbps=int(video), audio_kbps=audio, duration=duration,
                scaled=(h != sh), fps_changed=abs(f - (info.get("fps") or f)) > 0.5)


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


def _gpu_args(kind, v):
    rate = ["-b:v", f"{v}k", "-maxrate", f"{int(v * 1.5)}k", "-bufsize", f"{int(v * 2)}k"]
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
            v = int(v * 0.96)        # hardware encoders overshoot a little more than x264
            for attempt in range(3):
                label = "Compressing on GPU" + (" (retry)" if attempt else "")
                pix = "nv12" if gpu == "qsv" else "yuv420p"
                try:
                    _run([*head, *_graph(plan, n_audio, mix_audio, pix), *_gpu_args(gpu, v), *audio_args,
                          "-movflags", "+faststart", *tail, tmp], duration, on_progress, cancel, 0, 1, label)
                except RuntimeError as e:
                    log(f"GPU encoder failed, using CPU instead: {e}")
                    break
                size = os.path.getsize(tmp)
                if size <= limit_bytes:
                    return finish(gpu)
                log(f"GPU result {size / 1e6:.1f} MB was over the limit; lowering bitrate")
                v = int(v * limit_bytes * 0.95 / size)

        passlog_dir = tempfile.mkdtemp(prefix="clipdrop_")
        passlog = os.path.join(passlog_dir, "pass")
        try:
            for attempt in range(3):
                x264 = ["-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-b:v", f"{v}k",
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
