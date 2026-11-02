"""Release gates and integrity checks execute without GitHub credentials."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import os
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load():
    path = ROOT / 'scripts/ci_release.py'
    assert path.exists(), 'release implementation missing'
    spec = importlib.util.spec_from_file_location('ci_release', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseTests(unittest.TestCase):
    def test_publisher_refuses_corrupt_readback_before_exposing_release(self):
        m = load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / 'public'
            public.mkdir()
            for name in m.ASSETS:
                (public / name).write_bytes(b'fixture')
            manifest = {'commit': 'a' * 40, 'version': '0.1.11',
                        'sha256': {n: hashlib.sha256(b'fixture').hexdigest() for n in m.ASSETS}}
            (public / 'manifest.json').write_text(json.dumps(manifest))
            metadata = root / 'plasma-widget/org.troyborg.weatherhorde/metadata.json'
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps({'KPlugin': {'Version': '0.1.11'}}))
            env = {'GITHUB_SHA': 'a' * 40, 'GITHUB_EVENT_NAME': 'push',
                   'GITHUB_REF': 'refs/heads/main', 'GITHUB_RUN_ID': '123',
                   'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_REPOSITORY': 'fixture/repo'}
            calls = []
            corrupt = True
            def fake_gh(*args):
                calls.append(args)
                if args[0] == 'api':
                    return 'a' * 40 if '/commits/' in args[1] else '{}'
                if args[:2] == ('release', 'view'):
                    if args[-1] == 'assets':
                        return json.dumps({'assets': [{'name': p.name, 'size': p.stat().st_size} for p in public.iterdir()]})
                    return json.dumps({'isDraft': False, 'isPrerelease': True,
                                       'tagName': 'ci-123-1-aaaaaaaaaaaa', 'url': 'https://example.invalid/release'})
                if args[:2] == ('release', 'download'):
                    directory = Path(args[-1])
                    for p in public.iterdir():
                        (directory / p.name).write_bytes(p.read_bytes())
                    if corrupt:
                        (directory / m.ASSETS[0]).write_bytes(b'corruption')
                return ''
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, env), patch.object(m, 'gh', fake_gh):
                    with self.assertRaises(ValueError): m.publish()
                    self.assertFalse(any(c[:2] == ('release', 'edit') for c in calls))
                    corrupt = False
                    calls.clear()
                    m.publish()
                create = next(c for c in calls if c[:2] == ('release', 'create'))
                edit = next(c for c in calls if c[:2] == ('release', 'edit'))
                for flag in ('--draft', '--verify-tag', '--prerelease', '--latest=false'):
                    self.assertIn(flag, create)
                self.assertIn('--latest=false', edit)
                self.assertNotIn('--clobber', str(calls))
            finally:
                os.chdir(previous)

    def test_only_main_push_or_matching_version_tag_can_publish(self):
        m = load()
        sha = 'a' * 40
        self.assertEqual(m.release_target('push', 'refs/heads/main', '0.1.11', sha, '123', '2'),
                         ('ci-123-2-aaaaaaaaaaaa', True))
        self.assertEqual(m.release_target('push', 'refs/tags/v0.1.11', '0.1.11', sha, '123', '1'),
                         ('v0.1.11', False))
        for event, ref in [('pull_request', 'refs/heads/main'), ('push', 'refs/heads/ci/foo'),
                           ('push', 'refs/tags/v0.1.12'), ('push', 'refs/tags/v0.1.11-rc1'),
                           ('workflow_dispatch', 'refs/heads/main')]:
            with self.subTest(event=event, ref=ref), self.assertRaises(ValueError):
                m.release_target(event, ref, '0.1.11', sha, '123', '1')

    def test_artifact_verification_rejects_mismatch_extra_and_wrong_commit(self):
        m = load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in m.ASSETS:
                (root / name).write_bytes(b'fixture')
            manifest = {'commit': 'a' * 40, 'version': '0.1.11',
                        'sha256': {n: hashlib.sha256(b'fixture').hexdigest() for n in m.ASSETS}}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(m.verify_assets(root, 'a' * 40), manifest)
            with self.assertRaises(ValueError): m.verify_assets(root, 'b' * 40)
            (root / 'private.log').write_text('not publishable')
            with self.assertRaises(ValueError): m.verify_assets(root, 'a' * 40)
            (root / 'private.log').unlink()
            (root / m.ASSETS[0]).write_bytes(b'corrupt')
            with self.assertRaises(ValueError): m.verify_assets(root, 'a' * 40)
