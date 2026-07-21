# Android BaseUnit USB Device Debug — SetupAPI Enumeration Skill

This skill enumerates **all present USB devices** on Windows using `SetupAPI` / `CfgMgr32` (no subprocess, no WMI) and filters for **VID:046D** (Logitech / Android BaseUnit Wired RoomDock). Use this to verify that Windows correctly recognises the Android BaseUnit composite gadget and all expected interface nodes are present.

---

## 1. Trigger Conditions

Invoke this skill when the user reports any of:

- "Android BaseUnit not showing up in Windows"
- "Camera / speakerphone / HID missing in Device Manager"
- "USB enumeration failed"
- "VID/PID not matching expected 046D:087C"

---

## 2. How to Run

**Windows only** — requires Python 3.8+ (no pip dependencies, pure `ctypes`).

```powershell
# From the gadget repo root
python scripts\debug_usb.py
```

Or from any directory if the script is on PATH:

```powershell
python "C:\path\to\scripts\debug_usb.py"
```

---

## 3. Output Interpretation

Each block represents one matching device node under `VID_046D`:

```
  hw=USB\VID_046D&PID_087C&MI_00\...
  name=Android BaseUnit Wired RoomDock Camera  CR=0  status=0x0000000C  problem=0
  Col=True  MI_00=True  MI_02=False  MI_03=False
```

| Field | Meaning |
|-------|---------|
| `hw=` | Raw Hardware ID string — check VID, PID, MI_xx suffix |
| `name=` | Windows friendly name from the INF / driver |
| `CR=0` | CfgMgr32 return code — 0 = success |
| `status=0x0000000C` | Device node status flags (CM_Get_DevNode_Status) |
| `problem=0` | Problem code — 0 = OK; non-zero = driver/config error |
| `Col=True` | Device node has `&Col` (collection) suffix — composite sub-device |
| `MI_00/MI_02/MI_03` | Interface presence flags |

**Expected interface nodes for Android BaseUnit g1:**

| Interface | MI | Windows role |
|-----------|-----|-------------|
| UVC camera | `MI_00` | "Android BaseUnit Wired RoomDock Camera" |
| HID telemetry | `MI_02` | HidUsb / hidtelephonydriver |
| UAC2 speakerphone | `MI_03` | "Android BaseUnit Wired RoomDock Speakerphone" |

**Common status flags** (`status` field):
- `0x00000008` = DN_DRIVER_LOADED — driver bound
- `0x00000004` = DN_STARTED — device started
- `0x0000000C` = DN_DRIVER_LOADED | DN_STARTED — fully operational ✅
- Any `problem > 0` → device error (e.g., 28 = no driver, 43 = driver failure)

---

## 4. Troubleshooting Guide

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Zero `VID_046D` matches | Gadget not mounted or wrong VID/PID | Check `setup_uvc.sh` ran, verify `idVendor=0x046D` in ConfigFS |
| Only MI_00 present | HID or UAC2 function not linked in g1 | Check `ln -s` symlinks in ConfigFS `configs/b.1/` |
| `problem=28` | No INF driver installed | Install Logitech C300RS `.inf` or run `pnputil` |
| `problem=43` | Driver-reported failure | Check Windows Event Log → System for usbhub3/usbvideo errors |
| `Col=False` on MI_00 | Composite descriptor wrong | Check IAD in `setup_uvc.sh` — UVC must be first function |

---

## 5. Script Architecture

```
debug_usb.py
  └─ SetupDiGetClassDevsW(DIGCF_PRESENT | DIGCF_ALLCLASSES)
       └─ SetupDiEnumDeviceInfo() loop
            ├─ _reg_prop(SPDRP_HARDWAREID)   → hw ID filter on VID_046D
            ├─ _reg_prop(SPDRP_FRIENDLYNAME) → human name
            └─ CM_Get_DevNode_Status()       → status + problem code
```

No external pip packages required. Script exits after one enumeration pass.

---

## 6. Related Skills

- [`skill-wasapi-capture-debug`](../skill-wasapi-capture-debug/SKILL.md) — verify UAC2 capture endpoint visible to WASAPI
- [`skill-usb-gadget-monitor`](../skill-usb-gadget-monitor/SKILL.md) — real-time GUI combining USB + WASAPI + UVC status
