# Forced refresh — 0.1.12 (local review candidate)

Not an installed or published release. No gaming/VR throughput or image-quality claim is made from fixtures.

## Owner controls

Guarded remains the default, including migration from settings without `automation_policy`. In Schedule, choose Auto, **Auto: generate + apply wallpapers**, targets and interval separately. Open **Force Generate + Apply (gaming/VR)**, acknowledge the risks, then enable Force. Five minutes is already an available interval; enabling Force does not change it or enable Auto. Independent All monitors still renders each distinct geometry; panorama still renders one coherent master and validates all crops before applying them sequentially.

Force may cause stutter, VR disruption, GPU out-of-memory, failed renders or application crashes. It bypasses gaming/VR detection, GPU utilization/client classification, unknown/stale resource telemetry and free-VRAM reserves, including the reviewed-model admission reserve. It is not an OOM guarantee or a guarantee of a completed wallpaper every five minutes. Raw telemetry stays visible.

Force does NOT bypass authentication/origin restrictions, owner session, same-owner Comfy listener identity, exclusive queue/job identity, compatible model/graph geometry, trusted bounded image decoding, explicit target matching or transactional wallpaper readback. Locked/unavailable graphical sessions remain blocked; no wake/unlock or power-policy changes occur.

## Consent and revocation

`automation_policy` persists `guarded` or `force`. Force consent and its generation are memory-only. Restart with selected force pauses scheduling and says **Reconfirm forced mode**. The authenticated `PUT /v1/force-override` accepts `enabled` (strict boolean) and optional `confirmation`; enabling requires exactly `I accept gaming stutter, VR disruption and GPU OOM risk`. Unknown fields/types fail before mutation. Selecting a policy through settings alone never grants consent. Enabling requires idle and is mutually exclusive with the original ten-minute manual testing override.

Disabling Force revokes the frozen job generation immediately when the controller receives the request. If the widget already has an HTTP request in progress, it visibly queues one disable and sends it after that request completes or times out; consent is not yet revoked while queued. During an owned job the UI reports draining; it returns to guarded when the job is reconciled. Running GPU work is not globally interrupted. Pending cancellation targets only the controller's own prompt; an uncertain submission retains its journal/lock. Disable Auto remains available and also revokes consent. No historical quarantined image is released by enabling Force later. Manual Generate uses selected force consent but never implicitly applies; explicit saved-image Apply retains its existing separate semantics.

## Gate map

- `Controller.dispatch`: authenticated server routes, strict consent/settings validation, idle enable, frozen policy, model compatibility and single-flight admission.
- `Controller.forced_policy`: live session polling, settings/topology snapshot and consent generation; independently verified `ComfyTransport.owned_gpu_pid`; allowlisted resource decisions only. Slow telemetry/owner reads recheck session and consent afterward, including the final guard after the wallpaper pending journal is durable.
- `Controller.model_gate(resources=False)`: skips only memory policy, not reviewed structural profile selection. `model_catalog` geometry/profile compatibility remains unchanged; that module has no independent free-memory threshold in this integrated baseline.
- `Controller.startup_guard` / frozen guard `.startup`: collect raw telemetry; cold startup may bypass resource admission but not subsequent service/listener identity. `ComfyService.ensure_ready` retains unit/port lifecycle validation.
- `Controller.render_images`: refresh model inventory and validate live loader; snapshot targets; preflight wallpaper journals; freeze policy into the worker and transport. Recheck before submission, polling, image validation, store publication and every automatic apply.
- `ComfyTransport.queue`: validates node contracts and empty queue, checks listener identity twice around the selected guard, never retries an ambiguous POST. `inspect`, `image`, `cancel_pending` retain owned prompt checks.
- `PreviewStore.save`: bounded decode, native dimensions, hash and late guard; blocked output remains quarantined. Force receipts are in `automation_policy`; manual testing metadata remains false for forced images.
- `WallpaperManager.preflight/apply`: pending receipt, image/target integrity, current snapshot, compare/replace and readback remain mandatory. No force-specific wallpaper adapter or alternate bypass path exists.

## Cadence and receipts

The existing coordinator is used for force regardless of the optional catch-up switch. Due times advance from the prior request deadline, not render completion. Busy due periods coalesce into one successor intent; there is still one active owned batch. Unlock/resume requests coalesce, never establish safety. Retry backoff remains 1, 5, 15 minutes with a bounded retry budget and permanent-action latch; no automatic resolution/model downgrade or unrelated termination is introduced.

Status exposes selected/active force and generation, pending/missed cadence, controller work state, retained last error, and per-target successful application times through `refresh.last_success.image_wallpaper`. `next_eligible_at` is the request cadence deadline, not the retry deadline. `refresh_timing` separately reports `cadence_due_at`, the finite wall-clock `retry_due_at` converted from monotonic backoff, `next_attempt_at` (earliest eligibility, subject to fresh checks), pending targets and state (`disabled`, `blocked`, `action_required`, `rendering`, `retry_wait`, `pending`, or `cadence_wait`). Active work and permanent/session blocks have no promised next attempt. A missed period is not a successful apply. Explicit refresh reconciliation uses current live force consent to omit the resource reserve only; it still rejects incompatible models, outstanding jobs, pending wallpaper transactions and missing original plugins. Native fixture tests use synthetic PNGs and temporary HTTP servers on port 0, not real GPU submissions or the owner's wallpaper bus.

## Review scope

Review particularly the allowlisted resource vocabulary, force/default separation, revoke-before-publication/apply behavior, cold startup identity handoff, stale source/restart consent and scheduler successor handling. Full native package/offscreen validation is required before publication. Owner deployment, loaded widget/controller authentication and two gaming refresh cycles remain separate, unapproved acceptance work.
