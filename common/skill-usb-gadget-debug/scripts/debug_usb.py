import ctypes
import ctypes.wintypes as wt

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

def _reg_prop(hdi, pdev, prop):
    buf  = (wt.BYTE * 512)()
    got  = wt.DWORD()
    ok = _setupapi.SetupDiGetDeviceRegistryPropertyW(
        hdi, pdev, prop, None, buf, 512, ctypes.byref(got))
    if not ok or got.value < 2:
        return ""
    try:
        return bytes(buf[:got.value]).decode("utf-16-le").split("\x00")[0]
    except Exception:
        return ""

hdi = _setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
print(f"hdi={hdi}  INVALID={INVALID_HANDLE_VALUE}  valid={hdi != INVALID_HANDLE_VALUE}")

dev = _SP_DEVINFO_DATA()
dev.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
idx = 0
found = 0

while _setupapi.SetupDiEnumDeviceInfo(hdi, idx, ctypes.byref(dev)):
    idx += 1
    hw = _reg_prop(hdi, ctypes.byref(dev), SPDRP_HARDWAREID)
    if "VID_046D" not in hw:
        continue
    found += 1
    name = _reg_prop(hdi, ctypes.byref(dev), SPDRP_FRIENDLYNAME)
    st = wt.ULONG(0); pb = wt.ULONG(0)
    cr = _cfgmgr.CM_Get_DevNode_Status(ctypes.byref(st), ctypes.byref(pb), dev.DevInst, 0)
    print(f"  hw={hw[:60]}")
    print(f"  name={name}  CR={cr}  status=0x{st.value:08x}  problem={pb.value}")
    print(f"  Col={'&Col' in hw}  MI_00={'MI_00' in hw}  MI_02={'MI_02' in hw}  MI_03={'MI_03' in hw}")
    print()

print(f"Total enumerated: {idx}  VID_046D matches: {found}")
_setupapi.SetupDiDestroyDeviceInfoList(hdi)
