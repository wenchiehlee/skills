# UVC 4K Capture — Camera-Agnostic Runtime Detection Skill

This skill describes how to enable **4K UVC streaming** on the Android BaseUnit Wired RoomDock while preserving full backward compatibility with lower-resolution cameras. The design detects the plugged camera's maximum MJPEG capability at runtime — no recompilation needed when switching cameras.

---

## 1. Design Principle — Camera-Agnostic Runtime Detection

The gadget (`setup_uvc.sh`) always **advertises the full 4K frame descriptor** to the host. The userspace forwarder (`uvc_camera_forward`) **detects the actual camera maximum at startup** via `VIDIOC_ENUM_FRAMESIZES` and clamps all UVC negotiation to that limit.

```
Host Windows ──GET_MAX──▶  gadget (bFrameIndex=4, 3840×2160)
                              │
                              ▼  cap_detect_max_mjpeg_idx() at startup
                         Jieli U20:    g_cap_max_frame_idx = 3 (1080p)
                         Logitech MeetUp: g_cap_max_frame_idx = 4 (4K)
                              │
Host ──COMMIT bFrameIndex=4──▶  CLAMP to g_cap_max_frame_idx
                              │
                         cap_init() requests: 1080p (Jieli) or 4K (MeetUp)
```

---

## 2. Trigger Conditions

Invoke or reference this skill when:

- Adding a new camera that supports higher resolution than 1080p
- Host reports 4K in Device Manager but stream is black/frozen
- Need to verify which camera is active and what resolution it negotiated
- `setup_uvc.sh` UVC descriptor tree needs a new frame entry

---

## 3. Changes Required

### 3.1 `setup_uvc.sh` — 4K Frame Descriptor

Add after the 1080p block, before the symlink section:

```bash
# 4K — Logitech MeetUp confirmed 3840×2160 MJPEG @ 30fps (SuperSpeed USB3)
mkdir -p $MDIR/4k
echo 0    > $MDIR/4k/bmCapabilities
echo 3840 > $MDIR/4k/wWidth
echo 2160 > $MDIR/4k/wHeight
echo 497664000  > $MDIR/4k/dwMinBitRate
echo 1990656000 > $MDIR/4k/dwMaxBitRate
echo 16588800   > $MDIR/4k/dwMaxVideoFrameBufferSize   # 3840*2160*2
echo 333333     > $MDIR/4k/dwDefaultFrameInterval
cat > $MDIR/4k/dwFrameInterval << 'INTRV'
333333
INTRV
```

Add symlink alongside 480p/720p/1080p:

```bash
ln -s $MDIR/4k $SHDR/4k 2>/dev/null
```

### 3.2 `uvc_camera_forward.c` — Runtime Detection

**New constant and global** (after existing `UVC_FRAME_1080P_MJPEG`):

```c
#define UVC_FRAME_4K_MJPEG    4  /* bFrameIndex=4: 4K (3840×2160) — Logitech MeetUp */

static uint8_t g_cap_max_frame_idx = UVC_FRAME_1080P_MJPEG; /* updated at startup */
```

**Extended `frame_idx_to_dims()`** — add 4K case:

```c
case UVC_FRAME_4K_MJPEG:    *w = 3840; *h = 2160; return;
```

**New `cap_detect_max_mjpeg_idx()`** — call after `open(cap_dev)`, before `cap_init()`:

```c
static void cap_detect_max_mjpeg_idx(void)
{
    struct v4l2_frmsizeenum fse = {0};
    fse.pixel_format = V4L2_PIX_FMT_MJPEG;
    uint8_t best = UVC_FRAME_480P_MJPEG;
    for (fse.index = 0; ioctl(g_cap_fd, VIDIOC_ENUM_FRAMESIZES, &fse) == 0; fse.index++) {
        uint32_t w = (fse.type == V4L2_FRMSIZE_TYPE_DISCRETE)
                   ? fse.discrete.width : fse.stepwise.max_width;
        uint32_t h = (fse.type == V4L2_FRMSIZE_TYPE_DISCRETE)
                   ? fse.discrete.height : fse.stepwise.max_height;
        if      (w >= 3840 && UVC_FRAME_4K_MJPEG    > best) best = UVC_FRAME_4K_MJPEG;
        else if (w >= 1920 && UVC_FRAME_1080P_MJPEG > best) best = UVC_FRAME_1080P_MJPEG;
        else if (w >= 1280 && UVC_FRAME_720P_MJPEG  > best) best = UVC_FRAME_720P_MJPEG;
    }
    g_cap_max_frame_idx = best;
}
```

**Updated `GET_MAX`/`GET_DEF`** — use `g_cap_max_frame_idx`:

```c
p.bFrameIndex = g_cap_max_frame_idx;
frame_idx_to_dims(g_cap_max_frame_idx, &mw, &mh);
p.dwMaxVideoFrameSize = mw * mh;
```

**COMMIT clamp** — in `UVC_EVENT_DATA` handler before accepting host's `bFrameIndex`:

```c
if (hc.bFrameIndex > g_cap_max_frame_idx) {
    printf("[OUT] COMMIT clamp: bFrameIndex %u → %u (camera max)\n",
           hc.bFrameIndex, g_cap_max_frame_idx);
    hc.bFrameIndex = g_cap_max_frame_idx;
}
```

---

## 4. Supported Cameras

| Camera | VID:PID | Max MJPEG | `g_cap_max_frame_idx` | USB Speed |
|--------|---------|-----------|----------------------|-----------|
| Jieli U20 (original) | 1124:2925 | 1920×1080 | 3 | USB2 HS |
| Logitech MeetUp | 046D:0866 | 3840×2160 | 4 | USB3 SS |

Adding a new camera requires no code change — `cap_detect_max_mjpeg_idx()` auto-detects at runtime.

---

## 5. Build & Deploy

```powershell
# Cross-compile for aarch64 Android (run from repo root on Windows)
zig cc -target aarch64-linux-musl -static -O2 -o uvc_camera_forward uvc_camera_forward.c

# Push and restart (device must be in Ethernet ADB state)
adb -s 192.168.10.1:5555 push uvc_camera_forward /data/local/tmp/
adb -s 192.168.10.1:5555 push setup_uvc.sh /data/local/tmp/
```

Or use `start-wired-roomdock.ps1` for the full deploy + restart flow.

---

## 6. Verification

```bash
# On device after stream starts — check detected camera max
grep "detected max MJPEG" /data/local/tmp/uvc_stream.log
# Expected (MeetUp): [CAP] detected max MJPEG: 3840x2160 (bFrameIndex=4)
# Expected (Jieli):  [CAP] detected max MJPEG: 1920x1080 (bFrameIndex=3)

# Check negotiated resolution after Windows opens the camera
grep "resolution:" /data/local/tmp/uvc_stream.log | tail -1
# Expected: [OUT] resolution: 1920x1080 → 3840x2160 (bFrameIndex=4)
```

On Windows: open Camera app or Teams — should show 3840×2160 in "Camera settings".

---

## 7. Known Constraints

- 4K MJPEG requires **USB3 SuperSpeed** on the camera-side USB-A port — USB2 cameras (Jieli U20) cannot produce 4K regardless of descriptor
- Host Windows must select 4K; some apps (Teams preview) default to lower resolution for bandwidth reasons
- `dwMaxVideoFrameBufferSize = 16588800` (3840×2160×2) must be set in `setup_uvc.sh` **before** `ln -s` symlink — cannot be changed after the function is linked into a config

---

## 8. Related Skills

- [`skill-adb-gadget`](../skill-adb-gadget/SKILL.md) — ADB dual transport for safe deploy/restart
- [`skill-usb-gadget-debug`](../skill-usb-gadget-debug/SKILL.md) — verify Windows sees bFrameIndex=4 in device descriptor
- [`skill-usb-gadget-monitor`](../skill-usb-gadget-monitor/SKILL.md) — real-time UVC stream resolution display
