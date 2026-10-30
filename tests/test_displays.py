import importlib.util
import unittest
from unittest.mock import patch


class DisplayTests(unittest.TestCase):
    def test_native_mode_rotates_without_multiplying_scale(self):
        self.assertIsNotNone(importlib.util.find_spec('displays'), 'display detection missing')
        from displays import parse_outputs, discover, base_size
        def output(name, w, h, rotation=1, scale=1):
            return {'name':name, 'enabled':True, 'connected':True, 'currentModeId':'0', 'rotation':rotation,
                    'scale':scale, 'priority':1, 'modes':[{'id':'0','size':{'width':w,'height':h}}]}
        result = parse_outputs({'outputs':[output('DP-1',3440,1440,scale=1.25),output('DP-2',1920,1080,2)]})
        positioned=output('DP-X',1920,1080,2,1.25) | {'pos':{'x':2752,'y':0}}
        p=parse_outputs({'outputs':[positioned]})[0]
        self.assertEqual((p.get('x'),p.get('y')),(2752,0))
        self.assertEqual([(d['width'], d['height']) for d in result], [(3440,1440),(1080,1920)])
        self.assertEqual(base_size(3440,1440), (1720,720))
        w,h = base_size(1080,1920)
        self.assertEqual(w*1920,h*1080)
        self.assertEqual(w%8+h%8,0)
        self.assertLessEqual(w*h,1500000)
        with self.assertRaises(ValueError): parse_outputs({'outputs':[output('DP-1',0,1440)]})
        with self.assertRaises(ValueError): parse_outputs({'outputs':[output('DP-1',3440,1440,3)]})
        with patch('displays.subprocess.run') as runner:
            result, error = discover({})
            self.assertEqual(result, [])
            self.assertIn('graphical', error)
            runner.assert_not_called()

if __name__ == '__main__': unittest.main()
