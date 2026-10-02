# ClipDrop: design handoff

**Ask:** design a better-looking UI for ClipDrop, a small Windows desktop app. Keep every screen and state listed below, and make it look like a polished, modern gaming utility (think Medal, Outplayed or the NVIDIA App, but simpler and calmer). Screenshots of the current UI are in `screens/`. They work fine but are plain.

---

## What the app is

ClipDrop is for a group of friends who play games together and share clips in their Discord server. Each friend uses a different capture app (OBS, NVIDIA ShadowPlay, Medal, Xbox Game Bar, AMD ReLive...) on different PCs. ClipDrop:

1. **Watches their clip folders**, however many and wherever they are, and shows every clip in one list, newest first, grouped by Today / Yesterday / This week / Last week / month.
2. **Lets them trim** a clip (start/end handles on a timeline, keyboard shortcuts).
3. **Compresses it to fit Discord's upload limit**: free accounts get 20 MB, Nitro Basic 50 MB, Nitro 500 MB, or a custom size. It picks resolution and frame rate automatically and shows the result ahead of time ("0:20 selected → 1080p60 · about 19.6 MB").
4. **Gets it into Discord**: drag the finished file straight into a Discord chat, or press Copy and Ctrl+V. Or press **Share to Discord** to post it to the group's #media channel with an optional message ("Jake via ClipDrop").
5. **Updates itself** from GitHub.

The core loop takes 20 seconds: *new clip appears → pick it → drag the handles → Compress → drag it into Discord.* Design for that loop first; everything else is secondary.

**Users:** gamers aged 16–30, not technical. Short, plain words. Never show bitrates or codecs unless they ask (an "Advanced" area is fine).

---

## Hard constraints (it's a native Qt app, not a web page)

The UI is **Qt Widgets (PySide6) styled with Qt stylesheets (QSS)** plus a few custom-painted widgets. Please design within what that can do:

- ✅ Solid colors, borders, border-radius, padding, simple linear gradients, custom fonts (we can bundle .ttf files), icons as SVG/PNG, hover/pressed/disabled states, custom-painted components (timeline, clip cards, progress).
- ⚠️ Limited: drop shadows (one effect per widget, use sparingly), simple animations (fades and slides are OK; no complex motion).
- ❌ No backdrop blur/glass, no CSS filters, no blend modes, **nothing drawn on top of the video** (the video area is a native surface; overlays must sit above or below it, not on it).
- Windows 10/11, **dark theme only**, window default 1400×860, minimum about 1100×700. The three columns are resizable splitters.
- Fonts: currently Segoe UI. A bundled font is fine (pick one with good numerals for timecodes).

---

## Current design tokens (feel free to replace)

| Token | Value | Use |
|---|---|---|
| BG | `#111214` | window background |
| PANEL | `#18191c` | sidebar, cards |
| SURFACE | `#222328` | inputs, buttons, hover |
| SURFACE_HI | `#2b2d33` | selected row |
| BORDER | `#2f3137` | dividers |
| TEXT | `#e9eaee` | |
| MUTED | `#999ba3` | secondary text |
| ACCENT | `#5865f2` (hover `#6f7af5`) | primary buttons, trim selection, handles |
| GOOD | `#3ba55d` | "ready / posted" |
| BAD | `#ed4245` | errors, "too long" |

The accent is currently Discord-blurple. A distinct brand color is welcome. (Dustin's other app, ClipCrew, uses lime `#B6F23D`, so a shared family look could be nice.) Don't use Discord's logo or make it look like an official Discord product.

**Logo:** currently a rounded square with a play triangle and a bar under it. Please propose an app icon that reads well at 16, 32 and 256 px.

---

## Layout

Three columns:

```
┌──────────┬────────────────┬────────────────────────────────────────┐
│ Sidebar  │ Clip list      │ Editor                                  │
│ ~220px   │ ~380px         │ fills the rest                          │
│          │                │                                         │
│ ClipDrop │ [search][sort] │ Title · game · 1080p60 · 0:40 · 155 MB  │
│ tagline  │                │ ┌────────────────────────────────────┐  │
│          │ TODAY  2 ───── │ │                                    │  │
│ FOLDERS  │ [thumb] name   │ │             video                  │  │
│ All  7   │   game · size  │ │                                    │  │
│ OBS  4   │   time  NEW    │ └────────────────────────────────────┘  │
│ Medal 3  │ [thumb] name   │ [====|■■■■■■■■■■■■|=========] timeline  │
│          │ YESTERDAY 1 ── │ ▶ 0:09.0/0:40  [Start here][End here]   │
│          │ ...            │               Reset · 0:20 clip · Loop 🔊│
│[Update]  │                │ ┌ Export card ───────────────────────┐  │
│[+ Add]   │                │ │ Fit under [20 MB ▾] Res [Auto] FPS │  │
│[Find]    │                │ │ ☑ Mix audio  ☑ Copy when done      │  │
│ Settings │                │ │ 0:20 → 1080p60, ~19.6 MB [Compress]│  │
└──────────┴────────────────┴─┴────────────────────────────────────┴──┘
  status bar: "NVIDIA GPU encoder found" / "New clip: …" / "Ready: …"
```

---

## Screens and states to design

### 1. Main: clip picked, trimming (`screens/1-main-trim-and-options.png`)
**Sidebar**
- App name and tagline ("Clips → Discord, sized right.")
- FOLDERS list: "All clips 7" plus one row per watched folder with a count. A missing folder shows "(missing)". Right-click: Open in Explorer / Stop watching.
- **Update to 1.2.0** button (accent): only visible when an update exists.
- "+ Add folder", "Find my clip folders", Settings link.

**Clip list**
- Search box and sort menu (Newest first / Oldest first / Name / Biggest). Date group headers only appear for the newest/oldest sorts.
- **Date group header:** "TODAY 2 ─────" (title, count, hairline).
- **Clip card** (about 88 px tall):
  - 16:9 thumbnail (128×72) with a duration badge
  - name in bold (middle-truncated)
  - "game folder · size"
  - "Today 9:38 PM"
  - badges: **NEW** (accent pill) and **✓ 18.6 MB** (green pill: a compressed copy is ready)
  - states: hover, selected, "Can't read this file" (error)
  - **Cards are draggable straight into Discord.** Please give a visual hint for that (grip, cursor, tooltip).

**Editor**
- Header: clip title, a meta line (game · 1080p60 · 0:40 · 154.6 MB · 2 audio tracks), and a "Show in folder" button.
- Video (black, native; nothing can sit on top of it). Fallback state: "Can't preview this video here. You can still trim by time and compress it."
- **Timeline** (custom-painted, the most important piece):
  - the full track
  - the selected range in accent with a slightly brighter fill
  - two draggable handles with grips
  - a white playhead with a top knob
  - tick labels underneath
  - areas outside the selection dimmed
  - mouse wheel zooms, and a "zoomed · double-click to reset" hint appears when zoomed
  - Also design the hover state on a handle (resize cursor) and the dragging state.
- Transport row: play/pause, "0:09.0 / 0:40.0", **[ Start here**, **End here ]**, Reset, "0:20.0 clip", Loop toggle, volume slider.
- Keyboard: Space play, I/O or [ ] set start/end, ←/→ 1 s (Shift = 5 s), , . frame step, Ctrl+Enter compress. A subtle shortcut hint or a "?" overlay would help.

**Export card, options state**
- "Fit under" dropdown: Discord (free) 20 MB / Nitro Basic 50 MB / Nitro 500 MB / Custom… (Custom shows an MB number box)
- Resolution (Auto / Original / 1440p / 1080p / 720p / 480p) and Frame rate (Auto / Original / 60 / 30). These could move behind "Advanced".
- "Mix all audio tracks" checkbox (only shown when the clip has more than one track) and "Copy to clipboard when done".
- Prediction line plus primary button **Compress for Discord**. Its variants:
  - normal: "0:20 selected → 1080p60 · 7.4 Mbps, about 19.6 MB"
  - already small: "0:12 selected. Already under 20 MB, so no compressing needed." The button becomes **Use as is**.
  - too long (red, button disabled): "1:20 selected: too long to fit in 20 MB. Trim it to under 11:42."
  - still reading: "Reading the video…" (disabled)
  - failed (red): "Compressing failed: …"

### 2. Compressing (`screens/2-compressing.png`)
Label "Compressing on GPU… 43%" (or "Analyzing… / Compressing…" for the CPU's two passes, or "(retry)"), "about 6s left", progress bar, Cancel. You can still browse other clips meanwhile.

### 3. Ready (`screens/3-ready-drag-or-share.png`): the payoff moment
- **Drop card:** thumbnail, "Drag me into Discord", "file.mp4 · 18.6 MB", "…or press Copy, then Ctrl+V in any Discord chat." The whole card is the drag source. It should *look* grabbable and feel satisfying.
- Info line: "18.6 MB of 20 MB. 1080p60 · GPU (NVIDIA) · took 11s. Copied. Click Discord's message box and press Ctrl+V."
- Buttons: **Share to Discord** (primary), Copy, Show file, Make another version.
- After sharing, the info line reads "Posted to #media ✓".

### 4. First run / empty (`screens/4-first-run-empty.png`)
- List column: "Where do your clips go?" + explanation + **Find my clip folders** button. Also design a "No clips here yet" variant (folders added, nothing recorded yet) and a "No matches" variant (search).
- Editor column: "Pick a clip on the left / Trim it, shrink it to fit Discord, then drag it straight into your chat."
- On first launch the Find-folders dialog opens by itself. This could be a friendlier onboarding: welcome, find folders, pick a size limit, done.

### 5. Find my clip folders dialog (`screens/5-find-folders-dialog.png`)
Detected folders, each with a checkbox, the path, its source ("OBS", "NVIDIA ShadowPlay / NVIDIA App", "Medal", "Xbox Game Bar", "AMD ReLive"...) and a video count. "Add selected" / Cancel. Empty variant: "Nothing new found. Use “Add folder” to pick a folder yourself."

### 6. Settings (`screens/6-settings-dialog.png`)
The title shows the version. Sections:
- **Save compressed clips to:** path + Browse.
- **Compressing:** Fast (uses your NVIDIA/AMD/Intel GPU, or the CPU if there's none) vs Best quality (CPU, about 3× slower), with the note "Works on any PC…".
- **Folders:** include sub-folders.
- **Discord sharing:**
  - "Post clips as [name]"
  - channel list (built-in ones tagged "came with ClipDrop" and not removable)
  - "+ Add channel" / Remove
  - hint text

### 7. Share to Discord dialog (`screens/7-share-dialog.png`)
- Thumbnail, "Share to Discord", file name and size.
- Channel dropdown (#media…, remembers the last one).
- Message (optional, placeholder "bro look at this").
- "Posting as **Dustin**" + Change name.
- Send / Cancel.
- States:
  - uploading: progress bar, inputs locked, Cancel still works
  - posted: "Posted to #media ✓" in green, the button becomes Done
  - errors (red):
    - "Too big for this Discord server. Pick a smaller “Fit under” size and try again."
    - "This channel's webhook link doesn't work anymore…"
    - "Discord is busy (rate limited)…"
- The first time someone shares, a small "What name should your clips be posted under?" prompt appears.

### 8. Add a Discord channel (`screens/8-add-channel-dialog.png`)
How-to text (Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL), a channel name field, a webhook URL field, **Check and add**, and an inline status ("Checking with Discord…", or an error).

### 9. Update available (`screens/9-update-dialog.png`)
- "ClipDrop 1.2.0 is out", "You have 1.1.0. Updating takes about a minute; your clips, folders and settings stay as they are."
- Release notes box.
- Update now / Later.
- States: downloading (progress), "Installing… ClipDrop will reopen by itself.", error.

### Small things
- Status bar messages: "NVIDIA GPU encoder found", "New clip: name.mp4", "Ready: name.mp4 (18.6 MB)", "Posted to #media", "Cancelled". This could become toasts.
- Right-click menu on a clip:
  - Copy compressed clip (Ctrl+V in Discord)
  - Show compressed clip
  - Delete compressed copy
  - Copy original file
  - Show original in folder
- Tooltips on every icon-only control.

---

## What to deliver

1. **Design tokens:** colors, type scale, radii, spacing, all in plain values I can paste into QSS.
2. **Main window** at 1400×860 in these states: trimming, compressing, ready, empty/first-run.
3. **Components** with all states: clip card (default/hover/selected/new/ready/error), group header, timeline (idle/hover handle/dragging/zoomed), buttons (primary/secondary/flat/icon; hover/pressed/disabled), inputs, dropdowns, checkboxes and toggles, progress bar, pills/badges, drop card, toasts.
4. **Dialogs:** Find folders, Settings, Share, Add channel, Update, Name prompt (or a better onboarding flow).
5. **App icon** at 16/32/48/256.
6. A couple of icons for play/pause, volume, folder, share, copy, settings, update (SVG).

Keep the copy (wording) as is unless you have something clearer. It's been written to be short and plain.
