# ClipDrop

Pull your gaming clips from any capture app, trim them, shrink them to fit Discord, and drag them straight into chat.

## Download

**[Download ClipDrop-Setup.exe](https://github.com/gilby95/ClipDrop/releases/latest/download/ClipDrop-Setup.exe)**, run it, done: desktop icon, Start menu entry, uninstall from Windows settings. No admin needed.

Windows may say "Windows protected your PC" because the installer isn't code-signed: click **More info → Run anyway**.

Works on any Windows PC: it compresses with your NVIDIA / AMD / Intel GPU if you have one, otherwise the CPU. ClipDrop updates itself: when there's a new version you'll see **Update to x.y** in the sidebar.

## Using it

1. **Find my clip folders** finds where OBS, ShadowPlay / NVIDIA App, AMD ReLive, Medal, Xbox Game Bar and Outplayed save. Or **+ Add folder** for any folder. Add as many as you like; sub-folders are included.
2. New clips appear on their own (marked **NEW**) once they finish saving.
3. Pick a clip, drag the blue handles to trim (or **I** / **O** at the playhead). Space plays, ← → skip 1 s (Shift = 5 s), `,` `.` step one frame, scroll on the timeline to zoom.
4. Choose **Fit under**: Discord free 20 MB, Nitro Basic 50 MB, Nitro 500 MB, or a custom size. It's remembered.
5. **Compress for Discord** (Ctrl+Enter). Then drag the **Drag me into Discord** card into a chat, or just press Ctrl+V in Discord (it's copied automatically).

You can also drag any clip straight from the list; it sends the compressed copy if there is one.

Settings: where compressed clips are saved (default `Videos\ClipDrop`), and Fast (GPU) vs Best quality (CPU, about 3x slower).

## Sharing to Discord

**Share to Discord** posts the finished clip into a channel through a Discord webhook (no bot needed). Channels in `share_channels.json` (not committed) or added in Settings are built into the installer by `build.bat`.

## Developing

- `run.bat` runs from source (sets up `.venv` and downloads ffmpeg the first time).
- `build.bat` makes `ClipDrop-Setup.exe` (needs Inno Setup: `winget install JRSoftware.InnoSetup --scope user`).
- `release.bat "what changed"` bumps the version, builds, and publishes a GitHub release; everyone's ClipDrop offers the update next time it opens.

Code: `clipdrop/compress.py` (size targeting), `library.py` (folder watching), `finder.py` (capture-app folders), `ui/` (Qt windows).
