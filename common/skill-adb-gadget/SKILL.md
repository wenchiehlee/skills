# ADB Gadget Dual-Transport Management Skill

PowerShell module (`AndroidBaseUnitAdb.psm1`) for managing **dual ADB transports — USB + Ethernet** — on an embedded Android device that exposes a USB composite gadget (UVC camera + UAC2 speakerphone + HID). When the gadget mounts on USB-C, the USB ADB path disappears and only Ethernet ADB survives. This skill encodes all state transitions and safety checks.

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

```powershell
Import-Module .\scripts\AndroidBaseUnitAdb.psm1
```

Requires PowerShell 5.1+. `adb` must be on PATH.

---

## 3. Exported Functions

### `Get-AndroidBaseUnitAdbState`
Probe both transports and return current state object.

```powershell
$s = Get-AndroidBaseUnitAdbState -DeviceIP "192.168.10.1"
$s.State        # "A" | "B" | "C" | "Unknown"
$s.UsbSerial    # "1882001373" or $null
$s.EthConnected # $true/$false
$s.UvcMounted   # $true if vendor.usb.adb.uvc == "99"
$s.BestAdb      # "-s <id>" string for the preferred transport
```

### `Wait-AndroidBaseUnitUsbAdb`
Block until a USB ADB device appears. Returns serial string.

```powershell
$serial = Wait-AndroidBaseUnitUsbAdb -TimeoutSec 120 -PollingInterval 5
```

### `Connect-AndroidBaseUnitEthernetAdb`
Bootstrap Ethernet ADB using an existing USB ADB session.  
Assigns IP to `eth0`, sets `persist.adb.tcp.port 5555`, calls `adb connect`.

```powershell
$ok = Connect-AndroidBaseUnitEthernetAdb -UsbSerial $serial -DeviceIP "192.168.10.1"
```

### `Invoke-AndroidBaseUnitReboot`
Safe reboot. By default waits for USB ADB to reappear, requests root, and re-bootstraps Ethernet ADB.

```powershell
# Reboot and wait for full recovery
$serial = Invoke-AndroidBaseUnitReboot -DeviceIP "192.168.10.1"

# Fire-and-forget reboot
Invoke-AndroidBaseUnitReboot -WaitForRecovery:$false
```

### `Invoke-AndroidBaseUnitMount`
State-aware gadget mount. Reads `vendor.usb.adb.uvc` first:

- **State C (already mounted, `adb.uvc=99`):** Kills and restarts stream processes over Ethernet ADB only — **never** re-runs `setup_uvc.sh` (kernel panic risk).
- **State A/B (not mounted):** Ensures Ethernet ADB is up, optionally pushes binaries, launches `setup_uvc.sh` in background, monitors log until `DONE`.

```powershell
# Full mount from scratch
$serial = Wait-AndroidBaseUnitUsbAdb
Connect-AndroidBaseUnitEthernetAdb -UsbSerial $serial
Invoke-AndroidBaseUnitMount -RepoRoot "C:\repo\gadget"

# macOS host mode (sets streaming_maxburst=0)
Invoke-AndroidBaseUnitMount -MacOSMode

# Restart streams only (gadget already mounted)
Invoke-AndroidBaseUnitMount -SkipPush
```

---

## 4. HID Function Control (`Configure-HidSupport.ps1`)

Separate helper to enable/disable HID in the gadget configuration via `persist.barco.gadget.enable_hid`. Used on devices with MTU3 QMU HID kernel panic issue.

```powershell
. .\scripts\Configure-HidSupport.ps1

# Disable HID on affected device (default IP)
Set-HidSupport -Mode Disable

# Enable HID on a specific device
Set-HidSupport -Mode Enable -DeviceIP "192.168.20.5"
```

Change takes effect on next gadget setup (reboot or re-run of `setup_uvc.sh`).

| Mode | `persist.barco.gadget.enable_hid` | Gadget functions |
|------|-----------------------------------|-----------------|
| Enable | `1` | UVC + UAC2 + HID |
| Disable | `0` | UVC + UAC2 only (MTU3 QMU workaround) |

---

## 5. Typical Workflow

```powershell
Import-Module .\scripts\AndroidBaseUnitAdb.psm1

# 1. Check current state
$s = Get-AndroidBaseUnitAdbState
Write-Host "State: $($s.State)"

# 2. If State A — bootstrap Ethernet before mount
if ($s.State -eq "A") {
    $serial = Wait-AndroidBaseUnitUsbAdb
    Connect-AndroidBaseUnitEthernetAdb -UsbSerial $serial
}

# 3. Mount gadget (or restart streams if already mounted)
Invoke-AndroidBaseUnitMount -RepoRoot "C:\repo\gadget"

# 4. Reboot and recover both paths
$serial = Invoke-AndroidBaseUnitReboot
```

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Wait-AndroidBaseUnitUsbAdb` times out | USB cable not connected to USB-C1 (laptop-icon port) | Check cable; device must be booted |
| `Connect-AndroidBaseUnitEthernetAdb` returns `$false` | Host NIC has no 192.168.10.x/24 address | Assign static IP to host NIC on same subnet |
| `Invoke-AndroidBaseUnitMount` skips `setup_uvc.sh` | `vendor.usb.adb.uvc=99` — gadget already mounted | Expected — streams will be restarted safely |
| Kernel panic after mount attempt | `setup_uvc.sh` ran while gadget was mounted | Always check `Get-AndroidBaseUnitAdbState` first |
| USB ADB lost during mount | USB-C1 taken over by UVC gadget (State B→C) | Expected — Ethernet ADB takes over |

---

## 7. Related Skills

- [`skill-usb-gadget-debug`](../skill-usb-gadget-debug/SKILL.md) — verify USB device nodes on Windows host
- [`skill-usb-gadget-monitor`](../skill-usb-gadget-monitor/SKILL.md) — real-time status monitor on Windows host
