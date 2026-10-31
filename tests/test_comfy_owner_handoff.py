import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

class ComfyOwnerHandoffTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        (self.root/'.venv/bin').mkdir(parents=True)
        for name in ('main.py', '.venv/bin/python', 'extra_model_paths.yaml'):
            (self.root/name).write_text('# fixture')
        (self.root/'.venv/bin/python').chmod(0o700)
        self.enterContext(patch.dict('os.environ', WEATHER_HORDE_COMFY_ROOT=directory,
                                    WEATHER_HORDE_OWNER='fixture-owner'))

    def test_launch_requires_owner_and_unoccupied_port(self):
        path=Path(__file__).resolve().parents[1]/'scripts/comfy-owner.py'
        self.assertTrue(path.exists(), 'Owner helper missing')
        spec=importlib.util.spec_from_file_location('comfy_owner',path)
        m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        for uid, rows in [(1001,[]),(1000,[(1001,'123')]),(1000,[(1000,'123')])]:
            with self.subTest(uid=uid,rows=rows), self.assertRaises(RuntimeError):
                m.require_launch(uid,1000,rows)
        m.require_launch(1000,1000,[])

    def test_idle_cross_owner_and_busy_queues_never_start(self):
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        import io
        path=Path(__file__).resolve().parents[1]/'scripts/comfy-owner.py'
        spec=importlib.util.spec_from_file_location('comfy_owner',path)
        m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        for busy in (False,True):
            opener=MagicMock()
            opener.open.return_value.__enter__.return_value=io.StringIO(
                '{"queue_running":'+('[[]]' if busy else '[]')+',"queue_pending":[]}')
            with patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000)), patch.object(m.os,'getuid',return_value=1000), patch.object(m,'listeners',return_value=[(1001,'123')]), patch.object(m,'build_opener',return_value=opener), patch.object(m.os,'execve') as execute, patch.object(m.sys,'argv',['helper','--start']):
                with self.assertRaisesRegex(RuntimeError,'busy' if busy else 'occupied'): m.main()
                execute.assert_not_called()

    def test_default_check_does_not_start(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        path=Path(__file__).resolve().parents[1]/'scripts/comfy-owner.py'
        spec=importlib.util.spec_from_file_location('comfy_owner',path)
        m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        with patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000)), patch.object(m.os,'getuid',return_value=1000), patch.object(m,'listeners',return_value=[]), patch.object(m.socket,'socket'), patch.object(m.os,'execve') as execute, patch.object(m.sys,'argv',['helper']):
            m.main(); execute.assert_not_called()
