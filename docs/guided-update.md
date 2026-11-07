# Guided owner update

Use the immutable delivery's short wrapper **from your own KDE terminal**:

```sh
bash /path/to/delivery/deploy.sh
```

`--help` shows options. `--preflight` verifies/extracts the hash-pinned candidate and authenticates the current controller without changing services or settings. Extraction is a local file write, not a live install. The original `OWNER-DEPLOY.sh --deploy` stopped-only installer remains available.

The interactive command asks you to type `UPDATE` and leave the widget/other controller clients untouched. It captures **the settings at this invocation**, not historical backup preferences. It retains the old source, backs up entry settings/unit/enablement privately, waits for idle and pending wallpaper receipts, sends Auto OFF through the authenticated API, rechecks idle/preferences/identity, stops the persistent controller, waits boundedly for port reuse, and invokes the existing preserving installer. Foreign listeners are refused, never killed. It starts with persisted Auto OFF and verifies the authenticated candidate source fingerprint, capabilities, displays, preferences and enablement before restoring exact entry settings bytes.

## Important legacy limitation

The old controller has no atomic maintenance gate. Changing settings during a scheduled render can cancel pending work. Therefore this updater **requires entry Auto already OFF**; it refuses Auto ON without changing anything. It does not offer automatic ON-to-OFF-to-ON updates or select an older backup's ON setting. That needs a controller-side atomic drain protocol, not more polling. The user's current manually selected Auto OFF is retained.

The owner must keep all controller clients untouched during the exclusive maintenance window. Idle polling and the stopped-only controller lifetime lock cannot eliminate a racing manual render on the old controller. This is a guided owner maintenance operation, not an unattended/race-free updater. Busy jobs and pending applies are waited on, never explicitly cancelled or killed by the updater. Each wait defaults to 180 seconds; timeout is failure, not permission to interrupt work.

## Failure and recovery

The command prints a private `~/.local/state/weather-horde-kde/guided-update-*` backup immediately after creating it. It contains the entry settings bytes, original unit, old source path, enablement and recovery notes. The existing `preserving-deploy-*` backup additionally contains the old package and retargeted unit. Old source directories are never deleted.

Before stop, failures leave the old controller running. After stop, an installer failure invokes its guarded stopped-only rollback and leaves it stopped. A startup/runtime verification failure never automatically rolls back live source or restores automation; the candidate may remain running with Auto OFF. Inspect the stage and backups before recovery. Never copy historical ON settings over current owner preferences just to complete an update.

No Plasma shell restart or render/apply acceptance test is performed. **Widget verification remains pending**, even after controller verification succeeds. Reloading Plasma requires separate explicit owner consent, and any such reload still needs owner-visible widget reconnection verification. No global restart is hidden in this command.

Tests use real subprocess orchestration, ephemeral authenticated fixture HTTP servers, temporary settings/units and fixture-only manager calls. The existing native suite covers full preserving installer rollback, package readback, QML loading and model discovery/4x contracts. These do not prove live owner render quality, UI pairing or login persistence.
