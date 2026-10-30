import tempfile, time, unittest
from unittest.mock import patch
from weather_controller import Controller
from test_preview_pipeline import Transport

class ScheduledImagesTests(unittest.TestCase):
    @patch('weather_controller.weather_preview',return_value={'positive':'fixture','negative':'fixture'})
    def test_schedule_generates_validated_preview_never_applies(self, _):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,checkpoint='fixture',transport=Transport(),render_guard=lambda:'safe',poll_seconds=0)
            c.displays=[{'id':'TEST','width':64,'height':128}]
            c.guard={'decision':'safe','observed_at':time.time()}
            c.settings['location']={'town':'fixture'}
            s=c.dispatch('PUT','/v1/settings',{'automation_kind':'image_preview','automation_enabled':True})
            self.assertEqual(s['automation_scope'],'image_preview_only')
            c.tick(c.next_eligible_at+1)
            c.render_thread.join(3)
            self.assertEqual(c.state,'image_preview_ready')
            self.assertFalse(c.image_preview['testing_override']['enabled'])
            self.assertFalse(c.status()['apply_enabled'])
            c.guard={'decision':'unknown','observed_at':time.time()}
            c.render_guard=lambda:'unknown'
            old=c.image_preview['id']
            c.tick(c.next_eligible_at+1)
            self.assertEqual(c.state,'deferred')
            self.assertEqual(c.image_preview['id'],old)

    def test_unconfigured_and_invalid_modes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d)
            for mode in ('image_preview','auto_apply',None):
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'automation_kind':mode})
