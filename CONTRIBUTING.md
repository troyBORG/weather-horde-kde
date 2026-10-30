# Contributing

Licensing/attribution approval is pending; do not assume permission to relicense original work or third-party code. Preserve Astronomy Engine notices. Describe AI assistance accurately.

Use focused branches: `feat/<topic>`, `fix/<issue>`, `test/<coverage>`, `docs/<topic>`. Write the intended failing regression first for behavior changes, show RED then GREEN, and run the complete relevant suite. Do not remove safety cases just to reduce test counts. Keep portability work separate from publication cleanup.

Use ordinary merges when retaining individual commits and their dates matters. Squashing creates a new single commit; rebase/cherry-pick changes object identity and usually committer time. Never reconstruct fictional historic branches or backdate a baseline. Do not force-push published history without separate approval.

## Isolated validation

Read [testing](docs/testing.md) before running anything. Use a disposable tree as a non-graphical-owner account, not the live controller checkout. Build package/native harness first. Never let fixtures call a real graphical owner's `systemctl --user enable`, render API or wallpaper bus; persistent-installer tests use explicit command adapters and temporary target links. A changed XDG_CONFIG_HOME alone does not isolate a real user manager.

Record collected/executed methods, errors, failures, skips, exact source manifest, environment and logs. Subtests are not extra methods. A dependency skip is not a full-suite pass. Tests may read telemetry and model-path accessibility; no claim of a complete network/security sandbox is made.

Review source diffs, run `git diff --check`, inspect explicit allowlisted staged paths, and scan before commit. Never stage artifacts, private receipts, logs, tokens, credentials, generated wallpapers, screenshots, model weights, or original recovery Git data. Use current timestamps and a confirmed repository-local author identity. CI must be a separately exercised workflow, not a decorative green badge.
