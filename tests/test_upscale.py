import io
import tempfile
import unittest
from PIL import Image
from comfy_preview import build_workflow, PreviewStore
from displays import parse_outputs


class UpscaleTests(unittest.TestCase):
    def test_native_targets_exact_aspect_bounded_latent_and_validated_output(self):
        outputs = []
        for name, w, h, rotation, scale in [('wide',3440,1440,1,1.25),('portrait',1920,1080,2,1.5)]:
            outputs.append(dict(name=name, connected=True, enabled=True, currentModeId='0', rotation=rotation, scale=scale,
                                modes=[{'id':'0','size':{'width':w,'height':h}}]))
        targets = parse_outputs({'outputs':outputs})
        self.assertEqual([(t['width'],t['height']) for t in targets],[(3440,1440),(1080,1920)])
        for target in targets:
            w,h=target['width'],target['height']
            flow=build_workflow('approved.safetensors','fixture','fixture',w,h,42)
            base=flow['4']['inputs']; bw,bh=base['width'],base['height']
            self.assertLessEqual(bw*bh,1500000)
            self.assertEqual(bw*h,bh*w)
            self.assertEqual((bw%8,bh%8),(0,0))
            self.assertEqual(flow['7']['inputs']['model_name'],'RealESRGAN_x2plus.pth')
            self.assertEqual(flow['8']['class_type'],'ImageUpscaleWithModel')
            final=flow['10']['inputs']
            self.assertEqual((final['width'],final['height']),(w,h))
            self.assertEqual(final['crop'],'disabled')
            self.assertEqual(flow['9']['inputs']['images'],['10',0])
            raw=io.BytesIO(); Image.new('RGB',(w,h),'navy').save(raw,'PNG')
            with tempfile.TemporaryDirectory() as d:
                stored=PreviewStore(d).save(raw.getvalue(),(w,h),{'fixture':True})
                self.assertEqual((stored['width'],stored['height']),(w,h))

    def test_impossible_or_oversize_geometry_rejected_before_submission(self):
        for size in [(16384,16384),(3441,1440),(True,128),(0,128)]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                build_workflow('approved.safetensors','p','n',*size,42)
