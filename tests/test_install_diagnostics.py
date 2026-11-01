"""No owner manager/state is accessed by these diagnostic regressions."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer_diagnostics_test', ROOT/'scripts/install-controller-service.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DiagnosticTests(unittest.TestCase):
    def test_error_report_is_structured_and_never_echoes_sensitive_payloads(self):
        self.assertTrue(hasattr(m, 'failure_details'), 'installer still hides exception provenance')
        secret = 'SECRET_TOKEN_LOCATION_ARGV'
        for exc in [PermissionError(13, secret, '/private/'+secret),
                    ValueError(secret), RuntimeError(secret),
                    subprocess.CalledProcessError(1, ['systemctl', '--user', 'show', secret], output=secret, stderr=secret),
                    subprocess.TimeoutExpired(['kscreen-doctor', '-j', secret], 30, output=secret)]:
            with self.subTest(kind=type(exc).__name__):
                result = m.failure_details(exc, 'read-settings')
                text = json.dumps(result)
                self.assertNotIn(secret, text)
                self.assertEqual(result['stage'], 'read-settings')
                self.assertEqual(result['exception'], type(exc).__name__)
        self.assertEqual(m.failure_details(PermissionError(13, secret), 'backup-create')['errno'], 13)
        result = m.failure_details(subprocess.CalledProcessError(1, ['systemctl', '--user', 'is-enabled', secret]), 'enablement')
        self.assertEqual(result['command'], 'systemctl:is-enabled')
        self.assertEqual(result['returncode'], 1)

    def test_cpython_ignores_denied_bytecode_cache_writes(self):
        # A real loader import, with the cache write failing as on an unwritable
        # checkout. This is not evidence about historical owner filesystem state.
        import importlib.machinery
        import importlib._bootstrap_external
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'cache_probe.py'
            source.write_text('answer = 42\n')
            loader=importlib.machinery.SourceFileLoader('cache_probe', str(source))
            spec=importlib.util.spec_from_loader('cache_probe', loader)
            module=importlib.util.module_from_spec(spec)
            with patch.object(__import__('sys'), 'dont_write_bytecode', False), patch.object(
                importlib._bootstrap_external, '_write_atomic', side_effect=PermissionError(13, 'fixture')) as write:
                loader.exec_module(module)
            self.assertTrue(write.called)
            self.assertEqual(module.answer, 42)

    def test_readonly_audit_blocks_writes_and_mutating_commands(self):
        self.assertTrue(hasattr(m, 'readonly_audit'), 'no guarded exact-main probe')
        for event, args in [('open', ('secret', 'w', os.O_WRONLY)),
                            ('os.mkdir', ('secret', 0o700, -1)),
                            ('os.rename', ('a', 'b', -1, -1)),
                            ('socket.connect', (None, 'secret')),
                            ('subprocess.Popen', ('systemctl', ['systemctl', '--user', 'start', m.UNIT], None, None))]:
            with self.subTest(event=event), self.assertRaises(PermissionError):
                m.readonly_audit(event, args)
        for argv in [['systemctl', '--user', 'show', m.UNIT],
                     ['systemctl', '--user', 'is-enabled', m.UNIT], ['kscreen-doctor', '-j']]:
            m.readonly_audit('subprocess.Popen', (argv[0], argv, None, None))
        m.readonly_audit('open', ('secret', 'r', os.O_RDONLY))


if __name__ == '__main__':
    unittest.main()
