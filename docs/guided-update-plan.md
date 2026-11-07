# Guided owner update plan

1. Extend the maintained hash-pinned bootstrap with an opt-in guided update, retaining stopped-only deployment.
2. Capture entry settings bytes, unit, enablement and old source in a private recovery directory. Authenticate using the invoking owner's private token only. Never infer consent from old backups.
3. Wait boundedly for existing work before disabling Auto (changing settings can cancel scheduled work), then verify Auto OFF and idle again. Older controllers lack an atomic maintenance gate: require an explicit exclusive owner maintenance window, and refuse entry Auto ON on those versions rather than claim race-free quiescence.
4. Stop only an authenticated matching persistent controller, wait boundedly for port reuse while rejecting listeners, and invoke the existing stopped preserving transaction under its lifetime lock.
5. Start with persisted Auto OFF; authenticate candidate fingerprint/capabilities, verify preferences/enablement, then restore only entry Auto consent. Failure never restores automation or blindly restarts/rolls back a live controller. Installer rollback remains stopped-only.
6. No automatic Plasma restart. Report widget verification pending; owner reload/visual acceptance is a separate explicit action.
7. Exercise the orchestrator in real subprocess fixtures, build native package and run complete isolated desktop suite; commit/push a focused branch, generate an immutable owner-readable hash-pinned delivery.

Acceptance limitation: the installed old controller has no atomic maintenance endpoint. The guided updater must refuse entry Auto ON, never pretend polling excludes concurrent manual widget actions, and require the owner to leave the widget untouched. Full arbitrary-ON unattended updates require a future controller maintenance protocol. The current user's manually selected Auto OFF is preserved.
