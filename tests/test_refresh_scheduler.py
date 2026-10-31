import unittest
from refresh_scheduler import RefreshScheduler


class RefreshSchedulerTests(unittest.TestCase):
    def ready(self, targets=('A','B')):
        s = RefreshScheduler()
        s.configure(True, 'image_wallpaper', targets, 1800)
        s.reconcile(10000, 'startup')
        for n in range(0, 61, 10): s.observe_activity(True, True, n)
        return s

    def test_partial_failure_retries_only_missing_and_stale_callback_rejected(self):
        s = self.ready()
        job = s.next_action(10000, 60)
        self.assertTrue(s.complete('A', job['generation_id'], 10000))
        s.fail('apply_failed', monotonic_now=60)
        for n in range(70, 121, 10): s.observe_activity(True, True, n)
        retry = s.next_action(10060, 120)
        self.assertEqual(retry['targets'], ['B'])
        self.assertFalse(s.complete('B', job['generation_id'], 10060))
        self.assertNotIn('B', s.success['image_wallpaper'])
        s.configure(False, 'image_wallpaper', ['A','B'], 1800)
        self.assertFalse(s.complete('B', retry['generation_id'], 10060))
        self.assertFalse(s.pending)

    def test_unknown_lock_suspend_and_clock_reversal_restart_grace(self):
        for safe, unlocked, instant in [(False,True,70), (None,True,70), (True,False,70), (True,None,70), (True,True,6000), (True,True,30)]:
            with self.subTest(safe=safe, unlocked=unlocked, instant=instant):
                s = self.ready()
                s.observe_activity(safe, unlocked, instant)
                self.assertIsNone(s.next_action(10000, instant))
                for n in range(instant+10, instant+70,10):
                    s.observe_activity(True, True, n)
                    if safe is not True or unlocked is not True:
                        self.assertIsNone(s.next_action(10000,n))

    def test_fresh_unlock_mode_change_and_wallclock_rollback(self):
        s = self.ready(('A',))
        job = s.next_action(10000,60)
        s.complete('A',job['generation_id'],10000)
        for _ in range(20): s.reconcile(10001,'unlock')
        self.assertFalse(s.pending)
        s.reconcile(9000,'startup')
        self.assertEqual(set(s.pending), {'A'})
        s.configure(True,'image_preview',['A'],1800)
        s.reconcile(10001,'startup')
        self.assertEqual(set(s.pending), {'A'})

    def test_stale_observation_status_never_says_ready(self):
        s = self.ready()
        self.assertEqual(s.status(6000)['waiting_reason'], 'activity_unknown')
        self.assertIsNone(s.next_action(10000,6000))

    def test_blocked_intervals_coalesce_after_continuous_safe_minute(self):
        s = RefreshScheduler()
        s.configure(True, 'image_wallpaper', ['A'], 1800)
        for n in range(20):
            s.reconcile(10000 + n * 1800, 'interval')
            s.observe_activity(False, True, n * 10)
            self.assertIsNone(s.next_action(10000, n * 10))
        for n in range(200, 260, 10):
            s.observe_activity(True, True, n)
            self.assertIsNone(s.next_action(50000, n))
        s.observe_activity(True, True, 260)
        action = s.next_action(50000, 260)
        self.assertEqual(action['targets'], ['A'])
        self.assertIsNone(s.next_action(50000, 260))
        self.assertTrue(s.complete('A', action['generation_id'], 50000))
        s.reconcile(50001, 'unlock')
        self.assertFalse(s.pending)
