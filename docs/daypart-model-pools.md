# Daypart model pools — implementation checkpoint

Source-only feature branch; not deployed and no live GPU or wallpaper actions.

Implemented:
- Pure five-daypart resolver, exact identifier deduplication, injected RNG, avoid-repeat, no cross-pool fallback.
- Versioned opt-in policy with empty pools; existing manual checkpoint and automation preferences retained.
- Validate/persist prospective settings before publishing runtime state.
- Live loader intersection and one checkpoint/profile per batch; lighting retries retain selection, scene and seed, with durable retry context.
- Scene controls expose Day/Night checklists and collapsed five-daypart mapping; user actions alone save preferences.

Verification checkpoint:
- First complete isolated non-owner desktop discovery: **376 executed tests, zero failures/errors/skips**.
- Native plugin build/probe, isolated KPackage install/readback, packaged Plasma AppletContext checks passed.
- New native QML test opens two independent UI sessions and verifies three Day/two Night selections, persisted policy, no hydration writes and no render/apply POSTs.
- Expected offscreen missing-display/window-shadow diagnostics remain; this is not live graphical acceptance.
- Local headless host lacks CMake; native validation ran on the desktop's non-owner account, not the graphical user's session.

Remaining verification: additional HTTP batch/receipt edge cases, final artifact/source manifest equality and independent review. Owner deployment, live GPU/image-quality checks, actual wallpaper application and releases require separate approval. Gallery cleanup is a separate task outside this branch's implementation scope.
