# Requested refresh policy — 0.1.11

This candidate is staged only. It has not been run in the graphical owner's session.

* Intervals: 5, 10, 15, 30, 60, 120, 240, 480, 720 and 1440 minutes.
* Catch-up enabled: a verified locked→unlocked edge or observation gap requests all selected targets, even with fresh receipts. Repeated unlocked samples do not retrigger; unknown session telemetry is not an unlock. Wall-clock gaps also cover Linux suspend with a paused monotonic clock (a large clock adjustment can conservatively request a refresh). A gap never establishes safety.
* No additional sixty-second settling grace. A current safe observation and known unlocked session are still mandatory. Existing fresh submission/resource/VR/process-ownership checks remain unchanged and run throughout rendering.
* Geometry groups render serially. Quarantined output remains unusable. A fresh retry renders interrupted targets and the remaining targets, not already fulfilled targets. Current-mode pending intent survives a controller restart; Auto OFF/settings cancellation discards it.
* Retries wait 60, 300, then 900 seconds. A fourth failure latches an actionable error with pending targets retained. Explicit `/v1/refresh/reconcile` validation can clear a latch; it cannot release an old image. Permanent apply/receipt errors still require verified reconciliation.
* Per-target waiting/pending/rendering/completed state and the latched reason are visible in the widget. A current safe guard does not erase the historical quarantine reason.
* Automatic apply still requires weather age no greater than `min(interval, 3600)` and the current daypart. Thus five-minute Auto can defer when the provider observation exceeds five minutes; it never silently relaxes stale-image policy.

## Owner diagnosis / approved deployment

**The original efc8a02 helper is withdrawn for deployment.** It required a transient unit and could not migrate the existing persistent graphical service. Do not use the old desktop artifact's deployment command.

The repaired `deploy-preserving-owner.py` is deliberately **stopped-only**. There is no safe atomic stop/restore-Auto/rollback transaction against a running controller without a maintenance protocol: Auto may submit work before a failed readback. It therefore never pauses/resumes Auto, stops/starts a service, contacts the controller API, reads a token, reloads Plasma, or requests generation/apply.

Run only after arranging an owner-confirmed idle maintenance window and separately stopping the controller. Do not stop active rendering. Do not issue widget actions, concurrent installers, starts or login/logout while deploying. An exclusive controller lifetime lock plus repeated stopped/process/listener/journal checks exclude cooperating controllers; legacy processes are checked but external non-cooperating writers cannot be made atomic by idle polling.

From a newly extracted **owner-owned** trusted HOME copy, not the shared delivery mount or old mixed-index repository:

```sh
bash -c 'set -eu; export WEATHER_HORDE_OWNER=troyborg; old_root=$(systemctl --user show weather-horde-kde.service --property=WorkingDirectory --value); test -n "$old_root"; exec python3 -B scripts/deploy-preserving-owner.py --deploy --old-root "$old_root"'
```

The command queries the configured persistent source directory instead of assuming the historical catch-up path is still current. Run it from the newly extracted source directory in the `troyborg` terminal. `bash` is explicit so it is also callable from Fish.

This is not a start/reconnect command. It refuses active/transient/unknown units and unreviewed drop-ins. The existing persistent unit must use the reviewed installer syntax. Only its ExecStart source path and WorkingDirectory change: configured environment, exact argument flags, other unit directives, enablement and graphical target link remain untouched. No session environment is imported or baked in. Dynamic manager environment is not captured or asserted identical across logins.

All settings bytes (not just the five Auto fields) remain untouched. The helper privately backs up unit/settings/package, syntax-checks the proposed unit, replaces the entire installed package, reloads the unit definition and verifies persistent FragmentPath, package bytes, unchanged settings and enabled/disabled state. Whole-tree rollback removes new-only files; it never merges an old package over a new one. Displaced trees remain in private `.weather-horde-deploy-*` siblings for manual recovery. It leaves the controller stopped on success or failure. Concurrent state/enablement/unit changes cause refusal rather than overwriting another actor's changes; inspect the printed private backup if rollback is refused.

After successful stopped deployment, **a separate owner-approved start and UI reconnect/loaded-revision/capability check are still required**. Preserved Auto ON may schedule work on that start; no automatic rollback is attempted after it. This revision does not claim authenticated runtime or widget pairing verification. Existing `--automation-off` flags, if present, remain exactly as configured and will retain their normal startup semantics.

Without `--deploy`, the helper reports only read-only allowlisted systemd lifecycle properties. It no longer sends the token to an unattributed loopback listener. Obtain the actual historical quarantine reason through the owner's already-paired widget; offline regressions do not identify that live cause.

## Offline evidence

Fail-first regressions cover short intervals, immediate safe eligibility, fresh wake/unlock coalescing, unknown-telemetry deduplication, suspend clock behavior, per-target quarantine/progress, finite retry budget, durable fresh pending intent and preserving-deployment ordering. Two different native geometry fixtures exercise first-target and second-target quarantine, recovery of both, single-flight submissions and no unnecessary completed-target generation. Existing apply/stale/ownership/VR/native QML tests remain in the full suite.

Tests use synthetic PNGs and mocked transport/service boundaries, not production GPU calls. The full suite requires the desktop Qt/Plasma/native toolchain in a non-owner private XDG environment. Expected offscreen Qt warnings and the existing HTTPError ResourceWarning are retained in logs. Delivery receipts record the final committed archive, package hashes and actual counts; this document does not imply live deployment.
