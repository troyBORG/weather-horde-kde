import importlib.util
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

NIGHT_STAMP = datetime(2026, 10, 29, 6, 30, tzinfo=timezone.utc).timestamp()


class SceneTests(unittest.TestCase):
    @patch('scene.time.time', return_value=NIGHT_STAMP)
    def test_zip_confirmation_and_weather_prompt_without_visible_moon_claims(self, _clock):
        self.assertIsNotNone(importlib.util.find_spec('scene'), 'scene preview missing')
        from scene import resolve_zip, weather_preview
        called=[]
        def fetch(url):
            called.append(url)
            if 'zippopotam' in url:
                return {'places':[{'place name':'De Witt','state':'Iowa','latitude':'41.8267','longitude':'-90.5237'}]}
            return {'timezone':'America/Chicago', 'current':{'time':NIGHT_STAMP,
                    'temperature_2m':28, 'weather_code':3, 'is_day':0}}
        locations = resolve_zip('52742', fetch)
        self.assertEqual(locations[0]['timezone'], 'America/Chicago')
        self.assertEqual(locations[0]['town'], 'De Witt')
        preview = weather_preview(locations[0], fetch)
        self.assertIn('overcast', preview['positive'].lower())
        self.assertIn('night', preview['positive'])
        self.assertIn('visible moon', preview['negative'])
        self.assertNotIn('moon', preview['positive'])
        self.assertNotIn('snow', preview['positive'])
        with self.assertRaises(ValueError): resolve_zip('../52742', fetch)
        with self.assertRaises(ValueError): weather_preview(locations[0], lambda _: {'timezone':'America/Chicago','current':{'time':0,'temperature_2m':28,'weather_code':3,'is_day':0}})

if __name__ == '__main__': unittest.main()
