"""Release gates and integrity checks execute without GitHub credentials."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load():
    path = ROOT / 'scripts/ci_release.py'
    assert path.exists(), 'release implementation missing'
    spec = importlib.util.spec_from_file_location('ci_release', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseTests(unittest.TestCase):
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
