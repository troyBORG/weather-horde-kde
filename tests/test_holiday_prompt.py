from datetime import datetime
import unittest
from unittest.mock import patch
from scene import weather_preview, compose_for_target

LOCATION={'zip':'00000','town':'Fixture town','state':'Iowa','country_code':'US','subdivision_code':'IA','timezone':'America/Chicago','latitude':41.8,'longitude':-90.5}

class HolidayPromptTests(unittest.TestCase):
    def test_all_catalog_motifs_are_bounded_and_weather_neutral(self):
        import json
        from pathlib import Path
        from calendar_context import resolve_calendar,load_catalog
        from holiday_prompt import decorate
        root=Path(__file__).resolve().parents[1]
        themes=json.loads((root/'holiday_themes.json').read_text())['themes']
        wanted={e['theme_id'] for e in load_catalog()['events'] if e['theme_id']}
        self.assertEqual(set(themes),wanted)
        for theme in themes.values():
            for key in ('urban','natural'):
                self.assertTrue(0<len(theme[key])<=300)
                for forbidden in ('snow','fog','moon','skyline','fireworks','sunset'):
                    self.assertNotIn(forbidden,theme[key].lower())
        c=resolve_calendar(datetime.fromisoformat('2026-12-25T18:00:00+00:00'),LOCATION,{'holiday_themes':True})
        base={'positive':'Warm dry daytime.','negative':'original negatives','weather_evidence':{'scene_kind':'urban'}}
        result=decorate(base,c,{'seasonal_themes':True})
        self.assertIn('evergreen',result['positive'])
        self.assertNotIn('snow',result['positive'])
        self.assertIn('winter vegetation',result['positive'])
        subtle=decorate(base,c|{'theme_strength':'subtle'},{'seasonal_themes':False})
        self.assertNotEqual(subtle['positive'],result['positive'])
        off=decorate(base,c|{'selected_theme':None},{'seasonal_themes':False})
        self.assertEqual(off['positive'],base['positive'])


    def test_weather_scene_retains_lighting_and_negative_preset(self):
        stamp=datetime.fromisoformat('2026-10-31T18:00:00+00:00').timestamp()
        data={'current':{'time':stamp,'temperature_2m':65,'weather_code':61,'is_day':1,'cloud_cover':100,'precipitation':2}}
        with patch('scene.time.time',return_value=stamp):
            base=weather_preview(LOCATION,lambda _:data,scene_kind='urban')
        self.assertIn('calendar_context',base,'scene calendar metadata missing')
        with patch('scene.time.time',return_value=stamp):
            themed=weather_preview(LOCATION,lambda _:data,scene_kind='urban',calendar_settings={'holiday_themes':True})
        self.assertEqual(themed['selected_theme'],'halloween')
        self.assertIn('carved pumpkins',themed['positive'])
        self.assertIn('Rain streaks',themed['positive'])
        self.assertIn('Natural daytime illumination',themed['positive'])
        self.assertTrue(themed['negative'].startswith(base['negative']))
        self.assertEqual(themed['calendar_local_date'],'2026-10-31')
        self.assertEqual(themed['weather_evidence'],base['weather_evidence'])
        portrait=compose_for_target(themed,1080,1920)
        self.assertIn('lower 25-30%',portrait['positive'])
        with patch('scene.time.time',return_value=stamp):
            rural=weather_preview(LOCATION,lambda _:data,scene_kind='woodland',calendar_settings={'holiday_themes':True})
        self.assertNotIn('porch',rural['positive'])
        self.assertNotIn('storefront',rural['positive'])
