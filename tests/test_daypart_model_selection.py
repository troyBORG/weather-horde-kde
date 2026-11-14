"""Pure policy contracts; no model loading or clock reads."""
import unittest
import importlib.util

class SelectionTests(unittest.TestCase):
    def test_five_mappings_live_intersection_dedupe_and_rotation(self):
        from model_selection import resolve, defaults
        class RNG:
            def choice(self, values):
                self.values = values
                return values[-1]
        rng = RNG()
        p = defaults(); p.update(mode='lighting', day=['A', 'A', 'a', 'gone'], night=['N'])
        for daypart in ('daytime', 'golden hour', 'blue hour', 'twilight', 'night'):
            pool = p['mapping'][daypart]
            r = resolve(daypart, p, ['A', 'a', 'N'], 'manual', rng=rng)
            self.assertEqual(r['checkpoint'], 'a' if pool == 'day' else 'N')
            self.assertEqual(r['pool'], pool)
        self.assertEqual(resolve('daytime',p,['A','a'],'manual',previous='a',rng=rng)['checkpoint'],'A')
        self.assertEqual(rng.values,['A'])
        p['mapping']['twilight'] = 'day'
        self.assertEqual(resolve('twilight',p,['A'],'manual',previous='A',rng=rng)['checkpoint'],'A')
        for daypart, eligible in [('unknown',['A','N']),('night',['A']),('daytime',[])]:
            r=resolve(daypart,p,eligible,'manual',rng=rng)
            self.assertIsNone(r['checkpoint']); self.assertTrue(r['reason'])
        p['night']=[]
        self.assertIsNone(resolve('night',p,['A','N'],'manual',rng=rng)['checkpoint'])

    def test_single_mode_preserves_literal_checkpoint(self):
        self.assertIsNotNone(importlib.util.find_spec('model_selection'), 'pure policy module missing')
        from model_selection import resolve, defaults
        result = resolve('night', defaults(), ['sub/A.safetensors'], 'sub/A.safetensors')
        self.assertEqual(result['checkpoint'], 'sub/A.safetensors')
        self.assertEqual(result['pool'], 'single')
