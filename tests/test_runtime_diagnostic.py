import importlib.util, unittest
from unittest.mock import patch

class DiagnosticTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('diagnostic','scripts/runtime-repair-owner.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

    def test_sanitized_status_excludes_previews_location_and_paths(self):
        m=self.load()
        result=m.sanitized_status({'service_version':'0.1.7','state':'deferred','last_error':'Command [private argv] failed',
            'image_preview':{'secret':'private'},'location':{'secret':'private'},
            'wallpaper_action':{'state':'failed','target':'DP-2','reason':'Permission denied /home/example/private/file'},
            'guard':{'decision':'unknown','free_mib':24000,'reason':'unrecognized_gpu_client'}})
        text=str(result)
        self.assertNotIn('private',text);self.assertNotIn('/home/',text)
        self.assertEqual(result['wallpaper_action']['target'],'DP-2')
        self.assertEqual(result['guard']['reason'],'unrecognized_gpu_client')

    def test_wrong_owner_stops_before_private_access(self):
        m=self.load()
        with patch.object(m.pwd,'getpwuid') as user:
            user.return_value.pw_name='jorden'
            with self.assertRaisesRegex(RuntimeError,'troyborg'): m.require_owner()
