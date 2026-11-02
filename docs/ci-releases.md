# CI checks and automatic releases

[Workflow](../.github/workflows/ci.yml) runs on every branch push, every pull
request, and `v*` tag pushes. Branch pushes also let maintainers exercise a new
workflow before merging it. There are no path filters: documentation-only main
pushes receive the same checks and prerelease treatment.

## Checks and isolation

The Ubuntu 24.04 **host** runs Docker; it is not the native KDE toolchain.
`.github/ci/Dockerfile` pins the official Arch image by digest and signed packages
to the **2026-11-01 Arch Linux Archive snapshot**. This provides Qt6, Plasma6,
KPackage, CMake, Python/Pillow/PyYAML, Node, systemd and D-Bus. Updating the image
or snapshot is a reviewed dependency change requiring a fresh native pass.

`scripts/ci_check.py` runs as a non-root disposable account under trusted HOME
ancestry, with fresh short private XDG directories and offscreen/software Qt.
The test container has **no external network**, no added capabilities, no GPU,
no host user bus, no owner state and a read-only source mount. Only fixture
loopback HTTP and private D-Bus are used. Dependency installation happens in a
separate network-enabled image build. No services are enabled, no wallpaper is
changed, and this is not deployment or live GPU acceptance.

The image also supplies private container-local `/run/user/1001` for installer
fixtures that enforce the real owner-session runtime path. It contains no host
socket or running user manager. Systemd manual pages and `man-db` are retained
because real `systemd-analyze verify` checks documentation references as well as
unit syntax; the default minimal Arch image excludes those pages.

Checks build the native token reader/plugin with assertions enabled in its
boundary test, install/read back a fresh KPackage root, run standard full
unittest discovery (including the native offscreen Plasma/QML HTTP harness),
and fail on **any skip**, failure, error, or incomplete collection. Imported
TestCase duplication is counted honestly: the manifest records both executed
cases and unique IDs. The workflow policy tests require PyYAML.

Only after tests pass does CI assemble the owner installer using the same
already-tested plasmoid. It never rebuilds in the publishing job. The public
artifact contains exactly:

- `org.troyborg.weatherhorde.plasmoid`
- `weather-horde-controller.zip`
- `weather-horde-owner-installer.tar.gz`
- `manifest.json` — exact commit, metadata version, test counts and SHA-256s

These are Linux **x86_64 / Arch snapshot Qt6/Plasma6** artifacts, not universal
binaries for every distribution/Qt minor version. Build from source against the
target toolchain when ABI compatibility differs. The owner installer retains
its explicit same-user/stopped-controller safety requirements; a release does
not authorize or perform installation.

## Public artifact boundary

Generated QRC/CMake intermediates are not runtime files and can contain absolute
builder paths. The plugin inventory now allowlists its two shared libraries,
`qmldir` and QML type description. Release builds map compiler file prefixes to
relative names and retain `$ORIGIN` runtime lookup. KPackage readback compares
the actual archive contents, including bundled data. Raw build receipts remain
local: the owner archive receives only allowlisted digest/size/readback fields,
never validation paths, commands or output. A recursive scan of all public ZIP
and nested tar members fails on the actual checkout or HOME path and generated
QRC files. Logs, cache trees and private receipts are never uploaded as assets.
This is build-path privacy, not a claim of bit-for-bit reproducible ZIP/gzip
metadata across build times or a general secret scanner.

## Publication policy

- **PRs and feature branches:** read-only checks, downloadable CI artifacts for
  14 days, no release job. No `pull_request_target`, manual dispatch or secrets.
- **Successful pushes to `main`:** unique prerelease tag
  `ci-<run-id>-<attempt>-<commit-prefix>`, pointing to the full tested commit.
- **Successful version tag pushes:** stable releases only for exact `vX.Y.Z`
  tags matching `KPlugin.Version` in the tagged commit. Other `v*` tags fail
  checks rather than being published. All the same native checks run first.
- Tags are never moved and release assets are never overwritten. Stable reruns
  refuse an existing release. Failed publication may leave an immutable tag or
  draft for maintainer inspection; it does not silently repair/replace one.
- Every run has its own publication concurrency group, with cancellation
  disabled. New main pushes cannot discard an older pending release. Neither
  prereleases nor stable releases automatically change GitHub's **Latest**
  designation (`--latest=false`), so out-of-order completion can never promote
  an older build over a newer stable release. Maintainers may explicitly choose
  Latest after reviewing stable releases.

The release job requires successful checks and a trusted main/tag push. Only
that job grants `contents: write`; its ephemeral `GITHUB_TOKEN` is available
only to the publishing step. Checkout never persists credentials. Actions are
pinned to full upstream commit SHAs. No personal token is needed once merged.
Repository/organization Actions policy must permit the workflow token to create
releases. Branch protection/rulesets are repository settings, not installed by
this branch; require **Native Plasma 6 and fixtures** if merge gating is wanted.

The publishing step downloads the same-run named artifact, checks exact
inventory, all hashes, version and commit, and verifies the remote tag still
resolves to that commit. It creates a draft, uploads the assets, reads them back
and verifies their bytes before exposing the release. Release notes link to the
commit and workflow run. No build/test code runs with a write token.

## Existing versions and reproduction

Adding this workflow does **not** retroactively release the existing `v0.1.11`
tag. Do not delete/re-push it to force a release. After merging, main pushes
produce prereleases; a future metadata/version bump and matching new tag produce
a stable release. This workflow deliberately offers no manual bypass.

On a disposable Linux machine with Docker (not the graphical owner's checkout):

```sh
docker build -t weather-horde-ci .github/ci
docker create --name weather-horde-ci-check --network none --cap-drop ALL \
  --security-opt no-new-privileges \
  --mount type=bind,source="$PWD",target=/source,readonly \
  weather-horde-ci bash /source/scripts/ci_container.sh
docker start --attach weather-horde-ci-check
docker cp weather-horde-ci-check:/home/ci/public ./public
```

Use a clean ordinary clone, not a linked worktree whose `.git` points outside
the mounted directory. Inspect the exit status before copying outputs; use a
new container name and clean checkout for each reproduction.
