"""Exact installed native desktop identities; no real GPU or owner access."""
import unittest
from unittest.mock import patch
from safety import assess, gpu_client_identity

NATIVE = ('Telegram', 'soffice.bin', 'wordcraft', 'kate')
GOOD = dict(processes=['kwin_wayland'], complete=True, age=0,
            sample_gap=10, utilization=[0, 0], free_mib=20000)


class OrdinaryDesktopTests(unittest.TestCase):
    def test_installed_native_clients_are_recognized(self):
        for name in NATIVE:
            reported = f'/usr/bin/{name} --type=gpu-process'
            for executable in (None, f'/usr/bin/{name}', f'/usr/bin/{name} (deleted)'):
                with self.subTest(name=name, executable=executable), patch(
                        'safety.os.readlink', return_value=executable,
                        side_effect=PermissionError if executable is None else None):
                    identity = gpu_client_identity(424242, reported)
                    self.assertEqual(identity['name'], name)
                    self.assertEqual(identity['source'], 'nvidia_argv' if executable is None else 'proc_exe')
                    self.assertEqual(assess(GOOD | {'gpu_clients': [identity['name']]}),
                                     ('safe', 'checks_passed'))

    def test_arguments_substrings_and_kernel_mismatch_are_rejected(self):
        for name in NATIVE:
            for reported in (f'/opt/unknown /usr/bin/{name}',
                             f'/opt/unknown --output=/usr/bin/{name}',
                             f'/opt/{name}-helper', f'/opt/not{name}',
                             f'"/usr/bin/{name} (deleted)" --daemon'):
                with self.subTest(reported=reported):
                    self.assertEqual(assess(GOOD | {'gpu_clients': [reported]}),
                                     ('unknown', 'unrecognized_gpu_client'))
            with self.subTest(name=name), patch('safety.os.readlink', return_value='/opt/unknown'):
                identity = gpu_client_identity(424242, f'/usr/bin/{name}')
                self.assertEqual(assess(GOOD | {'gpu_clients': [identity['name']]})[0], 'unknown')

    def test_native_clients_retain_all_other_gates(self):
        for name in NATIVE:
            base = GOOD | {'gpu_clients': [name]}
            for change, expected in (({'utilization': [90, 90]}, 'gpu_busy'),
                                     ({'free_mib': 1000}, 'insufficient_vram'),
                                     ({'processes': ['Resonite']}, 'game_active'),
                                     ({'processes': ['vrserver']}, 'vr_active'),
                                     ({'complete': False}, 'unknown'),
                                     ({'age': 20}, 'unknown'),
                                     ({'gpu_clients': [name, 'native-unknown'],
                                       'gpu_pids': [101, 202], 'owned_pid': 303}, 'unknown')):
                with self.subTest(name=name, change=change):
                    self.assertEqual(assess(base | change)[0], expected)

    def test_generic_runtimes_remain_unrecognized_even_with_app_arguments(self):
        for reported in ('electron', 'electron43', 'python', 'python3', 'java',
                         '/usr/lib/electron43/electron /usr/lib/element/app.asar',
                         '/usr/lib/electron43/electron /usr/lib/obsidian/app.asar',
                         '/usr/bin/electron43 --app-name=Telegram',
                         '/usr/bin/python3 /usr/bin/wordcraft',
                         '/usr/bin/java /usr/bin/kate'):
            with self.subTest(reported=reported):
                self.assertEqual(assess(GOOD | {'gpu_clients': [reported]}),
                                 ('unknown', 'unrecognized_gpu_client'))
