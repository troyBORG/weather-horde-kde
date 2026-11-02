"""Real tar/extraction tests, no services or private state."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
class BundleTests(unittest.TestCase):
    def test_generator_is_tracked_and_refuses_existing_output(self):
        script = ROOT/'scripts/make-owner-delivery.py'
        self.assertTrue(script.is_file(), 'missing tracked wrapper generator')
        import subprocess
        with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
            existing = Path(tmp)/'existing'; existing.mkdir()
            keep = existing/'keep'; keep.write_bytes(b'original')
            result = subprocess.run(['python3','-B',str(script),str(existing)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(keep.read_bytes(),b'original')
            self.assertEqual(list(existing.iterdir()),[keep])

    def test_resume_requires_exact_archive_bytes_version_owner_and_inventory(self):
        script = ROOT/'scripts/owner-bootstrap.py'
        self.assertTrue(script.is_file(), 'missing tracked owner wrapper implementation')
        spec = importlib.util.spec_from_file_location('bootstrap', script)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
            root = Path(tmp); archive = root/'source.tar.gz'; dest = root/'candidate'
            files = {'plasma-widget/org.troyborg.weatherhorde/metadata.json': json.dumps({'KPlugin':{'Version':'0.1.11'}}).encode(), 'code.py':b'untouched'}
            with tarfile.open(archive,'w:gz') as tar:
                for name, data in files.items():
                    info = tarfile.TarInfo(name); info.size=len(data); info.mode=0o644
                    tar.addfile(info, io.BytesIO(data))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            m.prepare(archive,dest,digest,'0.1.11')
            before = {p.relative_to(dest): (p.read_bytes(),p.stat().st_mtime_ns) for p in dest.rglob('*') if p.is_file()}
            m.prepare(archive,dest,digest,'0.1.11')
            self.assertEqual(before, {p.relative_to(dest): (p.read_bytes(),p.stat().st_mtime_ns) for p in dest.rglob('*') if p.is_file()})
            for corruption in ('bytes','extra','mode','version','hash'):
                with self.subTest(corruption=corruption):
                    if corruption=='bytes': (dest/'code.py').write_bytes(b'corrupt')
                    if corruption=='extra': (dest/'extra').write_bytes(b'leave me')
                    if corruption=='mode': dest.chmod(0o777)
                    with self.assertRaises(RuntimeError):
                        m.prepare(archive,dest,'0'*64 if corruption=='hash' else digest,'9.9' if corruption=='version' else '0.1.11')
                    if corruption=='bytes': (dest/'code.py').write_bytes(b'untouched')
                    if corruption=='extra': self.assertEqual((dest/'extra').read_bytes(),b'leave me'); (dest/'extra').unlink()
                    if corruption=='mode': self.assertEqual(dest.stat().st_mode & 0o777,0o777); dest.chmod(0o700)
