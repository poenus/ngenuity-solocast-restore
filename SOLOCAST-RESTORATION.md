# Restoring HyperX SoloCast Support in NGENUITY (2025)

**Target:** HyperX NGENUITY 3.1.0.0 (the 2025 rewrite) · **Device:** HyperX SoloCast, HP-era revision (`USB\VID_03F0&PID_078B`) · **Result:** device recognized, full SoloCast 2 settings page, host-side audio engine DSP (input gain, 10-band EQ, high/low-pass, presence boost, AI effects) verified working on the original SoloCast's audio.

This documents the complete investigation, every patch applied (with exact offsets and rationale), the verification methodology, and what does/doesn't work after patching. It is written so the process can be reproduced on a new app version or extended to other dropped legacy mics.

---

## 1. Background

HyperX rebuilt NGENUITY from the ground up in 2025. The new app officially supports devices released after August 2025 "plus many older products" — but the original SoloCast is not on the list (only SoloCast 2 / 2 Pro / QuadCast 2 S / FlipCast are). The old "NGENUITY (Legacy)" app still recognizes the SoloCast but is in maintenance mode and will eventually be retired. In the legacy app, the SoloCast never had real settings (only firmware updates); gain was standard Windows UAC and tap-to-mute is on-device firmware.

**Why this restoration is possible at all:** in the new architecture, a SoloCast 2's settings are almost entirely *host-side* — implemented by an audio engine driver (HyperX Virtual Audio Device + a DSP service) that binds to the mic's Windows audio endpoint. That engine is mic-agnostic. The mic itself is just a capture device to it.

## 2. What the new NGENUITY actually is

Community claims that the new app is Electron are wrong. Actual architecture (from binary inspection):

| Component | Technology | Role |
|---|---|---|
| `NGENUITY.exe` / `NGENUITY.dll` | .NET 10, Avalonia UI 12, MVVM (CommunityToolkit), DryIoc | The UI |
| `NGENUITY.Common.dll` | .NET 10 | Shared types: `CommunicationHub.Products` enum, FlatBuffer protocol classes, device model |
| `Assets\Services\hxn-srv-communication-hub.exe` | **Rust** (native x64) | All USB/HID device detection & communication |
| `Assets\Services\hxn-srv-light-engine.exe` | Rust (native x64) | RGB engine |
| `Assets\Drivers\AudioEngine\` | Windows driver + services | Virtual audio cable (`vachpxkd.inf`), DSP engine, endpoint togglers |
| `Assets\Services\Libs\<Device>\` | firmware payloads | Per-device update files named by USB PID (e.g. `SoloCast2\03F00FBF.rfw`) |
| `Shared\RvcLib641001.dll` / `RvcHIDLib641001.dll` | native | Sonix-chip mic firmware tooling (`GetVIDPID`, `GetDevFirmwareInfo`, `UpdateFW_USB`, …) |

UI ↔ services communicate over **ZeroMQ (NetMQ)** on `127.0.0.1`: hub REQ 6890–6899, hub PUB 7890–7899; light engine REQ 1110–1115, PUB 2220–2225. Messages are **FlatBuffers** (schema classes in `NGENUITY.Common.dll`, namespace `CommunicationHub`).

### The device

The SoloCast hardware has two revisions:
- Kingston-era: `0951:170F` (2020)
- **HP-era: `03F0:078B`** (later production run — this is the revision this project targets)

It exposes MI_00 (USB Audio Class capture) and MI_02 (HID) with three collections: **vendor-defined (usage page `0xFFC0`)**, consumer control, and telephony — the same vendor-collection family as the new-gen mics (the upstream Linux 7.3 `hid-hyperx` driver documents this protocol family for QuadCast 2). It speaks enough of the universal protocol to answer the hub's identity query: it self-reports its name (`"SoloCast"`), VID/PID strings, firmware string (`"4112"`), and — crucially — **`Product = 81` (`Products.SoloCast`)**.

## 3. How the investigation proceeded

1. **Strings/metadata survey** — found the full 104-entry device enum *including* `SoloCast` in both the Rust hub and the C# `CommunicationHub.Products` enum (`SoloCast = 81`, `SoloCast2 = 82`).
2. **Rust hub static analysis** (capstone; Ghidra via REA kept timing out on the 6.5 MB Rust binary) — decoded the per-product updater descriptor table: monomorphized match arms storing `{pid: u16, protocol: u16, product_flags: u16}` triples per product. The SoloCast2Updater claims PID `0x0FBF`. **No arm exists for `0x078B`.**
3. **Live HID probe** (hidapi) — confirmed the `0xFFC0` vendor collection on the connected mic; feature-report GETs are rejected (the protocol uses input/output reports).
4. **Ran the app with the mic connected** — its logs (`%LOCALAPPDATA%\NGENUITY\Logs\`) showed the hub *opening the mic's vendor collection and publishing `DeviceAdded`* — i.e. detection was never the blocker.
5. **MITM'd the UI↔hub protocol** — patched the UI's IL port constants to route through a local TCP relay, captured the ZMTP/FlatBuffer traffic. Decoded the hub's `DeviceList` and `DeviceInformation` replies: the mic truthfully reports `Product = 0x51 (81)`, `Category = 4`, `DeviceId = 0xB0`, and a minimal feature set (`SupportFeaturesB = [32]` = `GeneralAudioSettingsSupported`).
6. **IL analysis of the UI** (dnfile + dncil) — followed the device pipeline: `InitDevice → IsFrontSupported(Product) → SafeAddDevice → HXDevice → CreateNavigations → DeviceModelExtension.Get*Configuration → ConfigFeatureExtension.CreateChildViewModels → per-device ViewModel factories`.
7. **Crash-log-driven iteration** — every user-visible failure produced a full stack trace in the app's Serilog log naming the exact gate, which made each subsequent patch a single verified edit.

**Root cause in one line:** the mic honestly identifies itself as `Products.SoloCast (81)` and the new UI still contains all its naming/config slots — but ~6 activation points in `NGENUITY.dll` either throw `NotImplementedException` or return `null` for value 81, so the device was dropped, crashed the page, or rendered empty.

## 4. The patches

All patches are minimal, in-place, same-size byte edits. Original file hashes for version 3.1.0.0:

- `hxn-srv-communication-hub.exe` — SHA-256 `ab808dacf2f379603c2f3ca14e5f88228f4fae50e59c4c682cb37a45a7c6aac7`
- `NGENUITY.dll` — SHA-256 `03515f57445c3c1ebb20c793c3a69fad72e455a54fff842356fede5e49e4a4d9` (5,611,824 bytes)

Fully patched (user-verified working) build hashes:

- `hxn-srv-communication-hub.exe` — SHA-256 `3d144c1efc1a7bd3516872182406ae7f1a412a803c067bae4492471d8a2df228`
- `NGENUITY.dll` — SHA-256 `6fc267ba38a4b441c739b7fd40e0c28b40859a34f947a3a5a6d50db69ff20bd0`

`solocast-restore.py` was validated end-to-end against a virgin 3.1.0.0 copy: its output is **byte-identical** to the working build above; re-running reports "already patched" without changes; `--restore` reproduces the virgin files byte-identically; and any signature-count mismatch (e.g. a future app update) aborts before touching anything.

The guiding principle: **make value 81 (SoloCast) behave exactly like value 82 (SoloCast 2)** everywhere the two are interchangeable, because the SoloCast 2's feature set is host-side and works on any capture endpoint.

### Patch 1 — Hub: updater descriptor PID
- **File:** `Assets\Services\hxn-srv-communication-hub.exe`
- **Offset:** `0x139BF1` — bytes `BF 0F` → `8B 07`
- **Context:** `C7 00 BF 0F 07 41 66 C7 40 04 52 01` (`mov dword [rax], 0x41070FBF; mov word [rax+4], 0x0152`) — the SoloCast2Updater descriptor arm
- **Effect:** the SoloCast2 updater path claims PID `0x078B` (your mic) instead of `0x0FBF`. This makes the hub treat the device consistently as a SoloCast2-family product.

### Patch 2 — UI: audio endpoint PID binding
- **File:** `NGENUITY.dll`
- **Offset:** `0x13D904` — bytes `BF 0F 00 00` → `8B 07 00 00` (operand of `ldc.i4 0x0FBF` in `HXN.Configurations.Microphones.SoloCast2Configuration::get_AudioInputEndpointProductId`)
- **Effect:** the audio engine matches Windows endpoints by the config's declared PID; this points it at your mic's real endpoint. Log-verified: *"Matched audio endpoints: PID: 1931 … Target audio endpoint found: Microphone (HyperX SoloCast) … Assign process succeeded."*

### Patch 3 — UI: `IsFrontSupported` whitelist
- **Method:** `HXN.Extensions.DeviceModelExtension::IsFrontSupported` (body `0x12A4E8`)
- **Edit:** second switch (models 58–101, 44 slots) target table at `0x12A55E`; slot for model 81 (index 23) at `0x12A5BA`: rel32 `C4 00 00 00` → `28 00 00 00` (default-throw → the same true-block model 82 uses)
- **Effect:** `InitDevice` stops silently dropping the device. **This is the patch that makes the mic appear in the DEVICES page.**

### Patch 4 — UI: `GetDeviceAudioConfiguration`
- **Method:** `HXN.Extensions.DeviceModelExtension::GetDeviceAudioConfiguration` (body `0x129D74`)
- **Edits:** `ldc.i4.s 82` operand at `0x129DD6`: `52` → `51` (rebase switch 82→81); rewrite the 9-entry target table at `0x129DDD` (rel base `0x129E01`) so models 81 **and** 82 both → `SoloCast2Configuration` (`1220147`), FlipCast/Eve1800/CloudFlight2 preserved.
- **Effect:** opening the device's audio page returns the SoloCast 2 configuration instead of throwing `"SoloCast not implemented for IAudioConfiguration yet"`.

### Patch 5 — UI: `GetGeneralConfiguration`
- **Method:** `HXN.Extensions.DeviceModelExtension::GetGeneralConfiguration` (body `0x129FA8`)
- **Edit:** second switch (models 58–101) table at `0x12A01E`; slot 23 (model 81) at `0x12A07A`: rel32 `53 01 00 00` → `47 00 00 00` (default-throw → 82's target `1220885`)
- **Effect:** fixes the crash when clicking the device tile or the Sound nav (`"SoloCast not implemented for IGeneralConfiguration yet"`, from `CheckStandaloneFirmwareAvailable`).

### Patch 6 — UI: controls factory
- **Method:** `HXN.ViewModels.Audios.Controls.AudioSWControlViewModel::Create` (body `0xE6F8C`)
- **Edits:** `ldc.i4.s 82` operand at `0xE6FF7`: `52` → `51`; 9-entry table at `0xE6FFE` (rel base `0xE7022`) shifted so 81 **and** 82 → `SoloCast2AudioViewModel::Create` (`946259`).
- **Effect:** the settings panel gets its content. Before this patch the factory produced **`Content = null`** for 81 — the "empty page with only a microphone test" symptom.

### Patch 7 — UI: preview factory
- **Method:** `HXN.ViewModels.Audios.AudioPreviewViewModel::Create` (body `0xE165C`)
- **Edits:** `ldc.i4.s 82` operand at `0xE1691`: `52` → `51`; 9-entry table at `0xE1698` (rel base `0xE16BC`) shifted so 81 **and** 82 → `SoloCast2AudioPreviewViewModel::Create` (`923372`).
- **Effect:** the proper SoloCast 2 preview renders instead of a null/generic preview.

### Patch 8 — Safety: firmware defusal
- **File:** rename `Assets\Services\Libs\SoloCast2\03F00FBF.rfw` → `03F00FBF.rfw.disabled`
- **Rationale:** with the hub claiming your mic as SoloCast2-family, a firmware-update flow could in principle attempt to push **SoloCast 2 firmware at the original SoloCast — a brick risk**. With the payload renamed, the updater fails at "Load FW Image" before touching the device. Deliberate and reversible.

### Known collateral
Patches 4/6/7 rebase 9-slot switches from 82 to 81, which pushes model 90 (`CloudXFlight2Xbox`) off the end of each table into the default path. Irrelevant on a machine without that headset, but documented for honesty. A future refinement could extend the tables instead.

### Diagnostic-only (reverted, not part of the patch set)
The UI's IPC port constants (`ldc.i4` of 1110/1115/2220/2225/6890/6899/7890/7899, 16 sites) were temporarily repointed at a local TCP relay (`2xxxx` ports) to capture the UI↔hub FlatBuffer traffic. All 16 sites were restored to stock afterward. The relay + ZMTP parser used for this are preserved in this folder (`relay.py`, `zparse.py`, `eavesdrop.py`).

## 5. Why it works — and what actually works

Verified working (by the user, on real audio):
- Device appears in DEVICES with its own name and category
- Full SoloCast 2 settings page renders
- **Input gain, 10-band EQ, high-pass, low-pass — audibly and visibly working** (the engine's `SetInputEQGains`, `SetInputParametricEQSettings`, `SetMicModuleBypassStates` all ack'd `Okay` in the log)
- AI noise reduction / compressor / limiter run in the same engine chain (testable per the tips in the README)

Works because **all of this is host-side DSP**: the audio engine binds your mic's capture endpoint (Patch 2) and processes it in the HyperX Virtual Audio Device path. To the engine, the model number is irrelevant.

Firmware-dependent (untested / partial by nature):
- **Mute-state sync** (app reflecting physical tap-to-mute) — requires the mic's firmware to push status over the `0xFFC0` HID channel. The HP-era revision speaks the protocol family, so it may work; not yet verified.
- Anything querying the device for new-gen capabilities will get the old firmware's minimal answers (it reports only `GeneralAudioSettingsSupported`).

Never going to work:
- Onboard features the original SoloCast hardware lacks (on-device EQ, polar patterns, etc.)
- Firmware updates (intentionally defused — see Patch 8)

Scope note: this was tested on the **`03F0:078B` HP-era revision**. Kingston-era `0951:170F` units speak a different generation of the protocol and were not tested; the method may not apply to them.

## 6. Generalizing to other dropped mics

The same recipe applies to any legacy mic whose firmware answers the hub's identity query and whose `Products` value we can find in the enum:

| Products enum (NGENUITY.Common) | Value |
|---|---|
| DuoCast | 50 |
| QuadCast | 77 |
| QuadCast2 | 78 |
| QuadCast2S | 79 |
| QuadCastS | 80 |
| SoloCast | 81 |
| SoloCast2 | 82 |

The uniform transforms (implemented in `solocast-restore.py`):
- **82-based 9-slot switches** (3 occurrences): rebase to 81, shift targets so the legacy model and 82 share 82's original target.
- **58-based 44-slot switches** (2 occurrences: `IsFrontSupported`, `GetGeneralConfiguration`): retarget the legacy model's slot to 82's target.

For QuadCastS → donor `QuadCast2SConfiguration`, DuoCast/QuadCast → likely `SoloCast2Configuration` or `FlipCastConfiguration` as donors — each needs its own endpoint-PID patch, its own hub descriptor edit (or none, if the updater path should stay untouched), and testing. The firmware-defusal step applies to every donor.

## 7. Tools used

- **REA MCP** (Ghidra-backed) — initial binary triage, managed metadata
- **capstone** — Rust hub disassembly, jump-table decoding
- **dnfile + dncil** — .NET metadata + IL disassembly, cross-referencing, patch verification
- **pyzmq + custom ZMTP/FlatBuffer parsers** — protocol MITM and decoding
- **hidapi** — device HID enumeration/probing
- **RapidOCR + PrintWindow** — UI verification without focus stealing
- The app's own Serilog logs — crash stack traces drove every fix

## 8. Legal / distribution notes (not legal advice)

- This project modifies the user's **own legally obtained, free software** on their own machine, to restore functionality of hardware they own. No license check, encryption, or copy protection is circumvented anywhere — the gates removed are product whitelists, not DRM.
- HP's software EULA almost certainly contains no-reverse-engineering/no-modification clauses; those are contract terms between each user and HP, and the modding community has operated in this space for decades. Enforcement against non-piracy feature-restoration mods is vanishingly rare.
- Safest distribution model (implemented): **source script only** — no HP binaries are redistributed; each user patches their own installation. The script verifies every target byte before writing and aborts on any mismatch (including future app versions), backs up originals, and can restore them.
- Ship with: MIT license, "unofficial, not affiliated with HP/HyperX" disclaimer, a note that HyperX may restore these devices officially (they added devices back during the beta), and a request to also upvote the idea on the r/HyperX feedback threads.
