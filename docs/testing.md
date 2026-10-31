# Isolated validation — 2026-10-30

The publication candidate was copied to a fresh scratch tree on a CachyOS desktop under a **non-graphical-owner account**. Package construction, native token-reader probe and isolated KPackage readback succeeded. The full unchanged unittest discovery suite executed **189 cases in 26.178 seconds: zero failures, errors or skips**.

There are **188 unique unittest IDs**, not 189 unique methods: `test_electron_identity.ElectronIdentityTests.test_verified_element_ancestry` is discovered twice through an imported class. We preserved standard discovery behavior rather than silently deduplicating it. No subtest count is added to this total. A previous external AST-based audit runner could not enumerate inherited methods in this snapshot; a count-only standard-unittest runner was used instead. No product/test source was changed to obtain a pass.

## Portability validation — 2026-10-31

The portability branch uses temporary Comfy files and explicit synthetic account/UID fixtures instead of installed model paths or named developer accounts. Standard discovery executed **199 cases / 198 unique IDs, with zero failures, errors or skips** in an isolated non-owner desktop scratch tree. The duplicate imported test ID described above remains intentional. Native package build, token-reader probe, offscreen Plasma/QML harness and real generated-unit `systemd-analyze --user verify` checks passed. Offscreen Qt emits expected missing-display/window-shadow warnings; this is not a warning-free graphical-session test.

New regressions cover configured/default Comfy paths, absolute-path rejection, same-UID/non-root owner selection, explicit staging trust, checkout-relative launching, transient environment propagation, unit syntax and literal dollar/template-token paths. Fail-first runs caught the original fixed mount/home paths and unit escaping mistakes before the passing runs. No production owner bus, GPU job, service restart or wallpaper action was used. Owner deployment and actual live generation remain separate acceptance work.

## Verified toolchain

```text
python 3.14.8-1
python-pillow 13.0.0-1
qt6-base 6.12.0-3.1
qt6-declarative 6.12.0-3.1
plasma-workspace 6.8.2-1.1
libplasma 6.8.2-1.1
kpackage 6.31.0-1.1
cmake 4.4.5-1.1
gcc 16.2.1+r23+gd564253eb6c8-3
nodejs 26.12.1-2
systemd 262.1-1
dbus 1.16.2-2.1
```

The suite includes the compiled Qt token reader and real offscreen Plasma/QML harness, ephemeral HTTP servers, synthetic PNG fixtures, mocked service command traces and real systemd syntax checks. Installer enablement writes use fixture adapters; no real owner manager is enabled. QML runs on private D-Bus configured without service activation directories. The standalone `tests/kconfig-readback.cpp` is not a separately collected test and was not run as an additional contract target.

## Reproduction

Use a **disposable checkout** with the above dependencies under the existing non-owner developer account. The historical snapshot above had two Comfy handoff cases dependent on installed model paths and owner fixtures dependent on site accounts. The portability revision replaces those dependencies with temporary files and synthetic account fixtures. Native Qt/Plasma/systemd dependencies are still required; this is not a generic dependency-free CI claim. Keep the normal non-owner HOME under trusted non-world-writable ancestors; using HOME beneath `/tmp` conflicts with the installer's safety checks.

Set SCRATCH to a freshly created private directory under that account's home, containing the disposable source as `repo/`. Then:

```sh
umask 077
mkdir -p "$SCRATCH/xdg/config" "$SCRATCH/xdg/state" "$SCRATCH/xdg/data" "$SCRATCH/xdg/cache" "$SCRATCH/xdg/runtime"
chmod 700 "$SCRATCH/xdg/runtime"
export XDG_CONFIG_HOME="$SCRATCH/xdg/config" XDG_STATE_HOME="$SCRATCH/xdg/state"
export XDG_DATA_HOME="$SCRATCH/xdg/data" XDG_CACHE_HOME="$SCRATCH/xdg/cache"
export XDG_RUNTIME_DIR="$SCRATCH/xdg/runtime"
export QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software PYTHONDONTWRITEBYTECODE=1
unset DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS
cd "$SCRATCH/repo"
python3 scripts/package.py
timeout 180 python3 -m unittest discover -s tests -q
```

The recorded first complete pass used an external runner around the same standard unittest discovery to retain exact collected IDs and structured result counts. Package outputs stay under scratch `artifacts/` and generated QML plugin paths, both ignored by Git. Python startup tests can read telemetry and shared model paths; this is not a network-sandbox or exhaustive system-call trace claim.

No production owner token/state, render job, wallpaper action, controller restart or Plasma reload was used. No actual generated-image quality, owner-live scheduled apply or logout/login persistence is inferred. Private raw test/package logs and source manifests are kept outside the candidate repository. A remote clone/CI run is a separate publication check, not established by this document alone.
