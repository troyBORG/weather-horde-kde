# Instructions for coding assistants

Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the relevant task documentation before changing code. Keep the README focused on installation and everyday use; put engineering detail in `docs/` and assistant-specific operating rules here.

## Scope and consent

- Source edits, commits, packages and GitHub releases are not deployment. Do not install into live Plasma, restart services, reload the shell, change settings, generate images or apply wallpapers without separate owner approval.
- Work in a disposable checkout, never the running controller tree. Preserve unrelated work and private recovery material.
- Do not borrow another user's session bus or token, run owner helpers as root, weaken trust checks or use testing overrides to make acceptance pass.
- Preserve the separation between enabling controller capabilities and granting automation consent. Updates must not silently change Auto mode, targets, interval, location or calendar settings.

## Validation

- Follow [isolated validation](docs/testing.md) and [CI reproduction](docs/ci-releases.md). Build the native package before running the complete suite. A missing dependency or skipped native test is not a full pass.
- Fixture tests must not reach the real graphical user's service manager, render API or wallpaper bus. A different XDG_CONFIG_HOME alone does not isolate that manager.
- For behavior changes, reproduce the defect with a failing regression before changing implementation. Retain safety coverage.
- Report actual executed counts, failures, errors and skips. Keep historical test results distinct from checks of the current commit.
- Review `git diff --check`, staged paths and artifact boundaries before committing. Never commit private receipts, tokens, logs, screenshots, generated wallpapers, model weights or recovery Git/index data.

## Claims and documentation

- Distinguish the source commit, packaged revision, authenticated loaded controller revision and loaded widget. None proves the others.
- After an approved deployment, verify loaded capabilities/revision and widget reconnection. Actual render/apply behavior and login persistence require their own acceptance checks.
- Prompt tests and synthetic fixture images do not prove generated image quality or visible wallpaper application.
- Keep current behavior separate from old design notes. The current catch-up policy is [requested refresh](docs/requested-refresh-0.1.11.md), not the superseded 60-second grace design.
- Do not invent historical commits, release dates, licensing grants or human authorship. Preserve Astronomy Engine license and provenance.

## Cleanup boundaries

Trace imports, subprocess calls, packaging, CI and test references before deleting a helper. A script with “deploy” in its name is not necessarily obsolete: the persistent installer and hash-pinned owner delivery are maintained release paths. Preserve recovery behavior unless it has a verified replacement; retire one-off release orchestration separately from shared implementation.
