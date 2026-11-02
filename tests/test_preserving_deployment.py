"""Offline transaction fixtures: never contact a user manager or owner state."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]

class PreservingDeploymentTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location('preserving', ROOT/'scripts/deploy-preserving-owner.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_running_controller_rejected_before_backup_or_mutation(self):
        m = self.load()
        io = Mock()
        io.require_stopped.side_effect = RuntimeError('active controller')
        with self.assertRaisesRegex(RuntimeError, 'active controller'):
            m.deploy(io)
        self.assertEqual([c[0] for c in io.method_calls], ['require_stopped'])

    def test_transaction_never_starts_or_changes_settings(self):
        m = self.load()
        io = Mock()
        m.deploy(io)
        self.assertEqual([c[0] for c in io.method_calls],
                         ['require_stopped','capture','backup','require_stopped','install','verify'])
        io = Mock()
        io.verify.side_effect = RuntimeError('readback failed')
        with self.assertRaisesRegex(RuntimeError, 'readback failed'):
            m.deploy(io)
        self.assertEqual([c[0] for c in io.method_calls][-2:], ['require_stopped','rollback'])

    def test_persistent_rewrite_preserves_flags_environment_and_enablement(self):
        m = self.load()
        old = Path('/owner/old source')
        new = Path('/owner/new $ % source')
        raw = ('[Unit]\nPartOf=graphical-session.target\n[Service]\n'
               'WorkingDirectory=/owner/old source\n'
               'ExecStart="/usr/bin/python3" "/owner/old source/weather_controller.py" "--preview-checkpoint" "a$$b%%.safetensors" "--managed-comfy"\n'
               'Environment="LANG=en_US.UTF-8"\n[Install]\nWantedBy=graphical-session.target\n').encode()
        result = m.retarget_unit(raw, old, new)
        self.assertIn(b'WorkingDirectory=/owner/new $ %% source\n', result)
        self.assertIn(b'"/owner/new $$ %% source/weather_controller.py"', result)
        self.assertEqual(result.split(b' "--preview-checkpoint"',1)[1],raw.split(b' "--preview-checkpoint"',1)[1])
        for bad in (raw+b'ExecStart=/bad\n', raw.replace(b'WorkingDirectory=',b'#WorkingDirectory='), raw.replace(b'"/owner/old source/weather_controller.py"',b'/other.py')):
            with self.assertRaises(RuntimeError): m.retarget_unit(bad, old, new)

    def test_real_stopped_transaction_and_exact_rollback(self):
        import tempfile, os, json, zipfile
        from unittest.mock import patch
        m = self.load()
        with tempfile.TemporaryDirectory(prefix='.deploy-fixture-', dir=Path.home()) as tmp:
            root = Path(tmp)
            obj = m.OwnerDeployment.__new__(m.OwnerDeployment)
            obj.helper = m.load('install-controller-service.py')
            obj.state = root/'state'; obj.state.mkdir(mode=0o700)
            settings = b'{"automation_enabled":true,"custom":"retain formatting"}\n'
            (obj.state/'settings.json').write_bytes(settings)
            (obj.state/'settings.json').chmod(0o600)
            obj.old_root = root/'old'; obj.old_root.mkdir()
            obj.destination = root/'units/weather-horde-kde.service'; obj.destination.parent.mkdir()
            raw = ('[Service]\nWorkingDirectory='+str(obj.old_root)+'\nExecStart="/usr/bin/python3" "'+str(obj.old_root)+'/weather_controller.py" "--managed-comfy"\nEnvironment="LANG=C"\n[Install]\nWantedBy=graphical-session.target\n').encode()
            obj.destination.write_bytes(raw)
            obj.package = root/'packages/widget'; obj.package.mkdir(parents=True)
            (obj.package/'old-only').write_text('old')
            archive = root/'package.zip'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('new-only','new')
            obj.installer = Mock(); obj.installer.verify_release.return_value = archive
            props = {'LoadState':'loaded','Transient':'no','FragmentPath':str(obj.destination),'DropInPaths':'','ActiveState':'inactive','MainPID':'0'}
            obj.helper.require_stopped = Mock(return_value=props)
            obj.helper.props = Mock(return_value=props)
            calls = []
            def ctl(*args, **kwargs):
                calls.append(args)
                return Mock(stdout='disabled\n',returncode=1 if args[0]=='is-enabled' else 0)
            obj.helper.ctl = ctl
            obj.helper.run = Mock()
            with patch.object(m, 'ROOT',root), patch.object(m, 'load', return_value=obj.helper):
                m.deploy(obj)
                self.assertEqual((obj.state/'settings.json').read_bytes(), settings)
                self.assertFalse((obj.package/'old-only').exists())
                self.assertEqual((obj.package/'new-only').read_text(),'new')
                obj.rollback(obj.saved)
                self.assertEqual(obj.destination.read_bytes(),raw)
                self.assertEqual((obj.package/'old-only').read_text(),'old')
                self.assertFalse((obj.package/'new-only').exists())
                # Fail after package replacement and after unit replacement.
                for phase in ('unit-write','reload','verify'):
                    with self.subTest(phase=phase):
                        original_atomic = obj.helper.atomic
                        failed = False
                        def atomic(path, data):
                            nonlocal failed
                            if phase == 'unit-write' and path == obj.destination and data != raw and not failed:
                                failed = True
                                raise RuntimeError('injected unit-write')
                            return original_atomic(path, data)
                        def failure_ctl(*args, **kwargs):
                            nonlocal failed
                            if phase == 'reload' and args[0] == 'daemon-reload' and not failed:
                                failed = True
                                raise RuntimeError('injected reload')
                            return ctl(*args, **kwargs)
                        original_verify = obj.verify
                        def verify(saved):
                            if phase == 'verify': raise RuntimeError('injected verify')
                            return original_verify(saved)
                        with patch.object(obj.helper,'atomic',atomic), patch.object(obj.helper,'ctl',failure_ctl), patch.object(obj,'verify',verify):
                            with self.assertRaisesRegex(RuntimeError,'injected'):
                                m.deploy(obj)
                        self.assertEqual(obj.destination.read_bytes(),raw)
                        self.assertEqual(obj.tree(obj.package),{'old-only':b'old'})
                        self.assertEqual((obj.state/'settings.json').read_bytes(),settings)
            self.assertTrue(all(call[0] in ('is-enabled','daemon-reload') for call in calls))
            self.assertEqual((obj.state/'settings.json').read_bytes(), settings)

    def test_main_holds_exclusive_lock_and_never_loads_token_client(self):
        from unittest.mock import patch
        from contextlib import contextmanager
        m = self.load()
        events = []
        @contextmanager
        def lock(state, *, exclusive):
            self.assertTrue(exclusive)
            events.append('lock')
            yield
            events.append('unlock')
        io = Mock()
        with patch.object(m, 'OwnerDeployment',return_value=io), patch.object(m,'deploy',side_effect=lambda _: events.append('deploy')), patch('receipt_lock.state_lock',lock), patch('sys.argv',['helper','--deploy','--old-root','/owner/old']):
            m.main()
        self.assertEqual(events,['lock','deploy','unlock'])
        helper = Mock(); helper.props.return_value={'Transient':'no','ActiveState':'inactive'}
        with patch.object(m,'load',return_value=helper) as loader, patch('portable_paths.require_owner'), patch('sys.argv',['helper']):
            m.main()
        self.assertEqual(loader.call_args.args,('install-controller-service.py',))
        helper.OwnerIO.assert_not_called()

    def test_dangling_package_symlink_refused_without_writes(self):
        import tempfile
        m = self.load()
        obj = m.OwnerDeployment.__new__(m.OwnerDeployment)
        obj.helper = m.load('install-controller-service.py')
        with tempfile.TemporaryDirectory(prefix='.deploy-link-',dir=Path.home()) as tmp:
            obj.package = Path(tmp)/'package'
            obj.package.symlink_to(Path(tmp)/'missing')
            before = set(Path(tmp).iterdir())
            with self.assertRaises(RuntimeError): obj.replace_package(None)
            self.assertEqual(set(Path(tmp).iterdir()), before)
            self.assertTrue(obj.package.is_symlink())

    def test_enablement_checked_without_normalizing_disabled_to_enabled(self):
        import tempfile
        m = self.load()
        obj = m.OwnerDeployment.__new__(m.OwnerDeployment)
        obj.helper = m.load('install-controller-service.py')
        with tempfile.TemporaryDirectory(prefix='.deploy-enabled-',dir=Path.home()) as tmp:
            obj.destination = Path(tmp)/obj.helper.UNIT
            obj.destination.write_text('[Service]\n')
            obj.helper.ctl = Mock(return_value=Mock(stdout='disabled\n',returncode=1))
            self.assertEqual(obj.enablement(),'disabled')
            link = Path(tmp)/'graphical-session.target.wants'/obj.helper.UNIT
            link.parent.mkdir(); link.symlink_to(obj.destination)
            obj.helper.ctl.return_value = Mock(stdout='enabled\n',returncode=0)
            self.assertEqual(obj.enablement(),'enabled')
            link.unlink(); link.symlink_to(Path(tmp)/'wrong')
            with self.assertRaises(RuntimeError): obj.enablement()
            obj.helper.ctl.return_value = Mock(stdout='masked\n',returncode=1)
            with self.assertRaises(RuntimeError): obj.enablement()
            self.assertTrue(all(c.args[0]=='is-enabled' for c in obj.helper.ctl.call_args_list))

    def test_concurrent_package_edit_is_not_overwritten(self):
        import tempfile
        m = self.load()
        with tempfile.TemporaryDirectory(prefix='.deploy-race-', dir=Path.home()) as tmp:
            root = Path(tmp)
            obj = m.OwnerDeployment.__new__(m.OwnerDeployment)
            obj.helper = m.load('install-controller-service.py')
            obj.package = root/'package'; obj.package.mkdir()
            (obj.package/'concurrent').write_bytes(b'keep this')
            obj.destination = root/'unit'; obj.destination.write_bytes(b'old unit')
            obj.backup_dir = root/'backup'; obj.backup_dir.mkdir()
            obj.require_stopped = Mock()
            obj.check_unchanged = Mock()
            import zipfile
            obj.archive = root/'package.zip'
            with zipfile.ZipFile(obj.archive, 'w') as archive:
                archive.writestr('new-only', 'new')
            (obj.backup_dir/'package').mkdir()
            (obj.backup_dir/'package/old-only').write_bytes(b'old')
            obj.helper.ctl = Mock()
            obj.expected_package = {'new-only':b'new'}
            saved = {'unit':b'old unit', 'new_unit':b'new unit', 'package':{'old-only':b'old'}}
            for action in (obj.install, obj.rollback):
                with self.subTest(action=action.__name__):
                    with self.assertRaisesRegex(RuntimeError, 'Package changed concurrently'):
                        action(saved)
                    self.assertEqual(obj.tree(obj.package), {'concurrent':b'keep this'})
                    self.assertEqual(obj.destination.read_bytes(), b'old unit')

    def test_unknown_persistent_load_state_refused(self):
        m = self.load()
        obj = m.OwnerDeployment.__new__(m.OwnerDeployment)
        obj.destination = Path('/owner/units/weather-horde-kde.service')
        obj.helper = Mock()
        for state in ('error', 'not-found', None):
            obj.helper.require_stopped.return_value = {'Transient':'no', 'FragmentPath':str(obj.destination), 'LoadState':state}
            with self.subTest(state=state), self.assertRaises(RuntimeError):
                obj.require_stopped()

    def test_diagnostic_only_allowlisted_fields(self):
        m = self.load()
        result = m.diagnostic({'state':'quarantined','token':'SECRET'})
        self.assertNotIn('SECRET', str(result))
