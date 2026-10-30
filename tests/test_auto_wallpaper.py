import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import test_preview_pipeline as pipeline

class AutoWallpaperTests(unittest.TestCase):
    def test_explicit_target_schedule_applies_only_after_validated_render(self):
        with tempfile.TemporaryDirectory() as td, patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'test'}):
            c,t=pipeline.PipelineTests().make(td,['safe'])
            c.wallpaper=Mock(); c.wallpaper.available.return_value=[]
            c.wallpaper.apply.side_effect=lambda display, identifier, guard: {'state':'applied','target':display['id'],'preview_id':identifier,'verified':guard()=='safe'}
            c.dispatch('PUT','/v1/settings',{'automation_kind':'image_wallpaper','automation_target':'TEST','automation_enabled':True})
            c.tick(c.next_eligible_at+1); pipeline.PipelineTests().finish(c)
            self.assertEqual(c.wallpaper.apply.call_count,1)
            self.assertEqual(c.wallpaper.apply.call_args.args[0]['id'],'TEST')
            self.assertEqual(c.status()['previews_by_target']['TEST']['id'],c.image_preview['id'])
            self.assertEqual(c.state,'wallpapers_applied')

    def test_game_or_disabled_schedule_never_applies(self):
        for decisions in (['game_active'], ['safe','game_active']):
            with tempfile.TemporaryDirectory() as td, patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'test'}):
                c,t=pipeline.PipelineTests().make(td,list(decisions)); c.wallpaper=Mock();c.wallpaper.available.return_value=[]
                c.dispatch('PUT','/v1/settings',{'automation_kind':'image_wallpaper','automation_target':'TEST','automation_enabled':True})
                c.tick(c.next_eligible_at+1)
                if c.render_thread: pipeline.PipelineTests().finish(c)
                c.wallpaper.apply.assert_not_called()

    def test_manual_generate_does_not_apply_even_with_auto_mode_selected(self):
        with tempfile.TemporaryDirectory() as td, patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'test'}):
            c,t=pipeline.PipelineTests().make(td,['safe']); c.wallpaper=Mock(); c.wallpaper.available.return_value=[]
            c.dispatch('PUT','/v1/settings',{'automation_kind':'image_wallpaper','automation_target':'TEST'})
            c.dispatch('POST','/v1/render',{'target':'TEST'}); pipeline.PipelineTests().finish(c)
            c.wallpaper.apply.assert_not_called()

    def test_all_targets_and_disable_during_render(self):
        for disable in (False, True):
            with tempfile.TemporaryDirectory() as td, patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'test'}):
                c,t=pipeline.PipelineTests().make(td,['safe'])
                c.displays=[{'id':target,'width':64,'height':128} for target in ('DP-2','DP-3')]
                c.wallpaper=Mock();c.wallpaper.available.return_value=[]
                c.wallpaper.apply.side_effect=lambda display, identifier, guard: {'state':'applied','target':display['id'],'preview_id':identifier,'verified':True}
                c.dispatch('PUT','/v1/settings',{'automation_kind':'image_wallpaper','automation_target':'all','automation_enabled':True})
                if disable:
                    image=t.image
                    def stop_before_publication(job):
                        raw=image(job);c.dispatch('PUT','/v1/settings',{'automation_enabled':False});return raw
                    t.image=stop_before_publication
                c.tick(c.next_eligible_at+1);pipeline.PipelineTests().finish(c)
                self.assertEqual([call.args[0]['id'] for call in c.wallpaper.apply.call_args_list],[] if disable else ['DP-2','DP-3'])

    def test_override_pauses_auto_instead_of_bypassing_activity(self):
        with tempfile.TemporaryDirectory() as td:
            c,t=pipeline.PipelineTests().make(td,['game_active']);c.wallpaper=Mock();c.wallpaper.available.return_value=[]
            c.dispatch('PUT','/v1/settings',{'automation_kind':'image_wallpaper','automation_enabled':True})
            c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})
            c.tick(c.next_eligible_at+1)
            self.assertIsNone(c.render_thread);c.wallpaper.apply.assert_not_called()
            self.assertFalse(c.settings['automation_enabled'])

    def test_per_target_previews_survive_restart(self):
        from weather_controller import Controller
        with tempfile.TemporaryDirectory() as td, patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'test'}):
            c,t=pipeline.PipelineTests().make(td,['safe'])
            for target in ('DP-2','DP-3'):
                c.displays=[{'id':target,'width':64,'height':128}]
                c.dispatch('POST','/v1/render',{'target':target}); pipeline.PipelineTests().finish(c)
            restarted=Controller(td,checkpoint='test',transport=t,render_guard=lambda:'safe')
            self.assertEqual(set(restarted.status()['previews_by_target']),{'DP-2','DP-3'})
            self.assertNotEqual(restarted.previews_by_target['DP-2']['id'],restarted.previews_by_target['DP-3']['id'])
