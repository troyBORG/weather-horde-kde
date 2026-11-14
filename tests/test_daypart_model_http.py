"""Mock Comfy HTTP integration: real transport, graphs and synthetic PNG receipts."""
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
from model_catalog import PROFILES
from weather_controller import Controller
from test_night_realism import preview, LOCATION


class DaypartHttp(unittest.TestCase):
    @patch('comfy_preview.listener_identity', return_value=(123,1000,1))
    def test_manual_independent_and_panorama_then_fresh_day_batch(self, _identity):
        graphs=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def reply(self,data):
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(data).encode())
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                graphs.append(body['prompt']); self.reply({'prompt_id':str(len(graphs))})
            def do_GET(self):
                if self.path.startswith('/object_info/'):
                    name=self.path.rsplit('/',1)[1]
                    if name=='CheckpointLoaderSimple':
                        self.reply({name:{'input':{'required':{'ckpt_name':[['day','night']]}},'output':['MODEL','CLIP','VAE']}}); return
                    inputs={'UpscaleModelLoader':{'model_name':[['RealESRGAN_x4plus.pth']]},'ImageUpscaleWithModel':{'image':['IMAGE'],'upscale_model':['UPSCALE_MODEL']},'ImageScale':{'image':['IMAGE'],'upscale_method':[['lanczos']],'crop':[['disabled']],'width':['INT',{'min':0,'max':16384}],'height':['INT',{'min':0,'max':16384}]}}
                    self.reply({name:{'input':{'required':inputs[name]}}})
                elif self.path=='/queue': self.reply({'queue_running':[],'queue_pending':[]})
                elif self.path.startswith('/history/'):
                    job=self.path.rsplit('/',1)[1]
                    self.reply({job:{'status':{'completed':True,'status_str':'success'},'outputs':{'9':{'images':[{'filename':'fixture.png','type':'output'}]}}}})
                else:
                    size=graphs[-1].get('10',graphs[-1]['4'])['inputs']; raw=io.BytesIO()
                    Image.new('RGB',(size['width'],size['height']),'navy').save(raw,'PNG')
                    self.send_response(200); self.send_header('Content-Type','image/png');self.end_headers();self.wfile.write(raw.getvalue())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever);worker.start()
        try:
            for panorama in (False,True):
                base=preview();base['weather_evidence']['daypart']='night'
                with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview',return_value=base):
                    t=ComfyTransport(f'http://127.0.0.1:{server.server_port}')
                    c=Controller(d,checkpoint='manual',transport=t,render_guard=lambda:'safe',poll_seconds=.01)
                    c.settings.update(location=LOCATION,connected_panorama=panorama)
                    c.settings['model_policy'].update(mode='lighting',day=['day'],night=['night'])
                    c.models=[dict(id='day',**PROFILES['sd15']),dict(id='night',**PROFILES['sdxl'])]
                    c.refresh_models=lambda:c.models;c.enforce_models=True
                    c.displays=[{'id':'LEFT','width':64,'height':128,'x':0,'y':0,'scale':1,'rotation':0},{'id':'RIGHT','width':128,'height':64,'x':64,'y':0,'scale':1,'rotation':0}]
                    c.guard={'decision':'safe','observed_at':time.time(),'total_mib':24576,'free_mib':24000}
                    before=len(graphs)
                    self.assertEqual(c.dispatch('POST','/v1/render',{'target':'all'})['state'],'queued')
                    c.render_thread.join(5); self.assertFalse(c.render_thread.is_alive())
                    self.assertEqual(c.state,'image_preview_ready',c.last_error)
                    self.assertEqual(len(graphs)-before,1 if panorama else 2)
                    self.assertEqual({g['1']['inputs']['ckpt_name'] for g in graphs[before:]},{'night'})
                    for receipt in c.previews_by_target.values():
                        self.assertEqual(receipt['scene']['checkpoint'],'night')
                        self.assertEqual(receipt['scene']['model_selection']['daypart'],'night')
                    base['weather_evidence']['daypart']='daytime';before=len(graphs)
                    c.dispatch('POST','/v1/render',{'target':'all'});c.render_thread.join(5)
                    self.assertEqual(c.state,'image_preview_ready',c.last_error)
                    self.assertEqual({g['1']['inputs']['ckpt_name'] for g in graphs[before:]},{'day'})
                    self.assertEqual(c.checkpoint,'manual')
        finally: server.shutdown();server.server_close();worker.join()
