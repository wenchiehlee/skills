"""audio_utils.py — Audio file resolver for Whisper pipeline.

Resolution order for get_audio_path():
  1. Local repo path   ({stock_id}/{stem}.m4a|mp3)
  2. Cache dir         (tmp/{stem}.m4a|mp3)
  3. GitHub Releases   (fetched from InvestorConference manifest)
"""
import json
import os
import requests
from pathlib import Path

_IC_MANIFEST_URL = (
    "https://raw.githubusercontent.com/wenchiehlee-money/InvestorConference"
    "/main/audio_manifest.json"
)


def _fetch_ic_manifest() -> dict:
    try:
        r = requests.get(_IC_MANIFEST_URL, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[audio] Could not fetch IC manifest: {e}")
        return {}


def _download_url(url: str, dest_path: Path) -> Path | None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[audio] Downloading {dest_path.name} from GitHub Releases …", end=" ", flush=True)
    try:
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)
        size_mb = dest_path.stat().st_size / 1_048_576
        print(f"✓ ({size_mb:.1f} MB)")
        return dest_path
    except Exception as e:
        print(f"\n[audio] Download failed: {e}")
        dest_path.unlink(missing_ok=True)
        return None


class AudioLoader:
    def __init__(self):
        self.manifest_path = Path(__file__).parent / "audio_manifest.json"

    def get_audio_path(self, stock_id: str, year: str, quarter: str) -> str | None:
        stem = f"{stock_id}_{year}_q{quarter}"
        cache_dir = Path(__file__).parent / "tmp"

        # 1 & 2 — local paths
        for ext in (".m4a", ".mp3"):
            for local_path in [
                Path(__file__).parent / stock_id / f"{stem}{ext}",
                cache_dir / f"{stem}{ext}",
            ]:
                if local_path.exists():
                    return str(local_path)

        # 3 — GitHub Releases
        ic_manifest = _fetch_ic_manifest()
        if stem in ic_manifest:
            url = ic_manifest[stem]
            if url.startswith("https://"):
                dest = cache_dir / url.split("/")[-1]
                result = _download_url(url, dest)
                if result:
                    return str(result)

        print(f"[audio] Audio file for {stem} not found locally or on GitHub Releases.")
        return None


# Shared instance
audio_mgr = AudioLoader()

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == "get":
        # python audio_utils.py get 2308 2025 4
        path = audio_mgr.get_audio_path(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"Audio path: {path}")
