import unittest
from refresh_freshness import result_fresh


class RefreshFreshnessTests(unittest.TestCase):
    def test_stale_daypart_and_weather_age_rejected(self):
        scene = {'observed_at':1000, 'weather_evidence':{'daypart':'night'}}
        self.assertTrue(result_fresh(scene, 1020, 1800, 'night'))
        self.assertFalse(result_fresh(scene, 1020, 1800, 'daylight'))
        self.assertFalse(result_fresh(scene, 2801, 1800, 'night'))
        self.assertFalse(result_fresh(scene, 999, 1800, 'night'))
        self.assertFalse(result_fresh({}, 1020, 1800, 'night'))
