"""Public packages must not ship CMake's absolute-path build intermediates."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import io
import sys
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load():
    path = ROOT / 'scripts/public_artifacts.py'
    assert path.exists(), 'public artifact policy is missing'
    spec = importlib.util.spec_from_file_location('public_artifacts', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicArtifactTests(unittest.TestCase):
    def test_scanner_inspects_compressed_members_and_qrc_names(self):
        with patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
            from ci_check import scan
        forbidden = [b'/private-builder-checkout']
        for name, data in [('runtime.so', forbidden[0]), ('generated.qrc', b'innocuous')]:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(name, data)
            with self.subTest(name=name), self.assertRaises(ValueError):
                scan(stream.getvalue(), forbidden)
        scan(b'public relative runtime data', forbidden)

    def test_runtime_inventory_excludes_build_intermediates(self):
        policy = load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = root / 'contents/ui/WeatherHorde/LocalPairing'
            plugin.mkdir(parents=True)
            names = ['qmldir', 'weatherpairing.qmltypes', 'libweatherpairing.so',
                     'libweatherpairingplugin.so', 'weatherpairing.qrc', 'private.cpp', '.cache']
            for name in names:
                (plugin / name).write_text('/private/build/path')
            (root / 'metadata.json').write_text('{}')
            actual = {p.name for p in policy.package_files(root)}
            self.assertEqual(actual, {'metadata.json', *names[:4]})

    def test_public_receipt_is_allowlisted_not_private_log_redaction(self):
        policy = load()
        receipt = {'sha256': 'a' * 64, 'readback_matches_source': True,
                   'bytes': 123, 'archive': '/private/archive', 'validation_root': '/private/root',
                   'command': ['/private/tool'], 'output': 'secret', 'future_private_field': 'secret'}
        public = policy.public_receipt(receipt)
        self.assertEqual(public, {'sha256': 'a' * 64, 'readback_matches_source': True,
                                 'bytes': 123, 'live_plasma_installed': False})
        self.assertNotIn('private', json.dumps(public))
