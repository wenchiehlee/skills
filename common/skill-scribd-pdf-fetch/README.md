# Scribd PDF Fetch Skill

An agent skill that wraps the external `scribd-downloader` command to export a Scribd document as a local PDF. Use it only for documents you are authorized to access and download; follow applicable copyright law and Scribd's terms.

## Install from npm

From the project where you want the skill installed:

```bash
npm install --save-dev @wenchiehlee1020/skill-scribd-pdf-fetch
npx skills experimental_sync -a codex -y
```

For Claude Code, replace `-a codex` with `-a claude-code`. The `skills` CLI currently labels `experimental_sync` as experimental.

## Requirements

- Python 3.10 or later
- Git
- Google Chrome
- The Python dependencies required by the upstream downloader (installed into its checkout with the skill script's `--install-deps` option)

The npm package contains this skill's instructions and wrapper only. It does not include the upstream `scribd-downloader` source, which the wrapper clones at runtime. Review that upstream project's licensing and code before use.

## Publish updates

The repository workflow `.github/workflows/publish-scribd-pdf-fetch.yml` publishes this package. The repository Actions secret `NPM_TOKEN` must be configured. Increment the version in `package.json`, then push a tag matching `skill-scribd-pdf-fetch-v<version>` (for example, `skill-scribd-pdf-fetch-v1.0.1`). The workflow checks that the tag matches the package version and publishes with provenance. A maintainer can also run it manually from GitHub Actions by selecting a ref.

## Run

After installing the skill in a compatible agent, follow its `SKILL.md` instructions. The wrapper can also be run directly:

```bash
python path/to/skill-scribd-pdf-fetch/scripts/scribd_pdf_fetch.py "<scribd-url>" --install-deps
```
