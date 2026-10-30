import unittest,threading,json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from comfy_preview import ComfyTransport,SubmissionDeferred
class CheckpointContract(unittest.TestCase):
 def test_actual_http_discovery_contract(self):
  self.assertTrue(hasattr(ComfyTransport,'validate_checkpoint'),'live checkpoint contract missing')
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_GET(self):
    data={'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['exact.safetensors']]}},'output':['MODEL','CLIP','VAE']}}
    self.send_response(200);self.end_headers();self.wfile.write(json.dumps(data).encode())
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   t=ComfyTransport(f'http://127.0.0.1:{server.server_port}')
   t.validate_checkpoint('exact.safetensors')
   with self.assertRaises(SubmissionDeferred):t.validate_checkpoint('renamed.safetensors')
  finally:server.shutdown();server.server_close()
