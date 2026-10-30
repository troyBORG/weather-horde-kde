import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
from unittest.mock import patch


class ImagePreviewTests(unittest.TestCase):
    @patch('comfy_preview.listener_identity',return_value=(123,1000,1))
    def test_real_http_transport_to_validated_preview_store(self, _identity):
        from comfy_preview import ComfyTransport, PreviewStore, build_workflow
        image = io.BytesIO(); Image.new('RGB', (64, 128), 'navy').save(image, 'PNG')
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, body))
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"prompt_id":"owned-id"}')
            def do_GET(self):
                calls.append((self.path, None))
                if self.path == '/queue': data = {'queue_running':[], 'queue_pending':[]}
                elif self.path == '/history/owned-id': data = {'owned-id': {'status':{'completed':True,'status_str':'success'},'outputs':{'9':{'images':[{'filename':'preview.png','subfolder':'','type':'output'}]}}}}
                else:
                    self.send_response(200); self.send_header('Content-Type','image/png'); self.end_headers(); self.wfile.write(image.getvalue()); return
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(data).encode())
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            transport = ComfyTransport('http://127.0.0.1:'+str(server.server_port))
            workflow = build_workflow('approved.safetensors', 'weather', 'moon', 64,128,42)
            job = transport.queue(workflow)
            self.assertEqual(transport.inspect(job),'complete')
            raw = transport.image(job)
            with tempfile.TemporaryDirectory() as d:
                result = PreviewStore(d).save(raw, (64,128), {'prompt_id':job})
                self.assertTrue(result['thumbnail'].startswith('data:image/png;base64,'))
                with Image.open(Path(d)/result['id']/'image.png') as decoded:
                    self.assertEqual(decoded.size,(64,128))
                self.assertEqual(json.loads((Path(d)/result['id']/'metadata.json').read_text())['prompt_id'],job)
                self.assertEqual(PreviewStore(d).latest()['id'],result['id'])
            self.assertEqual([p for p,_ in calls if p == '/prompt'],['/prompt'])
            # Full HTTP controller -> real HTTP Comfy adapter -> validated store.
            from weather_controller import Controller, make_server
            from unittest.mock import patch
            import urllib.request
            import time
            with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview',return_value={'positive':'fixture','negative':'moon'}):
                c=Controller(d,checkpoint='approved.safetensors',transport=transport,render_guard=lambda:'safe',poll_seconds=.01)
                c.settings['location']={'town':'fixture'}
                c.displays=[{'id':'FIXTURE','width':64,'height':128}]
                c.guard={'decision':'safe','observed_at':time.time()}
                api=make_server(c,port=0)
                worker=threading.Thread(target=api.serve_forever); worker.start()
                base='http://127.0.0.1:'+str(api.server_port)
                try:
                    req=urllib.request.Request(base+'/v1/render',data=b'{"target":"FIXTURE","force":true}',headers={'Authorization':'Bearer '+c.token,'Content-Type':'application/json'})
                    with urllib.request.urlopen(req) as response: self.assertEqual(json.load(response)['state'],'queued')
                    c.render_thread.join(3)
                    req=urllib.request.Request(base+'/v1/status',headers={'Authorization':'Bearer '+c.token})
                    with urllib.request.urlopen(req) as response: status=json.load(response)
                    self.assertEqual(status['state'],'image_preview_ready')
                    self.assertEqual(status['image_preview']['targets'],['FIXTURE'])
                    self.assertTrue(status['image_preview']['thumbnail'].startswith('data:image/png;base64,'))
                    self.assertFalse(status['apply_enabled'])
                finally: api.shutdown(); api.server_close(); worker.join()
            self.assertFalse(any('/interrupt' in p for p,_ in calls))
        finally: server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__': unittest.main()
