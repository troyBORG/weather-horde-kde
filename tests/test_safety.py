import importlib.util
import unittest


class SafetyTests(unittest.TestCase):
    def test_guard_rejects_missing_busy_vr_game_and_stale_evidence(self):
        self.assertIsNotNone(importlib.util.find_spec('safety'), 'safety boundary missing')
        from safety import decide
        good = {'processes': ['kwin_wayland', 'Discord'], 'complete': True, 'utilization': [2, 3], 'free_mib': 20000, 'sample_gap': 10, 'age': 0}
        self.assertEqual(decide(good), 'safe')
        for change, expected in [({'complete':False},'unknown'), ({'age':20},'unknown'),
                ({'processes':['vrcompositor']},'vr_active'), ({'processes':['driftwood-xiloa']},'game_active'),
                ({'processes':['Resonite']},'game_active'), ({'processes':['unknown-game.exe']},'game_active'),
                ({'utilization':[35,50]},'gpu_busy'), ({'free_mib':4000},'insufficient_vram'),
                ({'utilization':['bad',0]},'unknown'), ({'sample_gap':1},'unknown')]:
            with self.subTest(change=change): self.assertEqual(decide(good | change), expected)
        self.assertEqual(decide(None), 'unknown')

    def test_unknown_gpu_client_blocks_safe_decision(self):
        from safety import decide
        snapshot = {'processes':['kwin_wayland'], 'complete':True, 'utilization':[0,0], 'free_mib':20000, 'sample_gap':10, 'age':0,
                    'gpu_clients':['/usr/bin/kwin_wayland', '/games/native-unknown']}
        self.assertEqual(decide(snapshot), 'unknown')

if __name__ == '__main__': unittest.main()
