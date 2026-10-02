"""Publishes a new ClipDrop version that friends' apps pick up automatically.

    release.bat "What's new in this version"

Bumps the version (1.1.0 -> 1.2.0, or pass --version 2.0.0), builds the installer,
and uploads it as a GitHub release. ClipDrop on friends' PCs checks on startup.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
INIT = os.path.join(ROOT, "clipdrop", "__init__.py")
UPDATE = os.path.join(ROOT, "clipdrop", "update.py")


def gh():
    for p in (shutil.which("gh"), r"C:\Program Files\GitHub CLI\gh.exe"):
        if p and os.path.exists(p):
            return p
    sys.exit("GitHub CLI isn't installed: winget install GitHub.cli")


def run(*args, capture=False):
    r = subprocess.run(args, cwd=ROOT, text=True, capture_output=capture)
    if r.returncode != 0:
        sys.exit(f"Failed: {' '.join(args[:3])}…\n{(r.stderr or '') if capture else ''}")
    return (r.stdout or "").strip()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("notes", nargs="?", default="")
    ap.add_argument("--version")
    ap.add_argument("--repo", help="owner/name of the GitHub repo for releases")
    a = ap.parse_args()

    g = gh()
    run(g, "auth", "status", capture=True)
    repo = a.repo or re.search(r'^REPO = "(.*)"', read(UPDATE), re.M).group(1)
    if not repo:
        sys.exit('No release repo set yet. Run once with --repo yourname/ClipDrop')
    run(g, "repo", "view", repo, "--json", "name", capture=True)

    old = re.search(r'__version__ = "(.+)"', read(INIT)).group(1)
    if a.version:
        new = a.version
    else:
        major, minor, *_ = (int(x) for x in old.split("."))
        new = f"{major}.{minor + 1}.0"
    write(INIT, f'__version__ = "{new}"\n')
    write(UPDATE, re.sub(r'^REPO = ".*"', f'REPO = "{repo}"', read(UPDATE), flags=re.M))
    print(f"Releasing ClipDrop {new} to github.com/{repo}")

    if subprocess.run(["cmd", "/c", os.path.join(ROOT, "build.bat")], cwd=ROOT, stdin=subprocess.DEVNULL).returncode:
        write(INIT, f'__version__ = "{old}"\n')
        sys.exit("Build failed; version left at " + old)
    setup = os.path.join(ROOT, "ClipDrop-Setup.exe")
    notes = a.notes or f"ClipDrop {new}"
    run(g, "release", "create", f"v{new}", setup, "--repo", repo, "--title", f"ClipDrop {new}", "--notes", notes)
    print(f"\nDone. Friends will see 'Update to {new}' next time they open ClipDrop.")
    print(f"First-time download link: https://github.com/{repo}/releases/latest/download/ClipDrop-Setup.exe")


if __name__ == "__main__":
    main()
