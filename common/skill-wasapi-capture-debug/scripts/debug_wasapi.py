#!/usr/bin/env python3
"""Debug WASAPI — enumerate ALL capture endpoints, print IDs and session states.
Uses c_long (not HRESULT) to avoid automatic exception on non-S_OK returns."""

import ctypes, struct

ole32 = ctypes.WinDLL("ole32")
ole32.CoInitializeEx(None, 0)
ole32.PropVariantClear.argtypes = [ctypes.c_void_p]
ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                    ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
ole32.CoCreateInstance.restype  = ctypes.c_long

HR = ctypes.c_long   # raw HRESULT — no auto exception

def wguid(s):
    s = s.strip('{}').replace('-','')
    d1, d2, d3 = int(s[:8],16), int(s[8:12],16), int(s[12:16],16)
    return (ctypes.c_byte*16)(*struct.pack('<IHH',d1,d2,d3), *bytes.fromhex(s[16:]))

CLSID_MME = wguid("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_MME   = wguid("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_ASM2  = wguid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")

class PV(ctypes.Structure):
    _fields_ = [("vt",ctypes.c_ushort),("p1",ctypes.c_ushort),
                ("p2",ctypes.c_ushort),("p3",ctypes.c_ushort),("val",ctypes.c_void_p)]

class PK(ctypes.Structure):
    _fields_ = [("fmtid",ctypes.c_byte*16),("pid",ctypes.c_uint)]

def make_pk(guid_str, pid):
    k = PK(); k.fmtid[:] = wguid(guid_str); k.pid = pid; return k

PKEY_FriendlyName = make_pk("a45c254e-df1c-4efd-8020-67d146a850e0", 14)
PKEY_InstanceId   = make_pk("78c34fc8-104a-4aca-9ea4-524d52996e57", 256)

def vt(obj):
    return ctypes.cast(ctypes.cast(obj,ctypes.POINTER(ctypes.c_void_p)).contents.value,
                       ctypes.POINTER(ctypes.c_void_p))
def rel(obj): ctypes.WINFUNCTYPE(HR,ctypes.c_void_p)(vt(obj)[2])(obj)

def read_prop(p_ps, pkey):
    pv = PV()
    hr = ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.POINTER(PK),ctypes.POINTER(PV))(
        vt(p_ps)[5])(p_ps, ctypes.byref(pkey), ctypes.byref(pv))
    if hr == 0 and pv.vt == 31 and pv.val:
        s = ctypes.cast(pv.val, ctypes.c_wchar_p).value or ""
        ole32.PropVariantClear(ctypes.addressof(pv))
        return s
    ole32.PropVariantClear(ctypes.addressof(pv))
    return f"(hr=0x{hr&0xFFFFFFFF:08x} vt={pv.vt})"

p_enum = ctypes.c_void_p()
hr = ole32.CoCreateInstance(ctypes.byref(CLSID_MME), None, 0x17,
                             ctypes.byref(IID_MME), ctypes.byref(p_enum))
print(f"CoCreateInstance hr=0x{hr&0xFFFFFFFF:08x}")
if hr != 0: raise SystemExit

# Enumerate ALL states so we see everything
p_coll = ctypes.c_void_p()
hr = ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,
                         ctypes.POINTER(ctypes.c_void_p))(vt(p_enum)[3])(
    p_enum, 1, 0xF, ctypes.byref(p_coll))
rel(p_enum)
print(f"EnumAudioEndpoints(eCapture,ALL) hr=0x{hr&0xFFFFFFFF:08x}")
if hr != 0 or not p_coll.value: raise SystemExit

cnt = ctypes.c_uint()
ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint))(
    vt(p_coll)[3])(p_coll, ctypes.byref(cnt))
print(f"Capture endpoint count: {cnt.value}\n")

fn_item = ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.c_uint,
                              ctypes.POINTER(ctypes.c_void_p))(vt(p_coll)[4])

SESS_STATES = {0:"Inactive", 1:"ACTIVE", 2:"Expired"}
DEV_STATES  = {1:"ACTIVE",2:"DISABLED",4:"NOTPRESENT",8:"UNPLUGGED"}

for i in range(cnt.value):
    p_dev = ctypes.c_void_p()
    fn_item(p_coll, i, ctypes.byref(p_dev))
    if not p_dev.value: print(f"[{i}] NULL"); continue

    # GetState (index 6)
    dev_state = ctypes.c_uint()
    ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint))(
        vt(p_dev)[6])(p_dev, ctypes.byref(dev_state))
    state_str = DEV_STATES.get(dev_state.value, hex(dev_state.value))

    # GetId (index 5)
    ep_id_p = ctypes.c_wchar_p()
    ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.POINTER(ctypes.c_wchar_p))(
        vt(p_dev)[5])(p_dev, ctypes.byref(ep_id_p))
    ep_id = (ep_id_p.value or "")[:90]

    # PropertyStore (index 4)
    p_ps = ctypes.c_void_p()
    ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.c_uint,
                        ctypes.POINTER(ctypes.c_void_p))(vt(p_dev)[4])(
        p_dev, 0, ctypes.byref(p_ps))
    friendly = inst_id = "(no propstore)"
    if p_ps.value:
        friendly = read_prop(p_ps, PKEY_FriendlyName)
        inst_id  = read_prop(p_ps, PKEY_InstanceId)
        rel(p_ps)

    print(f"[{i}] {state_str:12s}  {friendly}")
    print(f"     InstanceId: {inst_id}")
    print(f"     EndpointId: {ep_id}")

    # Only try sessions on ACTIVE devices
    if dev_state.value != 1:
        rel(p_dev)
        print()
        continue

    p_asm2 = ctypes.c_void_p()
    hr2 = ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.c_void_p,
                              ctypes.c_uint,ctypes.c_void_p,
                              ctypes.POINTER(ctypes.c_void_p))(vt(p_dev)[3])(
        p_dev, ctypes.byref(IID_ASM2), 0x17, None, ctypes.byref(p_asm2))
    print(f"     ASM2 hr=0x{hr2&0xFFFFFFFF:08x}", end="")
    if hr2 == 0 and p_asm2.value:
        p_se = ctypes.c_void_p()
        hr3 = ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_void_p))(vt(p_asm2)[5])(
            p_asm2, ctypes.byref(p_se))
        rel(p_asm2)
        print(f"  GetSessionEnum hr=0x{hr3&0xFFFFFFFF:08x}", end="")
        if hr3 == 0 and p_se.value:
            sc = ctypes.c_int()
            ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int))(
                vt(p_se)[3])(p_se, ctypes.byref(sc))
            print(f"  sessions={sc.value}")
            fn_gs = ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.c_int,
                                       ctypes.POINTER(ctypes.c_void_p))(vt(p_se)[4])
            for j in range(sc.value):
                p_ctrl = ctypes.c_void_p()
                fn_gs(p_se, j, ctypes.byref(p_ctrl))
                if not p_ctrl.value: continue
                s = ctypes.c_int()
                ctypes.WINFUNCTYPE(HR,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int))(
                    vt(p_ctrl)[3])(p_ctrl, ctypes.byref(s))
                rel(p_ctrl)
                print(f"       session[{j}] {SESS_STATES.get(s.value, s.value)}")
            rel(p_se)
        else:
            print()
    else:
        print()

    rel(p_dev)
    print()

rel(p_coll)
print("Done.")
