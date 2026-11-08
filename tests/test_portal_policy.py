"""Exact installed KDE portal provenance; no live owner access."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import safety

GOOD = dict(processes=['kwin_wayland'], complete=True, age=0, sample_gap=10,
            utilization=[0, 0], total_mib=24576, free_mib=20000)

class PortalPolicyTests(unittest.TestCase):
    def test_verified_portal_is_ordinary_desktop_client(self):
        with patch('safety.os.readlink', return_value='/usr/lib/xdg-desktop-portal-kde'), patch('safety.portal_identity', return_value=True, create=True):
            identity = safety.gpu_client_identity(424242, '/games/fake')
        self.assertEqual(safety.assess(GOOD | {'gpu_clients':[identity['name']], 'gpu_pids':[424242], 'gpu_client_identities':[identity]}), ('safe','checks_passed'))

    def test_exact_portal_requires_pid_bound_installed_identity(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            binary = root/'xdg-desktop-portal-kde'; binary.write_bytes(b'fixture')
            proc = root/'proc'; entry = proc/'424242'; entry.mkdir(parents=True)
            (entry/'exe').symlink_to(binary)
            (entry/'stat').write_text('424242 (portal) S 1 ' + '0 '*17 + '100 0')
            with patch('safety.PORTAL_EXECUTABLE', str(binary)), patch('safety.INSTALL_UID', os.getuid()):
                self.assertTrue(safety.portal_identity(424242, proc))

    def test_paths_argv_and_unverified_names_never_authorize_portal(self):
        self.assertEqual(safety.PORTAL_EXECUTABLE, '/usr/lib/xdg-desktop-portal-kde')
        for executable in ['/tmp/xdg-desktop-portal-kde', '/usr/lib/xdg-desktop-portal-kde-helper',
                           '/usr/lib/xdg-desktop-portal-kde (deleted)', '/games/unknown', None]:
            with self.subTest(executable=executable), patch('safety.os.readlink', return_value=executable,
                    side_effect=PermissionError if executable is None else None):
                identity = safety.gpu_client_identity(424242, '/usr/lib/xdg-desktop-portal-kde --daemon')
                self.assertEqual(safety.assess(GOOD | {'gpu_clients':[identity['name']], 'gpu_pids':[424242], 'gpu_client_identities':[identity]})[0], 'unknown')
        for reported in ['/usr/lib/xdg-desktop-portal-kde', 'xdg-desktop-portal-kde',
                         '/games/unknown /usr/lib/xdg-desktop-portal-kde']:
            self.assertEqual(safety.assess(GOOD | {'gpu_clients':[reported]})[0], 'unknown')
        with patch('safety.os.readlink', return_value=safety.PORTAL_EXECUTABLE), patch('safety.portal_identity', return_value=False):
            identity = safety.gpu_client_identity(424242, safety.PORTAL_EXECUTABLE)
        self.assertEqual(identity['source'], 'proc_exe')
        self.assertEqual(safety.assess(GOOD | {'gpu_clients':[identity['name']], 'gpu_pids':[424242], 'gpu_client_identities':[identity]})[0], 'unknown')

    def test_verified_portal_does_not_bypass_other_gates_or_pid_binding(self):
        identity = {'pid':424242, 'name':'xdg-desktop-portal-kde', 'source':'proc_installed_portal'}
        base = GOOD | {'gpu_clients':[identity['name']], 'gpu_pids':[424242], 'gpu_client_identities':[identity]}
        for change, expected in [({'utilization':[90,90]}, 'gpu_busy'), ({'free_mib':1000}, 'insufficient_vram'),
                                 ({'processes':['Resonite']}, 'game_active'), ({'processes':['vrserver']}, 'vr_active'),
                                 ({'complete':False}, 'unknown'), ({'age':16}, 'unknown'),
                                 ({'gpu_pids':[99]}, 'unknown'),
                                 ({'gpu_clients':[identity['name'], 'unknown-game'], 'gpu_pids':[424242,99]}, 'unknown')]:
            with self.subTest(change=change): self.assertEqual(safety.assess(base | change)[0], expected)

    def test_missing_untrusted_foreign_and_unstable_proc_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root=Path(directory); binary=root/'xdg-desktop-portal-kde'; binary.write_bytes(b'fixture')
            proc=root/'proc'; entry=proc/'424242'; entry.mkdir(parents=True)
            (entry/'exe').symlink_to(binary)
            statfile=entry/'stat'; good='424242 (portal) S 1 ' + '0 '*17 + '100 0'
            statfile.write_text(good)
            with patch('safety.PORTAL_EXECUTABLE', str(binary)), patch('safety.INSTALL_UID', os.getuid()):
                for invalid in [0, 1, True, '424242', 999999]:
                    self.assertFalse(safety.portal_identity(invalid, proc))
                binary.chmod(0o666)
                self.assertFalse(safety.portal_identity(424242, proc)); binary.chmod(0o600)
                for raw in ['broken', '424243 (portal) S 1 ' + '0 '*17 + '100 0', good.replace('100 0', '0 0'), 'x'*4097]:
                    statfile.write_text(raw); self.assertFalse(safety.portal_identity(424242, proc))
                statfile.write_text(good)
                with patch('safety.os.getuid', return_value=os.getuid()+1):
                    self.assertFalse(safety.portal_identity(424242, proc))
                with patch('safety.os.readlink', side_effect=[str(binary), str(binary)+' (deleted)']):
                    self.assertFalse(safety.portal_identity(424242, proc))
                with patch('safety.os.readlink', side_effect=PermissionError):
                    self.assertFalse(safety.portal_identity(424242, proc))
                alternate=root/'alternate'; alternate.write_bytes(b'fake')
                (entry/'exe').unlink(); (entry/'exe').symlink_to(alternate)
                with patch('safety.os.readlink', return_value=str(binary)):
                    self.assertFalse(safety.portal_identity(424242, proc))
                binary.unlink(); binary.symlink_to(alternate)
                self.assertFalse(safety.portal_identity(424242, proc))

if __name__ == '__main__': unittest.main()
