import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class ControllerTests(unittest.TestCase):
    def test_authenticated_settings_roundtrip_and_preview_only(self):
        self.assertIsNotNone(importlib.util.find_spec('weather_controller'), 'controller implementation missing')
        from weather_controller import Controller, make_server
        with tempfile.TemporaryDirectory() as d:
            c = Controller(Path(d))
            server = make_server(c, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(server.server_port)
            def request(path, method='GET', data=None, token=None, origin=None):
                headers = {'Content-Type': 'application/json'}
                if token: headers['Authorization'] = 'Bearer ' + token
                if origin: headers['Origin'] = origin
                req = Request(base+path, method=method, headers=headers,
                              data=json.dumps(data).encode() if data is not None else None)
                with urlopen(req, timeout=5) as r: return json.load(r)
            try:
                with self.assertRaises(HTTPError) as e:
                    request('/v1/settings', 'PUT', {'automation_enabled': True})
                self.assertEqual(e.exception.code, 401)
                e.exception.close()
                with self.assertRaises(HTTPError) as e:
                    request('/v1/status', token=c.token, origin='https://attacker.invalid')
                self.assertEqual(e.exception.code, 403)
                e.exception.close()
                got = request('/v1/settings', 'PUT', {'automation_enabled': True, 'interval_minutes': 120}, c.token)
                self.assertTrue(got['automation_enabled'])
                self.assertEqual(got['interval_minutes'], 120)
                self.assertFalse(got['apply_enabled'])
                self.assertFalse(got['render_enabled'])
                self.assertNotIn(c.token, json.dumps(got))
                self.assertEqual(Controller(Path(d)).settings['interval_minutes'], 120)
                for payload in ({'interval_minutes': 1}, {'apply_enabled': True}, {'automation_enabled': 'yes'}):
                    with self.assertRaises(HTTPError) as e:
                        request('/v1/settings', 'PUT', payload, c.token)
                    self.assertEqual(e.exception.code, 400)
                    e.exception.close()
                self.assertEqual(request('/v1/restore', 'POST', {'target':'all'}, c.token)['state'], 'blocked_preview_only')
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_location_confirm_preview_targets_and_scheduler(self):
        from weather_controller import Controller
        from unittest.mock import patch
        self.assertTrue(hasattr(Controller, 'tick'), 'orchestration and scheduler missing')
        location = {'zip':'52742', 'town':'De Witt', 'state':'Iowa', 'latitude':41.8267, 'longitude':-90.5237, 'timezone':'America/Chicago'}
        displays = [{'id':'DP-1','width':3440,'height':1440}, {'id':'DP-2','width':1080,'height':1920}]
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.resolve_zip', return_value=[location]), patch('weather_controller.weather_preview', return_value={'positive':'preview', 'negative':'visible moon', 'image_url':''}) as weather:
            c = Controller(Path(d))
            c.displays = displays
            c.guard = {'decision':'safe', 'observed_at':__import__('time').time()}
            lookup = c.dispatch('POST','/v1/location/lookup',{'zip':'52742'})
            self.assertIsNone(c.settings['location'])
            with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'location_confirmation':True})
            candidate = lookup['candidates'][0]
            c.dispatch('PUT','/v1/settings',{'location_confirmation':candidate['confirmation_id']})
            self.assertEqual(c.settings['location'],location)
            preview = c.dispatch('POST','/v1/preview',{'target':'DP-2'})
            self.assertEqual([x['id'] for x in preview['targets']],['DP-2'])
            with self.assertRaises(ValueError): c.dispatch('POST','/v1/preview',{'target':'missing'})
            for decision in ('vr_active','game_active','gpu_busy','unknown'):
                c.guard = {'decision':decision, 'observed_at':__import__('time').time()}
                got = c.dispatch('POST','/v1/render',{'target':'all','force':True})
                self.assertEqual(got['state'],'deferred')
                self.assertEqual(got['reason'],decision)
            c.guard = {'decision':'safe', 'observed_at':__import__('time').time()}
            self.assertEqual(c.dispatch('POST','/v1/render',{'target':'all','force':True})['state'], 'blocked_preview_only')
            c.dispatch('PUT','/v1/settings',{'automation_enabled':True,'interval_minutes':30})
            before=weather.call_count
            c.tick(c.next_eligible_at+1)
            self.assertEqual(weather.call_count,before+1)
            self.assertEqual(c.state,'preview_ready')
            c.tick(c.next_eligible_at-1)
            self.assertEqual(weather.call_count,before+1)
            c.dispatch('PUT','/v1/settings',{'automation_enabled':False})
            c.tick(c.next_eligible_at+100)
            self.assertEqual(weather.call_count,before+1)
            self.assertFalse(c.status()['apply_enabled'])

if __name__ == '__main__': unittest.main()
