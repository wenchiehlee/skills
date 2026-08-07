import sys
import re
from pathlib import Path

def convert_yt_to_gt(stem: str):
    """
    Convert standard SRT (Yating style) to simplified GT SRT format.
    Input:  GroundTrue/{stem}_YT.srt  (HH:MM:SS,mmm --> ...)
    Output: GroundTrue/{stem}_GT.srt  ((MM:SS.mmm) text)
    """
    yt_path = Path("GroundTrue") / f"{stem}_YT.srt"
    gt_path = Path("GroundTrue") / f"{stem}_GT.srt"
    
    if not yt_path.exists():
        # Try relative to current dir if not in GroundTrue/
        yt_path = Path(f"{stem}_YT.srt")
        gt_path = Path(f"{stem}_GT.srt")
        
    if not yt_path.exists():
        print(f"Error: {yt_path} not found.")
        return

    print(f"Converting {yt_path}...")
    content = yt_path.read_text(encoding="utf-8")
    # Normalize line endings
    content = content.replace('\r\n', '\n')
    
    # Split by standard SRT block separator (double newline)
    blocks = re.split(r'\n\n+', content.strip())
    
    gt_lines = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
            
        # Line 0: Index (ignored)
        # Line 1: Timestamps (HH:MM:SS,mmm --> HH:MM:SS,mmm)
        ts_line = lines[1]
        ts_match = re.search(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", ts_line)
        if not ts_match:
            continue
            
        hh, mm, ss, ms = map(int, ts_match.groups())
        
        # Convert hours to total minutes
        total_mm = hh * 60 + mm
        
        # Format: (MM:SS.mmm) - Always include milliseconds for precision
        ts_str = f"({total_mm:02d}:{ss:02d}.{ms:03d})"
            
        # Join the remaining lines as text content
        text = " ".join(lines[2:]).strip()
        if text:
            gt_lines.append(f"{ts_str} {text}")
            
    gt_path.write_text("\n".join(gt_lines), encoding="utf-8")
    print(f"Success: Generated {gt_path} ({len(gt_lines)} lines)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_yt_to_gt.py <stem>")
        print("Example: python convert_yt_to_gt.py 2308_2025_q4")
    else:
        for arg in sys.argv[1:]:
            # Strip file extensions if provided
            stem = Path(arg).stem.replace("_YT", "").replace("_GT", "")
            convert_yt_to_gt(stem)
