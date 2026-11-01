from datetime import datetime
import tempfile
import unittest
from unittest.mock import patch
from weather_controller import Controller
from calendar_context import resolve_calendar
from test_holiday_prompt import LOCATION

class HolidayRefreshTests(unittest.TestCase):
    def test_stale_result_rejected_and_midnight_coalesced_while_locked(self):
        from refresh_freshness import result_fresh
        before=datetime.fromisoformat('2026-11-01T04:59:59+00:00').timestamp()
        after=before+2
        old=resolve_calendar(datetime.fromtimestamp(before).astimezone(),LOCATION,{'holiday_themes':True})
        new=resolve_calendar(datetime.fromtimestamp(after).astimezone(),LOCATION,{'holiday_themes':True})
        scene={'observed_at':before,'weather_evidence':{'daypart':'night'},'calendar_context_hash':old['context_hash']}
        # Existing freshness API must admit a current context argument.
        import inspect
        self.assertIn('calendar_context',inspect.signature(result_fresh).parameters)
        self.assertFalse(result_fresh(scene,after,3600,'night',new))
        self.assertTrue(result_fresh(scene,before,3600,'night',old))
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d); c.settings.update(location=LOCATION,holiday_themes=True,catch_up_refresh=True,automation_enabled=True)
            c.scheduler.success={'prompt_preview':{'prompt':before}}
            c.calendar_success={'prompt_preview':{'prompt':old['context_hash']}}
            with patch.object(c.session_activity,'poll',return_value=False),patch.object(c,'build_preview') as build:
                for i in range(3): c.tick(after+i,100+i)
                build.assert_not_called()
            self.assertEqual(set(c.scheduler.pending),{'prompt'})
            self.assertIn('calendar_change',c.scheduler.pending['prompt'])
            c.settings['automation_enabled']=False
            c.tick(after+4,104)
            self.assertFalse(c.scheduler.pending)


    def test_real_render_crossing_midnight_never_auto_applies(self):
        import io
        from PIL import Image
        from types import SimpleNamespace
        before=datetime.fromisoformat('2026-11-01T04:59:59+00:00').timestamp()
        clock=[before]
        class Transport:
            def queue(self,graph): return 'fixture-job'
            def inspect(self,job): clock[0]=before+2; return 'complete'
            def image(self,job):
                out=io.BytesIO(); Image.new('RGB',(512,512)).save(out,'PNG'); return out.getvalue()
        with tempfile.TemporaryDirectory() as d,patch('weather_controller.time.time',side_effect=lambda:clock[0]):
            c=Controller(d,checkpoint='fixture.safetensors',transport=Transport(),render_guard=lambda:'safe')
            c.settings.update(location=LOCATION,holiday_themes=True)
            c.wallpaper=SimpleNamespace(apply=lambda *a: self.fail('stale calendar reached wallpaper adapter'))
            data={'current':{'time':before,'temperature_2m':50,'weather_code':3,'is_day':0}}
            c.render_lock.acquire()
            with patch('weather_controller.fetch_json',return_value=data):
                c.render_images([{'id':'L','width':512,'height':512}],LOCATION,policy=(lambda:'safe',{}),auto_apply=True)
            self.assertIn('Stale',c.last_error)

    def test_completion_persists_only_actual_output_calendar(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d); c.settings.update(location=LOCATION,holiday_themes=True)
            c.scheduler.configure(True,'image_preview',['L'],3600)
            c.scheduler.request('calendar_change',['L'])
            c.scheduler.observe_activity(True,True,0)
            c.scheduler.grace=0
            action=c.scheduler.next_action(1,0)
            scene={'calendar_context_hash':'actual-image-hash'}
            c.previews_by_target['L']={'scene':scene}
            c.refresh_complete('L',action['generation_id'],1)
            self.assertEqual(c.calendar_success.get('image_preview',{}).get('L'),'actual-image-hash')
            self.assertEqual(Controller(d).calendar_success,c.calendar_success)
            c.refresh_complete('L','cancelled',2)
            self.assertEqual(c.scheduler.success['image_preview']['L'],1)

    def test_batch_resolves_calendar_once_and_shares_it(self):
        stamp=datetime.fromisoformat('2026-11-01T04:59:59+00:00').timestamp()
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d); c.settings.update(holiday_themes=True,location=LOCATION,scene_overrides={'R':'woodland'})
            data={'current':{'time':stamp,'temperature_2m':50,'weather_code':3,'is_day':0}}
            with patch('weather_controller.time.time',return_value=stamp), patch('weather_controller.fetch_json',return_value=data):
                scenes=c.target_scene_previews(LOCATION,[{'id':i,'width':512,'height':512} for i in ('L','R')])
            self.assertEqual([s['scene']['selected_theme'] for s in scenes],['halloween','halloween'])
            self.assertIs(scenes[0]['scene']['calendar_context'],scenes[1]['scene']['calendar_context'])
