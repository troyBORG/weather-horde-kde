import unittest, tempfile, time
from unittest.mock import patch
from test_night_realism import LOCATION, preview
from weather_controller import Controller

class SceneControls(unittest.TestCase):
    def test_lunar_and_curated_scene_in_preview(self):
        p=preview()
        self.assertIn('lunar',p['weather_evidence'])
        self.assertEqual(p['prompt_version'],'night-lunar-2')
        self.assertIn('park',preview(scene_kind='townpark')['positive'])
        self.assertIn('woodland',preview(scene_kind='woodland')['positive'])
    def test_scene_setting_and_expiring_observation(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d); c.settings['location']=LOCATION
            c.dispatch('PUT','/v1/settings',{'scene_kind':'woodland'})
            self.assertEqual(c.status()['scene_kind'],'woodland')
            body={'observed_at':time.time(),'ttl_minutes':15,'temperature_f':42,'cloud_cover_percent':100,'precipitation_mm':1,'weather_code':61,'location_zip':'52742'}
            c.dispatch('PUT','/v1/observation',body)
            self.assertTrue(c.status()['observation']['active'])
            stamp=time.time()
            with patch('scene.forecast',return_value={'current':{'time':stamp,'temperature_2m':60,'weather_code':0,'is_day':1}}):
                p=c.build_preview({})
                self.assertEqual(p['weather_evidence']['source'],'Manual user observation')
                self.assertEqual(p['weather_evidence']['provider_current']['temperature_2m'],60)
                self.assertIn('Rain',p['positive'])
            with patch('weather_controller.time.time', return_value=stamp+901):
                self.assertFalse(c.status()['observation']['active'])
            c.dispatch('PUT','/v1/observation',{'enabled':False})
            self.assertFalse(c.status()['observation']['active'])
            for changes in ({'cloud_cover_percent':101},{'weather_code':999},{'temperature_f':float('nan')},{'ttl_minutes':999},{'observed_at':stamp-7200},{'location_zip':'00000'},{'extra':'arbitrary'}):
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/observation',body|changes)
