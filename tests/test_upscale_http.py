import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from PIL import Image
from comfy_preview import ComfyTransport
from weather_controller import Controller

class UpscaleHttpTests(unittest.TestCase):
    @patch('comfy_preview.listener_identity',return_value=(123,1000,1))
    def test_real_transport_high_resolution_fixture_pipeline_and_missing_model_deferral(self, _identity):
        calls=[]; workflow={}; missing=[False]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def reply(self,data):
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(data).encode())
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(self.path); workflow.clear(); workflow.update(body['prompt'])
                self.reply({'prompt_id':'fixture'})
            def do_GET(self):
                if self.path.startswith('/object_info/'):
                    name=self.path.rsplit('/',1)[1]
                    if name=='CheckpointLoaderSimple':
                        self.reply({name:{'input':{'required':{'ckpt_name':[['approved.safetensors']]}},'output':['MODEL','CLIP','VAE']}})
                        return
                    inputs={'UpscaleModelLoader':{'model_name':['COMBO',{'options':[] if missing[0] else ['RealESRGAN_x2plus.pth']}]},
                      'ImageUpscaleWithModel':{'image':['IMAGE'],'upscale_model':['UPSCALE_MODEL']},
                      'ImageScale':{'image':['IMAGE'],'upscale_method':[['lanczos']],'crop':[['disabled']],'width':['INT',{'min':0,'max':16384}],'height':['INT',{'min':0,'max':16384}]}}
                    self.reply({name:{'input':{'required':inputs[name]}}})
                elif self.path=='/queue': self.reply({'queue_running':[],'queue_pending':[]})
                elif self.path.startswith('/history/'):
                    self.reply({'fixture':{'status':{'completed':True,'status_str':'success'},'outputs':{'9':{'images':[{'filename':'fixture.png','type':'output'}]}}}})
                else:
                    size=workflow['10']['inputs']; raw=io.BytesIO()
                    Image.new('RGB',(size['width'],size['height']),'navy').save(raw,'PNG')
                    self.send_response(200); self.send_header('Content-Type','image/png'); self.end_headers(); self.wfile.write(raw.getvalue())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever); worker.start()
        try:
            from model_catalog import PROFILES
            for w,h,kind in [(3440,1440,'sdxl'),(1080,1920,'sdxl'),(1080,1920,'sd15'),(3440,1440,'sd15')]:
                with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview',return_value={'positive':'CPU FIXTURE','negative':'fixture'}):
                    t=ComfyTransport('http://127.0.0.1:'+str(server.server_port))
                    c=Controller(d,checkpoint='approved.safetensors',transport=t,render_guard=lambda:'safe',poll_seconds=.01)
                    c.settings['location']={'town':'fixture'}; c.displays=[{'id':'FIXTURE','width':w,'height':h}]
                    c.guard={'decision':'safe','observed_at':time.time(),'free_mib':24000}
                    c.models=[dict(id='approved.safetensors',**PROFILES[kind])]
                    c.refresh_models=lambda:c.models
                    c.enforce_models=True
                    c.dispatch('POST','/v1/render',{'force':True}); c.render_thread.join(5)
                    self.assertFalse(c.render_thread.is_alive())
                    self.assertEqual(c.state,'image_preview_ready',c.last_error)
                    self.assertEqual((c.image_preview['width'],c.image_preview['height']),(w,h))
                    self.assertLessEqual(workflow['4']['inputs']['width']*workflow['4']['inputs']['height'],PROFILES[kind]['max_pixels'])
                    self.assertEqual(workflow['5']['inputs']['cfg'],PROFILES[kind]['cfg'])
            missing[0]=True; before=len(calls)
            from comfy_preview import build_workflow, SubmissionDeferred
            with self.assertRaises(SubmissionDeferred):
                t.queue(build_workflow('approved.safetensors','fixture','fixture',3440,1440,1))
            self.assertEqual(len(calls),before)
            self.assertFalse(t.uncertain)
        finally: server.shutdown(); server.server_close(); worker.join()
