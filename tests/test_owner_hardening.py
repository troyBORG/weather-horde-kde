"""Offline owner installer regression tests; no real user manager calls."""
import errno
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class HardeningTests(unittest.TestCase):
    def test_original_cause_survives_rollback_failure(self):
        m = load('deploy-preserving-owner.py')
        io = Mock()
        inner = OSError(errno.EIO, 'secret')
        original = RuntimeError('not public'); original.__cause__ = inner
        io.install.side_effect = original
        io.rollback.side_effect = OSError(errno.EROFS, 'secret rollback')
        with self.assertRaises(RuntimeError) as caught: m.deploy(io)
        self.assertIs(caught.exception.__cause__, inner)
        text = m.failure_report(caught.exception)
        self.assertIn('EIO', text)
        self.assertIn('EROFS', text)
        self.assertNotIn('secret', text)

    def test_listener_failure_identifies_family_without_skipping_guards(self):
        helper = load('install-controller-service.py')
        self.assertTrue(callable(getattr(helper, 'check_listeners', None)), 'missing family-aware listener probe')
        for family, code in ((helper.socket.AF_INET6, errno.EAFNOSUPPORT), (helper.socket.AF_INET6, errno.EADDRINUSE), (helper.socket.AF_INET, errno.EACCES)):
            seen = []
            def socket(af):
                seen.append(af)
                if af == family: raise OSError(code, 'SECRET')
                return Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock(return_value=False))
            with patch.object(helper.socket, 'socket', socket):
                with self.assertRaises(RuntimeError) as caught: helper.check_listeners()
            self.assertIn('IPv6' if family == helper.socket.AF_INET6 else 'IPv4', str(caught.exception))
            self.assertIsInstance(caught.exception.__cause__, OSError)
            self.assertNotIn('SECRET', str(caught.exception))
            self.assertEqual(seen[0], helper.socket.AF_INET)

    def test_exited_process_race_is_not_an_unexplained_oserror(self):
        helper = load('install-controller-service.py')
        proc = Mock(); process = Mock(); process.name = '123'
        proc.iterdir.return_value = [process]
        process.stat.side_effect = ProcessLookupError(errno.ESRCH, 'gone')
        self.assertFalse(helper.controller_running(proc))

    def test_readonly_preflight_precedes_stopped_checks_and_is_repeatable(self):
        m = load('deploy-preserving-owner.py')
        self.assertTrue(callable(getattr(m, 'preflight', None)), 'missing readonly preflight')
        io = Mock()
        for _ in range(2): m.preflight(io)
        self.assertEqual([c[0] for c in io.method_calls], ['capture','capture'])

    def test_malformed_environment_is_actionable_without_echoing_values(self):
        m = load('deploy-preserving-owner.py')
        import pwd
        with patch.dict(os.environ, WEATHER_HORDE_OWNER=pwd.getpwuid(os.getuid()).pw_name, XDG_DATA_HOME='/safe/../SECRET'):
            with self.assertRaises((ValueError, RuntimeError)) as caught: m.OwnerDeployment('/old')
        text = m.failure_report(caught.exception)
        self.assertIn('XDG_DATA_HOME', text)
        self.assertNotIn('SECRET', text)

    def test_staged_os_failure_is_sanitized_and_retains_rollback_cause(self):
        m = load('deploy-preserving-owner.py')
        self.assertTrue(callable(getattr(m, 'failure_report', None)), 'missing safe staged reporter')
        io = Mock()
        original = OSError(errno.ENOSPC, 'SECRET token settings', '/secret/env')
        rollback = OSError(errno.EACCES, 'SECRET rollback', '/secret/token')
        io.install.side_effect = original
        io.rollback.side_effect = rollback
        with self.assertRaises(OSError) as caught: m.deploy(io)
        self.assertIs(caught.exception, original)
        text = m.failure_report(caught.exception)
        for expected in ('install', 'ENOSPC', 'rollback', 'EACCES'): self.assertIn(expected, text)
        for forbidden in ('SECRET', '/secret', 'settings'): self.assertNotIn(forbidden, text)


    def test_untrusted_ancestor_reports_exact_mode_uid_and_narrow_advice(self):
        helper = load('install-controller-service.py')
        with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
            ancestor = Path(tmp)/'share'; ancestor.mkdir(); ancestor.chmod(0o777)
            child = ancestor/'unchanged'; child.write_bytes(b'keep')
            with self.assertRaises(RuntimeError) as caught:
                helper.safe_path(child, (0, os.getuid()))
            text = str(caught.exception)
            self.assertIn(str(ancestor), text)
            self.assertIn('0777', text)
            self.assertIn('uid='+str(os.getuid()), text)
            self.assertIn('chmod go-w', text)
            self.assertNotIn('chmod -R', text)
            self.assertEqual(ancestor.stat().st_mode & 0o777, 0o777)
            self.assertEqual(child.read_bytes(), b'keep')
