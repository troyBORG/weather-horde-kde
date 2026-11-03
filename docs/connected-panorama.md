# Connected panorama

The **Connected panorama — all monitors** checkbox in Scene controls is optional
and starts **off**. Turn it on to generate one shared scene across all enabled
monitors. The global scene selector is used; per-monitor scene overrides are
preserved but ignored until panorama is turned off.

Generation covers **all active monitors**, even when a single monitor is selected.
That also applies to automatic generation/application: one stale monitor refreshes
the complete connected scene. Your independent-mode monitor selection is retained.
Manual **Apply** and **Restore** remain explicit, single-monitor operations. To
apply a preview manually, select and apply each monitor's corresponding crop.

The scene follows KDE's **logical desktop layout**, including vertical offsets,
negative coordinates and gaps. Portrait dimensions are oriented once by KScreen
discovery; scale maps logical rectangles to each monitor's native pixels. This is
not physical-DPI or bezel calibration. Displays with different physical pixel
sizes may still need future alignment controls.

## Rendering and limits

One bounded base render is upscaled as a complete master through the existing
reviewed workflow. Each logical monitor rectangle is then cropped/resampled to its
native oriented dimensions. The master is padded to a 64-pixel grid and limited
to the existing nine-million-pixel final-image budget. Large arrangements therefore
share lower-density source detail; native-sized crops do not imply native detail.
Some extreme aspect ratios cannot fit the reviewed latent geometry and are refused,
not silently routed through an unreviewed rendering path.

Crop receipts retain the shared master hash, layout, scene and workflow hash.
Every crop is decoded/validated before any target pointers are published or any
automatic wallpaper write begins. If activity becomes unsafe during this stage,
the entire batch is quarantined. A changed layout requires a fresh generation;
old panorama crops are not automatically reinterpreted for a new arrangement.

Automatic application uses the existing per-monitor transactional writes and
readback, checking safety before each write. It is **not an atomic compositor
transaction**: if a game starts or a write fails between monitors, earlier writes
may already have succeeded. Their receipts remain accurate; no unsafe rollback or
forced completion is attempted. A connected retry regenerates the complete scene.
Independent mode keeps its existing partial-target retry behavior.

GPU admission, game/VR checks, uncertain-telemetry blocking, model selection,
quarantine and manual consent are not relaxed. Enabling panorama does not enable
Auto or provide a testing override.

## Validation and rollout

Tests use synthetic pixels and ephemeral/offscreen controls, not live GPU imagery.
They cover offset portrait/landscape geometry, mixed scale, rotation, native crop
pixels, one master submission, all-crop publication, late quarantine, stale layout
rejection, and all-output scheduler preflight. Full native/package and regression
checks must still pass for the exact delivery commit.

Use the maintained hash-pinned owner delivery described in
[owner installer hardening](owner-installer-hardening.md). Before an owner reload,
retain the previous settings and source, switch Auto **off** and verify it is off.
The stopped-only installer preserves those current settings and supplies a rollback
backup; it does not authenticate a newly started controller or reload Plasma for
you. Confirm the new source fingerprint, `connected_panorama` capability, and
visible checkbox before restoring previously approved automation settings. Do not
force a test render while game/VR activity or unknown telemetry blocks generation.
