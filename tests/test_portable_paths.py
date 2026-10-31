"""Portable configuration without any owner bus or installed Comfy dependency."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


class PortablePathsTests(unittest.TestCase):
    def test_comfy_root_shared_by_identity_and_catalog(self):
        with tempfile.TemporaryDirectory(prefix='comfy space ') as tmp:
            env = dict(os.environ, WEATHER_HORDE_COMFY_ROOT=tmp)
            result = subprocess.run([sys.executable, '-c',
                'import gpu_identity, model_catalog; '
                'print(gpu_identity.COMFY_ROOT); print(model_catalog.COMFY)'],
                env=env, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.splitlines(), [tmp, tmp])

    def test_configuration_rejects_relative_paths(self):
        with patch.dict(os.environ, WEATHER_HORDE_COMFY_ROOT='relative'):
            import portable_paths
            with self.assertRaises(ValueError): portable_paths.comfy_root()

    def test_owner_is_explicit_same_uid_non_root(self):
        import portable_paths
        import pwd
        account = pwd.getpwuid(os.getuid())
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError): portable_paths.require_owner()
        with patch.dict(os.environ, WEATHER_HORDE_OWNER=account.pw_name):
            self.assertEqual(portable_paths.require_owner().pw_uid, os.getuid())
            with patch.object(portable_paths.os, 'getuid', return_value=0):
                with self.assertRaises(RuntimeError): portable_paths.require_owner()
            with patch.object(portable_paths.os, 'getuid', return_value=account.pw_uid + 1):
                with self.assertRaises(RuntimeError): portable_paths.require_owner()
        with patch.dict(os.environ, WEATHER_HORDE_OWNER='no-such-weather-owner'):
            with self.assertRaises(RuntimeError): portable_paths.require_owner()

    def test_launcher_uses_checkout_not_original_home(self):
        import importlib.util
        path = Path('scripts/connect-owner.py').resolve()
        spec = importlib.util.spec_from_file_location('portable_launcher', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.REPO, path.parents[1])

    def test_comfy_unit_renders_configured_paths_and_owner(self):
        import importlib.util
        path = Path('scripts/install-comfy-service.py')
        spec = importlib.util.spec_from_file_location('portable_comfy_install', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='service space ') as tmp, patch.dict(
                os.environ, WEATHER_HORDE_COMFY_ROOT=tmp, WEATHER_HORDE_OWNER='fixture-owner'):
            rendered = module.render_unit()
            self.assertIn('WorkingDirectory='+tmp, rendered)
            self.assertIn('WEATHER_HORDE_OWNER=fixture-owner', rendered)
            self.assertIn(str(path.resolve().parents[1]/'scripts/comfy-owner.py'), rendered)
            self.assertNotIn('@', rendered)
            self.assertIn('ProtectSystem=strict', rendered)

    def test_comfy_unit_real_systemd_syntax(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('comfy_syntax', 'scripts/install-comfy-service.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='comfy unit ') as tmp, patch.dict(
                os.environ, WEATHER_HORDE_COMFY_ROOT=tmp, WEATHER_HORDE_OWNER='fixture-owner'):
            unit = Path(tmp)/module.UNIT
            unit.write_text(module.render_unit())
            result = subprocess.run(['systemd-analyze', '--user', 'verify', str(unit)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')

    def test_controller_environment_preserves_literal_dollar_path(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('controller_unit', 'scripts/install-controller-service.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with patch.dict(os.environ, WEATHER_HORDE_COMFY_ROOT='/srv/comfy $literal'):
            rendered = module.render_unit(['/usr/bin/python3', 'controller.py'])
            self.assertIn('Environment="WEATHER_HORDE_COMFY_ROOT=/srv/comfy $literal"', rendered)

    def test_defaults_and_staging_trust_are_not_site_specific(self):
        import portable_paths
        import pwd
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=Path(tmp)):
            self.assertEqual(portable_paths.comfy_root(), Path(tmp)/'.local/share/ComfyUI')
            self.assertEqual(portable_paths.trusted_source_uids(), (0, os.getuid()))
            with patch.dict(os.environ, XDG_DATA_HOME=tmp):
                self.assertEqual(portable_paths.comfy_root(), Path(tmp)/'ComfyUI')
            with patch.dict(os.environ, WEATHER_HORDE_STAGING_USER=pwd.getpwuid(os.getuid()).pw_name):
                self.assertEqual(portable_paths.trusted_source_uids(), (0, os.getuid(), os.getuid()))
            with patch.dict(os.environ, WEATHER_HORDE_STAGING_USER='no-such-staging-account'):
                with self.assertRaises(RuntimeError): portable_paths.trusted_source_uids()
            for invalid in ('relative', '/srv/../elsewhere', '/srv/bad\npath'):
                with patch.dict(os.environ, WEATHER_HORDE_COMFY_ROOT=invalid):
                    with self.assertRaises(ValueError): portable_paths.comfy_root()

    def test_unit_template_tokens_inside_paths_are_literal(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('comfy_tokens', 'scripts/install-comfy-service.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with patch.dict(os.environ, WEATHER_HORDE_COMFY_ROOT='/srv/@OWNER_ENV@', WEATHER_HORDE_OWNER='fixture-owner'):
            rendered = module.render_unit()
            self.assertIn('WorkingDirectory=/srv/@OWNER_ENV@\n', rendered)

    def test_paths_reject_trailing_whitespace_before_unit_rendering(self):
        import portable_paths
        with patch.dict(os.environ, WEATHER_HORDE_COMFY_ROOT='/srv/comfy '):
            with self.assertRaises(ValueError): portable_paths.comfy_root()
