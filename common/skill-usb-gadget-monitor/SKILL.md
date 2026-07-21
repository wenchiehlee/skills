# Android BaseUnit RoomDock Status Monitor Skill

Real-time **Tkinter GUI dashboard** for the Android BaseUnit Wired RoomDock (MT8395) on Windows. Combines USB device enumeration, UVC stream status, UAC2 call state, display topology detection, UC app presence detection, and bidirectional HID vendor report exchange — all in a single always-on-top window updated every 2 seconds.

---

## 1. Trigger Conditions

Invoke this skill when the user needs to:

- Monitor Android BaseUnit RoomDock health in real time during a meeting
- Diagnose why camera/speakerphone is not working in Teams / Zoom / Webex
- Verify display mode (single / clone / extend) is correctly detected
- Inspect HID telemetry reports flowing between Android BaseUnit and Windows
- Observe UVC stream resolution/fps as host app changes settings

---

## 2. How to Run

**Windows only** — requires Python 3.8+, `tkinter` (bundled with CPython on Windows), no pip install needed.

```powershell
# From the gadget repo root
python scripts\android_baseunit_monitor.py
```

The window opens immediately. Data refreshes every 2 seconds. Close the window to exit.

---

## 3. GUI Panel Overview

```
┌────────────────────────────────────────┐
│  Android BaseUnit Wired RoomDock Monitor          │
├─────────────────┬──────────────────────┤
│  USB Status     │  Display             │
│  UVC Stream     │  2 display(s) — Extend│
│  Call State     │                      │
├─────────────────┴──────────────────────┤
│  UC Apps: Teams ✔  Zoom ✗  Webex ✗    │
│  Shared display: ✔ Secondary (Extend)  │
├────────────────────────────────────────┤
│  Last updated: 14:32:07                │
└────────────────────────────────────────┘
```

| Panel | Data Source | What it Shows |
|-------|-------------|---------------|
| USB Status | SetupAPI (no WMI) | Android BaseUnit VID:046D device node present + problem code |
| UVC Stream | DirectShow graph + Registry | Current width × height @ fps, streaming active flag |
| Call State | WASAPI IAudioSessionManager2 | MIC_ACTIVE / SPK_ONLY / IDLE |
| Display | QueryDisplayConfig (user32) | # active paths + topology (Internal/Clone/Extend/External) |
| UC Apps | Process enumeration | Teams / Zoom / Webex process presence |
| Shared display | DRM sysfs / heuristic | Whether laptop is sharing its screen via Android BaseUnit DP Alt-Mode |
| HID Reports | HID MI_02 CreateFile | Vendor Input Report 0x10 (device→host stream status) |

---

## 4. HID Vendor Report Protocol

The monitor reads/writes **HID Vendor Reports** on the Android BaseUnit HID interface (`MI_02`, `hidtelephonydriver` bypassed via raw `CreateFile`):

### Report 0x10 — Device → Host (Input Report, 16 bytes)
Sent by `hid_monitor` daemon on Android BaseUnit every 2 s:

```
Byte 0:    0x10 (Report ID)
Bytes 1-2: width  (uint16 LE)
Bytes 3-4: height (uint16 LE)
Byte 5:    fps (uint8)
Byte 6:    flags  (bit0 = streaming active)
Bytes 7-15: reserved
```

### Report 0x11 — Host → Device (Output Report, 16 bytes)
Sent by the monitor to push display topology data to Android BaseUnit (for OSD overlay):

```
Byte 0:    0x11 (Report ID)
Byte 1:    display_count (uint8, 1–4)
Byte 2:    topology_id   (uint8: 1=Internal, 2=Clone, 4=Extend, 8=External)
Bytes 3-15: reserved (0x00)
```

**Send interval:** Every 2 s in the refresh loop, if HID path is open.  
**Transport:** `WriteFile` on the raw HID device path — bypasses `hidtelephonydriver` UMDF stack.

---

## 5. Display Topology Detection

Uses two Windows API calls, both via `ctypes` with no subprocess:

1. `GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS)` + `QueryDisplayConfig` →  
   `np.value` = number of **physical active display paths** (correct even in Clone, which presents 2 paths despite 1 logical display)

2. `GetDisplayConfigBufferSizes(QDC_DATABASE_CURRENT)` + `QueryDisplayConfig(..., &topologyId)` →  
   `topologyId`: 1=InternalOnly, 2=Clone, 4=Extend, 8=ExternalOnly

| TopologyId | count | Meaning |
|------------|-------|---------|
| 1 | 1 | Laptop screen only, no Android BaseUnit DP |
| 2 | 2 | Laptop + Android BaseUnit cloned |
| 4 | 2 | Laptop + Android BaseUnit extended |
| 8 | 1 | Android BaseUnit only (laptop lid closed) |

---

## 6. UVC Stream Status Detection

UVC resolution and fps are read without intercepting the camera feed:

1. **DirectShow** — `IFilterGraph2::EnumFilters()` scans for the Android BaseUnit camera filter; `IAMStreamConfig::GetFormat()` returns the active `VIDEOINFOHEADER`
2. **Registry fallback** — `HKCU\Software\Microsoft\Windows\CurrentVersion\VideoSettings\<device GUID>` stores last-used resolution

The streaming flag comes from HID Report 0x10 byte 6 bit 0 (pushed from device).

---

## 7. Architecture

```
android_baseunit_monitor.py
  ├─ MainWindow (Tkinter, main thread)
  │     └─ after(0, _update_ui)  ← thread-safe UI update
  │
  ├─ refresh thread (2 s loop)
  │     ├─ get_display_info()          → QueryDisplayConfig
  │     ├─ get_usb_status()            → SetupAPI enumeration
  │     ├─ get_wasapi_call_state()     → WASAPI IAudioSessionManager2
  │     ├─ get_uc_app_status()         → process list
  │     └─ get_shared_display_status() → heuristic on display count+topology
  │
  ├─ uvc_loop thread (2 s loop)
  │     └─ get_uvc_stream_status()     → DirectShow + registry
  │
  └─ hid_reader thread (blocking ReadFile)
        └─ find_android_baseunit_hid_path()       → HidD_GetHidGuid + SetupDi
             └─ CreateFile() → ReadFile() → Report 0x10 decode
                           ← WriteFile() → Report 0x11 (display topology push)
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Window doesn't open | `tkinter` missing | Use official CPython from python.org (not conda/Homebrew) |
| USB status blank | SetupAPI returning 0 matches | Gadget not mounted — run `setup_uvc.sh` first |
| Call state always IDLE | WASAPI query failed | Run as standard user; check UAC2 endpoint active |
| HID panel empty | HID MI_02 not found | Check `problem=0` in `skill-Android BaseUnit-usb-debug`; ensure no exclusive driver locked it |
| UVC stream shows 0×0 | DirectShow query failed | Ensure Teams/Zoom opened the camera first |
| Display shows "Query failed" | Running on non-display session (RDP?) | Must run on physical console session |

---

## 9. Related Skills

- [`skill-usb-gadget-debug`](../skill-usb-gadget-debug/SKILL.md) — lightweight USB node check (no GUI)
- [`skill-wasapi-capture-debug`](../skill-wasapi-capture-debug/SKILL.md) — detailed WASAPI capture endpoint dump
