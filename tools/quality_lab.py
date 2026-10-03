"""Quality lab: encodes one stretch of a recording several ways at the same size and scores each with VMAF.

    python tools/quality_lab.py "F:\\videos\\Game\\rec.mkv" START_SECONDS [--mb 20] [--dur 25] [--name label]

Writes quality-lab/<name>/ with every variant, a reference copy and results.md.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from clipdrop import compress, media  # noqa: E402
from clipdrop.paths import tool  # noqa: E402

FF = tool("ffmpeg")


def run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode:
        raise RuntimeError(r.stderr[-1500:])
    return r


def x264_2pass(ref, out, dur, w, h, fps, v_kbps, a_kbps, preset="slow", extra_vf="", n_audio=1):
    vf = ",".join(f for f in (extra_vf, f"scale={w}:{h}:flags=lanczos" if h != 1080 else "",
                              f"fps={fps}" if fps != 60 else "", "format=yuv420p") if f)
    log = os.path.join(tempfile.mkdtemp(), "p")
    common = [FF, "-hide_banner", "-y", "-i", ref, "-t", f"{dur}", "-vf", vf, "-c:v", "libx264", "-preset", preset,
              "-profile:v", "high", "-b:v", f"{v_kbps}k", "-passlogfile", log]
    run([*common, "-pass", "1", "-an", "-f", "null", os.devnull])
    run([*common, "-pass", "2", "-c:a", "aac", "-b:a", f"{a_kbps}k", "-ac", "2", "-movflags", "+faststart", out])
    shutil.rmtree(os.path.dirname(log), ignore_errors=True)


def nvenc_tuned(ref, out, dur, w, h, fps, v_kbps, a_kbps, **_):
    vf = ",".join(f for f in (f"scale={w}:{h}:flags=lanczos" if h != 1080 else "", f"fps={fps}" if fps != 60 else "",
                              "format=yuv420p") if f)
    run([FF, "-hide_banner", "-y", "-i", ref, "-t", f"{dur}", "-vf", vf, "-c:v", "h264_nvenc", "-preset", "p7",
         "-tune", "hq", "-rc", "vbr", "-multipass", "fullres", "-rc-lookahead", "32", "-spatial-aq", "1",
         "-temporal-aq", "1", "-aq-strength", "8", "-bf", "3", "-b_ref_mode", "middle", "-profile:v", "high",
         "-b:v", f"{v_kbps}k", "-maxrate", f"{int(v_kbps * 1.5)}k", "-bufsize", f"{int(v_kbps * 2)}k",
         "-c:a", "aac", "-b:a", f"{a_kbps}k", "-ac", "2", "-movflags", "+faststart", out])


def vmaf(ref, dist, fps, threads):
    """Mean and 5th-percentile VMAF (the worst moments are what people notice)."""
    work = tempfile.gettempdir()
    log_name = f"vmaf_{os.getpid()}_{threading.get_ident()}.json"
    log = os.path.join(work, log_name)
    ref_vf = f"fps={fps}," if fps != 60 else ""
    graph = (f"[0:v]scale=1920:1080:flags=bicubic,format=yuv420p,setpts=N/{fps}/TB[d];"
             f"[1:v]{ref_vf}format=yuv420p,setpts=N/{fps}/TB[r];"
             f"[d][r]libvmaf=log_fmt=json:log_path={log_name}:n_threads={threads}")
    run([FF, "-hide_banner", "-i", dist, "-i", ref, "-lavfi", graph, "-f", "null", "-"], cwd=work)
    with open(log, encoding="utf-8") as f:
        frames = [fr["metrics"]["vmaf"] for fr in json.load(f)["frames"]]
    os.remove(log)
    frames.sort()
    return sum(frames) / len(frames), frames[int(len(frames) * 0.05)]


def main():
    if os.name == "nt":       # below-normal priority (inherited by ffmpeg) so games stay smooth
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("start", type=float)
    ap.add_argument("--dur", type=float, default=25)
    ap.add_argument("--mb", type=float, default=20)
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    name = a.name or os.path.basename(os.path.dirname(a.src)) or "clip"
    out_dir = os.path.join(ROOT, "quality-lab", name)
    os.makedirs(out_dir, exist_ok=True)
    info = media.probe(a.src)

    # Near-lossless reference of exactly this stretch, all audio tracks mixed (like ClipDrop does).
    ref = os.path.join(out_dir, "00-reference.mkv")
    if not os.path.exists(ref):
        n = info["audio_tracks"]
        amix = (["-filter_complex", "".join(f"[0:a:{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0[a]",
                 "-map", "0:v:0", "-map", "[a]"] if n > 1 else ["-map", "0:v:0", "-map", "0:a:0?"])
        run([FF, "-hide_banner", "-y", "-ss", f"{a.start}", "-t", f"{a.dur}", "-i", a.src, *amix,
             "-c:v", "libx264", "-preset", "fast", "-crf", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", ref])
    rinfo = media.probe(ref)
    dur = a.dur
    limit_bytes = a.mb * 1_000_000
    full = int(a.mb * 8000 * 0.975 / dur)          # total kbps when using ~97.5% of the limit

    variants = [
        ("01-today-fast-gpu", "today", "fast", None),
        ("02-today-best-cpu", "today", "quality", None),
        ("03-cpu-slow-1080p60", x264_2pass, dict(w=1920, h=1080, fps=60), None),
        ("04-cpu-slow-900p60", x264_2pass, dict(w=1600, h=900, fps=60), None),
        ("05-cpu-slow-720p60", x264_2pass, dict(w=1280, h=720, fps=60), None),
        ("06-cpu-slow-1080p30", x264_2pass, dict(w=1920, h=1080, fps=30), None),
        ("07-cpu-slow-720p30", x264_2pass, dict(w=1280, h=720, fps=30), None),
        ("08-cpu-slow-720p60-denoise", x264_2pass, dict(w=1280, h=720, fps=60, extra_vf="hqdn3d=1.5:1.5:6:6"), None),
        ("09-gpu-tuned-720p60", nvenc_tuned, dict(w=1280, h=720, fps=60), None),
    ]
    results = []
    for label, how, opts, _ in variants:
        out = os.path.join(out_dir, label + ".mp4")
        side = os.path.join(out_dir, label + ".json")
        if os.path.exists(out) and os.path.exists(side):
            with open(side, encoding="utf-8") as f:
                prev = json.load(f)
            took, res, fps = prev["encode_s"], prev["res"], prev["fps"]
        else:
            took = None
        t0 = time.time()
        if took is not None:
            pass
        elif how == "today":
            r = compress.compress(ref, out, 0, dur, rinfo, a.mb, encoder=opts)
            fps = round(r["plan"].fps)
            res = f"{r['plan'].height}p{fps}"
        else:
            a_kbps = 96
            v = full - a_kbps
            for _attempt in range(3):
                how(ref, out, dur, v_kbps=v, a_kbps=a_kbps, **opts)
                size = os.path.getsize(out)
                if size <= limit_bytes:
                    break
                v = int(v * limit_bytes * 0.97 / size)
            fps = opts["fps"]
            res = f"{opts['h']}p{fps}"
        if took is None:
            took = time.time() - t0
            with open(side, "w", encoding="utf-8") as f:
                json.dump({"encode_s": round(took, 1), "res": res, "fps": fps}, f)
        size = os.path.getsize(out)
        mean, low = vmaf(ref, out, fps, threads=os.cpu_count() or 4)
        row = {"variant": label, "res": res, "mb": round(size / 1e6, 2), "encode_s": round(took, 1),
               "vmaf": round(mean, 1), "vmaf_worst5": round(low, 1)}
        results.append(row)
        print(json.dumps(row), flush=True)

    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    lines = [f"# {name}: {dur:g}s at {a.mb:g} MB (source {a.src} @ {a.start:g}s)", "",
             "| Variant | Res | Size | Encode time | VMAF | VMAF (worst 5%) |", "|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda r: -r["vmaf"]):
        lines.append(f"| {r['variant']} | {r['res']} | {r['mb']} MB | {r['encode_s']}s | {r['vmaf']} | {r['vmaf_worst5']} |")
    with open(os.path.join(out_dir, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
