# Daypart model pools

Source-only feature branch; not deployed. No live GPU or wallpaper actions were used.

## Controls and policy

Scene keeps the existing single-model picker and adds **Single model / Models by lighting**. Single mode is the migration default. Both saved pools start empty: suggested model lists are not consent.

In lighting mode, explicitly check models in Day and Night. Exact filenames are retained, including unavailable saved choices with reasons. Open **Solar daypart mapping** to independently map daytime, golden hour, blue hour, twilight and night. The initial mapping is Day for daytime/golden hour and Night for the other three; twilight remains independently editable. These are solar-elevation classes, not clock windows.

Each click saves only that explicit preference. Hydrating or reopening the widget does not write settings, render or apply. Selection is random among the active pool's compatible, live-loader identifiers, avoiding the preceding choice when an alternative exists. Empty/unavailable pools defer with an actionable reason; there is no other-pool or all-installed fallback.

## Batch and safety contracts

- Freeze the policy before slow preflight, one solar instant across scene variants, then one checkpoint/profile for all monitor graphs and panorama crops.
- Lighting retries retain generation identity, scene evidence, seed, chosen checkpoint and remaining targets. Durable refresh state supports restart; newly coalesced targets wait for a fresh batch.
- Recheck the chosen checkpoint before each submission. Missing checkpoints and changed retry geometry defer without rerolling.
- Preserve freshness, session/activity, Force consent, ownership, inflight-journal and render/apply separation. A frozen retry is **not** permission to apply stale weather after a boundary: existing freshness admission can still defer it. Restore the missing model/layout or cancel the old intent through explicit settings changes before requesting a fresh batch.
- Settings updates validate a prospective copy and atomically persist it before publishing runtime values. Invalid saved policy refuses startup rather than silently enabling a fallback.
- Preview metadata, job receipts, refresh events and authenticated status expose chosen checkpoint, pool, daypart and source evidence. The manual checkpoint remains unchanged.

## Verification checkpoint

Tested implementation: `947a6062603114118fc3b37199f44afb82ecef96` (this documentation update does not change runtime bytes).

- **15 targeted tests** passed.
- Full standard unittest discovery: **379 executions / 378 unique IDs**, zero failures, errors or skips. The existing imported duplicate ID remains counted normally.
- Native plugin build/probe, isolated KPackage install/readback and real packaged Plasma AppletContext checks passed.
- Native QML exercised three Day/two Night selections, an independent twilight mapping edit, UI restart, unavailable saved-choice retention and zero hydration/render/apply writes.
- Real Comfy HTTP fixtures exercised independent two-monitor and panorama batches, checkpoint/profile receipts and fresh selection after a daypart boundary. Synthetic CPU images are not GPU/image-quality evidence.
- Additional fixtures cover unknown/empty/unavailable pools, deterministic RNG/deduplication, failed settings writes, partial edits/restart, midflight edits, model disappearance, durable partial retries and geometry drift.
- All **187 tracked source files** matched the isolated tested manifest. Runtime and widget archived tracked bytes matched source; `model_selection.py` was present in the runtime archive and included in the import-time source fingerprint.
- Native environment: Plasma/libplasma 6.8.2, Qt base 6.12.0-3.1 / declarative 6.12.0-4.1, KPackage 6.31.0, Python 3.14.9, CMake 4.4.5. Expected offscreen missing-display/window-shadow diagnostics remain.

The headless editing host lacks CMake; native validation used an isolated non-graphical-owner desktop account, private XDG paths and a fixture-only D-Bus. No live graphical session was borrowed.

Independent reviewer sign-off, owner deployment, loaded-widget/controller verification, live GPU/image-quality acceptance and actual wallpaper application remain separate approvals. Nothing was merged or released. Gallery cleanup is a separate task outside this implementation scope.
