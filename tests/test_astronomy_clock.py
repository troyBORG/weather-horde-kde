import unittest
from unittest.mock import patch
from scene import weather_preview
from test_night_realism import LOCATION

class AstronomyClock(unittest.TestCase):
    def test_position_uses_render_time_not_old_weather_time(self):
        now=1793255400
        data={'current':{'time':now-3600,'temperature_2m':40,'weather_code':0,'is_day':0,'cloud_cover':0}}
        with patch('scene.time.time',return_value=now):
            p=weather_preview(LOCATION,lambda _:data)
        self.assertEqual(p['weather_evidence']['lunar']['calculated_at'],now)
        self.assertEqual(p['observed_at'],now-3600)
