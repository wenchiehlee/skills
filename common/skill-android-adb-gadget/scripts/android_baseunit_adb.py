#!/usr/bin/env python3
"""
Android BaseUnit ADB Skill — reusable helpers for managing dual-ADB (USB + Ethernet)
on Android BaseUnit (MT8395). Portable across Windows / macOS / Linux — pure
Python 3.8+, only external dependency is `adb` on PATH.

Android BaseUnit exposes two ADB transports whose availability depends on gadget
mount state:

    State A  (fresh boot / after reboot):
        USB ADB  OK   (device serial visible in `adb devices`)
        Eth ADB  --   (not yet configured)

    State B  (Ethernet bootstrapped, UVC not yet mounted):
        USB ADB  OK   (still alive)
        Eth ADB  OK   (192.168.10.1:5555)

    State C  (UVC/UAC gadget mounted — normal running state):
        USB ADB  --   (USB-C1 taken over by gadget functions)
        Eth ADB  OK   (only remaining path)

Transition rules encoded in this module:
  * Ethernet ADB MUST be bootstrapped via USB ADB (State A->B) before USB breaks.
  * setup_uvc.sh MUST NOT be run when vendor.usb.adb.uvc=99 (kernel panic risk).
  * After reboot, device always lands in State A — USB ADB must be re-awaited.

Use as a library:
    from android_baseunit_adb import get_state, wait_usb_adb, connect_ethernet_adb, \\
        reboot, mount, set_osd

Or as a CLI:
    python android_baseunit_adb.py state
    python android_baseunit_adb.py wait-usb --timeout 60
    python android_baseunit_adb.py connect-eth --usb-serial 1882001373
    python android_baseunit_adb.py reboot
    python android_baseunit_adb.py mount --repo-root /path/to/gadget
    python android_baseunit_adb.py osd --frames 300
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# ─── Portability: force UTF-8 stdout/stderr ──────────────────────────────────
# Legacy Windows consoles (cp1252/cp437) raise UnicodeEncodeError on the glyphs
# used below. reconfigure() is available on Python 3.7+ text streams; fall back
# silently (e.g. when stdout is already redirected/wrapped) if unsupported.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ─── Colour helpers (ANSI — works in Windows Terminal / PowerShell 7+ / macOS / Linux) ──

_NO_COLOR = os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty()


def _c(code: str, msg: str) -> str:
    if _NO_COLOR:
        return msg
    return f"\x1b[{code}m{msg}\x1b[0m"


def write_step(msg: str) -> None:
    print(f"\n{_c('36', '\u25b6  ' + msg)}")


def write_ok(msg: str) -> None:
    print(f"   {_c('32', '\u2714  ' + msg)}")


def write_warn(msg: str) -> None:
    print(f"   {_c('33', '\u26a0  ' + msg)}")


def write_fail(msg: str) -> None:
    print(f"   {_c('31', '\u2718  ' + msg)}")


def write_info(msg: str) -> None:
    print(f"   {_c('90', '\u2022  ' + msg)}")


# ─── Internal: run adb and return stdout+stderr combined ────────────────────────

def _adb(args: List[str], check: bool = False) -> str:
    proc = subprocess.run(
        ["adb", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed (exit {proc.returncode}): {proc.stdout}")
    return proc.stdout


def _adb_devices_lines() -> List[str]:
    """Return non-empty, non-offline lines from `adb devices` (header stripped)."""
    out = _adb(["devices"])
    lines = out.splitlines()[1:] if out.splitlines() else []
    return [ln for ln in lines if ln.strip() and "offline" not in ln]


def _find_usb_serial(lines: Optional[List[str]] = None) -> Optional[str]:
    lines = lines if lines is not None else _adb_devices_lines()
    for ln in lines:
        # TCP (Ethernet) devices look like "192.168.10.1:5555\tdevice"
        if re.match(r"^\d+\.\d+", ln):
            continue
        return re.split(r"\s", ln, maxsplit=1)[0]
    return None


# ─── AdbState ────────────────────────────────────────────────────────────────

@dataclass
class AdbState:
    usb_serial: Optional[str]
    eth_connected: bool
    uvc_mounted: bool
    best_adb: Optional[List[str]]
    state: str
    device_ip: str


def get_state(device_ip: str = "192.168.10.1") -> AdbState:
    """Probe both ADB transports and return the current Android BaseUnit ADB state."""
    adb_eth = f"{device_ip}:5555"

    lines = _adb_devices_lines()
    usb_serial = _find_usb_serial(lines)

    eth_connected = False
    eth_line = next((ln for ln in lines if adb_eth in ln), None)
    if eth_line and "offline" not in eth_line:
        ping = _adb(["-s", adb_eth, "shell", "echo ok"])
        eth_connected = "ok" in ping

    uvc_mounted = False
    best_adb: Optional[List[str]] = None
    if eth_connected:
        best_adb = ["-s", adb_eth]
        prop = _adb(["-s", adb_eth, "shell", "getprop vendor.usb.adb.uvc"]).strip()
        uvc_mounted = prop == "99"
    elif usb_serial:
        best_adb = ["-s", usb_serial]
        prop = _adb(["-s", usb_serial, "shell", "getprop vendor.usb.adb.uvc"]).strip()
        uvc_mounted = prop == "99"

    if usb_serial and not eth_connected and not uvc_mounted:
        state = "A"
    elif usb_serial and eth_connected and not uvc_mounted:
        state = "B"
    elif not usb_serial and eth_connected:
        state = "C"  # covers uvc_mounted True, and post-mount stream restart case
    else:
        state = "Unknown"

    return AdbState(
        usb_serial=usb_serial,
        eth_connected=eth_connected,
        uvc_mounted=uvc_mounted,
        best_adb=best_adb,
        state=state,
        device_ip=device_ip,
    )


def wait_usb_adb(timeout_sec: int = 120, polling_interval: int = 5) -> str:
    """Block until a USB ADB device appears, returning its serial."""
    write_step(f"Waiting for USB ADB device (timeout {timeout_sec}s)...")
    write_info("Connect USB-C cable to Android BaseUnit 'laptop-icon' port (USB-C1, no border).")

    elapsed = 0
    while elapsed < timeout_sec:
        serial = _find_usb_serial()
        if serial:
            write_ok(f"USB ADB device found: {serial}")
            return serial
        print(f"   \u23f3  ({elapsed}s) No USB ADB device yet...")
        time.sleep(polling_interval)
        elapsed += polling_interval

    raise TimeoutError(
        f"wait_usb_adb: timeout after {timeout_sec}s — no USB ADB device found.\n"
        "  Check: USB-C connected to laptop-icon port, device booted, USB debugging authorised."
    )


def connect_ethernet_adb(usb_serial: str = "", device_ip: str = "192.168.10.1") -> bool:
    """Bootstrap Ethernet ADB on Android BaseUnit using an already-established USB ADB session."""
    write_step(f"Bootstrapping Ethernet ADB ({device_ip})")

    if not usb_serial:
        usb_serial = _find_usb_serial()
        if not usb_serial:
            raise RuntimeError(
                "connect_ethernet_adb: no USB ADB device available. Run wait_usb_adb first."
            )
        write_info(f"Auto-detected USB serial: {usb_serial}")

    adb_usb = ["-s", usb_serial]
    adb_eth = f"{device_ip}:5555"

    _adb([*adb_usb, "root"])
    time.sleep(2)

    ip_cmd = f"ip addr add {device_ip}/24 dev eth0 2>/dev/null; true"
    _adb([*adb_usb, "shell", ip_cmd])

    _adb([*adb_usb, "shell", "setprop persist.adb.tcp.port 5555; setprop service.adb.tcp.port 5555"])
    write_info("TCP ADB port 5555 set")
    time.sleep(1)

    result = _adb(["connect", adb_eth])
    write_info(f"adb connect: {result.strip()}")
    time.sleep(1)

    ping = _adb(["-s", adb_eth, "shell", "echo ok"])
    if "ok" in ping:
        write_ok(f"Ethernet ADB responsive at {adb_eth}")
        return True

    write_warn("Ethernet ADB connection attempt succeeded but device did not respond.")
    write_info("Ensure host NIC has 192.168.10.x/24 address on the same LAN segment.")
    return False


def reboot(
    device_ip: str = "192.168.10.1",
    usb_serial: str = "",
    wait_for_recovery: bool = True,
    recovery_timeout_sec: int = 180,
) -> Optional[str]:
    """Reboot Android BaseUnit safely and optionally wait for USB + Ethernet ADB recovery."""
    write_step(f"Rebooting Android BaseUnit ({device_ip})")

    adb_args: List[str] = []
    if usb_serial:
        adb_args = ["-s", usb_serial]
        write_info(f"Using USB ADB: {usb_serial}")
    else:
        adb_eth = f"{device_ip}:5555"
        state = get_state(device_ip)
        if state.usb_serial:
            adb_args = ["-s", state.usb_serial]
            write_info(f"Using USB ADB: {state.usb_serial}")
        elif state.eth_connected:
            adb_args = ["-s", adb_eth]
            write_warn(f"USB ADB not available, using Ethernet ADB: {adb_eth}")
            write_warn("After reboot, USB ADB will reappear and Ethernet ADB will be lost.")
        else:
            raise RuntimeError(
                "reboot: no ADB transport available. Connect USB or ensure Ethernet ADB is alive."
            )

    out = _adb([*adb_args, "reboot"])
    for line in out.splitlines():
        if line.strip():
            write_info(line)
    write_ok("Reboot command sent")

    if not wait_for_recovery:
        write_info("wait_for_recovery not set — returning immediately.")
        return None

    write_info(f"Waiting for device to come back (USB ADB, up to {recovery_timeout_sec}s)...")
    time.sleep(5)  # give device a moment to actually start rebooting

    serial = wait_usb_adb(timeout_sec=recovery_timeout_sec, polling_interval=5)
    write_info(f"Device back on USB ADB: {serial}")

    write_info("Requesting root...")
    out = _adb(["-s", serial, "root"])
    for line in out.splitlines():
        if line.strip():
            write_info(line)
    time.sleep(3)

    # Re-detect USB serial post-root (adbd restart may change it)
    redetected = _find_usb_serial()
    if redetected:
        serial = redetected

    eth_ok = connect_ethernet_adb(usb_serial=serial, device_ip=device_ip)
    if eth_ok:
        write_ok(f"Recovery complete: USB={serial}  Eth={device_ip}:5555")
    else:
        write_warn("Recovery: USB ADB OK but Ethernet ADB not confirmed. Check host NIC config.")

    return serial


_RESTART_UVC_SH = """#!/bin/sh
GADGET_VIDEO=$(ls -la /proc/$(pgrep uvc_camera_forward 2>/dev/null | head -1)/fd 2>/dev/null \\
    | grep /dev/video | grep -v video0 | awk '{print $NF}' | head -1)
[ -z "$GADGET_VIDEO" ] && \\
    GADGET_VIDEO=$(ls /sys/class/video4linux/ | sort -t o -k2 -n | tail -1 | sed 's|^|/dev/|')
echo "gadget_device=$GADGET_VIDEO"
kill -9 $(pgrep uvc_camera_forward) 2>/dev/null
kill -9 $(pgrep uvc_still_frame)    2>/dev/null
sleep 3
nohup /data/local/tmp/uvc_camera_forward /dev/video0 $GADGET_VIDEO \\
    > /data/local/tmp/uvc_stream.log 2>&1 &
echo "restarted PID=$! -> $GADGET_VIDEO"
"""

_OSD_RESTART_SH = """GADGET_VIDEO=$(ls -la /proc/$(pgrep uvc_camera_forward 2>/dev/null | head -1)/fd 2>/dev/null \\
    | grep /dev/video | grep -v video0 | awk '{print $NF}' | head -1)
[ -z "$GADGET_VIDEO" ] && \\
    GADGET_VIDEO=$(ls /sys/class/video4linux/ | sort -t o -k2 -n | tail -1 | sed 's|^|/dev/|')
echo "gadget=$GADGET_VIDEO pid_before=$(pgrep uvc_camera_forward)"
kill $(pgrep uvc_camera_forward) 2>/dev/null
sleep 3
echo "pid_after=$(pgrep uvc_camera_forward)"
"""


def _push_inline_script(adb_target: List[str], script_body: str, remote_name: str) -> None:
    """Write script_body to a local temp file (LF line endings) and push it to the device."""
    fd, tmp_path = tempfile.mkstemp(suffix=".sh")
    try:
        with os.fdopen(fd, "w", newline="\n") as f:
            f.write(script_body)
        _adb([*adb_target, "push", tmp_path, f"/data/local/tmp/{remote_name}"])
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def mount(
    device_ip: str = "192.168.10.1",
    usb_serial: str = "",
    repo_root: str = "",
    skip_push: bool = False,
    macos_mode: bool = False,
    monitor_timeout_sec: int = 90,
) -> bool:
    """Safely mount the UVC/UAC/HID composite gadget on Android BaseUnit."""
    if not repo_root:
        repo_root = str(Path(__file__).resolve().parent.parent.parent)  # scripts/../.. -> repo root
        if not (Path(repo_root) / "setup_uvc.sh").exists():
            repo_root = str(Path(__file__).resolve().parent.parent)
    repo_path = Path(repo_root)

    adb_eth = f"{device_ip}:5555"
    device_tmp = "/data/local/tmp"

    write_step("mount — checking UVC state")

    state = get_state(device_ip)
    if not usb_serial and state.usb_serial:
        usb_serial = state.usb_serial
    adb_usb = ["-s", usb_serial] if usb_serial else []

    # ── Case 1: gadget already mounted (adb.uvc=99) ──────────────────────────
    if state.uvc_mounted:
        write_warn("UVC gadget already mounted (adb.uvc=99) — safe stream restart only.")
        write_info(f"USB ADB is dead; using Ethernet ADB: {adb_eth}")

        if not state.eth_connected:
            raise RuntimeError(
                f"mount: gadget mounted but Ethernet ADB unreachable at {adb_eth}.\n"
                "  USB ADB is also gone. Cannot recover without physical reboot."
            )

        adb_target = ["-s", adb_eth]
        _push_inline_script(adb_target, _RESTART_UVC_SH, "restart_uvc.sh")
        out = _adb([*adb_target, "shell", f"chmod +x {device_tmp}/restart_uvc.sh && {device_tmp}/restart_uvc.sh"])
        for line in out.splitlines():
            if line.strip():
                write_info(line)
        write_ok("Stream processes restarted (UDC untouched)")
        return True

    # ── Case 2: gadget not mounted — full setup_uvc.sh flow ──────────────────
    write_info("UVC gadget not mounted. Running full setup flow.")

    if not state.eth_connected:
        if not usb_serial:
            raise RuntimeError(
                "mount: no USB ADB device and Ethernet ADB not connected.\n"
                "  Run: serial = wait_usb_adb(); connect_ethernet_adb(usb_serial=serial)"
            )
        write_info("Ethernet ADB not connected — bootstrapping via USB ADB...")
        eth_ok = connect_ethernet_adb(usb_serial=usb_serial, device_ip=device_ip)
        if not eth_ok:
            write_warn("Ethernet ADB bootstrap did not confirm. Continuing anyway.")

    if not skip_push:
        write_step("Pushing files to device")
        files_to_push = [
            ("setup_uvc.sh", "setup_uvc.sh", False),
            ("uvc_camera_forward", "uvc_camera_forward", False),
            ("uvc_still_frame", "uvc_still_frame", False),
            ("hid_monitor", "hid_monitor", False),
            ("uac2_audio_bridge", "uac2_audio_bridge", False),
            ("uac2_monitor", "uac2_monitor", False),
            ("static_frame.jpg", "static_frame.jpg", True),
        ]
        for local_name, remote_name, optional in files_to_push:
            local_path = repo_path / local_name
            if not local_path.exists():
                if optional:
                    write_info(f"Optional file missing, skipping: {local_path}")
                    continue
                raise RuntimeError(
                    f"Required file not found: {local_path}.\n"
                    "  Build with: zig cc -target aarch64-linux-musl -static ..."
                )
            write_info(f"Pushing {local_name} ...")
            proc = subprocess.run(
                ["adb", *adb_usb, "push", str(local_path), f"{device_tmp}/{remote_name}"]
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Push failed: {local_path}")

        chmod_targets = " ".join(
            f"{device_tmp}/{r}" for _, r, opt in files_to_push if not opt
        )
        _adb([*adb_usb, "shell", f"chmod +x {chmod_targets} 2>/dev/null; true"])
        write_ok("Files pushed and permissions set")

    write_step("Launching setup_uvc.sh on device")
    write_info("Ensuring root access...")
    _adb([*adb_usb, "root"])
    time.sleep(2)
    write_warn("USB ADB will disconnect ~3-10s into setup (expected — UDC being reconfigured)")
    setup_cmd = f"nohup {device_tmp}/setup_uvc.sh > {device_tmp}/setup_uvc.log 2>&1 &"
    _adb([*adb_usb, "shell", setup_cmd])
    write_ok("setup_uvc.sh launched in background")

    write_step(f"Monitoring setup_uvc.log via Ethernet ADB ({adb_eth})")
    write_info("Waiting for USB drop then switching to Ethernet ADB...")
    time.sleep(8)

    elapsed = 0
    interval = 3
    last_log = ""
    done = False

    while elapsed < monitor_timeout_sec:
        devices_out = _adb(["devices"])
        if adb_eth not in devices_out:
            _adb(["connect", adb_eth])

        log = _adb(["-s", adb_eth, "shell", f"cat {device_tmp}/setup_uvc.log 2>/dev/null"])
        if log and log != last_log:
            new_part = log[len(last_log):] if log.startswith(last_log) else log
            for line in new_part.splitlines():
                if line.strip():
                    write_info(line)
            last_log = log
        if "DONE" in log:
            done = True
            break
        time.sleep(interval)
        elapsed += interval

    if done:
        write_ok("setup_uvc.sh completed — gadget mounted (State C)")
    else:
        write_warn(f"Monitor timeout after {monitor_timeout_sec}s. Last log:")
        for line in last_log.splitlines()[-5:]:
            write_info(line)

    return done


def set_osd(device_ip: str = "192.168.10.1", frames: int = 99999, disable: bool = False) -> None:
    """Enable, disable, or configure the OSD overlay on a running Android BaseUnit UVC stream."""
    if disable:
        frames = 0

    adb_eth = f"{device_ip}:5555"
    config_path = "/data/local/tmp/uvc_osd.conf"

    write_step(f"set_osd — OSD_DISPLAY_FRAMES={frames}")

    ping = _adb(["-s", adb_eth, "shell", "echo ok"])
    if "ok" not in ping:
        raise RuntimeError(
            f"set_osd: Ethernet ADB not reachable at {adb_eth}.\n"
            "  Run connect_ethernet_adb first, or check device state with get_state()."
        )

    _adb(["-s", adb_eth, "shell", f"echo 'OSD_DISPLAY_FRAMES={frames}' > {config_path}"])
    verify = _adb(["-s", adb_eth, "shell", f"cat {config_path}"]).strip()
    write_info(f"Config written: {verify}")

    write_info("Restarting uvc_camera_forward (watchdog will revive it in ~2s)...")
    adb_target = ["-s", adb_eth]
    _push_inline_script(adb_target, _OSD_RESTART_SH, "osd_restart.sh")
    out = _adb([*adb_target, "shell", "chmod +x /data/local/tmp/osd_restart.sh && /data/local/tmp/osd_restart.sh"])
    for line in out.splitlines():
        if line.strip():
            write_info(line)

    if frames == 0:
        write_ok("OSD disabled — takes effect on next stream start")
    elif frames >= 99999:
        write_ok("OSD always-on enabled — visible on next stream start")
    else:
        write_ok(f"OSD enabled for {frames} frames (~{round(frames / 30)}s at 30fps) per stream start")


def set_hid_support(mode: str, device_ip: str = "192.168.10.1") -> None:
    """Enable/disable the HID function via persist.barco.gadget.enable_hid (MTU3 QMU workaround)."""
    if mode not in ("Enable", "Disable"):
        raise ValueError("mode must be 'Enable' or 'Disable'")

    adb_target = f"{device_ip}:5555"

    write_step(f"CONFIGURING HID SUPPORT: {mode}")

    devices_out = _adb(["devices"])
    if adb_target not in devices_out:
        write_info(f"Connecting to {adb_target}...")
        _adb(["connect", adb_target])
        time.sleep(2)

    _adb(["-s", adb_target, "root"])
    time.sleep(2)

    serial = _adb(["-s", adb_target, "shell", "getprop ro.serialno"]).strip()
    write_info(f"Device serial: {serial}")

    if mode == "Disable":
        write_fail("DISABLING HID (MTU3 QMU workaround)")
        _adb(["-s", adb_target, "shell", "setprop persist.barco.gadget.enable_hid 0"])
        write_warn("Reason: Device-specific MTU3 QMU failure")
        write_info("  - Kernel panic when HID is active")
        write_info("  - Affects: Serial 1882001373 and similar devices")
        write_info("  - Solution: UVC + UAC2 only (no HID)")
    else:
        write_ok("ENABLING HID (normal operation)")
        _adb(["-s", adb_target, "shell", "setprop persist.barco.gadget.enable_hid 1"])
        write_warn("HID will provide:")
        write_info("  - Teams telemetry (Off-Hook/Mute LED)")
        write_info("  - UC App detection")
        write_info("  - Connected Device features")

    hid_enabled = _adb(["-s", adb_target, "shell", "getprop persist.barco.gadget.enable_hid"]).strip()
    write_step(f"Current setting: persist.barco.gadget.enable_hid = {hid_enabled}")
    write_warn("Change takes effect on next gadget setup (reboot or re-run setup_uvc.sh)")
    write_info("To apply now:")
    write_info("  1. Run: ./start-wired-roomdock.ps1 -Force  (or platform equivalent)")
    write_info("  2. Or reboot device")


@dataclass
class VideoDevice:
    path: str
    name: str


def list_video_devices(device_ip: str = "192.168.10.1") -> List[VideoDevice]:
    """List /dev/videoN nodes on the device with their V4L2 driver names.

    Distinguishes the physical USB camera capture node (e.g. a real webcam name)
    from the UVC *gadget* output node (name usually contains "UVC Gadget"/"webcam").
    """
    adb_target = f"{device_ip}:5555"
    out = _adb(["-s", adb_target, "shell", "ls /dev/video* 2>/dev/null"])
    devices: List[VideoDevice] = []
    for path in sorted(p.strip() for p in out.splitlines() if p.strip()):
        node = path.rsplit("/", 1)[-1]
        name = _adb(
            ["-s", adb_target, "shell", f"cat /sys/class/video4linux/{node}/name 2>/dev/null"]
        ).strip()
        devices.append(VideoDevice(path=path, name=name))
    return devices


@dataclass
class UsbDeviceInfo:
    sys_path: str
    vendor_id: str
    product_id: str
    manufacturer: str
    product: str


def list_usb_devices(device_ip: str = "192.168.10.1") -> List[UsbDeviceInfo]:
    """Enumerate USB devices on the Android BaseUnit via /sys/bus/usb/devices.

    Useful for identifying the brand/model of a newly attached camera (or any
    peripheral) without needing lsusb on the Android device.
    """
    adb_target = f"{device_ip}:5555"
    script = (
        'for d in /sys/bus/usb/devices/*; do '
        'if [ -f "$d/idVendor" ] && [ -f "$d/idProduct" ]; then '
        'v=$(cat "$d/idVendor"); p=$(cat "$d/idProduct"); '
        'mf=$(cat "$d/manufacturer" 2>/dev/null); pr=$(cat "$d/product" 2>/dev/null); '
        'if [ -n "$pr" ]; then echo "$d|$v|$p|$mf|$pr"; fi; '
        "fi; done"
    )
    out = _adb(["-s", adb_target, "shell", script])
    devices: List[UsbDeviceInfo] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) != 5:
            continue
        sys_path, vid, pid, mfr, product = parts
        devices.append(
            UsbDeviceInfo(
                sys_path=sys_path,
                vendor_id=vid.strip(),
                product_id=pid.strip(),
                manufacturer=mfr.strip(),
                product=product.strip(),
            )
        )
    return devices


def tail_log(device_ip: str = "192.168.10.1", remote_path: str = "/data/local/tmp/uvc_stream.log", lines: int = 20) -> str:
    """Tail a log file on the device (defaults to the UVC stream log)."""
    adb_target = f"{device_ip}:5555"
    return _adb(["-s", adb_target, "shell", f"tail -n {lines} {remote_path} 2>/dev/null"])


def grep_log(device_ip: str = "192.168.10.1", pattern: str = "", remote_path: str = "/data/local/tmp/uvc_stream.log", last: int = 10) -> str:
    """Grep a log file on the device for a pattern, returning the last N matches."""
    adb_target = f"{device_ip}:5555"
    return _adb(
        ["-s", adb_target, "shell", f"grep -F {pattern!r} {remote_path} 2>/dev/null | tail -n {last}"]
    )


def cat_file(device_ip: str = "192.168.10.1", remote_path: str = "") -> str:
    """Cat an arbitrary file on the device."""
    adb_target = f"{device_ip}:5555"
    return _adb(["-s", adb_target, "shell", f"cat {remote_path} 2>/dev/null"])


def pgrep(device_ip: str = "192.168.10.1", name: str = "") -> str:
    """Run `pgrep -l <name>` on the device to check if a process is running."""
    adb_target = f"{device_ip}:5555"
    return _adb(["-s", adb_target, "shell", f"pgrep -l {name} 2>/dev/null"])


def kill_process(device_ip: str = "192.168.10.1", name: str = "", signal: str = "-9") -> str:
    """Kill any process matching `name` on the device (used to clear stray/orphaned
    uvc_camera_forward processes holding /dev/video0 open after a crash)."""
    adb_target = f"{device_ip}:5555"
    return _adb(["-s", adb_target, "shell", f"pkill {signal} -f {name} 2>&1; echo done"])


def push_helper(local_path: str, device_ip: str = "192.168.10.1", remote_name: str = "") -> None:
    """Push a compiled diagnostic helper binary to /data/local/tmp and chmod +x it."""
    adb_target = f"{device_ip}:5555"
    name = remote_name or local_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    remote_path = f"/data/local/tmp/{name}"
    _adb(["-s", adb_target, "push", local_path, remote_path], check=True)
    _adb(["-s", adb_target, "shell", f"chmod 755 {remote_path}"])
    write_ok(f"Pushed {local_path} -> {remote_path}")


def list_camera_formats(device_ip: str = "192.168.10.1", video_node: str = "") -> str:
    """Enumerate all supported V4L2 frame sizes for MJPEG on the physical camera node.

    Tries `v4l2-ctl --list-formats-ext` first (if present on-device). Falls back to
    a raw ioctl probe via a tiny embedded busybox/toybox `v4l-utils` check, and if
    neither is available, reports that only the already-detected max (from the
    uvc_stream.log [CAP] line) is known.
    """
    adb_target = f"{device_ip}:5555"
    node = video_node
    if not node:
        # Best-effort: pick the first /dev/videoN whose name does NOT look like the
        # UVC gadget's own loopback/output node.
        for dev in list_video_devices(device_ip):
            name_lower = dev.name.lower()
            if "gadget" in name_lower or "uvc" in name_lower:
                continue
            node = dev.path
            break
    if not node:
        return "(no physical camera /dev/video node found)"

    has_v4l2ctl = _adb(
        ["-s", adb_target, "shell", "command -v v4l2-ctl 2>/dev/null || which v4l2-ctl 2>/dev/null"]
    ).strip()
    if has_v4l2ctl:
        return _adb(
            ["-s", adb_target, "shell", f"v4l2-ctl --list-formats-ext -d {node} 2>&1"]
        )

    # Fall back to our own tiny static helper (v4l2_enum_frames) if it has been
    # pushed to /data/local/tmp — see push_helper_and_run_enum().
    helper_present = _adb(
        ["-s", adb_target, "shell", "test -x /data/local/tmp/v4l2_enum_frames && echo yes"]
    ).strip()
    if helper_present == "yes":
        return _adb(
            ["-s", adb_target, "shell", f"/data/local/tmp/v4l2_enum_frames {node} MJPG 2>&1"]
        )

    return (
        f"(v4l2-ctl not present on device; cannot enumerate {node} directly)\n"
        "Falling back to the already-logged detection result — see:\n"
        "  python android_baseunit_adb.py grep-log \"[CAP]\""
    )


def identify_camera(device_ip: str = "192.168.10.1") -> Optional[UsbDeviceInfo]:
    """Best-effort identification of the physical USB camera attached to the device.

    Filters out Barco internal hubs and root xHCI controllers, returning the
    first remaining USB device that looks like a camera (has a "product" string
    and is not a hub).
    """
    for dev in list_usb_devices(device_ip):
        product_lower = dev.product.lower()
        if "hub" in product_lower or "xhci" in product_lower or "host controller" in product_lower:
            continue
        return dev
    return None


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Android BaseUnit ADB dual-transport management (portable Python CLI)."
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("state", help="Probe and print current ADB state")
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("wait-usb", help="Block until USB ADB device appears")
    sp.add_argument("--timeout", type=int, default=120)
    sp.add_argument("--interval", type=int, default=5)

    sp = sub.add_parser("connect-eth", help="Bootstrap Ethernet ADB via USB ADB")
    sp.add_argument("--usb-serial", default="")
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("reboot", help="Safe reboot with optional recovery wait")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--usb-serial", default="")
    sp.add_argument("--no-wait", action="store_true")
    sp.add_argument("--recovery-timeout", type=int, default=180)

    sp = sub.add_parser("mount", help="Safe UVC/UAC/HID gadget mount")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--usb-serial", default="")
    sp.add_argument("--repo-root", default="")
    sp.add_argument("--skip-push", action="store_true")
    sp.add_argument("--macos-mode", action="store_true")
    sp.add_argument("--monitor-timeout", type=int, default=90)

    sp = sub.add_parser("osd", help="Configure OSD overlay")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--frames", type=int, default=99999)
    sp.add_argument("--disable", action="store_true")

    sp = sub.add_parser("hid", help="Enable/disable HID function")
    sp.add_argument("mode", choices=["Enable", "Disable"])
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("list-video", help="List /dev/videoN nodes and their V4L2 names")
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("list-usb", help="List USB devices via /sys/bus/usb/devices")
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("camera-info", help="Identify the physical USB camera brand/model")
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("list-formats", help="Enumerate physical camera's supported V4L2 frame sizes (MJPEG)")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--video-node", default="")

    sp = sub.add_parser("push-helper", help="Push a compiled diagnostic helper binary to /data/local/tmp")
    sp.add_argument("local_path")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--remote-name", default="")

    sp = sub.add_parser("tail-log", help="Tail a log file on the device")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--path", default="/data/local/tmp/uvc_stream.log")
    sp.add_argument("--lines", type=int, default=20)

    sp = sub.add_parser("grep-log", help="Grep a log file on the device for a pattern")
    sp.add_argument("pattern")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--path", default="/data/local/tmp/uvc_stream.log")
    sp.add_argument("--last", type=int, default=10)

    sp = sub.add_parser("cat-file", help="Cat an arbitrary file on the device")
    sp.add_argument("remote_path")
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("pgrep", help="Check if a process is running on the device")
    sp.add_argument("name")
    sp.add_argument("--device-ip", default="192.168.10.1")

    sp = sub.add_parser("kill", help="Kill any process matching name (clear stray/orphaned processes)")
    sp.add_argument("name")
    sp.add_argument("--device-ip", default="192.168.10.1")
    sp.add_argument("--signal", default="-9")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "state":
            s = get_state(args.device_ip)
            print(s)
        elif args.command == "wait-usb":
            print(wait_usb_adb(args.timeout, args.interval))
        elif args.command == "connect-eth":
            ok = connect_ethernet_adb(args.usb_serial, args.device_ip)
            return 0 if ok else 1
        elif args.command == "reboot":
            reboot(args.device_ip, args.usb_serial, not args.no_wait, args.recovery_timeout)
        elif args.command == "mount":
            ok = mount(
                args.device_ip,
                args.usb_serial,
                args.repo_root,
                args.skip_push,
                args.macos_mode,
                args.monitor_timeout,
            )
            return 0 if ok else 1
        elif args.command == "osd":
            set_osd(args.device_ip, args.frames, args.disable)
        elif args.command == "hid":
            set_hid_support(args.mode, args.device_ip)
        elif args.command == "list-video":
            for dev in list_video_devices(args.device_ip):
                print(f"{dev.path}: {dev.name}")
        elif args.command == "list-usb":
            for dev in list_usb_devices(args.device_ip):
                print(
                    f"{dev.sys_path} VID:{dev.vendor_id} PID:{dev.product_id} "
                    f"MFR:{dev.manufacturer} PRODUCT:{dev.product}"
                )
        elif args.command == "camera-info":
            cam = identify_camera(args.device_ip)
            if cam:
                print(
                    f"Camera: {cam.product} (VID:{cam.vendor_id} PID:{cam.product_id}, "
                    f"MFR:{cam.manufacturer}) at {cam.sys_path}"
                )
            else:
                write_warn("No physical USB camera detected (only hubs/host controllers found).")
                return 1
        elif args.command == "list-formats":
            print(list_camera_formats(args.device_ip, args.video_node))
        elif args.command == "push-helper":
            push_helper(args.local_path, args.device_ip, args.remote_name)
        elif args.command == "tail-log":
            print(tail_log(args.device_ip, args.path, args.lines))
        elif args.command == "grep-log":
            print(grep_log(args.device_ip, args.pattern, args.path, args.last))
        elif args.command == "cat-file":
            print(cat_file(args.device_ip, args.remote_path))
        elif args.command == "pgrep":
            out = pgrep(args.device_ip, args.name)
            print(out if out.strip() else "(not running)")
        elif args.command == "kill":
            print(kill_process(args.device_ip, args.name, args.signal))
    except (RuntimeError, TimeoutError, ValueError) as exc:
        write_fail(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
