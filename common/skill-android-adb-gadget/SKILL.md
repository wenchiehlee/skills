# ADB Gadget Dual-Transport Management Skill

Portable Python module (`android_baseunit_adb.py`, Python 3.8+, only external dependency is `adb` on PATH) for managing **dual ADB transports — USB + Ethernet** — on an embedded Android device that exposes a USB composite gadget (UVC camera + UAC2 speakerphone + HID). Works identically on **Windows, macOS, and Linux**. When the gadget mounts on USB-C, the USB ADB path disappears and only Ethernet ADB survives. This skill encodes all state transitions and safety checks.

---

## 1. ADB State Machine

```
State A  (fresh boot / after reboot)
    USB ADB  ✔  (device serial visible in `adb devices`)
    Eth ADB  ✘  (not yet configured)

State B  (Ethernet bootstrapped, gadget not yet mounted)
    USB ADB  ✔  (still alive)
    Eth ADB  ✔  (192.168.10.1:5555)

State C  (UVC/UAC gadget mounted — normal running state)
    USB ADB  ✘  (USB-C1 taken over by gadget functions)
    Eth ADB  ✔  (only remaining path)
```

**Critical transition rules:**
- Ethernet ADB **must** be bootstrapped via USB ADB (A→B) **before** the gadget mounts (B→C).
- `setup_uvc.sh` **must not** run when `vendor.usb.adb.uvc=99` (gadget already mounted) — UDC unbind with open gadget fd triggers kernel panic.
- After any reboot, device always lands in State A — USB ADB must be re-awaited.

---

## 2. Import

```python
import sys
sys.path.insert(0, "./scripts")
from android_baseunit_adb import get_state, wait_usb_adb, connect_ethernet_adb, \
    reboot, mount, set_osd, set_hid_support
```

Or use it as a standalone CLI (no import needed):

```bash
python scripts/android_baseunit_adb.py state
```

Requires Python 3.8+. `adb` must be on PATH. No pip packages required.

---

## 3. Exported Functions

### `get_state(device_ip="192.168.10.1") -> AdbState`
Probe both transports and return current state object.

```python
s = get_state("192.168.10.1")
s.state          # "A" | "B" | "C" | "Unknown"
s.usb_serial     # "1882001373" or None
s.eth_connected  # True/False
s.uvc_mounted    # True if vendor.usb.adb.uvc == "99"
s.best_adb       # ["-s", "<id>"] args list for the preferred transport
```

CLI: `python scripts/android_baseunit_adb.py state --device-ip 192.168.10.1`

### `wait_usb_adb(timeout_sec=120, polling_interval=5) -> str`
Block until a USB ADB device appears. Returns serial string.

```python
serial = wait_usb_adb(timeout_sec=120, polling_interval=5)
```

CLI: `python scripts/android_baseunit_adb.py wait-usb --timeout 120`

### `connect_ethernet_adb(usb_serial="", device_ip="192.168.10.1") -> bool`
Bootstrap Ethernet ADB using an existing USB ADB session.
Assigns IP to `eth0`, sets `persist.adb.tcp.port 5555`, calls `adb connect`.

```python
ok = connect_ethernet_adb(usb_serial=serial, device_ip="192.168.10.1")
```

CLI: `python scripts/android_baseunit_adb.py connect-eth --usb-serial 1882001373`

### `reboot(device_ip="192.168.10.1", usb_serial="", wait_for_recovery=True, recovery_timeout_sec=180) -> str | None`
Safe reboot. By default waits for USB ADB to reappear, requests root, and re-bootstraps Ethernet ADB.

```python
# Reboot and wait for full recovery
serial = reboot(device_ip="192.168.10.1")

# Fire-and-forget reboot
reboot(wait_for_recovery=False)
```

CLI: `python scripts/android_baseunit_adb.py reboot --no-wait`

### `mount(device_ip="192.168.10.1", usb_serial="", repo_root="", skip_push=False, macos_mode=False, monitor_timeout_sec=90) -> bool`
State-aware gadget mount. Reads `vendor.usb.adb.uvc` first:

- **State C (already mounted, `adb.uvc=99`):** Kills and restarts stream processes over Ethernet ADB only — **never** re-runs `setup_uvc.sh` (kernel panic risk).
- **State A/B (not mounted):** Ensures Ethernet ADB is up, optionally pushes binaries, launches `setup_uvc.sh` in background, monitors log until `DONE`.

```python
# Full mount from scratch
serial = wait_usb_adb()
connect_ethernet_adb(usb_serial=serial)
mount(repo_root="/path/to/gadget")

# macOS host mode (sets streaming_maxburst=0)
mount(macos_mode=True)

# Restart streams only (gadget already mounted)
mount(skip_push=True)
```

CLI: `python scripts/android_baseunit_adb.py mount --repo-root /path/to/gadget`

---

## 4. HID Function Control (`set_hid_support`)

Enable/disable HID in the gadget configuration via `persist.barco.gadget.enable_hid`. Used on devices with MTU3 QMU HID kernel panic issue.

```python
from android_baseunit_adb import set_hid_support

# Disable HID on affected device (default IP)
set_hid_support("Disable")

# Enable HID on a specific device
set_hid_support("Enable", device_ip="192.168.20.5")
```

CLI: `python scripts/android_baseunit_adb.py hid Disable --device-ip 192.168.20.5`

Change takes effect on next gadget setup (reboot or re-run of `setup_uvc.sh`).

| Mode | `persist.barco.gadget.enable_hid` | Gadget functions |
|------|-----------------------------------|-----------------|
| Enable | `1` | UVC + UAC2 + HID |
| Disable | `0` | UVC + UAC2 only (MTU3 QMU workaround) |

---

## 5. Typical Workflow

```python
from android_baseunit_adb import get_state, wait_usb_adb, connect_ethernet_adb, mount, reboot

# 1. Check current state
s = get_state()
print(f"State: {s.state}")

# 2. If State A — bootstrap Ethernet before mount
if s.state == "A":
    serial = wait_usb_adb()
    connect_ethernet_adb(usb_serial=serial)

# 3. Mount gadget (or restart streams if already mounted)
mount(repo_root="/path/to/gadget")

# 4. Reboot and recover both paths
serial = reboot()
```

Equivalent one-liners via CLI:

```bash
python scripts/android_baseunit_adb.py state
python scripts/android_baseunit_adb.py wait-usb
python scripts/android_baseunit_adb.py connect-eth --usb-serial <serial>
python scripts/android_baseunit_adb.py mount --repo-root .
python scripts/android_baseunit_adb.py reboot
```

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `wait_usb_adb` times out | USB cable not connected to USB-C1 (laptop-icon port) | Check cable; device must be booted |
| `connect_ethernet_adb` returns `False` | Host NIC has no 192.168.10.x/24 address | Assign static IP to host NIC on same subnet |
| `mount` skips `setup_uvc.sh` | `vendor.usb.adb.uvc=99` — gadget already mounted | Expected — streams will be restarted safely |
| Kernel panic after mount attempt | `setup_uvc.sh` ran while gadget was mounted | Always check `get_state()` first |
| USB ADB lost during mount | USB-C1 taken over by UVC gadget (State B→C) | Expected — Ethernet ADB takes over |

---

## 7. Related Skills

- [`skill-usb-gadget-debug`](../skill-usb-gadget-debug/SKILL.md) — verify USB device nodes on Windows host
- [`skill-usb-gadget-monitor`](../skill-usb-gadget-monitor/SKILL.md) — real-time status monitor on Windows host
