# Usage: run from mlx-api-server-whisper/ directory
#   python gen_stage_gt.py 2357_2025_q3
#   python gen_stage_gt.py 2357_2025_q3 2357_2025_q4
#   python gen_stage_gt.py --merge-only 2357_2025_q4   # merge Draft SRTs only, skip stage cut
#
# Outputs:
#   GroundTrue/{stem}_turboscribe.srt           — merged full SRT (from Draft segments)
#   GroundTrue/{stem}_stage{N}_turboscribe.srt  — stage GT SRT（相對時間戳，從 00:00 起算）
#   GroundTrue/{stem}_stage{N}.m4a              — stage 音訊切段（committed to git）
#
# Each stage defines an absolute [start, end] in seconds from audio start.
# Stages are consecutive (non-overlapping); stage0/1/2 each start from the previous end.
#
# Draft SRT naming convention:
#   GroundTrue/Draft/{stem}_turboscribe-{start_mmss}-{end_mmss}.srt
#   where start/end are MMSS (e.g. 0000, 2956, 5947)

import io, json, re, subprocess, sys
from pathlib import Path

# Fix Windows cp1252 stdout for Unicode characters
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Stage window definitions (absolute seconds from audio start) ──────────────
# Each stage: {"start": int, "end": int}  (seconds)
STAGE_WINDOWS = {
    "2357_2025_q3": {
        # stage0/1/2 are consecutive, aligned to clause boundaries
        # stage0: 21:02–23:07  (~2:05, presentation closing section)
        # stage1: 23:07–32:58  (~9:51, Q&A Q1–Q2)
        # stage2: 32:58–53:09  (~20:11, Q&A Q3–end, audio end)
        "stages": {
            "stage0": {"start": 21*60+2,   "end": 23*60+7},
            "stage1": {"start": 23*60+7,   "end": 32*60+58},
            "stage2": {"start": 32*60+58,  "end": 53*60+9},
        }
    },
    "2357_2024_q4": {
        # stage0: 23:05–25:09  (~2:04, presentation closing — sustainability section)
        # stage1: 25:09–35:13  (~10:04, Q&A Q1–Q2)
        # stage2: 35:13–52:39  (~17:26, Q&A Q3–end, audio end)
        "stages": {
            "stage0": {"start": 23*60+5,  "end": 25*60+9},
            "stage1": {"start": 25*60+9,  "end": 35*60+13},
            "stage2": {"start": 35*60+13, "end": 52*60+39},
        }
    },
    "2357_2025_q4": {
        # Consecutive non-overlapping stages, aligned to clause boundaries
        # stage0: 27:43–29:36  (~1:53, presentation closing — AI Supercomputer section)
        # stage1: 29:36–39:36  (~10:00, AIoT section → Q&A Q1)
        # stage2: 39:36–59:46  (~20:10, Q&A Q2–end, audio end)
        "stages": {
            "stage0": {"start": 27*60+43, "end": 29*60+36},
            "stage1": {"start": 29*60+36, "end": 39*60+36},
            "stage2": {"start": 39*60+36, "end": 59*60+46},
        }
    },
    "2382_2025_q3": {
        # stage0: 11:13–13:30  (~2:17, Carol closing — GPU/2026 outlook → Q&A handover)
        # stage1: 13:30–23:03  (~9:33, Q&A Q1 Carrie + Q2 Albert JP Morgan)
        # stage2: 23:03–43:03  (~20:00, Q&A Q3 Alex Bernstein + Q4 Angela + ...)
        # NOTE: stage2 end boundary estimated — refine after segment 2 SRT is done
        "stages": {
            "stage0": {"start": 11*60+13, "end": 13*60+30},
            "stage1": {"start": 13*60+30, "end": 23*60+3},
            "stage2": {"start": 23*60+3,  "end": 43*60+3},
        }
    },
    "8299_2025_q4": {
        # stage0: 34:35–36:52  (~2:17, CEO closing — revenue mix summary → Q&A handover)
        # stage1: 36:52–46:44  (~9:52, Q&A Q1 LTA/NAND supply + Q2 Simon Wu Bank of America start)
        # stage2: 46:44–72:25  (~25:41, Q&A Q2 continued + Q3–end, audio end)
        "stages": {
            "stage0": {"start": 34*60+35, "end": 36*60+52},
            "stage1": {"start": 36*60+52, "end": 46*60+44},
            "stage2": {"start": 46*60+44, "end": 72*60+25},
        }
    },
}

AUDIO_ROOT        = Path(r"C:\Users\WJLEE\SynologyDrive\NAS\github.com\InvestorConference")
DRAFT_DIR         = Path("GroundTrue/Draft")
GT_DIR            = Path("GroundTrue")
DURATIONS_JSON    = AUDIO_ROOT / "audio_durations.json"
GAP_WARN_SEC      = 60   # warn if consecutive cues are more than this many seconds apart
COVERAGE_WARN_SEC = 120  # warn if SRT ends this many seconds before audio ends


def to_ts(sec: float) -> str:
    m = int(sec // 60)
    s = int(sec % 60)
    ms = int(round((sec % 1) * 1000))
    return f"({m:02d}:{s:02d}.{ms:03d})"


def mmss_to_sec(mmss: str) -> int:
    """Convert MMSS string (e.g. '2956') to seconds (1796)."""
    mmss = mmss.zfill(4)
    return int(mmss[:-2]) * 60 + int(mmss[-2:])


def _load_audio_duration(stem: str) -> int | None:
    """Return expected audio duration in seconds from audio_durations.json, or None."""
    if not DURATIONS_JSON.exists():
        return None
    stock_id = stem.split("_")[0]
    data = json.loads(DURATIONS_JSON.read_text(encoding="utf-8"))
    for ext in (".mp3", ".m4a", ".wav"):
        key = f"{stock_id}/{stem}{ext}"
        if key in data:
            return int(data[key])
    return None


def validate_srt(stem: str, entries: list[tuple[int, str]]) -> None:
    """
    Check merged SRT entries for:
      1. Large gaps between consecutive cues (> GAP_WARN_SEC)
      2. SRT ending well before the known audio duration (> COVERAGE_WARN_SEC short)
    Prints ⚠ WARNING lines; does not raise.
    """
    warnings = []

    # Gap check
    for i in range(1, len(entries)):
        gap = entries[i][0] - entries[i - 1][0]
        if gap > GAP_WARN_SEC:
            t_prev = to_ts(entries[i - 1][0])
            t_next = to_ts(entries[i][0])
            warnings.append(
                f"  ⚠ Gap {gap//60}m{gap%60:02d}s between cue {t_prev} and {t_next} "
                f"(text before gap: 「{entries[i-1][1][:30]}」)"
            )

    # Coverage check
    audio_dur = _load_audio_duration(stem)
    if audio_dur and entries:
        srt_end  = entries[-1][0]
        shortfall = audio_dur - srt_end
        if shortfall > COVERAGE_WARN_SEC:
            warnings.append(
                f"  ⚠ SRT ends at {to_ts(srt_end)} but audio is {to_ts(audio_dur)} "
                f"— {shortfall//60}m{shortfall%60:02d}s of audio may be uncovered"
            )

    if warnings:
        print(f"\n{'='*60}")
        print(f"  VALIDATION WARNINGS for {stem}_turboscribe.srt:")
        for w in warnings:
            print(w)
        print(f"{'='*60}\n")
    else:
        print(f"  [validate] ✓ No gaps > {GAP_WARN_SEC}s; SRT coverage looks complete.")


def merge_draft_srts(stem: str) -> Path:
    """
    Scan Draft/ for {stem}_turboscribe-{start}-{end}.srt files,
    sort by start offset, apply absolute timestamps, and write merged SRT to GroundTrue/.
    Returns path to merged SRT.
    """
    pat = re.compile(rf"^{re.escape(stem)}_turboscribe-(\d{{4}})-(\d{{4}})\.srt$")
    parts = []
    for f in sorted(DRAFT_DIR.glob(f"{stem}_turboscribe-*-*.srt")):
        m = pat.match(f.name)
        if m:
            parts.append((mmss_to_sec(m.group(1)), f))

    if not parts:
        raise FileNotFoundError(f"No Draft SRT segments found for {stem} in {DRAFT_DIR}")

    parts.sort(key=lambda x: x[0])
    all_entries = []
    for offset_sec, path in parts:
        content = path.read_text(encoding="utf-8")
        tokens  = re.findall(r'\((\d+):(\d{2})\)\s*(.*?)(?=\s*\(\d+:\d{2}\)|$)', content, re.DOTALL)
        for m_ts, s_ts, text in tokens:
            text = text.strip()
            if text:
                abs_sec = int(m_ts) * 60 + int(s_ts) + offset_sec
                all_entries.append((abs_sec, text))
        print(f"  [merge] {path.name}: {len(tokens)} cues, offset={offset_sec}s")

    # Deduplicate: segment boundaries produce the same absolute timestamp twice
    # (end of segment N and start of segment N+1 both map to the same second).
    # Keep the first occurrence — it comes from the segment with full prior context;
    # the duplicate is from the next segment's cold-start, often hallucinated text.
    seen: set[int] = set()
    deduped: list[tuple[int, str]] = []
    for abs_sec, text in all_entries:
        if abs_sec not in seen:
            seen.add(abs_sec)
            deduped.append((abs_sec, text))
    removed = len(all_entries) - len(deduped)
    if removed:
        print(f"  [merge] deduped {removed} boundary cue(s) with duplicate timestamps")
    all_entries = deduped

    merged_text = "\n".join(f"{to_ts(s)} {t}" for s, t in all_entries) + "\n"
    out = GT_DIR / f"{stem}_turboscribe.srt"
    out.write_text(merged_text, encoding="utf-8")
    first = to_ts(all_entries[0][0]) if all_entries else "?"
    last  = to_ts(all_entries[-1][0]) if all_entries else "?"
    print(f"  [merge] -> {out.name}  ({len(all_entries)} cues, {first}-{last})")
    validate_srt(stem, all_entries)
    return out

def gen_stage_gt(stem: str) -> None:
    cfg       = STAGE_WINDOWS[stem]
    stock_id  = stem.split("_")[0]
    audio_src = next(
        (AUDIO_ROOT / stock_id / f"{stem}{ext}" for ext in (".m4a", ".wav", ".mp3")
         if (AUDIO_ROOT / stock_id / f"{stem}{ext}").exists()),
        AUDIO_ROOT / stock_id / f"{stem}.m4a"  # fallback (will fail with clear ffmpeg error)
    )
    srt_src   = Path("GroundTrue") / f"{stem}_turboscribe.srt"
    gt_dir    = Path("GroundTrue")

    entries = []
    for line in srt_src.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\((\d+):(\d+)\)\s*(.*)", line.strip())
        if m:
            entries.append((int(m.group(1)) * 60 + int(m.group(2)), m.group(3)))

    stages_list = list(cfg["stages"].items())
    last_stage  = stages_list[-1][0]

    for stage, win in stages_list:
        start_sec, end_sec = win["start"], win["end"]
        dur = end_sec - start_sec
        # Exclude the end boundary (seam point belongs to the next stage's start).
        # Only the final stage uses <= so its last entry is included.
        if stage == last_stage:
            window = [(t, txt) for t, txt in entries if start_sec <= t <= end_sec]
        else:
            window = [(t, txt) for t, txt in entries if start_sec <= t < end_sec]

        # SRT — relative timestamps (from stage start = 00:00)
        srt_lines = [f"{to_ts(t - start_sec)} {txt}" for t, txt in window]
        srt_path  = gt_dir / f"{stem}_{stage}_turboscribe.srt"
        srt_path.write_text("\n".join(srt_lines) + "\n", encoding="utf-8")
        print(f"SRT   {srt_path.name}  ({len(srt_lines)} lines, {start_sec//60:02d}:{start_sec%60:02d}-{end_sec//60:02d}:{end_sec%60:02d})")

        # Audio — ffmpeg cut
        hh, rem = divmod(start_sec, 3600)
        mm, ss  = divmod(rem, 60)
        audio_path = gt_dir / f"{stem}_{stage}.m4a"
        # Re-encode to aac when source is not already m4a/aac; otherwise stream-copy
        if audio_src.suffix.lower() in (".wav", ".mp3"):
            codec_args = ["-c:a", "aac", "-b:a", "128k"]
        else:
            codec_args = ["-c", "copy"]
        cmd = ["ffmpeg", "-y", "-i", str(audio_src),
               "-ss", f"{hh:02d}:{mm:02d}:{ss:02d}", "-t", str(dur),
               *codec_args, str(audio_path)]
        r = subprocess.run(cmd, capture_output=True)
        status = "OK" if r.returncode == 0 else f"ERR {r.returncode}"
        print(f"Audio {audio_path.name}  {status}")

if __name__ == "__main__":
    args = sys.argv[1:]
    merge_only = "--merge-only" in args
    args = [a for a in args if not a.startswith("--")]

    for stem in args:
        print(f"\n=== {stem} ===")
        # Step 1: merge Draft SRTs if segments exist
        draft_segs = list(DRAFT_DIR.glob(f"{stem}_turboscribe-*-*.srt"))
        if draft_segs:
            print(f"Merging {len(draft_segs)} Draft SRT segment(s)...")
            merge_draft_srts(stem)
        else:
            print("No Draft segments found — using existing GroundTrue SRT.")

        # Step 2: generate stage GT files (unless --merge-only)
        if not merge_only:
            if stem not in STAGE_WINDOWS:
                print(f"[SKIP] {stem} not in STAGE_WINDOWS — add entry to generate stage GTs.")
                continue
            gen_stage_gt(stem)
