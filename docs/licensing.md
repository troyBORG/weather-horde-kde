# Licensing and third-party review — 2026-10-30

## Original project: unresolved grant

The existing Plasma metadata declares `GPL-3.0-or-later`. The preserved tree has no project-wide LICENSE text or verified owner/contributor relicensing consent. Metadata alone has not been treated as authority to license every Python, C++, QML, test and documentation file. No new LICENSE or copyright holder has been invented. Resolve scope, ownership and intended grant before public redistribution; private preparation does not resolve rights.

## Astronomy Engine: verified upstream provenance

`astronomy_vendor.py` is Astronomy Engine 2.1.19. The wheel URL and SHA-256 in `ASTRONOMY-PROVENANCE.json` were independently fetched/checked on 2026-10-30. Its `astronomy/astronomy.py` matches the vendored file byte-for-byte, and the wheel LICENSE matches `ASTRONOMY-LICENSE.txt` byte-for-byte. The original MIT copyright/permission notices remain intact (the source and wheel license use their original respective year ranges). No modifications or replacement license were applied.

## External dependencies and generated distributions

Qt, KDE Plasma/KPackage and their runtime/build components, Python/Pillow, systemd, D-Bus, Node.js, ComfyUI, model checkpoints and upscalers are external dependencies, not vendored source in this candidate. Their own licenses and any compiled-distribution obligations still apply; no blanket GPL compatibility certification or permission to redistribute model weights is claimed. This candidate excludes generated native binaries and packages. Reassess obligations before distributing binary release assets.

Open-Meteo and Zippopotam.us are external data services; their current usage/data terms must be checked for the intended deployment. A source license does not grant rights in external weather data, model weights or generated imagery. No model, wallpaper or private screenshot has been included.
