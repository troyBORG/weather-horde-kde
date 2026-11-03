# Connected panorama implementation plan

## Scope and prerequisites

Add an opt-in `connected_panorama` setting, default false. Independent rendering,
per-monitor scenes and all admission/game/VR/telemetry policies remain unchanged.
Connected mode uses the global scene; per-monitor overrides are retained but ignored.
One master covers all active logical outputs, including negative coordinates and
vertical offsets. Physical output sizes are already rotation-adjusted by discovery;
do not rotate them again or multiply native pixels by scale.

Discovery: upstream main was fetched before branching. The historical owner project
has no commits and a mixed index/worktree; leave it untouched. SSH is non-owner
`jorden`. Owner systemd configuration is permission denied and no owning graphical
session is available. Live geometry and installed-source identity remain unverified;
never substitute saved geometry or a screenshot for live KScreen output.

## Implementation and verification sequence

1. Add failing geometry/pixel fixture tests, then implement a bounded logical-layout
   planner and cropper. Reject missing/malformed geometry. Use one padded master,
   with a common density capped to the existing 9-million-pixel output budget.
   Crop logical extents and resample to each native oriented output size.
2. Add failing controller integration tests. Render one global scene/master; validate
   every crop before publishing target pointers or beginning automatic apply. Preserve
   quarantine and recheck guards before each existing transactional wallpaper write.
   No claim of atomic multi-monitor compositor writes: interruption may leave a
   partial application, accurately recorded by existing per-target receipts.
3. Add persistent settings and an optional widget checkbox. Selecting any monitor in
   connected mode requests the complete connected desktop (avoid disconnected batches).
   Keep all independent-mode preferences unchanged. Record layout and shared master
   identity in image metadata; reject stale layouts before connected automatic apply.
4. Build native package and run full offline suite under isolated non-owner HOME/XDG;
   preserve actual logs, counts, warnings and fixture-vs-live distinctions.
5. Review focused diff, commit, push, verify remote SHA; build delivery from committed
   bytes and verify archive and package hashes.
6. Deploy only through maintained owner tooling, with private backup, Auto OFF
   verified before reload, source authentication, settings preservation and rollback.
   If owner access is unavailable, deliver the exact owner entrypoint and explicitly
   report deployment, live geometry, loaded source and GPU visual acceptance blocked.
   Never borrow owner bus/token or use sudo; never override unknown telemetry.

## Deferred

Bezel/physical-size calibration and alignment UI. Logical desktop alignment is the
contract; differing physical DPI cannot establish real-world physical alignment.
Live visual render acceptance waits for owner session and safe generation admission.
