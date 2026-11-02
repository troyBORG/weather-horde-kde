#!/usr/bin/env python3
"""Non-owner CI entrypoint: native build, zero-skip suite, exact public outputs.
Run inside the network-disabled CI container, never in the graphical owner session.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

from ci_release import ASSETS, release_target, verify_assets

ROOT = Path(__file__).resolve().parents[1]


def scan(data, forbidden, member_name='asset'):
    """Inspect uncompressed archive members, including nested installer payloads."""
    if any(value in data for value in forbidden):
        raise ValueError('Public artifact contains builder path in ' + member_name)
    stream = io.BytesIO(data)
    if zipfile.is_zipfile(stream):
        with zipfile.ZipFile(stream) as archive:
            for name in archive.namelist():
                if name.endswith('.qrc'):
                    raise ValueError('Generated QRC is not a runtime artifact')
                scan(archive.read(name), forbidden, name)
    elif data[:2] == b'\x1f\x8b':
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            for member in archive:
                if member.isfile():
                    scan(archive.extractfile(member).read(), forbidden, member.name)


def main():
    os.chdir(ROOT)
    if os.getuid() == 0 or os.environ.get('DBUS_SESSION_BUS_ADDRESS') or os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
        raise RuntimeError('Use an isolated non-root, non-graphical CI account')
    os.umask(0o077)
    os.environ.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', PYTHONDONTWRITEBYTECODE='1')
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if sha != os.environ.get('CI_SHA', sha):
        raise RuntimeError('Checkout differs from event commit')
    version = json.loads((ROOT / 'plasma-widget/org.troyborg.weatherhorde/metadata.json').read_text())['KPlugin']['Version']
    ref = os.environ.get('CI_REF', '')
    if ref.startswith('refs/tags/'):
        release_target('push', ref, version, sha, '0', '0')
    with tempfile.TemporaryDirectory(prefix='ci-', dir=Path.home()) as tmp:
        for key, suffix in [('XDG_CONFIG_HOME','cfg'), ('XDG_STATE_HOME','state'), ('XDG_DATA_HOME','data'), ('XDG_CACHE_HOME','cache'), ('XDG_RUNTIME_DIR','run')]:
            path = Path(tmp) / suffix
            path.mkdir(mode=0o700)
            os.environ[key] = str(path)
        subprocess.run([sys.executable, 'scripts/package.py'], check=True)
        sys.path.insert(0, str(ROOT))
        suite = unittest.defaultTestLoader.discover('tests')
        def ids(test):
            if isinstance(test, unittest.TestSuite):
                return [item for child in test for item in ids(child)]
            return [test.id()]
        collected = ids(suite)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        summary = {'executed': result.testsRun, 'unique_ids': len(set(collected)),
                   'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped)}
        print(json.dumps(summary), flush=True)
        if not result.wasSuccessful() or result.skipped or result.testsRun != len(collected):
            # Public annotations contain only test IDs/counts, never raw fixture
            # tracebacks, receipts or environment. Useful without log-download auth.
            failed = [test.id() for test, _ in result.failures + result.errors + result.skipped]
            print('::error title=Native fixture checks::' + json.dumps(summary) + ' ' + ', '.join(failed), flush=True)
            raise RuntimeError('Full suite must pass with no skips')
        # Production generator checks that committed source is clean and the exact
        # already-tested plasmoid matches its readback receipt. Never rebuild here.
        delivery = ROOT / 'artifacts/ci-owner-delivery'
        subprocess.run([sys.executable, 'scripts/make-owner-delivery.py', str(delivery)], check=True)
        public = ROOT / 'public'
        public.mkdir()  # refuse reuse of stale outputs
        for name in ASSETS[:2]:
            shutil.copyfile(ROOT / 'artifacts' / name, public / name)
        with tarfile.open(public / ASSETS[2], 'w:gz') as archive:
            for file in sorted(delivery.iterdir()):
                archive.add(file, arcname=file.name)
        forbidden = [str(ROOT).encode(), str(Path.home()).encode()]
        for name in ASSETS:
            scan((public / name).read_bytes(), forbidden)
        manifest = {'commit': sha, 'version': version, 'tests': summary,
                    'platform': 'linux-x86_64', 'toolchain_snapshot': 'Arch 2026-11-01',
                    'sha256': {name: hashlib.sha256((public / name).read_bytes()).hexdigest() for name in ASSETS}}
        (public / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        verify_assets(public, sha)
        print('PUBLIC_ARTIFACTS_VERIFIED ' + sha)


if __name__ == '__main__':
    main()
