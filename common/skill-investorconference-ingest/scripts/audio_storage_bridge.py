import json
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

_curr = Path(__file__).resolve()
_root = None
for p in _curr.parents:
    if (p / "audio_manifest.json").exists() or (p / ".git").exists():
        _root = p
        break
if not _root:
    _root = _curr.parents[3]
load_dotenv(_root / ".env")

_REPO           = "wenchiehlee-money/InvestorConference"
_GH_RELEASE_TAG = "audio-files"
_GH_API         = "https://api.github.com"


def _gh_headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def _get_or_create_release(token: str) -> dict:
    r = requests.get(f"{_GH_API}/repos/{_REPO}/releases/tags/{_GH_RELEASE_TAG}",
                     headers=_gh_headers(token))
    if r.status_code == 200:
        return r.json()
    r = requests.post(f"{_GH_API}/repos/{_REPO}/releases",
                      headers=_gh_headers(token),
                      json={"tag_name": _GH_RELEASE_TAG,
                            "name": "Audio Files",
                            "body": "Investor conference call audio (CORS-friendly streaming).",
                            "draft": False, "prerelease": False})
    r.raise_for_status()
    return r.json()


def _upload_gh_asset(token: str, audio_path: Path) -> str:
    release = _get_or_create_release(token)
    for asset in release.get("assets", []):
        if asset["name"] == audio_path.name:
            print(f"[gh-release] Asset already exists. Deleting old asset: {asset['name']}...")
            del_r = requests.delete(asset["url"], headers=_gh_headers(token))
            del_r.raise_for_status()
            break

    suffix_map = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav"}
    content_type = suffix_map.get(audio_path.suffix.lower(), "application/octet-stream")
    upload_url = release["upload_url"].replace("{?name,label}", f"?name={audio_path.name}")
    headers = {**_gh_headers(token), "Content-Type": content_type}
    with open(audio_path, "rb") as f:
        r = requests.post(upload_url, headers=headers, data=f)
        r.raise_for_status()
    url = r.json()["browser_download_url"]
    print(f"[gh-release] Uploaded: {url}")
    return url


def upload_and_update_manifest(repo: Path, audio_path: Path):
    """Upload *audio_path* to GitHub Releases and store the URL in audio_manifest.json."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("REPO_FILE_SYNC_ZHONGZHENG782_MONEY") or os.environ.get("REPO_FILE_SYNC_WENCHIEHLEE_MONEY")
    if not token:
        raise ValueError("GITHUB_TOKEN, REPO_FILE_SYNC_ZHONGZHENG782_MONEY or REPO_FILE_SYNC_WENCHIEHLEE_MONEY must be set")

    manifest_path = repo / "audio_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except: pass

    existing_url = manifest.get(audio_path.stem)
    try:
        url = _upload_gh_asset(token, audio_path)
    except Exception as e:
        print(f"[DEBUG-UPLOAD] Failed to upload {audio_path.name}: {e}")
        import traceback
        traceback.print_exc()
        if existing_url:
            print(f"[gh-release] Upload failed but asset exists in manifest. Fallback to existing URL: {existing_url}")
            url = existing_url
        elif "403" in str(e) or "Forbidden" in str(e):
            fallback_url = f"https://github.com/{_REPO}/releases/download/{_GH_RELEASE_TAG}/{audio_path.name}"
            print(f"[gh-release] Upload 403 Forbidden. Using standard fallback URL: {fallback_url}")
            url = fallback_url
        else:
            raise e

    manifest[audio_path.stem] = url
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    # audio_path.unlink(missing_ok=True)
    return url, manifest_path


# Keep old name as alias so existing ingest.py calls still work
def upload_to_gdrive_and_update_manifest(repo: Path, stock_id: str, audio_path: Path):
    url, manifest_path = upload_and_update_manifest(repo, audio_path)
    return url, manifest_path


def get_audio_link_for_readme(repo: Path, stock_id: str, year: str, quarter: str, audio_min: float):
    stem = f"{stock_id}_{year}_q{quarter}"
    manifest_path = repo / "audio_manifest.json"
    dur_str = f"{audio_min:.1f} min" if audio_min else "無"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if stem in manifest:
                val = manifest[stem]
                url = val if val.startswith("https://") else \
                      f"https://drive.google.com/uc?export=download&id={val}"
                return f"[{dur_str}]({url})"
        except: pass

    for suffix in (".m4a", ".mp3", ".wav", ".mp4"):
        local_audio = repo / stock_id / f"{stem}{suffix}"
        if local_audio.exists():
            return f"[{dur_str}]({stock_id}/{stem}{suffix})"

    return dur_str
