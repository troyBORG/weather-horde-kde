# Weather Horde KDE

A KDE Plasma 6 widget and authenticated loopback controller for weather-aware wallpaper previews using local ComfyUI. The source snapshot reports version **0.1.11**; a version or Git tag is not proof of a loaded deployment.

**Experimental source release.** Owner and Comfy installation paths are explicit configuration; geographic defaults and some legacy recovery targets remain site-specific. Read [deployment](docs/deployment.md), [security](SECURITY.md), and [licensing status](docs/licensing.md) before installation or redistribution. No project-wide license grant has been invented.

## Owner installer update

See [owner installer hardening](docs/owner-installer-hardening.md) for hash-pinned delivery, read-only preflight, exact extraction resume and stopped-only preserving deployment. This does not restart or modify a running installation.

## What it does

- Weather-inspired rural, street, park, woodland and river scenes; fixed, random and per-monitor scene choices.
- Day/night and lunar evidence, expiring manual weather observations, and portrait-aware framing.
- Reviewed local SD1.5/SDXL checkpoint discovery and bounded native-geometry workflows. Model files are not included.
- Manual **Generate** creates a validated preview. **Apply** and **Restore** are separate selected-monitor transactions with readback.
- Explicit Auto choices distinguish prompt preview, generation, and generation plus wallpaper application. Installing capabilities is not new automation consent.
- Opt-in [catch-up refresh](docs/requested-refresh-0.1.11.md) coalesces pending work after unlock/gaming and pauses while locked or session state is unknown. Fresh, valid safe activity/resource observations and a known unlocked session allow eligibility **without an additional 60-second settling delay**; this does not bypass submission, VRAM, ownership, rendering or automatic-apply freshness guards.
- Refresh intervals include **5, 10 and 15 minutes**, alongside the existing longer choices. An existing saved **30-minute** interval stays 30 minutes until the user explicitly changes it; adding choices does not change Auto, mode or target consent.
- [Seasonal styling and holiday decorations](docs/seasons-and-holidays.md) are opt-in and default OFF for new and migrated installations. Calendar context is resolved offline for the scene timezone/jurisdiction, independently of weather evidence.
- Game/VR, unknown clients, GPU load/VRAM, queue ownership and image-validation guards defer unsafe work. Testing override is explicit and temporary, not a recommended deployment workaround.

**Known cosmetic documentation/UI issue:** the QML catch-up explanation still mentions 60 safe seconds, and the older [catch-up design notes](docs/catch-up-refresh.md) describe that superseded grace policy. Neither describes the current backend behavior above; the [requested refresh policy](docs/requested-refresh-0.1.11.md) is the current reference. This README correction does not change QML or runtime code. Immediate eligibility is not guaranteed immediate generation: other guards, retry backoff and latched errors still apply.

**Merged on GitHub is not deployed on the desktop.** A source commit, package or release does not update the running controller or loaded widget. Owner deployment, authenticated loaded-revision/capability checks and actual render/apply acceptance remain separate; no live installation, settings changes, service restart or Plasma reload is performed by publication. The stopped-only preserving deployment path retains existing settings/Auto consent; enabling catch-up or calendar styling is a separate explicit choice.

Prompts are not pixel constraints. Synthetic fixture images and passing tests do not prove generated visual quality or live wallpaper application.

## Requirements and build

GitHub Actions runs native Plasma 6/Qt6 and fixture checks on PRs and branch
pushes. Successful main pushes publish unique prereleases; matching new version
tags publish stable releases, using the exact tested artifacts. Neither deploys
anything. See [CI and release policy](docs/ci-releases.md) for isolation, pinned
toolchains, artifact privacy, permissions and the existing-tag caveat.

Full test discovery also needs PyYAML, the Plasma desktop shell package and
systemd manual pages/man-db for real unit verification. The CI container supplies
these dependencies; missing dependencies must not be counted as a passing suite.

Linux, Python 3 with Pillow, Plasma 6, Qt 6 development tools (Core/Qml/Quick), CMake, a C++17 compiler, KPackage including `kpackagetool6`, libplasma development files, D-Bus, systemd user tools and Node.js for the test harness. Runtime display discovery and wallpaper operations also require the applicable KDE command-line/session tools. Generation requires a separately installed local ComfyUI, compatible checkpoints/upscaler and suitable NVIDIA telemetry/GPU capacity. Dependency versions used for verification are recorded in [testing](docs/testing.md).

In a disposable source copy, not the running controller tree:

```sh
python3 scripts/package.py
python3 -m unittest discover -s tests -v
```

The package builder compiles the narrow same-user token-reader plugin, creates `artifacts/org.troyborg.weatherhorde.plasmoid`, installs it into a fresh **project-local validation root**, and verifies byte-for-byte readback. It does not install into live Plasma. Generated binaries are ABI-dependent: rebuild for your Qt toolchain. See [contributing](CONTRIBUTING.md) for isolated test setup and limitations.

## Current installation approach

Use the **persistent graphical-session controller installer**, not legacy transient rollout helpers. See [the deployment guide](docs/deployment.md) for stopped-controller prerequisites, settings preservation, explicit restoration and rollback. Installation is an owner action in the KDE terminal; this publication preparation performs none.

Build and verify the widget first. The existing owner-only widget helper supports `--verify-only`; actual installation and any shell reload are separate, disruptive actions. Source changes do not reload either the Python controller or the QML widget. Compare authenticated loaded `source_revision` and capabilities after a separately approved owner deployment.

## Privacy and scope

The API binds to loopback and requires the owner-private bearer token. Do not expose it through a reverse proxy, borrow another user's bus/token, attach private state to an issue, or run owner helpers as root. Weather/location lookup uses external providers (Open-Meteo and Zippopotam.us); rendering is local. This is not an entirely offline application.

Recovery receipts, owner settings/tokens, generated wallpapers, desktop screenshots, logs, release archives and original Git/index material are excluded from this source candidate. Installation paths no longer assume a particular home directory, mount or account. Configure the intended owner and reviewed Comfy installation before using owner helpers; see [path configuration](docs/deployment.md#portable-path-and-owner-configuration). Product IDs and security-sensitive system paths are not installation placeholders.

## Development and provenance

Development and publication preparation were AI-assisted, with human authorization and review gates. This is not a claim that a human personally authored every line. See [truthful history](docs/history.md). Consult [Actions runs](https://github.com/troyBORG/weather-horde-kde/actions) for actual per-commit CI results rather than inferring a pass from workflow presence. Astronomy Engine is preserved with its original [MIT license](ASTRONOMY-LICENSE.txt) and [provenance](ASTRONOMY-PROVENANCE.json).
