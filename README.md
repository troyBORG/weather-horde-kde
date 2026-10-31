# Weather Horde KDE

A KDE Plasma 6 widget and authenticated loopback controller for weather-aware wallpaper previews using local ComfyUI. The source snapshot reports version **0.1.10**; that is not a Git release tag or proof of a loaded deployment.

**Experimental source release.** Owner and Comfy installation paths are explicit configuration; geographic defaults and some legacy recovery targets remain site-specific. Read [deployment](docs/deployment.md), [security](SECURITY.md), and [licensing status](docs/licensing.md) before installation or redistribution. No project-wide license grant has been invented.

## What it does

- Weather-inspired rural, street, park, woodland and river scenes; fixed, random and per-monitor scene choices.
- Day/night and lunar evidence, expiring manual weather observations, and portrait-aware framing.
- Reviewed local SD1.5/SDXL checkpoint discovery and bounded native-geometry workflows. Model files are not included.
- Manual **Generate** creates a validated preview. **Apply** and **Restore** are separate selected-monitor transactions with readback.
- Explicit Auto choices distinguish prompt preview, generation, and generation plus wallpaper application. Installing capabilities is not new automation consent.
- Game/VR, unknown clients, GPU load/VRAM, queue ownership and image-validation guards defer unsafe work. Testing override is explicit and temporary, not a recommended deployment workaround.

Prompts are not pixel constraints. Synthetic fixture images and passing tests do not prove generated visual quality or live wallpaper application.

## Requirements and build

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

Development and publication preparation were AI-assisted, with human authorization and review gates. This is not a claim that a human personally authored every line. See [truthful history](docs/history.md). No CI badge or remote publication verification is claimed. Astronomy Engine is preserved with its original [MIT license](ASTRONOMY-LICENSE.txt) and [provenance](ASTRONOMY-PROVENANCE.json).
