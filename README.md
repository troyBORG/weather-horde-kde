# Weather Horde KDE

**Weather-aware AI wallpapers for KDE Plasma 6, generated on your own GPU with ComfyUI.**

Choose a scene, generate a preview, and apply it to a monitor. Weather Horde uses local weather, time of day and Moon position to guide the image prompt. Optional automation can refresh previews or wallpapers for you.

> **Experimental.** Setup is still hands-on, and generation currently relies on NVIDIA GPU telemetry. ComfyUI and model weights are not included. Weather and location lookups need internet access; image generation stays local.

## What you can do

- Pick rural, small-town street, park, woodland or river scenes—or rotate them randomly.
- Choose different scenes for different monitors, with portrait-aware framing.
- Optionally connect all monitors with [one shared panorama](docs/connected-panorama.md), respecting the desktop's vertical offsets and scaling.
- Preview an image before changing your wallpaper; apply or restore one selected monitor at a time.
- Enable automatic prompt previews, image previews, or generation **and** wallpaper changes. You choose the mode, monitors and interval.
- Optionally catch up on missed refreshes after unlocking or finishing a game.
- Add optional [seasonal styling and holiday decorations](docs/seasons-and-holidays.md). Both start off by default.

Generation pauses when game/VR activity, GPU load, low VRAM or uncertain monitoring makes it unsafe. A paused job is not necessarily an error; check the widget's explanation before changing settings.

## Before installing

You need:

- **Linux with KDE Plasma 6** and a systemd user session.
- **Python 3 with Pillow**, plus KDE's display and wallpaper command-line tools.
- **A local ComfyUI installation** with a compatible, reviewed SD1.5 or SDXL checkpoint and the upscaler required by your workflow.
- **An NVIDIA GPU with working telemetry and enough free VRAM.**

Building from source also needs Qt 6 development tools, CMake, a C++17 compiler and KPackage/libplasma development files. See [build and test instructions](CONTRIBUTING.md) for the full toolchain.

## Install or update

Start with the [releases](https://github.com/troyBORG/weather-horde-kde/releases) or a reviewed source checkout. Release assets target **Linux x86_64 with the pinned Arch Qt6/Plasma6 toolchain**; rebuild from source if your Qt ABI differs. Downloading a release does not update your installation.

There are two setup paths:

1. **First installation:** follow the [deployment guide](docs/deployment.md) to configure your KDE account and ComfyUI path, build/verify the widget, and install the persistent controller. This is not a one-click installer.
2. **Updating an existing persistent installation:** follow the [owner delivery guide](docs/owner-installer-hardening.md). The generated `OWNER-DEPLOY.sh` checks the delivery first; deployment requires a safely idle, stopped controller and preserves your settings. Starting the controller is a separate step.

Run installation tools as your normal KDE user, **not with sudo**. Keep the backup directory printed by the installer. An update preserves Auto settings, so an installation that had Auto on can resume scheduled work after you start it.

## First use

The widget has four sections: **Wallpaper** for layout, monitor and preview actions; **Schedule** for Auto; **Scene** for location, scenes and model; **Advanced** for collapsed pairing, manual weather, seed, testing override and diagnostics. Status stays visible above the sections. See [navigation and build identity](docs/widget-sections.md).

Once the controller and widget are installed and connected:

1. **Confirm your location.** The suggested location is not automatic detection of where you live.
2. **Choose a scene, model and monitor.** Start with one monitor to check the result.
3. **Generate a preview.** This renders an image without applying it. If generation is deferred, read the status reason.
4. **Select that monitor and apply the preview.** Manual Apply requires one monitor, not “all.” Restore is a separate action when a saved restore target is available.
5. **Enable Auto only if you want it.** Choose whether it previews prompts, generates images, or also changes wallpapers. Review the target monitors and interval before enabling it.

AI images may not match every detail of the weather or prompt. Inspect a preview before relying on a scene's accuracy.

<details>
<summary><strong>Refresh timing</strong></summary>

Refresh intervals include 5, 10, 15 and 30 minutes, as well as longer choices. Existing saved intervals are not changed by an update.

Catch-up refresh is opt-in. Once the session is known to be unlocked and fresh safety observations are valid, there is no extra 60-second settling requirement. Other safety checks, retry delays and errors can still defer generation.

The Schedule explanation reflects the [current refresh policy](docs/requested-refresh-0.1.11.md). Older loaded widgets may still mention “60 safe seconds”; check Advanced → Build identity after an owner-approved widget reload.

</details>

## Troubleshooting and privacy

- **Not paired / disconnected:** check that the controller is running in your KDE session and that the widget can load its local pairing helper. See [deployment](docs/deployment.md).
- **Preview only:** image rendering has not been enabled/configured in the controller.
- **Paused / monitoring unknown:** read the displayed reason. Do not use the testing override as a routine workaround.
- **Update refused:** follow the [installer diagnostics and recovery guide](docs/owner-installer-hardening.md). Do not recursively loosen permissions to bypass its checks.

The controller listens only on loopback and requires a private token. Do not expose it through a reverse proxy or post tokens, settings, screenshots or private logs in issues. Weather/location queries go to Open-Meteo and Zippopotam.us. See [security](SECURITY.md) for the trust boundaries.

## Development

For builds, tests and contribution rules, see [CONTRIBUTING.md](CONTRIBUTING.md). Automated coding assistants should also read [AGENTS.md](AGENTS.md).

- [CI checks and release policy](docs/ci-releases.md)
- [Test setup and historical validation](docs/testing.md)
- [Project history](docs/history.md)

Development was AI-assisted. See [licensing status](docs/licensing.md) before redistribution: there is currently no project-wide license grant. Vendored Astronomy Engine retains its [MIT license](ASTRONOMY-LICENSE.txt) and [provenance](ASTRONOMY-PROVENANCE.json).
