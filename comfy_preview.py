"""Local ComfyUI preview transport. Never applies wallpaper or interrupts jobs.

Standard Comfy nodes, explicitly selected existing checkpoint, exact-aspect
bounded latent geometry and reviewed existing RealESRGAN 2x + Lanczos resize.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import urllib.parse
import urllib.request
from PIL import Image
from gpu_identity import listener_identity

MAX_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 1500000  # latent budget
MAX_FINAL_PIXELS = 9000000
UPSCALE_MODEL = 'RealESRGAN_x2plus.pth'  # existing local model, no download
from displays import base_size


def build_workflow(checkpoint, positive, negative, width, height, seed, profile=None):
    if not isinstance(checkpoint, str) or not checkpoint or len(checkpoint) > 512:
        raise ValueError('Select an existing checkpoint locally')
    if any(type(x) is not int or not 64 <= x <= 16384 for x in (width, height)) or width*height > MAX_FINAL_PIXELS:
        raise ValueError('Native target exceeds validated output budget')
    bw, bh = base_size(width, height, profile['max_pixels'] if profile else MAX_PIXELS)
    if min(bw,bh) < 64 or (not profile and (width > bw*2 or height > bh*2)):
        raise ValueError('Exact-aspect base cannot reach native size with reviewed 2x upscale')
    workflow = {
        '1': {'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':checkpoint}},
        '2': {'class_type':'CLIPTextEncode','inputs':{'text':positive,'clip':['1',1]}},
        '3': {'class_type':'CLIPTextEncode','inputs':{'text':negative,'clip':['1',1]}},
        '4': {'class_type':'EmptyLatentImage','inputs':{'width':bw,'height':bh,'batch_size':1}},
        '5': {'class_type':'KSampler','inputs':{'seed':seed,'steps':20,'cfg':7.0,'sampler_name':'euler','scheduler':'normal','denoise':1.0,'model':['1',0],'positive':['2',0],'negative':['3',0],'latent_image':['4',0]}},
        '6': {'class_type':'VAEDecode','inputs':{'samples':['5',0],'vae':['1',2]}},
        '9': {'class_type':'SaveImage','inputs':{'images':['6',0],'filename_prefix':'weather-preview/'+secrets.token_hex(12)}}
    }

    if profile:
        workflow['5']['inputs'].update(steps=profile['steps'], cfg=profile['cfg'])
    if (bw,bh) != (width,height):
        workflow.update({
            '7': {'class_type':'UpscaleModelLoader','inputs':{'model_name':UPSCALE_MODEL}},
            '8': {'class_type':'ImageUpscaleWithModel','inputs':{'upscale_model':['7',0],'image':['6',0]}},
            '10': {'class_type':'ImageScale','inputs':{'image':['8',0],'upscale_method':'lanczos','width':width,'height':height,'crop':'disabled'}}
        })
        workflow['9']['inputs']['images'] = ['10',0]
    return workflow


class SubmissionDeferred(ValueError):
    """Proven no POST occurred; safe to release single-flight ownership."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Comfy redirects forbidden')


class ComfyTransport:
    def __init__(self, base='http://127.0.0.1:8188', guard=None):
        self.guard = guard
        url = urllib.parse.urlsplit(base)
        if (url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port
                or url.username or url.password or url.path or url.query or url.fragment):
            raise ValueError('Comfy URL must be literal loopback HTTP with a port')
        self.base = base
        self.client_id = secrets.token_hex(16)
        self.owned = set()
        self.active_job = None
        self.listener = None
        self.owned_gpu_active = False
        self.lock = threading.Lock()
        self.uncertain = False
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def owned_gpu_pid(self):
        """Verify same-UID socket owner + process birth + exclusive queue/client.

        Empty idle queue permits identifying the server, NOT subtracting load.
        Missing visibility, server restart or foreign jobs revokes attribution.
        """
        self.owned_gpu_active = False
        try:
            identity = listener_identity(urllib.parse.urlsplit(self.base).port)
            if identity is None or (self.listener is not None and identity != self.listener): return None
            queue = self.request('/queue')
            rows = queue['queue_running'] + queue['queue_pending']
            if rows:
                if len(rows) != 1: return None
                row = rows[0]
                if (row[1] != self.active_job or row[1] not in self.owned
                        or row[3].get('client_id') != self.client_id): return None
                self.owned_gpu_active = bool(queue['queue_running'])
            self.listener = identity
            return identity[0]
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError): return None

    def request(self, path, body=None, image=False):
        req = urllib.request.Request(self.base+path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type':'application/json'})
        with self.opener.open(req, timeout=15) as r:
            limit = MAX_BYTES if image else 4*1024*1024
            raw = r.read(limit+1)
            if len(raw) > limit: raise ValueError('Comfy response too large')
            if image:
                if r.headers.get_content_type() not in ('image/png','image/jpeg','image/webp'):
                    raise ValueError('Comfy output is not a supported image')
                return raw
            return json.loads(raw)

    def validate_checkpoint(self, identifier):
        try:
            node=self.request('/object_info/CheckpointLoaderSimple')['CheckpointLoaderSimple']
            option=node['input']['required']['ckpt_name']
            names=option[0] if isinstance(option[0],list) else option[1]['options']
            if identifier not in names or node['output'][:3] != ['MODEL','CLIP','VAE']:
                raise ValueError('Checkpoint missing or loader contract changed')
        except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
            raise SubmissionDeferred('Checkpoint preflight failed; no submission: '+str(exc)) from exc

    def validate_upscaler(self, workflow):
        if '7' not in workflow: return
        try:
            contracts = {}
            for name in ('UpscaleModelLoader','ImageUpscaleWithModel','ImageScale'):
                contracts[name] = self.request('/object_info/'+name)[name]['input']['required']
            option = contracts['UpscaleModelLoader']['model_name']
            models = option[0] if isinstance(option[0],list) else option[1]['options']
            if UPSCALE_MODEL not in models: raise ValueError('Reviewed existing upscaler missing')
            model = contracts['ImageUpscaleWithModel']
            if model['image'][0] != 'IMAGE' or model['upscale_model'][0] != 'UPSCALE_MODEL': raise ValueError('Model node contract changed')
            scale = contracts['ImageScale']
            if scale['image'][0] != 'IMAGE' or 'lanczos' not in scale['upscale_method'][0] or 'disabled' not in scale['crop'][0]:
                raise ValueError('Exact resize contract changed')
            for axis in ('width','height'):
                value = workflow['10']['inputs'][axis]
                if scale[axis][0] != 'INT' or not scale[axis][1]['min'] <= value <= scale[axis][1]['max']:
                    raise ValueError('Exact resize range changed')
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            raise SubmissionDeferred('Upscale preflight failed; no submission: '+str(error)) from error

    def queue(self, workflow):
        with self.lock:
            if self.uncertain: raise ValueError('Ambiguous submission; reconcile Comfy queue before restarting controller')
            self.validate_upscaler(workflow)
            queue = self.request('/queue')
            if queue['queue_running'] or queue['queue_pending']:
                raise SubmissionDeferred('Comfy queue busy; no submission')
            # Never retry a POST: an HTTP timeout may mean Comfy accepted it.
            if self.guard is not None and self.guard() != 'safe':
                raise SubmissionDeferred('Activity guard blocked submission')
            identity = listener_identity(urllib.parse.urlsplit(self.base).port)
            if identity is None or (self.listener is not None and identity != self.listener):
                raise SubmissionDeferred('Unverified same-owner Comfy listener; no submission')
            self.listener = identity
            if self.guard is not None and self.guard() != 'safe':
                raise SubmissionDeferred('Guard/consent expired before submission')
            self.uncertain = True
            response = self.request('/prompt', {'prompt':workflow,'client_id':self.client_id})
            job = response.get('prompt_id')
            if not isinstance(job,str) or not job or response.get('node_errors'):
                raise ValueError('Comfy rejected workflow or returned ambiguous job ID')
            self.owned.add(job)
            self.active_job = job
            self.uncertain = False
            return job

    def require_owned(self, job):
        if job not in self.owned: raise ValueError('Job is not owned by this controller')

    def history(self, job):
        self.require_owned(job)
        return self.request('/history/'+urllib.parse.quote(job,safe='')).get(job)

    def inspect(self, job):
        history = self.history(job)
        if history:
            status = history.get('status',{})
            if status.get('status_str') == 'error': return 'failed'
            if status.get('completed') is True and status.get('status_str') == 'success': return 'complete'
        queue = self.request('/queue')
        if any(row[1] == job for row in queue['queue_running']): return 'running'
        if any(row[1] == job for row in queue['queue_pending']): return 'pending'
        return 'unknown'

    def cancel_pending(self, job):
        self.require_owned(job)
        queue = self.request('/queue')
        if any(row[1] == job for row in queue['queue_pending']):
            self.request('/queue', {'delete':[job]})
        # A pending-to-running race cannot interrupt running work. Caller must
        # continue tracking ownership, not assume cancellation from HTTP success.

    def image(self, job):
        history = self.history(job)
        if not history or history.get('status',{}).get('status_str') != 'success' or history['status'].get('completed') is not True:
            raise ValueError('Image not complete')
        images = history.get('outputs',{}).get('9',{}).get('images',[])
        if len(images) != 1: raise ValueError('Expected exactly one selected SaveImage output')
        item = images[0]
        filename, subfolder = item['filename'], item.get('subfolder','')
        if (not isinstance(filename,str) or Path(filename).name != filename or '\\' in filename
                or Path(filename).suffix.lower() not in ('.png','.jpg','.jpeg','.webp')
                or not isinstance(subfolder,str) or '..' in Path(subfolder).parts
                or subfolder.startswith('/') or '\\' in subfolder or item.get('type') != 'output'):
            raise ValueError('Invalid Comfy image descriptor')
        return self.request('/view?'+urllib.parse.urlencode({'filename':filename,'subfolder':subfolder,'type':'output'}),image=True)


class PreviewStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)

    def save(self, raw, size, metadata, quarantined=False, guard=None):
        if len(raw) > MAX_BYTES: raise ValueError('Image too large')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.size != tuple(size) or image.width*image.height > MAX_FINAL_PIXELS or getattr(image,'n_frames',1) != 1:
                raise ValueError('Image format, frame count or native dimensions invalid')
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            image = image.convert('RGB')
            full = io.BytesIO(); image.save(full,'PNG')
            image.thumbnail((480,320))
            thumb = io.BytesIO(); image.save(thumb,'PNG')
        quarantined = quarantined or (guard is not None and guard() != 'safe')
        identifier = secrets.token_hex(16)
        temporary = self.root/('.partial-'+identifier)
        final = self.root/identifier
        temporary.mkdir(mode=0o700)
        record = dict(metadata, id=identifier, width=size[0], height=size[1],
                      sha256=hashlib.sha256(full.getvalue()).hexdigest(), quarantined=quarantined,
                      thumbnail='data:image/png;base64,'+base64.b64encode(thumb.getvalue()).decode())
        try:
            for name, content in [('image.png',full.getvalue()),('thumbnail.png',thumb.getvalue()),('metadata.json',json.dumps(record).encode())]:
                with open(temporary/name,'xb') as f:
                    os.chmod(temporary/name,0o600); f.write(content); f.flush(); os.fsync(f.fileno())
            temporary.rename(final)
            if not quarantined:
                pointer = self.root/'latest.tmp'
                pointer.write_text(identifier); pointer.chmod(0o600)
                # Slow image encoding and fsync must not consume the remaining
                # consent window and then publish an expired result.
                if guard is not None and guard() != 'safe':
                    record['quarantined'] = True
                    (final/'metadata.json').write_text(json.dumps(record))
                    pointer.unlink(missing_ok=True)
                else:
                    pointer.replace(self.root/'latest')
        finally:
            if temporary.exists(): shutil.rmtree(temporary)
        return record

    def latest(self):
        try:
            identifier = (self.root/'latest').read_text()
            if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier): return None
            record = json.loads((self.root/identifier/'metadata.json').read_text())
            return None if record.get('quarantined') else record
        except (OSError,ValueError): return None
