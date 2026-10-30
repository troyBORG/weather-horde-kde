# Persistent controller deployment

This is the current supported approach for the existing site-specific installation, not a generic installer for arbitrary accounts. Source still enforces its original graphical-owner and trusted-staging-account policy and fixed Comfy/model paths. Do not weaken those checks merely to make installation succeed elsewhere.

## Stopped-controller owner installation

Run only in the intended owner's KDE graphical terminal, from a trusted checkout at its reviewed location. Never use sudo or a different account's session bus/token. First arrange a verified-idle maintenance window: the helper **refuses** active, transitioning or unknown controllers, lingering processes, occupied API ports, unresolved render journals, unsafe source/state metadata and unreviewed drop-ins. It does not stop a job/controller for you.

For the existing generation + manual wallpaper + managed-Comfy capability profile:

```sh
python3 scripts/install-controller-service.py --preview-checkpoint natvisNaturalVision_v27.safetensors --manual-wallpapers --managed-comfy
```

The checkpoint name is an existing reviewed fallback, not a download instruction. A saved admitted checkpoint takes precedence. The default Comfy idle timeout is 300 seconds; use `--comfy-idle-seconds` only deliberately. The installer preserves saved settings bytes by default: Auto ON stays ON, OFF stays OFF, and location, scenes, framing, model and interval are retained. It does not request a forced render/apply, testing override, Plasma restart or Comfy start/stop. **Preserved Auto ON can schedule work later**; preservation is not equivalent to disabling automation.

Do not use `connect-owner.py`, `rollout-owner.py`, `release-owner.py --deploy` or `runtime-repair-owner.py --deploy` as substitutes for persistence: legacy rollout paths deliberately turn automation OFF and use transient launches. The checked-in controller systemd template is legacy preview-only, not the generated capability-bearing persistent unit.

## What gets installed and checked

The generated user unit is WantedBy/PartOf/Requisite `graphical-session.target`, uses absolute source/state/executable paths, private umask and NoNewPrivileges, and restarts on failure with bounded rate limits. This is graphical-login persistence, not system boot enablement or linger. The helper imports current owner session environment; it does not bake bus addresses into the unit.

It validates systemd syntax, persistent FragmentPath and `Transient=no`, enablement and the exact graphical target symlink, authenticated status, loaded source fingerprint, displays and requested capabilities, testing override OFF, unchanged settings and the scheduled deadline. Startup uses the saved interval rather than immediate catch-up generation. A saved OFF receipt proves preservation, not active scheduling.

## Explicit automation restoration

Only if the owner deliberately wants Auto ON / generate+apply / all monitors / 30 minutes, append:

```text
--restore-30min-generate-apply-all
```

This requires confirmed location and `--manual-wallpapers`. It still requires a stopped controller. Never describe it as a no-consent default.

## Backup and rollback

The installer prints an owner-private backup directory under `~/.local/state/weather-horde-kde/controller-install-<unique>/`. It retains original settings/unit/enablement, proposed unit and receipts, but not a copied token. Before-start failures restore prior stopped configuration; after a start request, a verification failure does not forcibly stop possibly active work.

Only after separately ensuring idle and owner-stopped operation:

```sh
python3 scripts/install-controller-service.py --rollback "$HOME/.local/state/weather-horde-kde/controller-install-REPLACE_WITH_PRINTED_SUFFIX"
```

Rollback restores prior settings/unit/enablement and leaves the controller stopped; it does not recreate a lost transient launch or render. Retain backups privately.

## Acceptance is separate from tests

Verify authenticated loaded revision/capabilities and widget reconnect after deployment. Observe the next eligible scheduled action and per-monitor verified wallpaper receipts plus intended visible monitors. Guard deferral is not a successful render, and a completed render is not proof of application. Enablement establishes configuration; an actual logout/login test is separate. Publication preparation has not run these owner-live checks or changed the live runtime.
