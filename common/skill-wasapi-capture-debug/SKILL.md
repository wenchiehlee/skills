# Android BaseUnit WASAPI Audio Debug — Capture Endpoint Enumeration Skill

This skill enumerates **all Windows WASAPI capture endpoints** (microphones) using raw COM vtable calls via `ctypes` (no subprocess, no WMI, no `pycaw`). Use it to verify that the Android BaseUnit UAC2 speakerphone is visible as a Windows capture device and that audio sessions are active when expected.

---

## 1. Trigger Conditions

Invoke this skill when the user reports any of:

- "Teams/Zoom can't see the Android BaseUnit microphone"
- "UAC2 audio not working on Windows"
- "Speakerphone not appearing in Sound settings"
- "WASAPI capture endpoint missing after gadget mount"

---

## 2. How to Run

**Windows only** — requires Python 3.8+ (no pip dependencies, pure `ctypes` COM).

```powershell
# From the gadget repo root
python scripts\debug_wasapi.py
```

---

## 3. Output Interpretation

Each block represents one audio capture endpoint:

```
[2] ACTIVE        Android BaseUnit Wired RoomDock Speakerphone
     InstanceId: SWD\MMDEVAPI\{0.0.1.00000000}...
     EndpointId: {0.0.1.00000000}.{guid}...
     ASM2 hr=0x00000000  GetSessionEnum hr=0x00000000  sessions=1
       session[0] ACTIVE
```

| Field | Meaning |
|-------|---------|
| `[N] ACTIVE` | Endpoint index and Windows device state |
| Friendly name | As reported by Windows audio subsystem |
| `InstanceId` | Stable identifier used by apps to select endpoint |
| `EndpointId` | COM endpoint GUID used by WASAPI internals |
| `ASM2 hr=0x00000000` | IAudioSessionManager2 activation — 0 = success |
| `sessions=N` | Number of active audio sessions on this endpoint |
| `session[N] ACTIVE` | An app is actively using this endpoint |

**Device states:**

| State | Meaning |
|-------|---------|
| `ACTIVE` | Endpoint present and enabled — apps can use it |
| `DISABLED` | Present but manually disabled in Sound settings |
| `NOTPRESENT` | Endpoint removed (gadget unmounted) |
| `UNPLUGGED` | Hardware removed but driver still registered |

---

## 4. Troubleshooting Guide

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Android BaseUnit speakerphone not listed | UAC2 function not in g1 or UDC unbound | Re-run `setup_uvc.sh`; check `f_uac2` in ConfigFS |
| State = `DISABLED` | User or policy disabled it in Sound settings | Re-enable in Windows Sound → Recording |
| State = `ACTIVE` but `sessions=0` | Device visible but no app opened it | Normal if no UC app running |
| `CoCreateInstance hr=0x80040154` | COM registration error | Run as regular user, not admin; check `ole32.dll` |
| `EnumAudioEndpoints hr≠0` | COM initialisation failed | Ensure `CoInitializeEx` called before use |

---

## 5. UAC2 Audio Path (Android BaseUnit Architecture)

```
Android BaseUnit device (MT8395)
  └─ f_uac2.usb0 (function driver)
       ├─ ISO OUT endpoint → speaker playback
       └─ ISO IN  endpoint → microphone capture

Windows UAC2 class driver (usbaudio2.sys)
  └─ IMMDeviceEnumerator
       └─ eCapture collection
            └─ "Android BaseUnit Wired RoomDock Speakerphone"  ← this script checks here
                 └─ IAudioSessionManager2
                      └─ Active sessions (Teams/Zoom holding mic open)
```

The Android BaseUnit gadget must be mounted and the UDC bound before the endpoint appears. Unmounting causes Windows to mark it `NOTPRESENT`.

---

## 6. Script Architecture

```
debug_wasapi.py
  └─ CoCreateInstance(CLSID_MMDeviceEnumerator, IID_IMMDeviceEnumerator)
       └─ IMMDeviceEnumerator::EnumAudioEndpoints(eCapture, ALL)
            └─ for each IMMDevice:
                 ├─ GetState()          → ACTIVE / DISABLED / ...
                 ├─ GetId()             → EndpointId string
                 ├─ OpenPropertyStore() → FriendlyName, InstanceId
                 └─ (ACTIVE only) Activate(IAudioSessionManager2)
                      └─ GetSessionEnumerator() → session count + states
```

All COM vtable calls use manual `WINFUNCTYPE` dispatch — no dependency on `comtypes`, `pycaw`, or any third-party package.

---

## 7. Related Skills

- [`skill-usb-gadget-debug`](../skill-usb-gadget-debug/SKILL.md) — verify USB device nodes present in Device Manager
- [`skill-usb-gadget-monitor`](../skill-usb-gadget-monitor/SKILL.md) — real-time GUI combining USB + WASAPI + UVC status
