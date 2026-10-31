import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from weather_controller import Controller
from test_preview_pipeline import Transport


class CatchupIntegrationTests(unittest.TestCase):
    def make(self, directory):
        c = Controller(directory, checkpoint='fixture', transport=Transport(), render_guard=lambda: 'safe', poll_seconds=0)
        c.displays = [{'id':'TEST','width':64,'height':128}]
        c.guard = {'decision':'safe','observed_at':time.time()}
        c.settings.update(location={'town':'fixture'}, automation_enabled=True, automation_kind='image_preview', catch_up_refresh=True)
        c.session_activity = Mock()
        c.session_activity.poll.return_value = True
        return c

    @patch('weather_controller.weather_preview', return_value={'positive':'fixture','negative':'fixture'})
    def test_startup_overdue_game_exit_coalesces_after_minute(self, _):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.guard['decision'] = 'game_active'
            for n in range(20):
                c.tick(now=5000, monotonic_now=n*10)
            self.assertIsNone(c.render_thread)
            self.assertEqual(c.status()['refresh']['pending'], ['TEST'])
            c.guard['decision'] = 'safe'
            for n in range(200, 260, 10):
                c.tick(now=5000, monotonic_now=n)
                self.assertIsNone(c.render_thread)
            c.tick(now=5000, monotonic_now=260)
            c.render_thread.join(3)
            self.assertEqual(c.state, 'image_preview_ready')
            self.assertGreater(c.image_preview['generated_at'], time.time()-5)
            self.assertFalse(c.scheduler.pending)
            prior = c.image_preview['id']
            c.tick(now=time.time(), monotonic_now=270)
            self.assertEqual(c.image_preview['id'], prior)

    @patch('weather_controller.weather_preview', return_value={'positive':'fixture','negative':'fixture'})
    @patch('refresh_freshness.result_fresh', return_value=False)
    def test_stale_completed_render_never_applies(self, fresh, _):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.settings['location'].update(latitude=40, longitude=-90)
            c.settings['automation_kind'] = 'image_wallpaper'
            c.wallpaper = Mock()
            c.wallpaper.available.return_value = []
            for n in range(0, 61, 10): c.tick(now=5000, monotonic_now=n)
            c.render_thread.join(3)
            c.wallpaper.apply.assert_not_called()
            self.assertEqual(c.scheduler.pending.keys(), {'TEST'})

    @patch('weather_controller.weather_preview', return_value={'positive':'fixture','negative':'fixture'})
    def test_overnight_unlock_once_and_quick_fresh_unlock_no_job(self, _):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.session_activity.poll.return_value=False
            for n in range(0,101,10): c.tick(now=time.time(),monotonic_now=n)
            self.assertIsNone(c.render_thread)
            c.session_activity.poll.return_value=True
            for n in range(110,170,10):
                c.tick(now=time.time(),monotonic_now=n)
                self.assertIsNone(c.render_thread)
            c.tick(now=time.time(),monotonic_now=170)
            thread=c.render_thread
            thread.join(3)
            c.session_activity.poll.return_value=False
            c.tick(now=time.time(),monotonic_now=180)
            c.session_activity.poll.return_value=True
            for n in range(190,261,10): c.tick(now=time.time(),monotonic_now=n)
            self.assertIs(c.render_thread,thread)
            self.assertFalse(c.scheduler.pending)

    @patch('weather_controller.weather_preview', return_value={'positive':'fixture','negative':'fixture'})
    def test_partial_monitor_freshness_dispatches_only_missing(self, _):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.displays.append({'id':'OTHER','width':64,'height':128})
            c.scheduler.success['image_preview']={'TEST':time.time()}
            for n in range(0,61,10): c.tick(now=time.time(),monotonic_now=n)
            c.render_thread.join(3)
            self.assertEqual(c.image_preview['targets'],['OTHER'])
            self.assertFalse(c.scheduler.pending)

    @patch('weather_controller.weather_preview', return_value={'positive':'fixture','negative':'fixture'})
    def test_prompt_completion_is_not_wallpaper_success(self, _):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.settings['automation_kind']='prompt_preview'
            for n in range(0,61,10): c.tick(now=time.time(),monotonic_now=n)
            self.assertIsNone(c.render_thread)
            self.assertIn('prompt',c.scheduler.success['prompt_preview'])
            self.assertFalse(c.scheduler.success['image_wallpaper'])

    @patch('weather_controller.weather_preview', return_value={'positive':'fixture','negative':'fixture'})
    def test_restart_recovers_generation_receipt_before_scheduler_save(self, _):
        with tempfile.TemporaryDirectory() as d:
            c=self.make(d)
            c.dispatch('POST','/v1/render',{'target':'TEST'})
            c.render_thread.join(3)
            restarted=self.make(d)
            for n in range(0,61,10): restarted.tick(now=time.time(),monotonic_now=n)
            if restarted.render_thread: restarted.render_thread.join(3)
            self.assertIsNone(restarted.render_thread)
            self.assertEqual(restarted.scheduler.success['image_preview']['TEST'], c.image_preview['generated_at'])

    def test_mid_render_unsafe_observation_resets_safe_grace(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.scheduler.configure(True,'image_preview',['TEST'],1800)
            c.scheduler.request('startup',['TEST'])
            for n in range(0,61,10): c.scheduler.observe_activity(True,True,n)
            c.scheduler.next_action(time.time(),60)
            c.render_images = Mock()
            c.dispatch('POST','/v1/render',{'target':'TEST'},scheduled=True)
            c.render_thread.join(3)
            policy = c.render_images.call_args.args[2][0]
            c.render_guard = lambda: 'game_active'
            self.assertEqual(policy(),'game_active')
            self.assertIsNone(c.scheduler.safe_since)

    def test_missing_location_is_actionable_not_retry_loop(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.settings['location'] = None
            for n in range(0,61,10): c.tick(now=5000, monotonic_now=n)
            self.assertTrue(c.status()['refresh']['action_required'])
            self.assertIsNone(c.render_thread)

    def test_private_audit_is_bounded_and_success_correlated(self):
        import json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            for n in range(110): c.refresh_event('trigger', generation_id=str(n))
            events=json.loads((Path(d)/'refresh-events.json').read_text())
            self.assertEqual(len(events),100)
            self.assertEqual(events[-1]['generation_id'],'109')
            self.assertNotIn(c.token, json.dumps(events))
            self.assertEqual((Path(d)/'refresh-events.json').stat().st_mode & 0o777,0o600)

    def test_auto_off_cancels_before_callback_and_restart_receipt_stays_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.scheduler.configure(True, 'image_preview', ['TEST'], 1800)
            c.scheduler.reconcile(time.time(), 'startup')
            for n in range(0,61,10): c.scheduler.observe_activity(True,True,n)
            action = c.scheduler.next_action(time.time(),60)
            c.dispatch('PUT','/v1/settings',{'automation_enabled':False})
            c.refresh_complete('TEST', action['generation_id'])
            self.assertNotIn('TEST', c.scheduler.success.get('image_preview',{}))
            c.scheduler.success={'image_preview':{'TEST':time.time()}}
            c.save_refresh()
            restarted = self.make(d)
            for n in range(0,61,10): restarted.tick(now=time.time(),monotonic_now=n)
            self.assertIsNone(restarted.render_thread)

    def test_managed_startup_rechecks_lock_not_resource_only(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            c.comfy_service = Mock()
            c.transport.owned_gpu_pid = lambda: None
            c.startup_guard = Mock(return_value='safe')
            c.session_activity.poll.return_value = False
            c.scheduler.configure(True,'image_preview',['TEST'],1800)
            c.scheduler.request('startup',['TEST'])
            c.scheduler.active={'generation_id':'fixture','targets':['TEST'],'mode':'image_preview'}
            result=c.dispatch('POST','/v1/render',{'target':'TEST'},scheduled=True)
            self.assertEqual(result['reason'],'session_locked')
            c.comfy_service.ensure_ready.assert_not_called()
            c.startup_guard.assert_not_called()

    def test_locked_unknown_and_auto_off_never_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.make(d)
            for unlocked in (False, None):
                c.session_activity.poll.return_value = unlocked
                for n in range(0, 100, 10): c.tick(now=5000, monotonic_now=n)
                self.assertIsNone(c.render_thread)
            c.dispatch('PUT','/v1/settings',{'automation_enabled':False})
            self.assertFalse(c.scheduler.pending)
