# ngenuity-solocast-restore

Restore HyperX SoloCast support in the 2025 rewrite of HyperX NGENUITY.

> **Unofficial community patch.** Not affiliated with, endorsed by, or supported by HP or HyperX. Use at your own risk.

- **Platform:** Windows · **Tested on:** NGENUITY **3.1.0.0** · **Device:** HyperX SoloCast, HP-era revision (`USB\VID_03F0&PID_078B`)

---

## Why I made this

I own an original HyperX SoloCast. The hardware works perfectly. The new NGENUITY — rebuilt from scratch in 2025 — simply refuses to acknowledge it, while officially supporting the SoloCast 2 and newer mics.

When I looked into *why*, it turned out the exclusion was cosmetic, not technical. The app's own device tables still contain the SoloCast's name, its product ID, and its configuration slots — only a handful of switch statements were pointed at their default (reject) paths. Meanwhile the features the new app sells for the SoloCast 2 (gain, EQ, high/low-pass filters, noise reduction) are not mic features at all: they run in a host-side audio engine driver that processes any capture device it's bound to, mic-agnostic by design. My SoloCast speaks the same vendor protocol family, honestly identifies itself as `Products.SoloCast` over it, and the engine happily processes its audio once it's allowed to.

So "unsupported" meant, quite literally, a few bytes in two files. This script changes those bytes.

**Result on my machine:** the SoloCast appears in the app under its own name with a full settings page, and the EQ, high-pass/low-pass filters, and gain are audibly and measurably working — real DSP on my mic's audio, verified by ear and by spectrogram.

*(Full technical write-up, including how this was reverse engineered: see [`SOLOCAST-RESTORATION.md`](./SOLOCAST-RESTORATION.md).)*

## What works

| Feature | Status |
|---|---|
| Device recognized in DEVICES (own name/category) | ✅ |
| SoloCast 2 settings page (input volume, EQ, high-pass, low-pass, presence boost, frequency filter) | ✅ — host-side audio engine DSP, verified working |
| Microphone test | ✅ |
| AI noise reduction / compressor / limiter | ✅ same engine chain (harder to hear casually — test with steady background noise) |
| Mute-state sync (app reflecting physical tap-to-mute) | ❓ firmware-dependent — untested |
| SoloCast 2 firmware updates | 🚫 deliberately disabled (flashing new-gen firmware at an older mic is a brick risk) |

## Requirements and scope

- Windows 10/11, NGENUITY 3.1.0.0 (the script locates patches by byte signature and **refuses to run on any other version** rather than corrupting your install — if HyperX ships an update, wait for an updated script)
- **HP-era SoloCast revision (`VID_03F0&PID_078B`)** — check Device Manager → Hardware Ids. This is the later production run. Kingston-era units (`VID_0951&PID_170F`) use a different protocol generation and are **untested — likely not covered**.
- The audio engine driver (the app itself will prompt you to install it)

## Usage

```bat
python solocast-restore.py --app-dir "C:\path\to\NGENUITY" --check
python solocast-restore.py --app-dir "C:\path\to\NGENUITY"
```

`--app-dir` is the folder containing `NGENUITY.dll` (for a portable copy, the extracted app folder; for a Store/installed copy, its install location).

The script:

1. verifies every patch location by unique byte signature *before* changing anything — any mismatch aborts with your install untouched
2. backs up `NGENUITY.dll` and `hxn-srv-communication-hub.exe` to `*.solocast-bak`
3. applies 8 byte-level patches (details in the technical doc)
4. renames the SoloCast 2 firmware payload (`03F00FBF.rfw`) so it can never be flashed onto a SoloCast 1
5. re-verifies everything it wrote

Restore to stock any time:

```bat
python solocast-restore.py --app-dir "C:\path\to\NGENUITY" --restore
```

Requires Python 3.8+, standard library only.

## How it works (short version)

The 2025 NGENUITY is a .NET 10 / Avalonia UI with a native Rust device hub. The mic honestly identifies itself over the hub's protocol as `Products.SoloCast` — the enum entry, display name, and config slots all still exist in the binaries. What's missing is ~6 activation points: a front-supported whitelist entry, two configuration factory cases, and three panel factory cases, all of which either throw `NotImplementedException` or return `null` for value 81. The patch makes model 81 take model 82's (SoloCast 2's) code paths everywhere the two are interchangeable, and repoints the audio-engine endpoint binding to the SoloCast's real USB PID.

Nothing here circumvents any license check, DRM, or copy protection — the removed gates are product whitelists, not access controls.

## Status: unmaintained

**This was a one-time project and I am not actively working on it.** The script is deliberately defensive: if HyperX ships an update that changes the binaries, it will detect the mismatch and refuse to run instead of breaking your install. It will not magically support future versions; someone would need to redo the offset analysis (the technical doc explains the whole method, so it's doable).

Issues and pull requests from the community are welcome and may get merged, but don't expect responses from me. If HyperX officially restores legacy mic support — which would be the best outcome for everyone — please use their version and archive this repo.

## Legal

- This repository contains **no HyperX/HP code or binaries** — only a patch script. Each user applies it to their own legally obtained copy of the free NGENUITY software on their own machine.
- No license check, encryption, or copy protection is circumvented anywhere.
- The software's EULA likely prohibits reverse engineering and modification; that is a contractual matter between each user and HP. This project is distributed in the same spirit as the broader hardware-modding community.
- HyperX and NGENUITY are trademarks of HP Development Company, L.P. This project is unofficial.
- Provided as-is, MIT licensed (see [`LICENSE`](./LICENSE)). Not legal advice — see the full notes in the technical doc.
