"""Offline, dated fixtures, not a claim about current local weather."""
from datetime import datetime
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scene import weather_preview

LOCATION = {'zip':'52742', 'town':'De Witt', 'state':'Iowa',
            'latitude':41.8267, 'longitude':-90.5237, 'timezone':'America/Chicago'}


def preview(hour=1, minute=30, code=3, temp=28, **kwargs):
    stamp = datetime(2026, 10, 29, hour, minute, tzinfo=ZoneInfo('America/Chicago')).timestamp()
    data = {'current':{'time':stamp, 'temperature_2m':temp, 'weather_code':code, 'is_day':0}}
    with patch('scene.time.time', return_value=stamp):
        return weather_preview(LOCATION, lambda _: data, **kwargs)


class NightRealismTests(TestCase):
    def test_solar_boundaries_override_coarse_provider_day_flag(self):
        # Frozen Iowa autumn fixtures: golden hour, civil twilight, true night.
        for hour, minute, expected in ((17, 30, 'golden hour'), (18, 15, 'blue hour'),
                                       (19, 0, 'twilight'), (21, 0, 'night'), (1, 30, 'night')):
            with self.subTest(hour=hour, minute=minute):
                p = preview(hour, minute, code=0)
                self.assertEqual(p['time_of_day'], expected)
                self.assertEqual('sunset' in p['negative'], expected == 'night')


    def test_weather_evidence_and_rain_visuals(self):
        p = preview(code=61)
        self.assertIn('wet surfaces', p['positive'])
        evidence = p['weather_evidence']
        self.assertEqual(evidence['source'], 'Open-Meteo model current conditions')
        self.assertEqual(evidence['weather_code'], 61)
        self.assertEqual(evidence['timezone'], 'America/Chicago')
        self.assertEqual(evidence['age_seconds'], 0)
        self.assertIn('T01:30:00-05:00', evidence['local_time'])
        self.assertIsNone(evidence['cloud_cover_percent'])
        self.assertIsNone(evidence['precipitation_mm'])
        self.assertEqual(evidence['temperature_f'], 28)
        self.assertLess(evidence['solar_elevation_degrees'], -18)
        self.assertFalse(evidence['manual_override'])

    def test_cloud_precipitation_fetch_and_evidence(self):
        from scene import forecast
        from urllib.parse import parse_qs, urlparse
        called = []
        forecast(LOCATION, lambda url: called.append(url))
        fields = parse_qs(urlparse(called[0]).query)['current'][0].split(',')
        self.assertIn('cloud_cover', fields)
        self.assertIn('precipitation', fields)
        stamp = datetime(2026, 10, 29, 1, 30, tzinfo=ZoneInfo('America/Chicago')).timestamp()
        data = {'current':{'time':stamp, 'temperature_2m':40, 'weather_code':0,
                           'is_day':0, 'cloud_cover':100, 'precipitation':0}}
        with patch('scene.time.time', return_value=stamp):
            p = weather_preview(LOCATION, lambda _: data)
        self.assertIn('Opaque cloud cover', p['positive'])
        self.assertNotIn('Unbroken open sky', p['positive'])
        self.assertIn('stars', p['negative'])
        self.assertEqual(p['weather_evidence']['cloud_cover_percent'], 100)
        self.assertEqual(p['weather_evidence']['precipitation_mm'], 0)

    def test_daypart_visuals_and_separate_rural_urban_compositions(self):
        sunny = preview(17, 30, code=0)
        cloudy = preview(17, 30, code=3)
        self.assertIn('low-angle sunlight', sunny['positive'])
        self.assertNotIn('low-angle sunlight', cloudy['positive'])
        self.assertIn('diffuse', cloudy['positive'])
        self.assertIn('faint residual solar light', preview(19, 0)['positive'])
        self.assertIn('cool ambient', preview(18, 15)['positive'].lower())
        rural = preview(scene_kind='rural')
        urban = preview(scene_kind='urban')
        self.assertIn('farmland', rural['positive'])
        self.assertNotIn('utility wires', rural['positive'])
        self.assertIn('low-rise', urban['positive'])
        self.assertNotIn('farmland', urban['positive'])
        with self.assertRaises(ValueError): preview(scene_kind='invented')

    def test_moon_cloud_and_temperature_policies(self):
        for code in (0, 1, 2, 3, 45, 61, 71):
            p = preview(code=code, temp=-10)
            self.assertNotIn('moon', p['positive'])
            self.assertIn('visible moon', p['negative'])
            self.assertEqual('stars' in p['negative'], code not in (0, 1, 2))
            self.assertEqual('snow' in p['positive'], code == 71)

    def test_exact_solar_boundaries_and_polar_cases(self):
        from scene import solar_daypart, solar_elevation
        for elevation, expected in ((-18.001,'night'),(-18,'twilight'),(-6,'blue hour'),
                                    (-0.833,'golden hour'),(6,'daytime')):
            self.assertEqual(solar_daypart(elevation), expected)
        for month, expected in ((6,'daytime'), (12,'night')):
            stamp = datetime(2026, month, 21, 12, tzinfo=ZoneInfo('UTC')).timestamp()
            self.assertEqual(solar_daypart(solar_elevation(stamp, 90, 0)), expected)

    def test_weather_input_validation_and_staleness(self):
        stamp = datetime(2026, 10, 29, 1, 30, tzinfo=ZoneInfo('America/Chicago')).timestamp()
        base = {'time':stamp, 'temperature_2m':28, 'weather_code':3, 'is_day':0}
        for extra in ({'cloud_cover':101}, {'cloud_cover':float('nan')},
                      {'precipitation':-1}, {'time':stamp-7201}, {'time':stamp+301}):
            with self.subTest(extra=extra), patch('scene.time.time', return_value=stamp):
                with self.assertRaises(ValueError):
                    weather_preview(LOCATION, lambda _: {'current':base | extra})

    def test_0130_overcast_has_dark_sky_and_local_not_solar_light(self):
        p = preview()
        self.assertEqual(p['time_of_day'], 'night')
        self.assertIn('deep night', p['positive'])
        self.assertIn('cool gray', p['positive'])
        self.assertIn('localized artificial', p['positive'])
        self.assertIn('silhouettes', p['positive'])
        for phrase in ('sunset', 'sunrise', 'dusk', 'twilight', 'orange horizon'):
            self.assertIn(phrase, p['negative'])
            self.assertNotIn(phrase, p['positive'])
        self.assertNotIn('snow', p['positive'])
        self.assertNotIn('moon', p['positive'])
        self.assertIn('visible moon', p['negative'])
