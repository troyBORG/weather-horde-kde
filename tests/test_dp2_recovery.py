import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

PATH=Path(__file__).resolve().parents[1]/'scripts/recover-dp2-owner.py'

class RecoveryTests(unittest.TestCase):
    def load(self):
        self.assertTrue(PATH.exists(), 'owner recovery wrapper is missing')
        spec=importlib.util.spec_from_file_location('recovery',PATH)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        return m

    def test_success_relaunches_original_capabilities_and_accepts_only_dp2(self):
        m=self.load()
        io=Mock()
        io.identity.return_value={'pid':42,'argv':['/usr/bin/python3','/repo/weather_controller.py','--preview-checkpoint','model','--managed-comfy','--manual-wallpapers','--comfy-idle-seconds','456'],'env':{}}
        io.status.return_value={'state':'idle','automation_enabled':False}
        m.recover(io)
        self.assertEqual(io.stop.call_count,1)
        io.accept.assert_called_once_with()
        io.launch.assert_called_once_with(io.identity.return_value)
        io.verify.assert_called_once_with(io.identity.return_value)
        self.assertLess([x[0] for x in io.mock_calls].index('backup'),[x[0] for x in io.mock_calls].index('stop'))

    def test_busy_refuses_before_pause_or_stop(self):
        m=self.load()
        for state in ('queued','rendering','checking_weather','failed_unreconciled','unknown'):
            with self.subTest(state=state), self.assertRaises(RuntimeError):
                m.require_idle({'state':state},False)
        m.require_idle({'state':'idle'},False)
        with self.assertRaises(RuntimeError): m.require_idle({'state':'idle'},True)

    def test_identity_race_never_stops(self):
        m=self.load();io=Mock();io.identity.side_effect=[{'pid':42},{'pid':43}];io.status.return_value={'automation_enabled':False}
        with self.assertRaises(RuntimeError): m.recover(io)
        io.stop.assert_not_called();io.accept.assert_not_called();io.launch.assert_not_called()

    def test_helper_failure_relaunches_and_preserves_error(self):
        m=self.load();io=Mock();io.identity.return_value={'pid':42};io.status.return_value={'automation_enabled':False}
        io.accept.side_effect=ValueError('receipt changed')
        with self.assertRaisesRegex(ValueError,'receipt changed'): m.recover(io)
        io.launch.assert_called_once_with({'pid':42});io.verify.assert_not_called()

    def test_restart_command_preserves_exact_flags_and_environment(self):
        m=self.load()
        argv=['/usr/bin/python3',str(m.ROOT/'weather_controller.py'),'--preview-checkpoint','model name','--managed-comfy','--manual-wallpapers','--comfy-idle-seconds','456']
        original={'argv':argv,'env':{'WAYLAND_DISPLAY':'wayland-0'}}
        command=m.launch_command(original)
        self.assertEqual(command[-len(argv)-1:],argv+['--automation-off'])
        self.assertIn('--setenv=WAYLAND_DISPLAY=wayland-0',command)
        self.assertIn('--unit=weather-horde-kde',command)
        self.assertNotIn('restart',command)
        self.assertNotIn('--testing-override',command)
        self.assertEqual(m.validate_argv(argv,Path('/owner/state')),argv)
        for bad in (argv+['--unknown'],argv+['--port','9999'],argv+['--state-dir','/other']):
            with self.assertRaises(RuntimeError): m.validate_argv(bad,Path('/owner/state'))

    def test_only_controller_stop_with_identity_recheck(self):
        from unittest.mock import patch
        m=self.load();io=object.__new__(m.OwnerIO);io.identity=Mock(return_value={'pid':43})
        with patch.object(m.subprocess,'run') as run:
            with self.assertRaises(RuntimeError): io.stop({'pid':42})
            run.assert_not_called()

    def test_race_busy_after_backup_never_stops(self):
        m=self.load();io=Mock();io.identity.return_value={'pid':42};io.status.return_value={'automation_enabled':False}
        io.idle.side_effect=[None,None,RuntimeError('busy')]
        with self.assertRaisesRegex(RuntimeError,'busy'): m.recover(io)
        io.stop.assert_not_called()

    def test_helper_and_restart_failure_keep_primary_error(self):
        m=self.load();io=Mock();io.identity.return_value={'pid':42};io.status.return_value={'automation_enabled':False}
        io.accept.side_effect=ValueError('receipt changed');io.launch.side_effect=RuntimeError('launch failed')
        with self.assertRaisesRegex(ValueError,'receipt changed') as caught: m.recover(io)
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)

    def test_automation_must_still_be_off_immediately_before_stop(self):
        m=self.load();io=Mock();io.identity.return_value={'pid':42};io.status.return_value={'automation_enabled':False}
        io.status.side_effect=[{'state':'idle'}, {'automation_enabled':False}, {'automation_enabled':True}]
        with self.assertRaises(RuntimeError): m.recover(io)
        io.stop.assert_not_called()

    def test_verify_rejects_changed_unselected_receipt(self):
        import json
        from unittest.mock import patch
        m=self.load();io=object.__new__(m.OwnerIO);io.state=Path('/state');io.revision='r'
        io.status=Mock(return_value={'source_revision':'r'});io.verify_status=Mock()
        io.before={'DP-3':{'state':'saved'}}
        changed={'DP-2':{'state':'accepted_current','before':{},'after':{}},'DP-3':{'state':'changed'}}
        with patch.object(m,'private_read',return_value=json.dumps(changed).encode()):
            with self.assertRaisesRegex(RuntimeError,'Unselected'): io.verify({})

    def test_launch_disables_systemd_argument_expansion(self):
        m=self.load()
        self.assertIn('--expand-environment=no',m.launch_command({'argv':['python3','controller','--preview-checkpoint','$MODEL'],'env':{}}))

    def test_concrete_stop_and_helper_have_no_unselected_actions(self):
        from unittest.mock import patch
        m=self.load();io=object.__new__(m.OwnerIO);original={'pid':42}
        io.identity=Mock(return_value=original);io.status=Mock(return_value={'automation_enabled':False});io.idle=Mock()
        with patch.object(m.subprocess,'run') as run:
            io.stop(original);io.accept()
            self.assertEqual([c.args[0] for c in run.call_args_list],[
                ['systemctl','--user','stop','weather-horde-kde.service'],
                ['/usr/bin/python3',str(m.ROOT/'scripts/reconcile-dp2-owner.py'),'--accept-current']])

    def test_wrong_owner_before_any_state_or_bus_access(self):
        from unittest.mock import patch
        m=self.load()
        with patch.dict('os.environ', {'WEATHER_HORDE_OWNER':'fixture-owner'}), patch.object(m.pwd,'getpwnam',return_value=Mock(pw_uid=-1)), patch.object(m,'private_read') as read, patch.object(m.subprocess,'run') as run:
            with self.assertRaises(RuntimeError): m.OwnerIO()
            read.assert_not_called();run.assert_not_called()

if __name__=='__main__': unittest.main()
