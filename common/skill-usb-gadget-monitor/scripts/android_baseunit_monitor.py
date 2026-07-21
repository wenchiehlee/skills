#!/usr/bin/env python3
"""Android BaseUnit Wired RoomDock Status Monitor — Windows"""

import ctypes
import ctypes.wintypes as wt
import struct
import subprocess
import tkinter as tk
import threading
import time
import winreg

# ── Display topology via QueryDisplayConfig ───────────────────────────────────

_QDC_ONLY_ACTIVE_PATHS = 0x00000002
_QDC_DATABASE_CURRENT  = 0x00000004
_TOPO_MAP = {1: "Internal Only", 2: "Clone", 4: "Extend", 8: "External Only"}

def get_display_info():
    u32 = ctypes.windll.user32
    # Use ONLY_ACTIVE_PATHS: counts physical display paths (correct even in Clone mode)
    np  = ctypes.c_uint32(0)
    nm  = ctypes.c_uint32(0)
    ret = u32.GetDisplayConfigBufferSizes(_QDC_ONLY_ACTIVE_PATHS, ctypes.byref(np), ctypes.byref(nm))
    if ret != 0:
        return u32.GetSystemMetrics(80), "Query failed"
    pa  = (ctypes.c_byte * (72 * max(np.value, 1)))()
    ma  = (ctypes.c_byte * (64 * max(nm.value, 1)))()
    ret = u32.QueryDisplayConfig(_QDC_ONLY_ACTIVE_PATHS,
                                  ctypes.byref(np), pa, ctypes.byref(nm), ma, None)
    if ret != 0:
        return u32.GetSystemMetrics(80), "Query failed"
    # np.value is updated to actual active path count = number of physical displays
    count = np.value
    # Topology from database (separate query)
    np2 = ctypes.c_uint32(0); nm2 = ctypes.c_uint32(0)
    tid = ctypes.c_uint32(0)
    if u32.GetDisplayConfigBufferSizes(_QDC_DATABASE_CURRENT, ctypes.byref(np2), ctypes.byref(nm2)) == 0:
        pa2 = (ctypes.c_byte * (72 * max(np2.value, 1)))()
        ma2 = (ctypes.c_byte * (64 * max(nm2.value, 1)))()
        u32.QueryDisplayConfig(_QDC_DATABASE_CURRENT,
                               ctypes.byref(np2), pa2, ctypes.byref(nm2), ma2, ctypes.byref(tid))
    return count, _TOPO_MAP.get(tid.value, f"Unknown ({tid.value})")

# ── USB device status via SetupDi (no subprocess, no WMI) ────────────────────

_setupapi = ctypes.WinDLL("setupapi")
_cfgmgr   = ctypes.WinDLL("cfgmgr32")

DIGCF_PRESENT    = 0x00000002
DIGCF_ALLCLASSES = 0x00000004
SPDRP_HARDWAREID   = 1
SPDRP_FRIENDLYNAME = 12
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize",   wt.DWORD),
        ("ClassGuid", ctypes.c_byte * 16),
        ("DevInst",  wt.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]

# Explicit restype/argtypes — critical on 64-bit: HDEVINFO is pointer-sized,
# default c_int restype would truncate the handle and break all subsequent calls.
_setupapi.SetupDiGetClassDevsW.restype  = ctypes.c_void_p
_setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, wt.DWORD]
_setupapi.SetupDiEnumDeviceInfo.restype  = wt.BOOL
_setupapi.SetupDiEnumDeviceInfo.argtypes = [
    ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_SP_DEVINFO_DATA)]
_setupapi.SetupDiGetDeviceRegistryPropertyW.restype  = wt.BOOL
_setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(_SP_DEVINFO_DATA), wt.DWORD,
    ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.BYTE), wt.DWORD, ctypes.POINTER(wt.DWORD)]
_setupapi.SetupDiDestroyDeviceInfoList.restype  = wt.BOOL
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

def _reg_prop(hdi, pdev, prop):
    buf = (wt.BYTE * 512)()
    got = wt.DWORD()
    ok  = _setupapi.SetupDiGetDeviceRegistryPropertyW(
        hdi, pdev, prop, None, buf, 512, ctypes.byref(got))
    if not ok or got.value < 2:
        return ""
    try:
        return bytes(buf[:got.value]).decode("utf-16-le").split("\x00")[0]
    except Exception:
        return ""

ADB_ETH = "192.168.10.1:5555"

_NO_WINDOW = subprocess.CREATE_NO_WINDOW  # suppress console flash on Windows

# ── HID Vendor Input Report reader (Report 0x10) — UVC streaming status ──────
# hid_monitor on the device writes Report 0x10 every 2 s to /dev/hidg0.
# Windows receives it as a HID Input report — no ADB needed.
# Layout (16 bytes): [0x10][w_lo][w_hi][h_lo][h_hi][fps_u8][flags][pad×9]
#   flags bit0 = streaming active

_kernel32 = ctypes.WinDLL("kernel32")
_kernel32.CreateFileW.restype  = ctypes.c_void_p
_kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, wt.DWORD, wt.DWORD,
                                   ctypes.c_void_p, wt.DWORD, wt.DWORD,
                                   ctypes.c_void_p]
_kernel32.ReadFile.restype  = wt.BOOL
_kernel32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
                                ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
_kernel32.CloseHandle.restype  = wt.BOOL
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

INVALID_HANDLE_VALUE_PTR = ctypes.c_void_p(-1).value
GENERIC_READ         = 0x80000000
FILE_SHARE_READ      = 0x00000001
FILE_SHARE_WRITE     = 0x00000002
OPEN_EXISTING        = 3
DIGCF_DEVICEINTERFACE = 0x00000010

def _wguid(s):
    """Convert '{xxxxxxxx-...}' GUID string to (c_byte*16) in COM wire order."""
    s = s.strip('{}').replace('-', '')
    d1, d2, d3 = int(s[:8], 16), int(s[8:12], 16), int(s[12:16], 16)
    return (ctypes.c_byte * 16)(*struct.pack('<IHH', d1, d2, d3),
                                 *bytes.fromhex(s[16:]))

_GUID_HID = (ctypes.c_byte * 16)(*_wguid("{4D1E55B2-F16F-11CF-88CB-001111000030}"))

class _SP_DEVIF_DATA(ctypes.Structure):
    _fields_ = [("cbSize",   wt.DWORD),
                ("Guid",     ctypes.c_byte * 16),
                ("Flags",    wt.DWORD),
                ("Reserved", ctypes.c_size_t)]

_setupapi.SetupDiEnumDeviceInterfaces.restype  = wt.BOOL
_setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    wt.DWORD, ctypes.c_void_p]
_setupapi.SetupDiGetDeviceInterfaceDetailW.restype  = wt.BOOL
_setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]

def find_android_baseunit_hid_path():
    """Return the device interface path for Android BaseUnit HID (MI_02), or None."""
    hdi = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(_GUID_HID), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if not hdi or hdi == INVALID_HANDLE_VALUE:
        return None
    result = None
    idx    = 0
    devif  = _SP_DEVIF_DATA()
    devif.cbSize = ctypes.sizeof(_SP_DEVIF_DATA)
    try:
        while _setupapi.SetupDiEnumDeviceInterfaces(
                hdi, None, ctypes.byref(_GUID_HID), idx, ctypes.byref(devif)):
            idx += 1
            req = wt.DWORD(0)
            _setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdi, ctypes.byref(devif), None, 0, ctypes.byref(req), None)
            if req.value < 8:
                continue
            buf = (ctypes.c_byte * req.value)()
            # cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_W: 8 on 64-bit Windows
            ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[0] = 8
            ok = _setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdi, ctypes.byref(devif), buf, req.value, ctypes.byref(req), None)
            if not ok:
                continue
            # DevicePath starts at offset 4 (after the DWORD cbSize field)
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            pl = path.lower()
            if "vid_046d" in pl and "pid_087c" in pl and "mi_02" in pl:
                result = path
                break
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdi)
    return result

# ── WASAPI call-state detection (Windows-side, no ADB) ───────────────────────
# Enumerates audio capture sessions on our UAC2 device (VID:046D / PID:087C).
# Near-instant leave-meeting detection — no multi-second Windows Audio lag.

_ole32 = ctypes.WinDLL("ole32")
_ole32.CoInitializeEx.argtypes  = [ctypes.c_void_p, ctypes.c_uint]
_ole32.CoInitializeEx.restype   = ctypes.HRESULT
_ole32.CoUninitialize.argtypes  = []
_ole32.CoUninitialize.restype   = None
_ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
_ole32.CoCreateInstance.restype  = ctypes.HRESULT
_ole32.PropVariantClear.argtypes = [ctypes.c_void_p]
_ole32.PropVariantClear.restype  = ctypes.HRESULT

_CLSID_MME = _wguid("BCDE0395-E52F-467C-8E3D-C4579291692E")
_IID_MME   = _wguid("A95664D2-9614-4F35-A746-DE8DB63617E6")
_IID_ASM2  = _wguid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")

class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt",   ctypes.c_ushort),
                ("pad1", ctypes.c_ushort), ("pad2", ctypes.c_ushort), ("pad3", ctypes.c_ushort),
                ("val",  ctypes.c_void_p)]   # pointer-sized union slot (VT_LPWSTR=31 → wchar_p)

class _PROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", ctypes.c_uint)]

# PKEY_Device_FriendlyName — UAC2 gadget appears as "Microphone (Source/Sink)"
# (no custom function_name set; InstanceId/pid=256 is unpopulated for audio endpoints)
_PKEY_NAME = _PROPKEY()
_PKEY_NAME.fmtid[:] = _wguid("a45c254e-df1c-4efd-8020-67d146a850e0")
_PKEY_NAME.pid = 14

def _vt(obj):
    """Return vtable pointer array for a COM object."""
    return ctypes.cast(
        ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value,
        ctypes.POINTER(ctypes.c_void_p))

def _rel(obj):
    """IUnknown::Release."""
    ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(_vt(obj)[2])(obj)

def get_wasapi_call_state():
    """Return 'MIC_ACTIVE', 'MIC_IDLE', or 'WASAPI_ERR'.

    Walks WASAPI capture endpoints, finds ours by FriendlyName "Source/Sink"
    (UAC2 gadget default Windows name), then checks whether any session is Active.
    """
    try:
        # IMMDeviceEnumerator
        p_enum = ctypes.c_void_p()
        if _ole32.CoCreateInstance(ctypes.byref(_CLSID_MME), None, 0x17,
                                   ctypes.byref(_IID_MME),
                                   ctypes.byref(p_enum)) != 0:
            return "WASAPI_ERR"

        # EnumAudioEndpoints(eCapture=1, DEVICE_STATE_ACTIVE=1)
        p_coll = ctypes.c_void_p()
        hr = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p))(_vt(p_enum)[3])(
            p_enum, 1, 1, ctypes.byref(p_coll))
        _rel(p_enum)
        if hr != 0 or not p_coll.value:
            return "WASAPI_ERR"

        cnt = ctypes.c_uint()
        ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_uint))(_vt(p_coll)[3])(
            p_coll, ctypes.byref(cnt))
        fn_item = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p))(_vt(p_coll)[4])

        result = "MIC_IDLE"
        for i in range(cnt.value):
            p_dev = ctypes.c_void_p()
            if fn_item(p_coll, i, ctypes.byref(p_dev)) != 0 or not p_dev.value:
                continue

            # OpenPropertyStore → check device instance path for our VID/PID
            p_ps = ctypes.c_void_p()
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint,
                ctypes.POINTER(ctypes.c_void_p))(_vt(p_dev)[4])(
                p_dev, 0, ctypes.byref(p_ps))
            is_ours = False
            if p_ps.value:
                pv = _PROPVARIANT()
                ctypes.WINFUNCTYPE(
                    ctypes.c_long, ctypes.c_void_p,
                    ctypes.POINTER(_PROPKEY), ctypes.POINTER(_PROPVARIANT))(
                    _vt(p_ps)[5])(p_ps, ctypes.byref(_PKEY_NAME), ctypes.byref(pv))
                if pv.vt == 31 and pv.val:           # VT_LPWSTR
                    fname = ctypes.cast(pv.val, ctypes.c_wchar_p).value or ""
                    is_ours = "Source/Sink" in fname or "Wired Roomdock Mic" in fname
                    _ole32.PropVariantClear(ctypes.addressof(pv))
                _rel(p_ps)

            if is_ours:
                # Activate IAudioSessionManager2
                p_asm2 = ctypes.c_void_p()
                hr2 = ctypes.WINFUNCTYPE(
                    ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_uint, ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p))(_vt(p_dev)[3])(
                    p_dev, ctypes.byref(_IID_ASM2), 0x17, None,
                    ctypes.byref(p_asm2))
                if hr2 == 0 and p_asm2.value:
                    # GetSessionEnumerator (vtable index 5)
                    p_se = ctypes.c_void_p()
                    ctypes.WINFUNCTYPE(
                        ctypes.HRESULT, ctypes.c_void_p,
                        ctypes.POINTER(ctypes.c_void_p))(_vt(p_asm2)[5])(
                        p_asm2, ctypes.byref(p_se))
                    _rel(p_asm2)
                    if p_se.value:
                        sc = ctypes.c_int()
                        ctypes.WINFUNCTYPE(
                            ctypes.HRESULT, ctypes.c_void_p,
                            ctypes.POINTER(ctypes.c_int))(_vt(p_se)[3])(
                            p_se, ctypes.byref(sc))
                        fn_gs = ctypes.WINFUNCTYPE(
                            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_int,
                            ctypes.POINTER(ctypes.c_void_p))(_vt(p_se)[4])
                        for j in range(sc.value):
                            p_ctrl = ctypes.c_void_p()
                            if fn_gs(p_se, j, ctypes.byref(p_ctrl)) != 0 \
                                    or not p_ctrl.value:
                                continue
                            state = ctypes.c_int()
                            ctypes.WINFUNCTYPE(
                                ctypes.HRESULT, ctypes.c_void_p,
                                ctypes.POINTER(ctypes.c_int))(_vt(p_ctrl)[3])(
                                p_ctrl, ctypes.byref(state))
                            _rel(p_ctrl)
                            if state.value == 1:    # AudioSessionStateActive
                                result = "MIC_ACTIVE"
                                break
                        _rel(p_se)

            _rel(p_dev)
            if result == "MIC_ACTIVE":
                break

        _rel(p_coll)
        return result
    except Exception:
        return "WASAPI_ERR"

# ── UC App process detection (Windows process list, no ADB) ──────────────────
# Uses CreateToolhelp32Snapshot to enumerate running processes.
# Detects Teams, Zoom, WebEx, Google Meet (browser-based via chrome/edge).

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE_VALUE_K = ctypes.c_void_p(-1).value

class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",              wt.DWORD),
        ("cntUsage",            wt.DWORD),
        ("th32ProcessID",       wt.DWORD),
        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID",        wt.DWORD),
        ("cntThreads",          wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             wt.DWORD),
        ("szExeFile",           ctypes.c_char * 260),
    ]

_kernel32.CreateToolhelp32Snapshot.restype  = ctypes.c_void_p
_kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
_kernel32.Process32First.restype  = wt.BOOL
_kernel32.Process32First.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32)]
_kernel32.Process32Next.restype   = wt.BOOL
_kernel32.Process32Next.argtypes  = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32)]
_kernel32.CloseHandle.restype     = wt.BOOL
_kernel32.CloseHandle.argtypes    = [ctypes.c_void_p]

# Map exe name (lowercase) → display label
_UC_PROCESSES = {
    "ms-teams.exe":  "Teams",
    "msteams.exe":   "Teams",
    "teams.exe":     "Teams (classic)",
    "zoom.exe":      "Zoom",
    "zoomwebex.exe": "WebEx",
    "ciscowebex.exe":"WebEx",
    "spark.exe":     "WebEx",
}

def get_uc_app_status():
    """Enumerate running processes to detect UC apps.
    Returns list of (app_name, pid) for all detected UC apps, sorted by name.
    """
    found = {}
    try:
        snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snap == _INVALID_HANDLE_VALUE_K or snap is None:
            return []
        try:
            pe = _PROCESSENTRY32()
            pe.dwSize = ctypes.sizeof(_PROCESSENTRY32)
            if _kernel32.Process32First(snap, ctypes.byref(pe)):
                while True:
                    exe = pe.szExeFile.decode("utf-8", errors="ignore").lower()
                    label = _UC_PROCESSES.get(exe)
                    if label and label not in found:
                        found[label] = pe.th32ProcessID
                    if not _kernel32.Process32Next(snap, ctypes.byref(pe)):
                        break
        finally:
            _kernel32.CloseHandle(snap)
    except Exception:
        pass
    return sorted(found.items())   # [(name, pid), ...]

# ── Teams Shared Display Mode detection ──────────────────────────────────────
# Teams (new) is an Electron app. All its top-level content windows use the
# window class "TeamsWebView".  The Shared Display "attendee view" window is
# the only TeamsWebView window that lands on a non-primary monitor — normal
# Teams windows (Chat, Meeting join, Calling…) always stay on the primary.
# Detection: find any visible, non-minimised TeamsWebView window on a
# secondary monitor that covers ≥40% of that monitor → Shared Display active.

_user32 = ctypes.WinDLL("user32", use_last_error=True)

_EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

_user32.EnumWindows.restype  = wt.BOOL
_user32.EnumWindows.argtypes = [_EnumWindowsProc, wt.LPARAM]
_user32.GetClassNameW.restype  = ctypes.c_int
_user32.GetClassNameW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
_user32.IsWindowVisible.restype  = wt.BOOL
_user32.IsWindowVisible.argtypes = [wt.HWND]
_user32.IsIconic.restype  = wt.BOOL
_user32.IsIconic.argtypes = [wt.HWND]
_user32.MonitorFromWindow.restype  = ctypes.c_void_p
_user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
_user32.GetWindowRect.restype  = wt.BOOL
_user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
_MONITOR_DEFAULTTONEAREST = 2

class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize",    wt.DWORD),
                ("rcMonitor", wt.RECT),
                ("rcWork",    wt.RECT),
                ("dwFlags",   wt.DWORD)]
_MONITORINFOF_PRIMARY = 1

_user32.GetMonitorInfoW.restype  = wt.BOOL
_user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]

# Keep these for uvc_loop (GetWindowTextW used elsewhere)
_user32.GetWindowTextW.restype  = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
_user32.GetWindowTextLengthW.restype  = ctypes.c_int
_user32.GetWindowTextLengthW.argtypes = [wt.HWND]

# Child window enumeration — used to detect TeamsVideo (in-call) vs shared display
_EnumChildProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_user32.EnumChildWindows.restype  = wt.BOOL
_user32.EnumChildWindows.argtypes = [wt.HWND, _EnumChildProc, wt.LPARAM]

def _teams_window_role(hwnd):
    """Classify a TeamsWebView HWND.
    Returns: 'shared_display' | 'incall' | 'main' | 'unknown'
    Logic (no title, no PID — pure child class inspection):
      - Has TeamsVideo child               → in-call meeting window
      - Child count (direct) >= 4 OR
        total child count > 30            → main app window (Calendar/Chat)
      - Otherwise                         → shared display attendee view
    """
    cls_buf  = ctypes.create_unicode_buffer(64)
    counters = [0, False]   # [total_children, has_video]

    def _child_cb(child_hwnd, _):
        counters[0] += 1
        _user32.GetClassNameW(child_hwnd, cls_buf, 64)
        if cls_buf.value == "TeamsVideo":
            counters[1] = True
        return True   # keep enumerating all descendants

    try:
        _user32.EnumChildWindows(hwnd, _EnumChildProc(_child_cb), 0)
    except Exception:
        return "unknown"

    if counters[1]:
        return "incall"           # TeamsVideo present → in-call
    if counters[0] > 30:
        return "main"             # too many children → main app window
    return "shared_display"
_user32.GetWindowThreadProcessId.restype  = wt.DWORD
_user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]

_TEAMS_WINDOW_CLASS  = "TeamsWebView"   # all Teams (new) content windows
_SHARED_MIN_COVERAGE = 0.3              # ≥30% of monitor = real content window (secondary)

def get_shared_display_status():
    """Detect Teams Shared Display Mode (attendee view window).
    Uses child class inspection via EnumChildWindows — no titles needed:
      - TeamsVideo child present → in-call meeting window  (skip)
      - Total descendants > 30  → main app window          (skip)
      - Otherwise               → shared display attendee view ✓
    Returns (found: bool, on_secondary: bool, label: str).
    """
    cls_buf   = ctypes.create_unicode_buffer(64)
    secondary = [False, 0]
    on_primary = [False]

    def _cb(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
            return True
        _user32.GetClassNameW(hwnd, cls_buf, 64)
        if cls_buf.value != _TEAMS_WINDOW_CLASS:
            return True
        hmon = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return True
        mi = _MONITORINFO(); mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return True
        mon_w = mi.rcMonitor.right  - mi.rcMonitor.left
        mon_h = mi.rcMonitor.bottom - mi.rcMonitor.top
        if mon_w * mon_h == 0:
            return True
        wr = wt.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(wr)):
            return True
        win_w = max(0, wr.right  - wr.left)
        win_h = max(0, wr.bottom - wr.top)
        if (win_w * win_h) / (mon_w * mon_h) < 0.1:
            return True   # zero-size background shell
        # Classify by child window inspection
        role = _teams_window_role(hwnd)
        if role != "shared_display":
            return True   # skip main or in-call
        if not (mi.dwFlags & _MONITORINFOF_PRIMARY):
            secondary[0] = True
            secondary[1] = mi.rcMonitor.left
            return False   # found on secondary — stop
        on_primary[0] = True
        return True

    try:
        _user32.EnumWindows(_EnumWindowsProc(_cb), 0)
    except Exception:
        return False, False, ""

    if secondary[0]:
        return True, True, f"Display 2 \u2713  (x={secondary[1]})"
    if on_primary[0]:
        return True, False, "Not active (on 1st display)"
    return False, False, ""

def _empty_usb():
    return {"uvc": (False, ""), "hid": (False, ""), "uac2": (False, "")}

# ── UVC stream status: DirectShow IAMStreamConfig + privacy registry ──────────
# No ADB needed — queries the Windows UVC driver directly.
#
# Resolution: DirectShow ICreateDevEnum → IMoniker → IBaseFilter → IPin →
#             IAMStreamConfig::GetFormat → AM_MEDIA_TYPE → VIDEOINFOHEADER
# Streaming:  HKCU CapabilityAccessManager webcam ConsentStore:
#             LastUsedTimeStart > LastUsedTimeStop → camera currently in use

_ole32.CoInitialize.restype  = ctypes.HRESULT
_ole32.CoInitialize.argtypes = [ctypes.c_void_p]
_ole32.CoCreateInstance.restype  = ctypes.HRESULT
_ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     wt.DWORD, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_void_p)]
_ole32.CoTaskMemFree.restype  = None
_ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

_oleaut32 = ctypes.WinDLL("oleaut32")
_oleaut32.SysFreeString.restype  = None
_oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]

# DirectShow GUIDs
_CLSID_SysDevEnum  = _wguid("{62BE5D10-60EB-11D0-BD3B-00A0C911CE86}")
_IID_ICreateDevEnum= _wguid("{29840822-5B84-11D0-BD3B-00A0C911CE86}")
_CLSID_VidInputCat = _wguid("{860BB310-5D01-11D0-BD3B-00A0C911CE86}")
_IID_IEnumMoniker  = _wguid("{00000102-0000-0000-C000-000000000046}")
_IID_IBaseFilter   = _wguid("{56A86895-0AD4-11CE-B03A-0020AF0BA770}")
_IID_IPropertyBag  = _wguid("{55272A00-42CB-11CE-8135-00AA004BB851}")
_IID_IAMStreamCfg  = _wguid("{C6E13340-30AC-11D0-A18C-00A0C9118956}")
_IID_IEnumPins     = _wguid("{56A86892-0AD4-11CE-B03A-0020AF0BA770}")
_IID_IPin          = _wguid("{56A86891-0AD4-11CE-B03A-0020AF0BA770}")
_IID_IBindCtx      = _wguid("{0000000E-0000-0000-C000-000000000046}")

_ole32.CreateBindCtx = ctypes.windll.ole32.CreateBindCtx
_ole32.CreateBindCtx.restype  = ctypes.HRESULT
_ole32.CreateBindCtx.argtypes = [wt.DWORD, ctypes.POINTER(ctypes.c_void_p)]

CLSCTX_INPROC = 0x1
PINDIR_OUTPUT  = 1

def _rel(p):
    if p and p.value:
        ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)(_vt(p)[2])(p)

def _qi(p, iid_bytes):
    """QueryInterface helper. Returns new c_void_p or None."""
    out = ctypes.c_void_p()
    iid = (ctypes.c_byte * 16)(*iid_bytes)
    hr  = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
          _vt(p)[0])(p, iid, ctypes.byref(out))
    return out if hr == 0 and out.value else None

def get_uvc_format_ds():
    """Query UVC camera current format via DirectShow IAMStreamConfig.
    Returns (width, height, fps_int) or (0, 0, 0).
    Works while Teams is streaming — Camera Frame Server allows shared access.
    """
    # COM must be initialized per-thread (this runs in uvc_loop background thread)
    _ole32.CoInitialize(None)
    try:
        # CoCreateInstance(CLSID_SystemDeviceEnum → ICreateDevEnum)
        p_sde = ctypes.c_void_p()
        hr = _ole32.CoCreateInstance(
            _CLSID_SysDevEnum, None, CLSCTX_INPROC,
            _IID_ICreateDevEnum, ctypes.byref(p_sde))
        if hr != 0 or not p_sde.value:
            return 0, 0, 0

        # CreateClassEnumerator(CLSID_VideoInputDeviceCategory → IEnumMoniker)
        # Signature: HRESULT CreateClassEnumerator(REFCLSID, IEnumMoniker**, DWORD)
        p_enum = ctypes.c_void_p()
        hr = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p), wt.DWORD)(_vt(p_sde)[3])(
            p_sde, _CLSID_VidInputCat, ctypes.byref(p_enum), 0)
        _rel(p_sde)
        if hr != 0 or not p_enum.value:
            return 0, 0, 0

        result = (0, 0, 0)
        # Create IBindCtx
        p_bc = ctypes.c_void_p()
        _ole32.CreateBindCtx(0, ctypes.byref(p_bc))

        # Enumerate monikers — find VID_046D&PID_087C&MI_00
        fn_next = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, wt.ULONG,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.ULONG))(_vt(p_enum)[3])
        while True:
            p_mk = ctypes.c_void_p()
            fetched = wt.ULONG(0)
            if fn_next(p_enum, 1, ctypes.byref(p_mk), ctypes.byref(fetched)) != 0:
                break
            if not p_mk.value:
                break

            # IMoniker::BindToStorage → IPropertyBag to check device path
            p_pb = ctypes.c_void_p()
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p))(_vt(p_mk)[9])(
                p_mk, p_bc, None, _IID_IPropertyBag, ctypes.byref(p_pb))

            found = False
            if p_pb.value:
                # IPropertyBag::Read(L"DevicePath") → check VID/PID
                class _VARIANT(ctypes.Structure):
                    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort),
                                 ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                                 ("val", ctypes.c_void_p), ("_pad", ctypes.c_void_p)]
                var = _VARIANT(); var.vt = 0
                name_buf = ctypes.create_unicode_buffer("DevicePath")
                ctypes.WINFUNCTYPE(
                    ctypes.HRESULT, ctypes.c_void_p, ctypes.c_wchar_p,
                    ctypes.c_void_p, ctypes.c_void_p)(_vt(p_pb)[3])(
                    p_pb, name_buf, ctypes.byref(var), None)
                if var.vt == 8 and var.val:   # VT_BSTR = 8
                    path = ctypes.wstring_at(var.val)
                    pl = path.lower()
                    if "vid_046d" in pl and "pid_087c" in pl and "mi_00" in pl:
                        found = True
                    _oleaut32.SysFreeString(ctypes.c_void_p(var.val))
                _rel(p_pb)

            if found:
                # IMoniker::BindToObject → IBaseFilter
                p_flt = ctypes.c_void_p()
                ctypes.WINFUNCTYPE(
                    ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p))(_vt(p_mk)[8])(
                    p_mk, p_bc, None, _IID_IBaseFilter, ctypes.byref(p_flt))

                if p_flt.value:
                    # IBaseFilter::EnumPins → find OUTPUT pin → IAMStreamConfig
                    p_ep = ctypes.c_void_p()
                    ctypes.WINFUNCTYPE(
                        ctypes.HRESULT, ctypes.c_void_p,
                        ctypes.POINTER(ctypes.c_void_p))(_vt(p_flt)[10])(
                        p_flt, ctypes.byref(p_ep))
                    if p_ep.value:
                        fn_pnext = ctypes.WINFUNCTYPE(
                            ctypes.HRESULT, ctypes.c_void_p, wt.ULONG,
                            ctypes.POINTER(ctypes.c_void_p),
                            ctypes.POINTER(wt.ULONG))(_vt(p_ep)[3])
                        while True:
                            p_pin = ctypes.c_void_p(); pf = wt.ULONG(0)
                            if fn_pnext(p_ep, 1, ctypes.byref(p_pin), ctypes.byref(pf)) != 0:
                                break
                            if not p_pin.value:
                                break
                            # QueryDirection
                            direction = ctypes.c_int(-1)
                            ctypes.WINFUNCTYPE(
                                ctypes.HRESULT, ctypes.c_void_p,
                                ctypes.POINTER(ctypes.c_int))(_vt(p_pin)[9])(
                                p_pin, ctypes.byref(direction))
                            if direction.value == PINDIR_OUTPUT:
                                p_sc = _qi(p_pin, _IID_IAMStreamCfg)
                                if p_sc:
                                    # IAMStreamConfig::GetFormat → AM_MEDIA_TYPE
                                    p_amt = ctypes.c_void_p()
                                    hr2 = ctypes.WINFUNCTYPE(
                                        ctypes.HRESULT, ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_void_p))(_vt(p_sc)[4])(
                                        p_sc, ctypes.byref(p_amt))
                                    if hr2 == 0 and p_amt.value:
                                       # AM_MEDIA_TYPE 64-bit layout:
                                       #   +0  majortype GUID (16)
                                       #   +16 subtype   GUID (16)
                                       #   +32 bFixed/bTemporal/lSampleSize (12)
                                       #   +44 formattype GUID (16) → end=60
                                       #   +60 [4 pad to align ptr]
                                       #   +64 pUnk  ptr  (8)
                                       #   +72 cbFormat   (4)
                                       #   +76 [4 pad]
                                       #   +80 pbFormat ptr (8)  ← correct offset
                                       amt = (ctypes.c_byte * 88)()
                                       ctypes.memmove(amt, p_amt.value, 88)
                                       pb_fmt = struct.unpack_from('<Q', amt, 80)[0]
                                       if pb_fmt:
                                           # VIDEOINFOHEADER:
                                           #   +40 AvgTimePerFrame (LONGLONG, 100ns units)
                                           #   +48 BITMAPINFOHEADER
                                           #   +52 biWidth  (LONG)
                                           #   +56 biHeight (LONG, may be negative)
                                           w   = ctypes.cast(pb_fmt + 52, ctypes.POINTER(ctypes.c_int32))[0]
                                           h   = abs(ctypes.cast(pb_fmt + 56, ctypes.POINTER(ctypes.c_int32))[0])
                                           tpf = ctypes.cast(pb_fmt + 40, ctypes.POINTER(ctypes.c_int64))[0]
                                           fps = int(10_000_000 / tpf) if tpf > 0 else 0
                                           if w > 0 and h > 0:
                                               result = (w, h, fps)
                                       # Free pbFormat buffer and AM_MEDIA_TYPE struct
                                       cb = struct.unpack_from('<I', amt, 72)[0]
                                       if pb_fmt and cb:
                                           _ole32.CoTaskMemFree(ctypes.c_void_p(pb_fmt))
                                       _ole32.CoTaskMemFree(ctypes.c_void_p(p_amt.value))
                                    _rel(p_sc)
                                    if result != (0, 0, 0):
                                        _rel(p_pin); break
                            _rel(p_pin)
                        _rel(p_ep)
                    _rel(p_flt)
                _rel(p_mk)
                break
            _rel(p_mk)

        _rel(p_enum)
        if p_bc.value:
            _rel(p_bc)
        return result
    except Exception:
        return 0, 0, 0

def is_camera_in_use():
    """Check if any app currently has the webcam open via Windows privacy registry.
    Returns True when camera is actively streaming (LastUsedTimeStart > LastUsedTimeStop).
    Checks both MSIX-packaged apps (new Teams Electron, UWP) at the root webcam key
    and unpackaged Win32 apps under the NonPackaged subkey.
    """
    _BASE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"

    def _check_key(sk):
        try:
            start = winreg.QueryValueEx(sk, "LastUsedTimeStart")[0]
            stop  = winreg.QueryValueEx(sk, "LastUsedTimeStop")[0]
            return start > stop
        except FileNotFoundError:
            return False

    try:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, _BASE) as root:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(root, i)
                            with winreg.OpenKey(root, sub) as sk:
                                if sub == "NonPackaged":
                                    # Win32 apps — one level deeper
                                    j = 0
                                    while True:
                                        try:
                                            sub2 = winreg.EnumKey(sk, j)
                                            with winreg.OpenKey(sk, sub2) as sk2:
                                                if _check_key(sk2):
                                                    return True
                                            j += 1
                                        except OSError:
                                            break
                                else:
                                    # MSIX-packaged apps (new Teams Electron, etc.)
                                    if _check_key(sk):
                                        return True
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                pass
    except Exception:
        pass
    return False

def get_uvc_stream_status():
    """Get UVC stream status from Windows driver directly — no ADB.
    Returns (width, height, fps, streaming).
    """
    w, h, fps = get_uvc_format_ds()
    streaming  = is_camera_in_use() if (w and h) else False
    return w, h, fps, streaming

def get_usb_status():
    hdi = _setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if hdi is None or hdi == INVALID_HANDLE_VALUE:
        return _empty_usb()

    result = _empty_usb()
    dev = _SP_DEVINFO_DATA()
    dev.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
    idx = 0
    try:
        while _setupapi.SetupDiEnumDeviceInfo(hdi, idx, ctypes.byref(dev)):
            idx += 1
            hw = _reg_prop(hdi, ctypes.byref(dev), SPDRP_HARDWAREID)
            if "VID_046D" not in hw or "PID_087C" not in hw or "&Col" in hw:
                continue
            name = _reg_prop(hdi, ctypes.byref(dev), SPDRP_FRIENDLYNAME)
            st = wt.ULONG(0); pb = wt.ULONG(0)
            ok = (_cfgmgr.CM_Get_DevNode_Status(
                      ctypes.byref(st), ctypes.byref(pb), dev.DevInst, 0) == 0
                  ) and pb.value == 0
            if "MI_00" in hw:
                result["uvc"]  = (ok, "Wired Roomdock Camera")
            elif "MI_02" in hw or "MI_03" in hw:
                # MI number shifts when HID is disabled (no-HID: UAC2=MI_02, HID-enabled: HID=MI_02/UAC2=MI_03)
                # Distinguish by device class: Audio=UAC2, HIDClass=HID
                cls = _reg_prop(hdi, ctypes.byref(dev), 7)  # SPDRP_CLASS = 7
                if cls.lower() == "hidclass" or cls.lower() == "hid":
                    result["hid"]  = (ok, "HID Telephony")
                else:
                    result["uac2"] = (ok, "Wired Roomdock Mic")
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdi)
    return result

# ── UI ────────────────────────────────────────────────────────────────────────

BG       = "#1e1e2e"
FG       = "#cdd6f4"
FG_DIM   = "#6c7086"
C_OK     = "#a6e3a1"
C_ERR    = "#f38ba8"
C_WARN   = "#f9e2af"
FONT     = ("Segoe UI", 10)
FONT_B   = ("Segoe UI", 10, "bold")
FONT_HDR = ("Segoe UI", 12, "bold")
FONT_SM  = ("Segoe UI", 9)
REFRESH_SEC = 2

class AndroidBaseUnitMonitor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Android BaseUnit RoomDock Monitor")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.wm_attributes('-topmost', True)
        self._stop = False
        self._build_ui()
        self._start_refresh()

    def _build_ui(self):
        tk.Label(self, text="Android BaseUnit Wired RoomDock Status Monitor",
                 bg=BG, fg=FG, font=FONT_HDR).pack(padx=18, pady=(14, 8))

        df = self._section("Display")
        self._lbl_count = self._row(df, "Monitor count", "--", FG)
        self._lbl_mode  = self._row(df, "Display mode",  "--", FG)

        uf = self._section("Android BaseUnit USB  (VID:046D / PID:087C)")
        self._lbl_uvc      = self._row(uf, "UVC  (Camera)", "--", FG)
        self._lbl_uvc_info = self._row(uf, "  └ Stream",   "--", FG_DIM)
        self._lbl_uac2     = self._row(uf, "UAC2 (Audio)",  "--", FG)
        self._lbl_hid      = self._row(uf, "HID  (Phone)",  "--", FG)

        cf = self._section("UC App Detection  (Windows WASAPI)")
        self._lbl_call = self._row(cf, "Mic / Call State", "--", FG)

        af = self._section("UC App  (Windows Process)")
        self._lbl_app_teams  = self._row(af, "Teams",          "Not running", C_ERR)
        self._lbl_app_zoom   = self._row(af, "Zoom",           "Not running", FG_DIM)
        self._lbl_app_webex  = self._row(af, "WebEx",          "Not running", FG_DIM)
        self._lbl_shared_disp= self._row(af, "Shared Display", "Not active",  FG_DIM)

        self._lbl_ts = tk.Label(self, text="", bg=BG, fg=FG_DIM, font=FONT_SM)
        self._lbl_ts.pack(pady=(6, 12))

    def _section(self, title):
        f = tk.LabelFrame(self, text=f"  {title}  ",
                          bg=BG, fg=FG, font=FONT_B,
                          bd=1, relief="groove", padx=10, pady=6)
        f.pack(fill="x", padx=14, pady=4)
        return f

    def _row(self, parent, label, init, color):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", pady=2)
        tk.Label(f, text=label, bg=BG, fg=FG_DIM,
                 font=FONT, width=20, anchor="w").pack(side="left")
        v = tk.Label(f, text=init, bg=BG, fg=color, font=FONT_B)
        v.pack(side="left")
        return v

    def _fmt(self, active, name):
        if active:
            return (f"Active  ({name})" if name else "Active"), C_OK
        return "Not detected", C_ERR

    def _update_uvc_detail(self, w, h, fps, streaming):
        fps_str = f"{fps} fps (cfg)" if fps else ""
        if w and h and streaming:
            txt   = f"StreamON: {w}×{h} @ {fps_str}" if fps_str else f"StreamON: {w}×{h}"
            color = C_OK
        elif w and h:
            txt   = f"StreamOFF: {w}×{h} @ {fps_str}" if fps_str else f"StreamOFF: {w}×{h}"
            color = FG_DIM
        else:
            txt   = "Not streaming"
            color = FG_DIM
        self._lbl_uvc_info.config(text=txt, fg=color)

    def _update_app_status(self, apps, shared_found, shared_secondary, shared_label):
        """Update UC App section. apps = [(name, pid), ...]"""
        running = {name for name, _ in apps}
        for lbl, key in [(self._lbl_app_teams, "Teams"),
                         (self._lbl_app_zoom,  "Zoom"),
                         (self._lbl_app_webex, "WebEx")]:
            if key in running or f"{key} (classic)" in running:
                pid = next((p for n, p in apps if n.startswith(key)), 0)
                lbl.config(text=f"Running  (PID {pid})", fg=C_OK)
            else:
                lbl.config(text="Not running", fg=FG_DIM)
        if not shared_found:
            self._lbl_shared_disp.config(text="Not active", fg=FG_DIM)
        elif shared_secondary:
            self._lbl_shared_disp.config(text=shared_label, fg=C_OK)   # green ✓
        else:
            self._lbl_shared_disp.config(text=shared_label, fg="orange") # on primary

    def _update_ui(self, count, mode, usb, call_state):
        dual = count >= 2
        self._lbl_count.config(text=str(count), fg=C_OK if dual else FG)
        topo_color = (C_OK if mode == "Extend" else C_WARN) if dual else FG
        self._lbl_mode.config(text=mode if dual else "— (single display)", fg=topo_color)
        for lbl, key in [(self._lbl_uvc, "uvc"), (self._lbl_uac2, "uac2"), (self._lbl_hid, "hid")]:
            txt, color = self._fmt(*usb[key])
            lbl.config(text=txt, fg=color)
        call_color = (C_OK  if call_state == "MIC_ACTIVE" else
                      C_WARN if call_state == "SPK_ONLY"  else
                      C_ERR  if "ERR" in call_state       else FG_DIM)
        self._lbl_call.config(text=call_state, fg=call_color)
        self._lbl_ts.config(text=f"Last updated: {time.strftime('%H:%M:%S')}")

    def _start_refresh(self):
        def loop():
            _ole32.CoInitializeEx(None, 0)   # COINIT_MULTITHREADED — required for WASAPI
            while not self._stop:
                try:
                    count, mode = get_display_info()
                    usb = get_usb_status()
                    call_state = get_wasapi_call_state()
                    apps = get_uc_app_status()
                    shared_found, shared_secondary, shared_label = get_shared_display_status()
                    if not self._stop:
                        self.after(0, self._update_ui, count, mode, usb, call_state)
                        self.after(0, self._update_app_status, apps, shared_found, shared_secondary, shared_label)
                except Exception:
                    pass
                time.sleep(REFRESH_SEC)
            _ole32.CoUninitialize()

        def uvc_loop():
            """Separate thread: query UVC stream status via DirectShow + registry."""
            while not self._stop:
                try:
                    w, h, fps, streaming = get_uvc_stream_status()
                    if not self._stop:
                        self.after(0, self._update_uvc_detail, w, h, fps, streaming)
                except Exception:
                    pass
                time.sleep(REFRESH_SEC)

        threading.Thread(target=loop,     daemon=True).start()
        threading.Thread(target=uvc_loop, daemon=True).start()
        self._start_hid_reader()

    def _start_hid_reader(self):
        """Background thread: open Android BaseUnit HID MI_02 and read Vendor Input Reports."""
        def reader():
            while not self._stop:
                path = find_android_baseunit_hid_path()
                if not path:
                    time.sleep(5)
                    continue
                h = _kernel32.CreateFileW(
                    path, GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None, OPEN_EXISTING, 0, None)
                if h == INVALID_HANDLE_VALUE_PTR or not h:
                    time.sleep(5)
                    continue
                try:
                    buf  = (ctypes.c_byte * 16)()
                    read = wt.DWORD(0)
                    while not self._stop:
                        ok = _kernel32.ReadFile(h, buf, 16, ctypes.byref(read), None)
                        if not ok or read.value < 7:
                            break
                        if (buf[0] & 0xFF) == 0x10:   # RPT_UVC_INFO
                            w   = (buf[1] & 0xFF) | ((buf[2] & 0xFF) << 8)
                            hh  = (buf[3] & 0xFF) | ((buf[4] & 0xFF) << 8)
                            fps = buf[5] & 0xFF
                            streaming = bool(buf[6] & 0x01)
                            if not self._stop:
                                self.after(0, self._update_uvc_detail,
                                           w, hh, fps, streaming)
                except Exception:
                    pass
                finally:
                    _kernel32.CloseHandle(h)
        threading.Thread(target=reader, daemon=True).start()

    def destroy(self):
        self._stop = True
        super().destroy()

if __name__ == "__main__":
    app = AndroidBaseUnitMonitor()
    app.mainloop()
