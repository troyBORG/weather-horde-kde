# Catch-up refresh — feature branch, runtime unverified

## Behavior and consent

`catch_up_refresh` is an explicit boolean setting (default **false**). The widget's
**Catch up overdue after unlock / gaming; pause while locked** switch enables one
combined policy. It does not enable Auto, change mode, target, interval, location,
scene or checkpoint. The installer offers `--enable-catch-up-refresh` with the same
scope. Existing installations retain their legacy interval policy until opted in.
Three independently configurable policy switches are **not** implemented in this
first version; the combined policy avoids ambiguous unsafe combinations.

When opted in and Auto is on:

* Startup reconciles successful receipts and queues overdue targets, rather than
  deliberately waiting a full interval. Interval ticks and unlock observations
  coalesce into one request; missed intervals never create a replay backlog.
* Locked or unknown session state blocks new automatic work. The existing monitor
  supplies game/VR/resource observations. Sixty seconds of continuously safe,
  unlocked observations are required. Unknown/unsafe observations, monotonic
  reversal and telemetry gaps over 15 seconds restart the grace period. Suspend
  therefore cannot count as observed safety.
* Only missing targets are retried after a partial success. Disconnected outputs
  are excluded from executable work without changing the saved selection.
* Auto OFF cancels intent and invalidates old completion IDs. Settings changes
  invalidate current automatic intent; subsequent ticks reconcile the new policy.
* Transient/incomplete work backs off for 1, 5, then at most 15 minutes. Missing
  location/renderer/apply capability requires configuration correction; unresolved
  submission journals remain blocked, not resubmitted. Change settings after
  correcting configuration to clear the action-required latch.
* Prompt, generated-preview and verified-wallpaper freshness are separate.
  Wallpaper transactions durably record `applied_at` only after compositor
  readback. Startup reconciles those receipts, including a crash before scheduler
  persistence. Restore invalidates current wallpaper freshness.
* Each generation recomputes weather/scene. Automatic catch-up apply rejects
  changed solar daypart, future scene timestamps and scene age greater than the
  smaller of the selected interval and one hour. Scene time is not a guarantee of
  provider observation freshness. No waiting-image replay queue was introduced:
  unsafe completed jobs retain the existing quarantine behavior and request a
  new render, rather than releasing quarantined images when activity later clears.
* Existing ownership, authentication, VRAM, owned-job and native-image/geometry
  validation remain mandatory. Managed Comfy startup has the same lock/Auto gate;
  the activity guard is rechecked before submission and every automatic apply.
  Manual Generate/Apply remain separate explicit actions.

The lock adapter performs bounded `qdbus6` polling in the owning Wayland session.
It verifies the `org.freedesktop.ScreenSaver` `/ScreenSaver` `GetActive` boolean
contract by introspection on every observation. Missing service/bus, malformed
contract or response fails closed. There are no signal subscribers or shell
watchers to duplicate after reconnect. **The actual owner's KDE lock service has
not yet been inspected; fixture contract tests are not owner verification.**

## Status and private evidence

The widget shows pending targets, waiting reason, settling/retry countdown and
last verified wallpaper timestamp per monitor. Disconnected/stale widget state
says **last known**, not current success. `next_eligible_at` remains the legacy
interval compatibility field; catch-up readiness is reported by `refresh`, not
that deadline. Countdown values are snapshots updated by regular status polling.

Owner-private `refresh-state.json` stores per-mode successful freshness and bounded
pending reasons. Restart recomputes pending intent from durable freshness; it does
not revive an old job ID or reuse an old prompt. `refresh-events.json` retains the
latest 100 coordinator/lifecycle events, with generation correlation, target and
private scene/model/time evidence. Existing private image/job and wallpaper
transaction receipts remain authoritative for integrity/readback. Do not publish
these files, bearer tokens, images, or owner paths in issues.

## Owner deployment gate

This branch is **locally/isolated-desktop tested, NOT owner-reloaded, NOT live
render/apply verified**. No GPU render, wallpaper change, owner service restart or
owner state edit was performed to develop it. Cross-account private-state and
unit access was denied and was not bypassed. The scheduler source defect explains
how a guarded timer can lose an opportunity, but does not prove the sole cause of
any specific overnight symptom.

Use a new owner-owned checkout/extracted source directory, leaving the mixed live
checkout untouched. Preserve its source/index and private settings/receipts/unit
backups. In the owner graphical terminal, first establish actual loaded revision,
service persistence, Auto/mode/target/interval, inflight state, current wallpapers
and lock-service contract. If reachability/ownership is broken, repair that
separately before deploying. Do not borrow the owner's bus or token from SSH.

After the owner verifies no job is active/unresolved and safely stops the
controller, use the reviewed persistent installer from the new source:

```sh
# Set the intended owner and existing reviewed Comfy root as documented in deployment.md.
python3 scripts/install-controller-service.py --enable-catch-up-refresh \
  --manual-wallpapers --managed-comfy
```

The last two flags must match separately approved existing capabilities; omit
capabilities not previously approved. The helper refuses running/transitioning
controllers, unresolved jobs, occupied ports, unsafe ownership and unknown manager
state. It does not stop a controller to deploy. It backs up unit/settings and
supports the existing `--rollback` contract while stopped. The new catch-up flag
changes only that preference; prior Auto, mode, selected monitors and interval
are preserved. Do **not** use `--restore-30min-generate-apply-all` for this rollout,
or legacy helpers that force Auto OFF. Saved Auto ON can start guarded catch-up
after restart; schedule this owner action outside gaming and with consent.

Widget installation/reload is a separate owner action; the package builder only
validates in a disposable package root. Verify authenticated `source_revision`
and settings after installation, not just file copy or package success.

## Acceptance ledger and remaining work

| Plan area | Evidence / disposition |
|---|---|
| Live baseline | Source and mixed/no-commits Git state inspected; private state/unit inaccessible. Effective Auto, service health, current readback and loaded revision remain owner-only unknowns. |
| Source preservation/reconciliation | Original allowlisted source and exact mixed index privately archived; upstream main fetched, feature branch based on merged portability work; live controller bytes matched publication baseline. No live index/source reset. |
| Pure coordinator | Fake-clock coalescing, continuous-safe grace, missing/unsafe lock/activity, telemetry gap/suspend, monotonic/wall-clock rollback, mode separation, partial completion, cancelled generation and fresh unlock tests. |
| Controller | Real offline transport fixture exercises overdue startup, overnight unlock, game exit, fresh unlock no-op, missing targets only, Auto OFF, prompt-only distinction, stale apply rejection and managed startup lock gate. |
| Lock adapter | Initial locked, duplicate observations, missing bus, malformed contract, reconnect fixtures. Actual KDE owner introspection/resume still pending. |
| Freshness/output | Durable successful readback timestamp/restart and failed readback tests; solar/age rejection; existing native geometry, hash, quarantine and transaction suite retained. New external-manual-wallpaper adoption policy and provider-weather-age thresholds are not added. |
| Widget/audit | Native isolated Plasma harness exercises pending/grace/consent and disconnected text. One combined switch rather than three independent preferences. Bounded private lifecycle events implemented. |
| Testing | Standard discovery plus real native package/harness on non-owner account, isolated HOME/XDG, no inherited GUI bus, offscreen/software Qt. See branch delivery receipt for exact final commit/count. |
| Deployment | Installer opt-in/preserved Auto ON/OFF and rollback fixture tests; no owner deployment or runtime acceptance claimed. |
| Publication | Feature branch only; no force-push or main merge. Independently compare remote SHA with tested commit in delivery receipt. |

Still required before claiming end-to-end completion: owner baseline/lock-contract
inspection; independent review; owner reload and authenticated revision/settings
readback; authorized actual GPU/image/hash/compositor acceptance; controlled real
lock/unlock and actual game-ending safe transition; visible owner confirmation;
and next-day overnight evidence. Simulated elapsed time is not overnight evidence.
The existing integration suite covers many guard/ownership races, but not every
combination of the proposed full live multi-monitor/VR matrix.

## Retrospective

The important boundary was **intent versus output success**: advancing an interval
before dispatch consumed an opportunity even when no image changed. A coordinator
owns intent; only successful output boundaries own freshness. Monotonic elapsed
time alone was insufficient: telemetry gaps must reset grace. A resource-only
managed-startup fallback also needed the session/Auto gate. Durable compositor
receipts close the crash window before coordinator save, and cancelled generation
IDs cannot advance success. Native QML tests caught fixture-contract mistakes;
headless-host test failures were missing CMake/Qt infrastructure, not a license to
replace execution with invented output. The native desktop toolchain was exercised
under a different account without borrowing the graphical owner's session.
