import os
import re
from pathlib import Path

def parse_md_to_srt(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    metadata = {}
    transcript = []
    
    # Simple regex for metadata table: | **Key** | `Value` |
    meta_regex = re.compile(r"\|\s*\*\*([^*]+)\*\*\s*\|\s*`?([^|`]+)`?\s*\|")
    # Simple regex for timestamps: **[mm:ss → mm:ss]** text
    ts_regex = re.compile(r"\*\*\[(\d{2}:\d{2}) → \d{2}:\d{2}\]\*\*\s*(.*)")

    for line in lines:
        line = line.strip()
        
        # Match metadata
        meta_match = meta_regex.search(line)
        if meta_match:
            key = meta_match.group(1).strip()
            value = meta_match.group(2).strip()
            # Normalize keys to match the new spec
            if key == "Transcription time": key = "Transcription-Time"
            if key == "Model Repo": key = "Model-Repo"
            if key == "Now": key = "Generated-At"
            metadata[key] = value
            continue
        
        # Match transcript
        ts_match = ts_regex.search(line)
        if ts_match:
            time_start = ts_match.group(1)
            text = ts_match.group(2).strip()
            transcript.append(f"({time_start}) {text}")

    # Build new SRT content
    output = ["[METADATA]"]
    for key in ["Source", "Provider", "Model", "Model-Repo", "Duration", "Transcription-Time", "RTF", "Generated-At"]:
        if key in metadata:
            val = metadata[key]
            # Strip RTF extra labels
            if key == "RTF":
                val = val.split(" ")[0].strip("`")
            output.append(f"{key}: {val}")
    
    output.append("---")
    output.extend(transcript)
    
    return "\n".join(output)

def main():
    sandbox_dir = Path("Mac-mini/mlx-api-server-whisper/whisper-sandbox")
    md_files = list(sandbox_dir.glob("*.md"))
    
    # Exclude report files
    md_files = [f for f in md_files if "_cer_report" not in f.name and "_key_cer_detail" not in f.name and "leaderboard" not in f.name]

    print(f"Found {len(md_files)} files to convert.")
    
    for md_file in md_files:
        srt_file = md_file.with_suffix(".srt")
        print(f"Converting: {md_file.name} -> {srt_file.name}")
        
        try:
            srt_content = parse_md_to_srt(md_file)
            with open(srt_file, "w", encoding="utf-8") as f:
                f.write(srt_content)
            # Remove old md file after successful conversion
            # os.remove(md_file) 
        except Exception as e:
            print(f"  Error converting {md_file.name}: {e}")

if __name__ == "__main__":
    main()
