# Owner installer hardening (0.1.11 installer revision)

The earlier owner's generic `OSError` has **not been diagnosed**. A later,
separate probe established a writable `.local/share` ancestor. This revision
improves refusal, diagnostics and recovery; it does not claim permissions caused
the original exception or that a fresh GPU render/widget reload has been verified.

## Owner workflow

Use the generated `OWNER-DEPLOY.sh` with **explicit bash**, including from Fish:

```sh
# Bash form; substitute your actual KDE account name, not the staging account.
WEATHER_HORDE_OWNER="$(id -un)" bash /path/to/new-delivery/OWNER-DEPLOY.sh
```

Fish equivalent:

```fish
env WEATHER_HORDE_OWNER=(id -un) bash /path/to/new-delivery/OWNER-DEPLOY.sh
```

Default operation verifies trusted home/data/state/unit ancestry **before
extraction**, verifies the pinned archive and full extracted inventory, then runs
read-only static deployment preflight. It never requests a stop before those
static checks pass. Preflight does not prove free disk/quota, future write success,
runtime quiescence or absence of later concurrent edits.

Only after that succeeds, and after the owner arranges a safely idle/stopped
maintenance window, rerun the same command with `--deploy`. Nothing automatically
stops or starts the controller. Deployment repeats static checks, obtains the
exclusive lifetime lock, checks persistent unit/process/listener/journal state,
and preserves exact settings bytes, flags, environment, package rollback and
persistent enabled/disabled state. Owner start remains separate: preserved Auto
ON may submit work after start.

`WEATHER_HORDE_OWNER` must name the current non-root kernel UID. Bootstrap HOME
must match that account's passwd home. `XDG_DATA_HOME`, when set, must be an absolute
path without traversal, surrounding whitespace or controls; otherwise use the
normal `~/.local/share`. Do not inherit another account's environment or session
bus. No sudo is supported. The direct helper also requires explicit owner identity:

```sh
WEATHER_HORDE_OWNER="$(id -un)" python3 -B scripts/deploy-preserving-owner.py \
  --preflight --old-root /absolute/current/persistent/source
```

Permission refusals report the precise ancestor, octal mode and numeric UID. Any
repair must be reviewed by the owner, limited to that exact path (e.g. `chmod go-w
-- /exact/path` if unintended write bits), never recursive and never automatic.
Do not weaken trust policy to make a check pass. IPv4 and IPv6 listener exclusion
are both required. Unsupported/disabled IPv6 now gives a family-specific refusal
with errno rather than silently bypassing listener protection. An exited-process
ENOENT/ESRCH race is harmless; unreadable evidence still fails closed.

Transaction failures retain operation, exception type and numeric/symbolic errno;
subprocess output/argv, raw OS messages and filenames are suppressed. Reviewed
public admission messages are shown; settings, tokens and environment values are
not. Original causal exceptions and additional rollback failures are retained.
Private backups are retained, not removed automatically.

## Re-running a delivery

Only a byte-exact, owner-owned, non-writable-by-others extraction of the **same
pinned archive and version**, with exact file/directory inventory and no symlinks
or hardlinks, can be reused. Stale/corrupt/partially extracted directories are
refused unchanged. Choose a new path/delivery instead of overwriting one. No
mutable “latest” file is produced. Application version remains 0.1.11; installer
candidates include their distinct Git revision in their name.

## Maintained packaging

From a clean committed disposable checkout, after `python3 scripts/package.py`:

```sh
python3 -B scripts/make-owner-delivery.py /new/nonexistent/delivery-directory
```

This records the Git commit and package receipt, normalizes archive modes, and
ships the tracked bootstrap plus a generated hash-pinned bash wrapper. Existing
output is refused. The bootstrap hash and source archive SHA256 are both pinned.
Hashes protect integrity relative to the trusted wrapper; they are not signatures
and do not authenticate an untrusted distribution channel.

Offline regressions cover writable ancestry without mutation, malformed env,
repeatable static preflight, sanitized stage/errno output, original and rollback
causes, IPv4/IPv6 failure distinctions, process exit races, exact extraction
resume/refusal, and unchanged persistent enablement/settings/package rollback.
Real owner rendering, restart/login persistence and UI pairing are separate
acceptance steps and are not implied by fixture success.
