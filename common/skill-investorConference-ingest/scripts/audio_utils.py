import os
import json
import re
from pathlib import Path

_curr = Path(__file__).resolve()
REPO_ROOT = None
for p in _curr.parents:
    if (p / "audio_manifest.json").exists() or (p / ".git").exists():
        REPO_ROOT = p
        break
if not REPO_ROOT:
    REPO_ROOT = _curr.parents[3]

class AudioLoader:
    def __init__(self):
        self.manifest_path = REPO_ROOT / "audio_manifest.json"
        self.manifest = self._load_manifest()

    def _load_manifest(self):
        if self.manifest_path.exists():
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def _save_manifest(self):
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=4, ensure_ascii=False)

    def get_audio_path(self, stock_id, year, quarter):
        """Transparently get the path to an audio file."""
        filename = f"{stock_id}_{year}_q{quarter}.m4a"
        
        # 1. Check local path (relative to repo root)
        local_path = REPO_ROOT / "data" / stock_id / filename
        if local_path.exists():
            return str(local_path)
        
        # 2. Check cache directory (tmp/)
        cache_path = REPO_ROOT / "tmp" / filename
        if cache_path.exists():
            return str(cache_path)
            
        print(f"Audio file {filename} not found locally.")
        return None

# Instantiate shared loader
audio_mgr = AudioLoader()

if __name__ == "__main__":
    pass
