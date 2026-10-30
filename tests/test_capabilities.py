import tempfile, unittest
from weather_controller import Controller

class CapabilitiesTests(unittest.TestCase):
    def test_loaded_revision_and_explicit_capabilities(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d)
            s=c.dispatch('GET','/v1/status',{})
            self.assertEqual(s.get('api_version'), 1)
            self.assertEqual(s.get('service_version'), '0.1.10')
            self.assertEqual(len(s.get('source_revision','')),64)
            self.assertTrue(s['capabilities']['testing_override'])
            self.assertFalse(s['capabilities']['manual_apply'])
            self.assertFalse(s['capabilities']['scheduled_images'])
            self.assertIn('not configured',s['apply_blocker'])
