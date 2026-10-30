"""Sanitized NVIDIA argv regression; never run GPU work or touch a desktop."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from safety import assess, collect

DISCORD = ('/home/example/.config/discord/app-1.0.166/Discord '
           '--type=gpu-process --ozone-platform=wayland '
           '--render-node-override=/dev/dri/renderD128 --private-token=DO_NOT_REPORT')
GOOD = dict(processes=['kwin_wayland', 'Discord'], complete=True, age=0,
            sample_gap=10, utilization=[0, 0], free_mib=20000)

class GPUClientParsingTests(unittest.TestCase):
    def test_full_argv_discord_is_not_last_argument_basename(self):
        self.assertEqual(assess(GOOD | {'gpu_clients':[DISCORD]}), ('safe','checks_passed'))

    def test_arguments_cannot_impersonate_allowed_executable(self):
        for name in ['/opt/unknown --output=/tmp/Discord', '/opt/Discord-helper',
                     '/opt/notDiscord', '/games/native-unknown',
                     '/opt/Discord.exe --type=gpu-process',
                     '/opt/unknown "/tmp/Discord"', '"/opt/Discord',
                     '/opt/unknown\x00/Discord']:
            with self.subTest(name=name):
                self.assertNotEqual(assess(GOOD | {'gpu_clients':[name]})[0], 'safe')

    def test_quoted_spaces_and_ambiguous_unquoted_spaces(self):
        self.assertEqual(assess(GOOD | {'gpu_clients':['"/opt/space dir/Discord" --type=gpu-process']})[0], 'safe')
        self.assertEqual(assess(GOOD | {'gpu_clients':['/opt/space dir/Discord --type=gpu-process']})[0], 'unknown')

    def test_discord_does_not_relax_other_gates(self):
        base=GOOD | {'gpu_clients':[DISCORD]}
        for change, expected in [({'processes':['Resonite']}, 'game_active'),
                                 ({'processes':['vrserver']}, 'vr_active'),
                                 ({'free_mib':1000}, 'insufficient_vram'),
                                 ({'utilization':[90,90]}, 'gpu_busy'),
                                 ({'complete':False}, 'unknown')]:
            with self.subTest(change=change): self.assertEqual(assess(base | change)[0], expected)

    def test_kernel_deleted_suffix_is_only_normalized_for_proc_exe(self):
        for executable, expected in [('/usr/bin/plasmashell (deleted)', 'safe'),
                                     ('/usr/bin/kwin_wayland (deleted)', 'safe'),
                                     ('/games/native-unknown (deleted)', 'unknown'),
                                     ('/opt/plasmashell-helper (deleted)', 'unknown'),
                                     ('/opt/plasmashell (deleted) (deleted)', 'unknown'),
                                     ('/opt/plasmashell (deleted)-evil', 'unknown')]:
            with self.subTest(executable=executable), patch('safety.os.readlink', return_value=executable):
                result = self.collect_fixture()
                self.assertEqual(result['decision'], expected)
                self.assertEqual(result['gpu_client_identities'][0]['source'], 'proc_exe')
        # An argv token containing the suffix is not kernel identity evidence.
        with patch('safety.os.readlink', side_effect=PermissionError):
            from safety import gpu_client_identity
            identity = gpu_client_identity(424242, '"/usr/bin/plasmashell (deleted)" --daemon')
        self.assertEqual(identity['name'], 'unknown')
        self.assertEqual(identity['source'], 'nvidia_argv')

    def test_krunner_is_desktop_but_not_exempt_from_resource_gates(self):
        for executable in ['/usr/bin/krunner', '/usr/bin/krunner (deleted)']:
            with self.subTest(executable=executable), patch('safety.os.readlink', return_value=executable):
                result = self.collect_fixture()
                self.assertEqual(result['decision'], 'safe')
                self.assertEqual(result['gpu_client_identities'][0]['name'], 'krunner')
        base = GOOD | {'gpu_clients': ['/usr/bin/krunner --daemon']}
        for change, expected in [({}, 'safe'), ({'utilization': [90,90]}, 'gpu_busy'),
                                 ({'free_mib': 1000}, 'insufficient_vram'),
                                 ({'processes': ['Resonite']}, 'game_active'),
                                 ({'processes': ['vrserver']}, 'vr_active'),
                                 ({'complete': False}, 'unknown')]:
            with self.subTest(change=change):
                self.assertEqual(assess(base | change)[0], expected)
        for reported in ['/opt/unknown --output=/usr/bin/krunner', '/opt/krunner-helper --daemon',
                         '/games/native-unknown /usr/bin/krunner', '"/usr/bin/krunner (deleted)" --daemon']:
            with self.subTest(reported=reported):
                self.assertEqual(assess(GOOD | {'gpu_clients': [reported]})[0], 'unknown')

    def test_brave_full_argv_is_an_ordinary_desktop_client(self):
        reported = ('/opt/brave.com/brave-nightly/brave --type=gpu-process '
                    '--ozone-platform=wayland --render-node-override=/dev/dri/renderD128')
        self.assertEqual(assess(GOOD | {'gpu_clients': [reported]}), ('safe', 'checks_passed'))
        from safety import gpu_client_identity
        for executable in [None, '/opt/brave.com/brave-nightly/brave',
                           '/opt/brave.com/brave-nightly/brave (deleted)']:
            with self.subTest(executable=executable), patch(
                    'safety.os.readlink', return_value=executable,
                    side_effect=PermissionError if executable is None else None):
                identity = gpu_client_identity(424242, reported)
                self.assertEqual(identity['name'], 'brave')
                self.assertEqual(identity['source'], 'nvidia_argv' if executable is None else 'proc_exe')
                self.assertEqual(assess(GOOD | {'gpu_clients': [identity['name']]})[0], 'safe')

    def test_brave_name_cannot_be_spoofed_by_arguments_or_substrings(self):
        for reported in ['/opt/unknown --output=/tmp/brave', '/opt/unknown /tmp/brave',
                         '/opt/brave-helper --type=gpu-process', '/opt/notbrave',
                         '/opt/Brave', '/opt/brave.exe --type=gpu-process']:
            with self.subTest(reported=reported):
                self.assertEqual(assess(GOOD | {'gpu_clients': [reported]}),
                                 ('unknown', 'unrecognized_gpu_client'))
        from safety import gpu_client_identity
        with patch('safety.os.readlink', return_value='/opt/unknown'):
            identity = gpu_client_identity(424242, '/opt/brave --type=gpu-process')
        self.assertEqual(assess(GOOD | {'gpu_clients': [identity['name']]})[0], 'unknown')

    def test_brave_does_not_relax_resource_activity_or_owned_pid_gates(self):
        base = GOOD | {'gpu_clients': ['/opt/brave.com/brave-nightly/brave --type=gpu-process']}
        for change, expected in [({'utilization': [90, 90]}, 'gpu_busy'),
                                 ({'free_mib': 1000}, 'insufficient_vram'),
                                 ({'processes': ['Resonite']}, 'game_active'),
                                 ({'processes': ['vrserver']}, 'vr_active'),
                                 ({'complete': False}, 'unknown'),
                                 ({'gpu_clients': ['brave', '/opt/unknown'],
                                   'gpu_pids': [101, 202], 'owned_pid': 303}, 'unknown')]:
            with self.subTest(change=change):
                self.assertEqual(assess(base | change)[0], expected)

    def collect_fixture(self):
        xml=('<nvidia_smi_log><gpu><processes><process_info><pid>424242</pid>'
             '<process_name>'+DISCORD+'</process_name></process_info></processes></gpu></nvidia_smi_log>')
        def run(args, **kwargs):
            if args[:2]==['ps','-eo']: out='kwin_wayland\nDiscord'
            elif args[:2]==['ps','-C']: out=str(os.getuid())
            elif '-q' in args: out=xml
            else: out='0, 20000'
            return subprocess.CompletedProcess(args,0,stdout=out)
        with patch('safety.subprocess.run',side_effect=run), patch('safety.time.monotonic',return_value=100):
            return collect({'at':90, 'util':0})[0]

    def test_permission_fallback_and_nonsecret_diagnostics(self):
        with patch('safety.os.readlink',side_effect=PermissionError):
            result=self.collect_fixture()
        self.assertEqual(result['decision'],'safe')
        self.assertEqual(result['gpu_client_identities'],
                         [{'pid':424242,'name':'Discord','source':'nvidia_argv'}])
        self.assertNotIn('DO_NOT_REPORT',str(result))
        self.assertNotIn('/home/',str(result))

    def test_proc_exe_is_authoritative_including_spaces(self):
        for executable, expected in [('/opt/space dir/Discord','safe'),
                                      ('/games/unknown','unknown'),
                                      ('/opt/Discord-helper','unknown')]:
            with self.subTest(executable=executable), patch('safety.os.readlink',return_value=executable):
                result=self.collect_fixture()
                self.assertEqual(result['decision'],expected)
                self.assertEqual(result['gpu_client_identities'][0]['source'],'proc_exe')
                self.assertEqual(result['gpu_client_identities'][0]['name'],Path(executable).name)
