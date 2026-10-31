# Persistent controller deployment

Installation is still a deliberate graphical-owner action, not an unattended generic installer. Account and installation paths are configurable without removing same-UID, private-state, trusted-source, listener or graphical-session checks.

## Portable path and owner configuration

Run from your reviewed checkout in the intended owner's KDE terminal:

```sh
export WEATHER_HORDE_OWNER="$(id -un)"
export WEATHER_HORDE_COMFY_ROOT="$HOME/.local/share/ComfyUI"
```

`WEATHER_HORDE_OWNER` is required by owner helpers and resolved through the system account database. Missing/unknown owners, root and a caller with a different UID are rejected before owner actions. This is explicit deployment selection, not authentication or permission to borrow another account's bus/token. Existing session/display/private-file checks still apply.

`WEATHER_HORDE_COMFY_ROOT` defaults to `${XDG_DATA_HOME:-$HOME/.local/share}/ComfyUI`. Set it to the actual reviewed Comfy checkout (not its parent). Values must be absolute, without parent traversal, surrounding whitespace or control characters. Identity checks, model discovery and the launcher share this exact path. The installation must contain `main.py`, `.venv/bin/python`, and `extra_model_paths.yaml`; configure external model libraries in that YAML rather than editing Weather Horde. No model directory, permissions, virtual environment or checkpoint is created/downloaded by this change.

Source paths are discovered from the scripts' own checkout, not the current directory or a fixed `~/projects` layout. By default, source ancestors must be owned by root or the caller, and cannot be group/world writable or symlinks. Only when intentionally trusting a separate source-staging account, set `WEATHER_HORDE_STAGING_USER` to that account's name. No staging account is implicitly trusted.

Generated Comfy and persistent controller units capture the selected Comfy root; the Comfy unit also captures the configured owner. Re-run the appropriate installer in a stopped/idle maintenance window to change an installed path. Shell exports alone do not update an already installed unit. The checked-in systemd files are templates/examples, not directly installable units. The Comfy installer renders and syntax-checks its actual unit before installing, retaining `ProtectSystem=strict`, private writable state and no login enablement.

For compatibility, owner installers still use the invoking owner's `~/.config/systemd/user` and `~/.local/state/weather-horde-{kde,comfy}`. This patch does not migrate existing state or provide custom-XDG-state deployment support; keep Plasma/controller state configuration consistent. Package lookup follows absolute `XDG_DATA_HOME` (or `~/.local/share`). `/proc`, `/usr/bin/python3`, packaged application identity paths and the stable `org.troyborg.weatherhorde` ID are intentional, not personal installation paths. Legacy DP-2 recovery tools and location defaults are outside this path-only change.

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
