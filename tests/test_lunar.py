import unittest
from datetime import datetime
import scene

class LunarTests(unittest.TestCase):
    def test_reference_full_new_and_polar(self):
        self.assertTrue(callable(getattr(scene, 'lunar_evidence', None)), 'calculated lunar evidence missing')
        stamp=lambda s: datetime.fromisoformat(s).timestamp()
        full=scene.lunar_evidence(stamp('2024-03-25T07:00:00+00:00'),41.8,-90.5)
        new=scene.lunar_evidence(stamp('2024-04-08T18:21:00+00:00'),41.8,-90.5)
        self.assertGreater(full['illumination'], .99)
        self.assertLess(new['illumination'], .01)
        self.assertGreater(full['altitude_degrees'],0)
        polar=scene.lunar_evidence(stamp('2024-03-25T07:00:00+00:00'),90,0)
        self.assertTrue(-90 <= polar['altitude_degrees'] <= 90)
        self.assertIn('terrain',polar['uncertainty'])
    def test_visibility_never_below_horizon_or_opaque(self):
        self.assertTrue(callable(getattr(scene,'moon_visible',None)), 'visibility policy missing')
        for altitude,illum,cloud,part,expected in [(20,.8,10,'night',True),(-1,.8,0,'night',False),(20,.001,0,'night',False),(20,.8,95,'night',False),(20,.8,0,'daytime',False),(1,.8,0,'night',False),(20,.8,None,'night',False)]:
            self.assertEqual(scene.moon_visible({'altitude_degrees':altitude,'illumination':illum},cloud,False,part),expected)
