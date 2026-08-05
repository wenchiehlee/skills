"""
migrate_audio_to_gh_releases.py
────────────────────────────────
For every entry in audio_manifest.json that still holds a bare GDrive file ID
(not a full URL), this script:

  1. Fetches the real filename from GDrive metadata
  2. Downloads the audio to a temp directory
  3. Uploads to the GitHub Release tag "audio-files"
  4. Replaces the bare GDrive ID with the GitHub Release URL in the manifest
  5. Writes the updated manifest after every successful migration
     (safe to re-run if interrupted — already-uploaded assets are skipped)

Usage:
    python migrate_audio_to_gh_releases.py [--dry-run] [--stems 2308_2025_q4 2330_2025_q4 ...]

Requirements:
    GDRIVE_API_CREDENTIALS  – GDrive service-account JSON (env var)
    GDRIVE_AUDIO_FOLDER_ID  – GDrive root folder ID (env var)
    GITHUB_TOKEN            – GitHub PAT or Actions token with contents:write

"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_curr = Path(__file__).resolve()
REPO_ROOT = None
for p in _curr.parents:
    if (p / "audio_manifest.json").exists() or (p / ".git").exists():
        REPO_ROOT = p
        break
if not REPO_ROOT:
    REPO_ROOT = _curr.parents[3]

load_dotenv(REPO_ROOT / ".env")

from audio_storage import AudioStorageClient, GitHubReleasesClient

REPO            = "wenchiehlee-money/InvestorConference"
GH_RELEASE_TAG  = "audio-files"
MANIFEST_PATH   = REPO_ROOT / "audio_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def get_gdrive_filename(gdrive: AudioStorageClient, file_id: str) -> str:
    meta = gdrive.service.files().get(fileId=file_id, fields="name").execute()
    return meta["name"]


def migrate_one(stem: str, file_id: str,
                gdrive: AudioStorageClient,
                gh: GitHubReleasesClient,
                tmp_dir: Path,
                dry_run: bool) -> str | None:
    """Download from GDrive, upload to GH Releases. Returns new URL or None on failure."""
    try:
        filename = get_gdrive_filename(gdrive, file_id)
    except Exception as e:
        print(f"  ✗ Could not get GDrive metadata for {stem}: {e}")
        return None

    local_path = tmp_dir / filename
    print(f"  ↓ Downloading {filename} from GDrive …", end=" ", flush=True)

    if dry_run:
        print("(dry-run, skipped)")
        return f"https://github.com/{REPO}/releases/download/{GH_RELEASE_TAG}/{filename}"

    try:
        gdrive.download_audio(file_id, local_path)
        print(f"✓ ({local_path.stat().st_size / 1_048_576:.1f} MB)")
    except Exception as e:
        print(f"\n  ✗ Download failed: {e}")
        return None

    print(f"  ↑ Uploading {filename} to GitHub Release …", end=" ", flush=True)
    try:
        url = gh.upload_audio(local_path)
        print(f"✓")
    except Exception as e:
        print(f"\n  ✗ Upload failed: {e}")
        local_path.unlink(missing_ok=True)
        return None

    local_path.unlink(missing_ok=True)
    return url


def main():
    parser = argparse.ArgumentParser(description="Migrate GDrive audio IDs → GitHub Release URLs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without downloading/uploading")
    parser.add_argument("--stems", nargs="+", metavar="STEM",
                        help="Only migrate specific stems (default: all bare GDrive IDs)")
    args = parser.parse_args()

    manifest = load_manifest()

    # Identify entries that still have bare GDrive IDs
    to_migrate = {
        stem: val
        for stem, val in manifest.items()
        if not val.startswith("https://")
    }

    if args.stems:
        unknown = set(args.stems) - set(manifest)
        if unknown:
            print(f"Unknown stems: {unknown}", file=sys.stderr)
            sys.exit(1)
        to_migrate = {s: to_migrate[s] for s in args.stems if s in to_migrate}
        already_done = [s for s in args.stems if s not in to_migrate]
        if already_done:
            print(f"Already migrated (skipping): {already_done}")

    if not to_migrate:
        print("Nothing to migrate — all entries already have GitHub Release URLs.")
        return

    # Resolve GitHub token: GITHUB_TOKEN → REPO_FILE_SYNC_WENCHIEHLEE_MONEY
    if not os.environ.get("GITHUB_TOKEN"):
        fallback = os.environ.get("REPO_FILE_SYNC_ZHONGZHENG782_MONEY") or os.environ.get("REPO_FILE_SYNC_WENCHIEHLEE_MONEY")
        if fallback:
            os.environ["GITHUB_TOKEN"] = fallback
        elif not args.dry_run:
            print("Error: GITHUB_TOKEN, REPO_FILE_SYNC_ZHONGZHENG782_MONEY or REPO_FILE_SYNC_WENCHIEHLEE_MONEY must be set in .env",
                  file=sys.stderr)
            sys.exit(1)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Migrating {len(to_migrate)} entries …\n")

    gdrive = AudioStorageClient()
    gh     = GitHubReleasesClient(repo=REPO, tag=GH_RELEASE_TAG)

    ok = fail = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for stem, file_id in to_migrate.items():
            print(f"[{stem}]")
            url = migrate_one(stem, file_id, gdrive, gh, tmp_dir, args.dry_run)
            if url:
                if not args.dry_run:
                    manifest[stem] = url
                    save_manifest(manifest)          # persist after every success
                print(f"  → {url}\n")
                ok += 1
            else:
                fail += 1
                print()

    print(f"Done. {ok} migrated, {fail} failed.")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
