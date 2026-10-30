import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import weather_controller

class SafetyRevisionTests(unittest.TestCase):
    def test_safety_only_change_requires_a_new_loaded_revision(self):
        original=Path.read_bytes
        def modified(path):
            data=original(path)
            return data+b'\n# simulated safety patch\n' if path.name=='safety.py' else data
        source=Path(weather_controller.__file__)
        spec=importlib.util.spec_from_file_location('revision_fixture',source)
        module=importlib.util.module_from_spec(spec)
        with patch.object(Path,'read_bytes',modified):
            spec.loader.exec_module(module)
        self.assertNotEqual(module.SOURCE_REVISION,weather_controller.SOURCE_REVISION)
        # Removing the disk-change simulation must not change the loaded value.
        loaded=module.SOURCE_REVISION
        self.assertEqual(module.Controller.status.__globals__['SOURCE_REVISION'],loaded)

    def test_owner_rollout_imports_same_loaded_revision(self):
        source=Path('scripts/rollout-owner.py')
        spec=importlib.util.spec_from_file_location('rollout_revision_fixture',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.SOURCE_REVISION,weather_controller.SOURCE_REVISION)
