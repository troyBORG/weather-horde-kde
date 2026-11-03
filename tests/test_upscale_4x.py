import unittest
from comfy_preview import build_workflow
from model_catalog import PROFILES


class FourTimesUpscaleTests(unittest.TestCase):
    def test_reviewed_4x_model_preserves_native_targets_and_sampler(self):
        for kind in ('sdxl', 'sd15'):
            profile = PROFILES[kind]
            for width, height in ((3440, 1440), (1080, 1920), (4544, 1920)):
                with self.subTest(kind=kind, size=(width, height)):
                    graph = build_workflow(
                        'fixture.safetensors', 'fixture', 'fixture',
                        width, height, 123, profile=profile)
                    base = graph['4']['inputs']
                    self.assertLessEqual(base['width'] * base['height'],
                                         profile['max_pixels'])
                    self.assertEqual(base['width'] * height,
                                     base['height'] * width)
                    self.assertEqual(graph['7']['inputs']['model_name'],
                                     'RealESRGAN_x4plus.pth')
                    self.assertEqual(graph['8']['class_type'],
                                     'ImageUpscaleWithModel')
                    self.assertEqual(graph['8']['inputs']['image'], ['6', 0])
                    self.assertEqual(graph['10']['inputs']['image'], ['8', 0])
                    self.assertEqual(graph['10']['inputs']['width'], width)
                    self.assertEqual(graph['10']['inputs']['height'], height)
                    self.assertEqual(graph['10']['inputs']['crop'], 'disabled')
                    self.assertEqual(graph['9']['inputs']['images'], ['10', 0])
                    self.assertEqual(graph['5']['inputs']['seed'], 123)
                    self.assertEqual(graph['5']['inputs']['steps'], profile['steps'])
                    self.assertEqual(graph['5']['inputs']['cfg'], profile['cfg'])

    def test_panorama_intermediate_reaches_final_canvas(self):
        graph = build_workflow('fixture.safetensors', 'p', 'n',
                               4544, 1920, 123, profile=PROFILES['sdxl'])
        base = graph['4']['inputs']
        self.assertEqual((base['width'], base['height']), (1136, 480))
        self.assertEqual((base['width'] * 4, base['height'] * 4), (4544, 1920))
        self.assertEqual(graph['7']['inputs']['model_name'],
                         'RealESRGAN_x4plus.pth')

    def test_native_small_target_does_not_add_unneeded_upscale(self):
        graph = build_workflow('fixture.safetensors', 'p', 'n',
                               512, 512, 123, profile=PROFILES['sdxl'])
        self.assertNotIn('7', graph)
        self.assertNotIn('8', graph)
        self.assertNotIn('10', graph)
        self.assertEqual(graph['9']['inputs']['images'], ['6', 0])
