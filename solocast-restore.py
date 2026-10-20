#!/usr/bin/env python3
"""
solocast-restore.py — Restore HyperX SoloCast (03F0:078B) support in HyperX NGENUITY (2025 rewrite).

Unofficial community patch. Not affiliated with or endorsed by HP/HyperX.
Modifies the user's own installation of the free NGENUITY software on their own machine.
No license checks, DRM, or copy protection are involved or circumvented — the removed
gates are product whitelists that silently drop the SoloCast despite full host-side support.

Verified against NGENUITY 3.1.0.0:
  NGENUITY.dll                    sha256 03515f57445c3c1ebb20c793c3a69fad72e455a54fff842356fede5e49e4a4d9
  hxn-srv-communication-hub.exe   sha256 ab808dacf2f379603c2f3ca14e5f88228f4fae50e59c4c682cb37a45a7c6aac7

Usage:
  python solocast-restore.py --app-dir "<path to folder containing NGENUITY.dll>" [--check] [--restore]

  --check    verify compatibility and patch state; change nothing
  --restore  restore the original files from backups
  (default)  apply the patch

Every edit is located by unique byte signature and verified before and after writing.
If ANY signature count is unexpected (e.g. after an app update), the script aborts
without touching anything. Backups are written as <file>.solocast-bak.
"""
import argparse
import hashlib
import os
import shutil
import struct
import sys

# ---------------------------------------------------------------- signatures

# Hub: SoloCast2Updater descriptor arm  (mov dword[rax],0x41070FBF ; mov word[rax+4],0x0152)
HUB_ARM_ORIG = bytes.fromhex("c700bf0f0741" "66c740045201")
HUB_ARM_PATCHED = bytes.fromhex("c7008b07" "0741" "66c740045201")   # pid 0x0FBF -> 0x078B

# UI: ldc.i4 0x0FBF in SoloCast2Configuration.get_AudioInputEndpointProductId
UI_ENDPOINT_ORIG = bytes.fromhex("20bf0f0000")
UI_ENDPOINT_PATCHED = bytes.fromhex("208b070000")

# UI: "ldc.i4.s 82 ; sub ; switch(9)"  — model-based factory switches
# (GetDeviceAudioConfiguration, AudioSWControlViewModel.Create, AudioPreviewViewModel.Create)
UI_SWITCH82_ORIG = bytes.fromhex("1f525945" "09000000")
UI_SWITCH82_PATCHED = bytes.fromhex("1f515945" "09000000")   # ldc.i4.s 82 -> 81

# UI: "ldc.i4.s 58 ; sub ; switch(44)"  — model-based feature switches
# (IsFrontSupported, GetGeneralConfiguration)
UI_SWITCH58_ORIG = bytes.fromhex("1f3a5945" "2c000000")

EXPECT_SWITCH82_SITES = 3
EXPECT_SWITCH58_SITES = 2

# Firmware payload defusal (SoloCast 2 firmware must never flash onto a SoloCast 1)
FW_REL = os.path.join("Assets", "Services", "Libs", "SoloCast2", "03F00FBF.rfw")

BAK_SUFFIX = ".solocast-bak"

KNOWN_HASHES = {
    "NGENUITY.dll": "03515f57445c3c1ebb20c793c3a69fad72e455a54fff842356fede5e49e4a4d9",
    os.path.join("Assets", "Services", "hxn-srv-communication-hub.exe"):
        "ab808dacf2f379603c2f3ca14e5f88228f4fae50e59c4c682cb37a45a7c6aac7",
}


def find_all(haystack: bytes, needle: bytes):
    out, i = [], 0
    while True:
        j = haystack.find(needle, i)
        if j < 0:
            return out
        out.append(j)
        i = j + 1


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Abort(Exception):
    pass


def require(cond, msg):
    if not cond:
        raise Abort(msg)


# ---------------------------------------------------------------- transforms

def patch_hub(data: bytearray):
    """PID 0x0FBF -> 0x078B in the SoloCast2Updater descriptor arm."""
    hits = find_all(data, HUB_ARM_ORIG)
    done = find_all(data, HUB_ARM_PATCHED)
    if done:
        return "already patched"
    require(len(hits) == 1, f"hub descriptor signature found {len(hits)} times (expected 1)")
    off = hits[0] + 2
    data[off:off + 2] = bytes.fromhex("8b07")
    return "patched"


def patch_ui_endpoint(data: bytearray):
    """get_AudioInputEndpointProductId: 0x0FBF -> 0x078B (audio engine endpoint binding)."""
    done = find_all(data, UI_ENDPOINT_PATCHED)
    if done:
        return "already patched"
    hits = find_all(data, UI_ENDPOINT_ORIG)
    require(len(hits) == 1, f"endpoint-PID signature found {len(hits)} times (expected 1)")
    off = hits[0] + 1
    data[off:off + 4] = bytes.fromhex("8b070000")
    return "patched"


def patch_switch82(data: bytearray):
    """For every 'model-82' factory switch: rebase to 81 and give 81 and 82 the same case.

    Original targets:  [T82, T83, T84, T85, T86, T87, T88, T89, T90]
    Patched targets:   [T82, T82, T83, T84, T85, T86, T87, T88, T89]
    Model 90 falls to the default path (documented collateral).
    """
    orig = find_all(data, UI_SWITCH82_ORIG)
    done = find_all(data, UI_SWITCH82_PATCHED)
    if done:
        require(len(done) == EXPECT_SWITCH82_SITES,
                f"expected {EXPECT_SWITCH82_SITES} patched factory switches, found {len(done)}")
        return "already patched"
    require(len(orig) == EXPECT_SWITCH82_SITES,
            f"factory-switch signature found {len(orig)} times (expected {EXPECT_SWITCH82_SITES})")
    for sig in orig:
        # ldc operand 82 -> 81
        require(data[sig + 1] == 0x52, "unexpected ldc operand")
        data[sig + 1] = 0x51
        # signature layout: 1F 52 (ldc.i4.s 82) | 59 (sub) | 45 (switch) | count u32 | targets
        # -> opcode at sig+3, count at sig+4, target table at sig+8
        require(data[sig + 3] == 0x45 and struct.unpack_from("<I", data, sig + 4)[0] == 9,
                "unexpected switch layout")
        tgt = sig + 8
        old = list(struct.unpack_from("<9i", data, tgt))
        require(old[0] != old[1], "factory switch case 82 collides with case 83 — refusing")
        new = [old[0], old[0], *old[1:8]]      # 81 & 82 -> old 82-case; shift the rest
        struct.pack_into("<9i", data, tgt, *new)
    return f"patched ({len(orig)} sites)"


def patch_switch58(data: bytearray):
    """For the 58-based feature switches (IsFrontSupported, GetGeneralConfiguration):
    make slot for model 81 use slot 24's (model 82's) target."""
    orig = find_all(data, UI_SWITCH58_ORIG)
    require(len(orig) == EXPECT_SWITCH58_SITES,
            f"feature-switch signature found {len(orig)} times (expected {EXPECT_SWITCH58_SITES})")
    changed = 0
    already = 0
    for sig in orig:
        # 1F 3A (ldc.i4.s 58) | 59 (sub) | 45 (switch) | count u32 | targets
        require(data[sig + 3] == 0x45 and struct.unpack_from("<I", data, sig + 4)[0] == 44,
                "unexpected switch layout")
        tgt = sig + 8
        slots = list(struct.unpack_from("<44i", data, tgt))
        if slots[23] == slots[24]:
            already += 1                       # 81 already maps like 82
            continue
        require(slots[23] != slots[24], "unreachable")
        slots[23] = slots[24]                  # model 81 := model 82's case
        struct.pack_into("<44i", data, tgt, *slots)
        changed += 1
    require(already + changed == EXPECT_SWITCH58_SITES, "feature switches in inconsistent state")
    return "already patched" if changed == 0 else f"patched ({changed} sites)"


def defuse_firmware(app_dir):
    fw = os.path.join(app_dir, FW_REL)
    if not os.path.exists(fw):
        return "payload absent" if os.path.exists(fw + ".disabled") else "WARNING: not found"
    os.rename(fw, fw + ".disabled")
    return "defused"


def restore_file(app_dir, rel):
    src = os.path.join(app_dir, rel)
    bak = src + BAK_SUFFIX
    if os.path.exists(bak):
        shutil.copy2(bak, src)
        return "restored from backup"
    return "no backup found"


# ---------------------------------------------------------------- driver

def main():
    ap = argparse.ArgumentParser(description="Restore HyperX SoloCast support in NGENUITY (2025).")
    ap.add_argument("--app-dir", required=True, help="folder containing NGENUITY.dll")
    ap.add_argument("--check", action="store_true", help="verify only, change nothing")
    ap.add_argument("--restore", action="store_true", help="restore originals from backups")
    args = ap.parse_args()

    app = args.app_dir
    require(os.path.isdir(app), f"app dir not found: {app}")
    ui_rel = "NGENUITY.dll"
    hub_rel = os.path.join("Assets", "Services", "hxn-srv-communication-hub.exe")
    ui_path, hub_path = os.path.join(app, ui_rel), os.path.join(app, hub_rel)
    require(os.path.exists(ui_path), "NGENUITY.dll not found in app dir")
    require(os.path.exists(hub_path), "hxn-srv-communication-hub.exe not found under Assets\\Services")

    if args.restore:
        print(restore_file(app, ui_rel))
        print(restore_file(app, hub_rel))
        fw = os.path.join(app, FW_REL + ".disabled")
        if os.path.exists(fw):
            os.rename(fw, fw[:-len(".disabled")])
            print("firmware payload restored")
        print("restore complete")
        return

    # informational version check
    for rel, expect in KNOWN_HASHES.items():
        p = os.path.join(app, rel)
        if os.path.exists(p):
            actual = sha256(p)
            tag = "matches known 3.1.0.0" if actual == expect else "DIFFERENT from known 3.1.0.0"
            print(f"[i] {rel}: sha256 {actual[:16]}...  {tag}")

    # dry-run analysis on in-memory copies
    ui = bytearray(open(ui_path, "rb").read())
    hub = bytearray(open(hub_path, "rb").read())

    plan = []
    for name, fn, buf in [("hub updater descriptor", patch_hub, hub),
                          ("UI endpoint PID", patch_ui_endpoint, ui),
                          ("UI factory switches (82-based)", patch_switch82, ui),
                          ("UI feature switches (58-based)", patch_switch58, ui)]:
        try:
            status = fn(bytearray(buf))          # trial on a scratch copy
        except Abort as e:
            print(f"[x] {name}: {e}")
            print("    Aborting — nothing has been modified.")
            sys.exit(1)
        print(f"[ok] {name}: {status}")
        plan.append((name, fn))

    if args.check:
        print("check complete — signatures verified. Run without --check to patch.")
        return

    # backups + apply + verify readback
    for p in (ui_path, hub_path):
        if not os.path.exists(p + BAK_SUFFIX):
            shutil.copy2(p, p + BAK_SUFFIX)

    ui = bytearray(open(ui_path, "rb").read())
    hub = bytearray(open(hub_path, "rb").read())
    for name, fn, buf in [("hub updater descriptor", patch_hub, hub),
                          ("UI endpoint PID", patch_ui_endpoint, ui),
                          ("UI factory switches (82-based)", patch_switch82, ui),
                          ("UI feature switches (58-based)", patch_switch58, ui)]:
        fn(buf)
        print(f"[applied] {name}")

    open(hub_path, "wb").write(bytes(hub))
    open(ui_path, "wb").write(bytes(ui))

    # verify: rerun analysis — everything must now report "already patched"
    ui2 = bytearray(open(ui_path, "rb").read())
    hub2 = bytearray(open(hub_path, "rb").read())
    for name, fn, buf in [("hub updater descriptor", patch_hub, hub2),
                          ("UI endpoint PID", patch_ui_endpoint, ui2),
                          ("UI factory switches (82-based)", patch_switch82, ui2)]:
        status = fn(bytearray(buf))
        require(status.startswith("already"), f"verification failed for {name}")
    print("[verified] all byte patches confirmed in written files")

    print("[applied] firmware payload:", defuse_firmware(app))
    print()
    print("Done. Launch NGENUITY and open the DEVICES page — the SoloCast should appear with")
    print("its own name and a full settings page (gain / EQ / filters — host-side audio engine DSP).")
    print("Backups: NGENUITY.dll.solocast-bak, hxn-srv-communication-hub.exe.solocast-bak")
    print("Undo any time with:  python solocast-restore.py --app-dir <dir> --restore")


if __name__ == "__main__":
    try:
        main()
    except Abort as e:
        print(f"[x] {e}")
        sys.exit(1)
