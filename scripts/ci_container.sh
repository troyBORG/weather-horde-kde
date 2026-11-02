#!/usr/bin/env bash
# Run only inside the isolated CI image with /source mounted read-only.
set -euo pipefail
umask 077
# Randomized private HOME distinguishes leaked builder paths from the public,
# documented /home/ci container layout when scanning nested source archives.
HOME=$(mktemp -d /home/ci/build-XXXXXXXX)
export HOME
cd "$HOME"
git -c safe.directory=/source clone --no-hardlinks /source repo
cd repo
python scripts/ci_check.py
cp -a public /home/ci/public
