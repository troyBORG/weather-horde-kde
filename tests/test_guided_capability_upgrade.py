"""Offline verification seam: no owner API, settings, or service operations."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('guided_caps', ROOT/'scripts/guided-update-owner.py')
guided = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guided)


class CapabilityUpgradeTests(unittest.TestCase):
    def verify(self, additions=None, changes=None, force=False):
        io = guided.OwnerUpdate(SimpleNamespace(helper=None, state=None, enablement=lambda: 'enabled'))
        io.entry_enabled = 'enabled'
        io.before = {'capabilities': {'manual_apply': True, 'scheduled_images': True,
                     'model_selection': True}, 'render_enabled': True, 'apply_enabled': True,
                     'comfy_service': {'managed': True}}
        status = {**io.before, 'capabilities': {**io.before['capabilities'], **(additions or {})},
                  'source_revision': 'fixture', 'testing_override': {'active': False},
                  'force_override': {'active': force}, 'displays': [{}]}
        status.update(changes or {})
        io.api = lambda: status
        io.expected_revision = lambda: 'fixture'
        io.preferences = lambda saved, actual: None
        io.verify({})

    def test_reviewed_additive_capabilities_are_not_runtime_flag_changes(self):
        self.verify({'forced_automation': True, 'connected_panorama': True})

    def test_unknown_addition_still_fails(self):
        with self.assertRaises(RuntimeError): self.verify({'unreviewed': True})

    def test_existing_capability_change_still_fails(self):
        with self.assertRaises(RuntimeError): self.verify({'manual_apply': False})

    def test_reviewed_capability_false_still_fails(self):
        with self.assertRaises(RuntimeError): self.verify({'forced_automation': False})

    def test_force_addition_requires_inactive_consent(self):
        with self.assertRaises(RuntimeError): self.verify({'forced_automation': True}, force=True)

    def test_runtime_flags_still_fail(self):
        for key in ('render_enabled', 'apply_enabled'):
            with self.subTest(key=key), self.assertRaises(RuntimeError): self.verify(changes={key: False})

    def test_removed_capability_still_fails(self):
        with self.assertRaises(RuntimeError): self.verify(changes={'capabilities': {}})
