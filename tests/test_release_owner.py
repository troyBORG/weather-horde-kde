import unittest, importlib.util
from pathlib import Path
class OwnerRelease(unittest.TestCase):
 def test_left_only_preview_never_applies_or_enables(self):
  path=Path('scripts/release-owner.py');self.assertTrue(path.exists(),'owner preview handoff missing')
  spec=importlib.util.spec_from_file_location('release_owner',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  displays=[dict(id='DP-2',x=0,width=1080,height=1920),dict(id='DP-3',x=1080,width=3440,height=1440)]
  self.assertEqual(m.left_target(displays)['id'],'DP-2')
  with self.assertRaises(RuntimeError):m.left_target([dict(id='DP-3',x=0,width=3440,height=1440)])
  source=path.read_text();self.assertNotIn("'/v1/apply'",source);self.assertNotIn("'/v1/restore'",source)
  with self.assertRaises(RuntimeError):m.check_status({'automation_enabled':True})
  with self.assertRaises(RuntimeError):m.check_status({'automation_enabled':False,'testing_override':{'active':True}})
  m.check_status({'automation_enabled':False,'testing_override':{'active':False},'prompt_version':'night-lunar-2','service_version':'0.1.10','source_revision':m.SOURCE_REVISION})
