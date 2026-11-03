# Widget sections — 0.1.11 / sections-1

## Implementation and verification plan

1. Base the UI on `946cc1490abf123251b57c4ddb17f2d07e21991e` (connected panorama), not its older main parent. Preserve controller, scheduler, render and wallpaper code unchanged.
2. Keep connection, guard reason, automation scope and latest action above a four-tab scroll area. Default to Wallpaper. Tabs and disclosures do not write settings.
3. Move existing controls and handlers without changing their consent, capability or validation gates. Keep panorama default OFF; status remains authoritative after layout changes.
4. Exercise the real Plasma AppletContext with authenticated ephemeral controllers, native packaging and the entire regression suite. Capture synthetic offscreen views; do not use the owner's bus or GPU.
5. Commit/push a focused branch and stage a hash-pinned owner bundle. Installation/reload remains a separate owner action.

## Everyday navigation

- **Wallpaper:** independent/panorama selector, monitor target, Generate now, Apply, Restore, image preview and apply eligibility. Panorama generates all monitor crops; manual Apply/Restore remains one selected monitor. Auto writes crops sequentially with per-write checks, **not an atomic all-screen switch**.
- **Schedule:** Auto switch, action, target, interval and wake/unlock catch-up. The actual requested-refresh policy has no additional 60-second settling grace. Safe unlocked state and resource/ownership gates remain mandatory. Failed attempts retry after 1, 5, then 15 minutes before requiring attention.
- **Scene:** confirmed location, global/per-monitor scenes, seasonal/holiday options, framing and model selection. Monitor scene overrides are preserved but ignored for panorama.
- **Advanced:** collapsed Connection/manual pairing, manual weather, comparison seed, temporary testing override and diagnostics. Preview prompt opens diagnostics rather than leaving an apparently ineffective button. Raw prompt and weather evidence are retained here, not removed.

An active testing override is shown persistently even when Advanced is closed. The original risk acknowledgment and bounded controller consent remain separate. No override authorizes Auto.

## Build identity

Advanced → Build identity and diagnostics shows `Widget: 0.1.11 / sections-1 / panorama` and the authenticated controller's import-time `source_revision`. The widget label identifies this UI revision, **not a Git hash**. The immutable owner delivery records the exact Git commit and package hash. The controller fingerprint is intentionally unchanged by this QML-only redesign. Installed files, loaded QML and running Python are distinct layers.

## Missing panorama investigation

The supplied screenshots show the older long-form UI without a visible panorama control. The panorama branch places its checkbox immediately after the global Scene selector and does not hide it based on backend capability (it disables unsupported interaction). A controller reporting version 0.1.11 alone cannot establish which QML is loaded.

Read-only cross-user inspection was denied for both the owner's installed package and extracted source. The observed plasmashell process started November 2, before this redesign, but its age does not prove which QML component is loaded or rule out an alternate package instance. **Stale loaded QML is plausible, not confirmed.** Do not state the screenshots prove a packaging or cache defect. No token, private configuration, bus access, cache deletion or reload was used to diagnose it.

## Staged owner acceptance (not performed by the agent)

Use the delivery's OWNER-README for its exact path and command. Arrange an idle maintenance window: do not stop an in-flight render or issue simultaneous widget actions. The preserving installer requires the persistent controller to be stopped by the owner. It leaves settings bytes and Auto preferences unchanged and leaves the controller stopped.

After deployment, the owner can reload **only Plasma's widget host** from their KDE terminal:

```sh
systemctl --user restart plasma-plasmashell.service
```

This briefly reloads the desktop/panel. It is not a controller restart. If that user unit is unavailable, use a normal logout/login instead; do not kill arbitrary shell processes. Because the controller is enabled for the graphical session, logging in may start it with preserved Auto ON and therefore schedule GPU work. Choose that alternative only when ready for that consequence.

Separately, when ready for preserved Auto's possible work:

```sh
systemctl --user start weather-horde-kde.service
```

Open Weather Horde. Wallpaper should show the layout selector at the top. Advanced → Build identity and diagnostics must show the widget revision above, a connected controller and its runtime fingerprint. Check Schedule's Auto/action/targets/interval against your existing preferences. No generation, wallpaper change, owner-visible pairing, login persistence or visual panorama quality is claimed by offline test results.
