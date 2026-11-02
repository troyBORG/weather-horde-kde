import tempfile
import unittest
from pathlib import Path
from weather_controller import Controller, INTERVALS


class RequestedRefreshTests(unittest.TestCase):
    def test_short_intervals_backend_and_ui(self):
        qml = (Path(__file__).resolve().parents[1]/'plasma-widget/org.troyborg.weatherhorde/contents/ui/main.qml').read_text()
        with tempfile.TemporaryDirectory() as d:
            c = Controller(d)
            for minutes in (5, 10, 15):
                self.assertIn(minutes, INTERVALS)
                c.dispatch('PUT', '/v1/settings', {'interval_minutes': minutes})
                self.assertEqual(c.settings['interval_minutes'], minutes)
                self.assertIn('"%s minutes"' % minutes, qml)

    def test_safe_observation_dispatches_without_extra_grace(self):
        from refresh_scheduler import RefreshScheduler
        s = RefreshScheduler()
        s.configure(True, 'image_preview', ['A'], 300)
        s.reconcile(1000)
        self.assertIsNone(s.next_action(1000, 0))
        s.observe_activity(True, True, 0)
        self.assertIsNotNone(s.next_action(1000, 0))
        self.assertIsNone(s.next_action(1000, 0))  # no overlap
        s.fail('unsafe', monotonic_now=0)
        self.assertIsNone(s.next_action(1060, 60))  # old observation invalid
        s.observe_activity(None, True, 60)
        self.assertIsNone(s.next_action(1060, 60))
        s.observe_activity(True, True, 60)
        self.assertIsNotNone(s.next_action(1060, 60))

    def test_fresh_unlock_and_wake_enqueue_all_once_auto_off_stays_off(self):
        import time
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            c = Controller(d)
            c.displays = [{'id':'A'}, {'id':'B'}]
            c.settings.update(automation_enabled=True, automation_kind='image_preview', catch_up_refresh=True)
            c.session_activity = Mock()
            c.session_activity.poll.return_value = False
            c.scheduler.success['image_preview'] = {'A':time.time(), 'B':time.time()}
            c.render_lock.acquire()  # inspect intents without starting any work
            c.tick(monotonic_now=0)
            c.session_activity.poll.return_value = True
            c.tick(monotonic_now=10)
            self.assertEqual(set(c.scheduler.pending), {'A','B'})
            c.scheduler.pending.clear()  # simulate fulfilled request
            for n in (20, 30, 40): c.tick(monotonic_now=n)
            self.assertFalse(c.scheduler.pending)
            c.tick(monotonic_now=100)  # telemetry gap / resume
            self.assertEqual(set(c.scheduler.pending), {'A','B'})
            c.scheduler.pending.clear()
            c.tick(monotonic_now=110)
            self.assertFalse(c.scheduler.pending)
            c.session_activity.poll.return_value = None
            c.tick(monotonic_now=120)
            c.session_activity.poll.return_value = True
            c.tick(monotonic_now=130)
            self.assertFalse(c.scheduler.pending, 'unknown telemetry is not another unlock')
            c.dispatch('PUT','/v1/settings',{'automation_enabled':False})
            c.tick(monotonic_now=500)
            self.assertFalse(c.scheduler.pending)
            self.assertFalse(c.settings['automation_enabled'])
            c.render_lock.release()

    def test_mixed_geometry_quarantine_recovery_and_progress(self):
        self.mixed_geometry_recovery(1)

    def test_completed_geometry_not_regenerated_when_second_quarantined(self):
        self.mixed_geometry_recovery(2)

    def mixed_geometry_recovery(self, interrupted_job):
        import io
        import time
        from PIL import Image
        from unittest.mock import Mock, patch
        class GeometryTransport:
            def __init__(self):
                self.sizes = []
                self.interrupted = True
                self.active = False
            def queue(self, workflow):
                assert not self.active
                self.active = True
                inputs = workflow.get('10', workflow['4'])['inputs']
                self.sizes.append((inputs['width'], inputs['height']))
                return str(len(self.sizes))
            def inspect(self, job): return 'complete'
            def image(self, job):
                self.active = False
                out = io.BytesIO()
                Image.new('RGB', self.sizes[-1], 'navy').save(out, 'PNG')
                return out.getvalue()
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview', return_value={'positive':'fixture','negative':'fixture'}):
            transport = GeometryTransport()
            c = Controller(d, checkpoint='fixture', transport=transport,
                render_guard=lambda: 'vr_active' if transport.active and transport.interrupted and len(transport.sizes) == interrupted_job else 'safe', poll_seconds=0)
            c.displays = [{'id':'A','width':64,'height':128}, {'id':'B','width':128,'height':64}]
            c.settings.update(location={'town':'fixture'}, automation_enabled=True, automation_kind='image_preview', catch_up_refresh=True)
            c.session_activity = Mock()
            c.session_activity.poll.return_value = True
            c.guard = {'decision':'safe','observed_at':time.time()}
            c.tick()
            c.render_thread.join(3)
            self.assertEqual(c.state, 'quarantined')
            self.assertEqual(set(c.scheduler.pending), {'A','B'} if interrupted_job == 1 else {'B'})
            self.assertEqual(set(c.previews_by_target), set() if interrupted_job == 1 else {'A'})
            progress = c.status()['refresh']
            self.assertIn('vr_active', progress['waiting_reason'])
            self.assertEqual(progress['targets']['B']['state'], 'waiting')
            transport.interrupted = False
            c.scheduler.retry_at = 0  # advance retry deadline, never release old output
            c.guard = {'decision':'safe','observed_at':time.time()}
            c.tick()
            c.render_thread.join(3)
            self.assertEqual(set(c.previews_by_target), {'A','B'})
            self.assertFalse(c.scheduler.pending)
            self.assertEqual(transport.sizes, [(64,128),(64,128),(128,64)] if interrupted_job == 1 else [(64,128),(128,64),(128,64)])
            progress = c.status()['refresh']['targets']
            self.assertEqual([progress[t]['state'] for t in ('A','B')], ['completed','completed'])
            c.tick()
            self.assertEqual(len(transport.sizes), 3)

    def test_suspend_wallclock_gap_with_paused_monotonic_clock(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            c = Controller(d)
            c.displays = [{'id':'A'}, {'id':'B'}]
            c.settings.update(automation_enabled=True, automation_kind='image_preview', catch_up_refresh=True)
            c.session_activity = Mock()
            c.session_activity.poll.return_value = True
            c.scheduler.success['image_preview'] = {'A':1000, 'B':1000}
            c.render_lock.acquire()
            c.tick(now=1000, monotonic_now=10)
            self.assertFalse(c.scheduler.pending)
            c.tick(now=1100, monotonic_now=20)
            self.assertEqual(set(c.scheduler.pending), {'A','B'})
            c.scheduler.pending.clear()
            c.tick(now=1110, monotonic_now=30)
            self.assertFalse(c.scheduler.pending)
            c.render_lock.release()

    def test_fresh_pending_wake_intent_survives_restart(self):
        import time
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            c = Controller(d)
            c.settings.update(automation_enabled=True, automation_kind='image_preview', catch_up_refresh=True)
            c.save()
            c.scheduler.configure(True, 'image_preview', ['A','B'], 3600)
            c.scheduler.success['image_preview'] = {'A':time.time(), 'B':time.time()}
            c.scheduler.request('unlock', ['A','B'])
            c.save_refresh()
            resumed = Controller(d)
            resumed.displays = [{'id':'A'}, {'id':'B'}]
            resumed.session_activity = Mock()
            resumed.session_activity.poll.return_value = False
            resumed.tick()
            self.assertEqual(set(resumed.scheduler.pending), {'A','B'})

    def test_retry_budget_leaves_targets_pending_with_action_required(self):
        from refresh_scheduler import RefreshScheduler
        s = RefreshScheduler()
        s.configure(True, 'image_preview', ['A','B'], 300)
        s.request('unlock', ['A','B'])
        for attempt in range(4): s.fail('vr_active', monotonic_now=attempt*1000)
        self.assertTrue(s.status(4000)['action_required'])
        self.assertEqual(set(s.pending), {'A','B'})
        s.observe_activity(True, True, 4000)
        self.assertIsNone(s.next_action(4000,4000))

    def test_five_minute_freshness_boundary(self):
        from refresh_freshness import result_fresh
        scene = {'observed_at':1000, 'weather_evidence':{'daypart':'day'}}
        self.assertTrue(result_fresh(scene, 1300, 300, 'day'))
        self.assertFalse(result_fresh(scene, 1301, 300, 'day'))
        self.assertFalse(result_fresh(scene, 1100, 300, 'night'))
        for stamp in (None, float('nan'), 1400):
            self.assertFalse(result_fresh(dict(scene, observed_at=stamp), 1300, 300, 'day'))
