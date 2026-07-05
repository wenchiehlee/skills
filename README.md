# Skills Registry

This repository is a shared registry for reusable skills collected from multiple
repositories. Its goal is to make skills easy to discover, version, reuse, and
update across projects without copying undocumented or stale skill definitions.

## Goals

- Collect reusable skills from different repositories in one place.
- Preserve clear ownership, source, and version information for every skill.
- Make outdated skill copies detectable in downstream repositories.
- Support automatic updates by fetching the latest approved skill version from
  this repository.
- Deploy skills according to the rules of each target LLM.
- Keep each skill self-contained so it can be reused without depending on the
  original source repository.

## Skill Versioning

Every skill in this registry must be versioned. Versioning allows consumers to
compare their local copy with the registry and detect when a skill is outdated.

Recommended version format:

```text
MAJOR.MINOR.PATCH
```

Version changes should follow these rules:

- `MAJOR`: Breaking changes to behavior, required inputs, file structure, or
  external assumptions.
- `MINOR`: Backward-compatible features, new workflows, or expanded coverage.
- `PATCH`: Fixes, wording improvements, metadata corrections, or small internal
  updates that do not change expected behavior.

Each skill should include metadata that identifies:

- Skill name
- Current version
- Source repository or origin
- Maintainer or owning team
- Short description
- Last updated date
- Compatibility notes, if any

## Suggested Skill Layout

Skills should be grouped by target LLM. Each LLM has its own sub-folder under
`skills/`, and the skills in that folder must follow that LLM's deployment
rules.

```text
skills/
  <llm-name>/
    <skill-name>/
      SKILL.md
      metadata.json
      README.md
      references/
      scripts/
```

Minimum required files:

- `SKILL.md`: The main reusable skill instructions.
- `metadata.json`: Machine-readable metadata used for version checks and update
  automation.

Optional files:

- `README.md`: Human-readable usage notes for the skill.
- `references/`: Supporting documentation, examples, or templates.
- `scripts/`: Helper scripts used by the skill.

Example `metadata.json`:

```json
{
  "name": "example-skill",
  "version": "1.0.0",
  "source": "https://github.com/example/project",
  "maintainer": "example-team",
  "description": "Reusable instructions for an example workflow.",
  "updated_at": "2026-07-05",
  "compatibility": {
    "codex": ">=1.0.0"
  }
}
```

## LLM Deployment Rules

Deployment is organized by LLM-specific folders. A skill should be deployed from
the folder that matches the target LLM runtime, because different LLMs may expect
different filenames, metadata fields, packaging rules, or instruction formats.

For example:

```text
skills/
  codex/
    skill-a/
  claude/
    skill-a/
  gemini/
    skill-a/
```

The same conceptual skill may exist in multiple LLM folders, but each copy must
carry its own version and metadata. If an LLM-specific version diverges from the
shared behavior, update its version independently and document the compatibility
notes in `metadata.json`.

Deployment tooling should:

1. Select the target LLM folder.
2. Validate that each skill follows that LLM's required structure.
3. Compare versions within the selected LLM folder.
4. Install or update only the skills compatible with that target LLM.

## Update Model

Downstream repositories should treat this repository as the source of truth for
shared skills.

A consumer can check for updates by comparing the local skill metadata with the
metadata in this registry:

1. Read the local skill name and version.
2. Fetch the matching skill metadata from this repository.
3. Compare versions.
4. If the registry version is newer, replace or merge the local skill from this
   repository.
5. Record the updated version in the consumer repository.

This makes stale skills visible and gives projects a consistent way to update to
the latest approved skill definition.

## Collection Rules

When adding or updating a skill:

1. Put the skill in a dedicated directory under the correct LLM folder.
2. Include `SKILL.md` and `metadata.json`.
3. Use semantic versioning.
4. Preserve the original source or origin in metadata.
5. Keep the skill self-contained.
6. Follow the deployment rules for the target LLM folder.
7. Document breaking changes by increasing the `MAJOR` version.
8. Avoid unrelated formatting churn when importing a skill from another
   repository.
9. Verify that the skill can be read and reused without private repository
   context.

## Future Automation

This repository is intended to support tooling such as:

- A version checker that reports outdated skills in a consumer repository.
- An updater that fetches the newest skill version from this registry.
- A validation command that checks required files and metadata fields.
- A changelog generator that summarizes skill updates by version.

The first automation target should be a simple command that answers:

```text
Which local skills are outdated compared with this registry?
```

The second target should be:

```text
Update selected local skills to the newest compatible version.
```

## Status

This is the first version of the registry README. The repository structure,
metadata schema, and automation commands may evolve as more skills are collected.
