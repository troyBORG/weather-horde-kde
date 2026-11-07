"""Configured Comfy checkpoint inventory; headers only, never torch or weights.
Structural compatibility is not provenance or an image-quality guarantee. Family
metadata can withhold known specialized models, but cannot authenticate training.
"""
import json
import math
import os
import re
import stat
import struct
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from portable_paths import comfy_root
COMFY = comfy_root()
MAX_HEADER = 8*1024*1024
MAX_INVENTORY = 1024*1024
PROFILES = {
    'sd15':dict(architecture='sd15',native_resolution=512,max_pixels=393216,steps=24,cfg=6.0),
    'sdxl':dict(architecture='sdxl',native_resolution=1024,max_pixels=1048576,steps=28,cfg=5.5),
}


class Catalog(list):
    def __init__(self):
        super().__init__()
        self.excluded = []


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Malformed header: duplicate key')
        result[key] = value
    return result


def _open_regular(path):
    """No-follow descriptor walk: reject swapped symlink ancestors and FIFOs."""
    path = Path(path).absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = new
        result = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        if not stat.S_ISREG(os.fstat(result).st_mode):
            os.close(result)
            raise ValueError('Unsafe model path: regular file required')
        return os.fdopen(result, 'rb')
    finally:
        os.close(fd)


def inspect_model(path):
    path = Path(path)
    if path.suffix.lower() != '.safetensors':
        raise ValueError('Unsupported format: safetensors required; pickle is never loaded')
    try:
        with _open_regular(path) as stream:
            size = os.fstat(stream.fileno()).st_size
            raw = stream.read(8)
            if len(raw) != 8: raise ValueError('Malformed header: missing length')
            length = struct.unpack('<Q', raw)[0]
            if not 2 <= length <= MAX_HEADER or length > size-8:
                raise ValueError('Malformed header: oversized or truncated')
            header = json.loads(stream.read(length), object_pairs_hook=_unique)
        if not isinstance(header, dict): raise ValueError('Malformed header: object required')
        metadata = header.get('__metadata__', {})
        if not isinstance(metadata, dict) or any(not isinstance(v,str) for v in metadata.values()):
            raise ValueError('Malformed header: invalid metadata')
        spans = []
        sizes = {'F64':8,'F32':4,'F16':2,'BF16':2,'I64':8,'I32':4,'I16':2,'I8':1,'U8':1,'BOOL':1,'F8_E4M3':1,'F8_E5M2':1}
        for key, value in header.items():
            if key == '__metadata__': continue
            if not isinstance(value,dict): raise ValueError('Malformed tensor header')
            shape = value.get('shape'); offsets = value.get('data_offsets'); dtype = value.get('dtype')
            if (not isinstance(shape,list) or len(shape)>8 or
                any(type(n) is not int or not 0<=n<=2**32 for n in shape) or
                not isinstance(offsets,list) or len(offsets)!=2 or
                any(type(n) is not int for n in offsets) or not isinstance(dtype,str) or dtype not in sizes):
                raise ValueError('Malformed tensor header: shape, dtype or offsets')
            start, end = offsets
            if not 0 <= start <= end <= size-8-length or end-start != math.prod(shape)*sizes[dtype]:
                raise ValueError('Malformed tensor header: data bounds')
            spans.append((start,end))
        end = 0
        for start, stop in sorted(spans):
            if start != end: raise ValueError('Malformed tensor header: overlapping or gapped data')
            end = stop
        if end != size-8-length: raise ValueError('Malformed tensor header: trailing data')
        prefix='model.diffusion_model.'
        if header.get(prefix+'input_blocks.0.0.weight',{}).get('shape') != [320,4,3,3]:
            raise ValueError('Unsupported architecture: expected SD 1.5 / SDXL four-channel UNet')
        if header.get('first_stage_model.decoder.conv_out.weight',{}).get('shape') != [3,128,3,3]:
            raise ValueError('Compatible embedded VAE required')
        contexts={v['shape'][-1] for k,v in header.items() if k.startswith(prefix) and k.endswith('attn2.to_k.weight') and len(v['shape'])==2}
        if contexts == {2048} and header.get('conditioner.embedders.1.model.text_projection',{}).get('shape') == [1280,1280]: kind='sdxl'
        elif contexts == {768} and any(k.startswith('cond_stage_model.transformer.text_model.') for k in header): kind='sd15'
        else: raise ValueError('Unsupported conditioning architecture')
        text=json.dumps(metadata).lower()
        if re.search(r'pony|illustrious|noob|flux|z[-_]image|lightning|hyper[-_]sd|turbo|(?<![a-z0-9])lcm(?![a-z0-9])', text):
            raise ValueError('Unreviewed specialized prompt/sampling family (declared in metadata)')
        return dict(PROFILES[kind])
    except (json.JSONDecodeError, UnicodeError, RecursionError, struct.error) as exc:
        raise ValueError('Malformed safetensors header') from exc


def catalog(discovered, roots=None):
    result=Catalog()
    trusted = [Path(p).resolve() for p in roots] if roots is not None else None
    for identifier,path in sorted(discovered.items()):
        try:
            name=PurePosixPath(identifier)
            if (not identifier or name.is_absolute() or '..' in name.parts or '\\' in identifier or
                any(ord(c)<32 for c in identifier)):
                raise ValueError('Unsafe checkpoint identifier path')
            # Reject pickle before touching the file.
            if name.suffix.lower() != '.safetensors':
                raise ValueError('Unsupported format: safetensors required; pickle is never loaded')
            resolved=Path(path).resolve(strict=True) if path else None
            if resolved is None or (trusted is not None and not any(resolved.is_relative_to(p) for p in trusted)):
                raise ValueError('Model path outside configured checkpoint directories')
            profile=inspect_model(resolved)
            if re.search(r"pony|illustrious|noob|lightning|hyper[-_]sd|turbo|(?<![a-z0-9])lcm(?![a-z0-9])", identifier.lower()):
                raise ValueError("Unreviewed specialized family: identifier hint, not verified training provenance")
        except (OSError,ValueError,TypeError) as exc:
            reason = str(exc) if isinstance(exc,ValueError) else 'Model path unavailable or unsafe'
            result.excluded.append(dict(id=identifier,reason=reason))
            continue
        result.append(dict(id=identifier,**profile))
    return result


# Run only folder_paths and its extra-path loader in the configured trusted Comfy
# installation. No nodes/main/torch imports, refresh cache in a fresh process.
DISCOVERY_CODE = '''
import sys, importlib.abc, json, pathlib, contextlib, os
class NoGPU(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','tensorflow','jax','nodes'}:
            raise ImportError('GPU/model modules forbidden during discovery')
sys.meta_path.insert(0, NoGPU())
with contextlib.redirect_stdout(sys.stderr):
    import folder_paths, utils.extra_config
    config=pathlib.Path('extra_model_paths.yaml')
    if config.exists(): utils.extra_config.load_extra_path_config(str(config))
    roots=folder_paths.get_folder_paths('checkpoints')
    names=set(); skipped=[]; count=0
    extensions={'.safetensors','.ckpt','.pt','.pt2','.bin','.pth','.pkl','.sft'}
    for configured in roots:
        root=pathlib.Path(configured).resolve()
        if str(root) in {'/','/home','/mnt','/usr','/var','/tmp'}:
            raise ValueError('Checkpoint directory too broad')
        for directory, dirs, files in os.walk(root, followlinks=False):
            count+=1+len(files)
            if count>20000: raise ValueError('Configured inventory exceeds scan bound')
            for name in list(dirs):
                p=pathlib.Path(directory)/name
                if name=='.git': dirs.remove(name)
                elif p.is_symlink():
                    dirs.remove(name)
                    skipped.append({'id':str(p.relative_to(root))+'/', 'reason':'Directory symlink not scanned; configure its target explicitly'})
            for name in files:
                p=pathlib.Path(directory)/name
                if p.suffix.lower() in extensions: names.add(str(p.relative_to(root)))
    files={n:folder_paths.get_full_path('checkpoints',n) for n in sorted(names)}
raw=json.dumps({'roots':roots,'files':files,'skipped':skipped})
if len(raw.encode())>1048576: raise ValueError('Model inventory too large')
print(raw)
'''


def discover_models():
    with tempfile.TemporaryFile() as output:
        try:
            subprocess.run([str(COMFY/'.venv/bin/python'),'-B','-c',DISCOVERY_CODE],cwd=COMFY,
                           env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=output,
                           stderr=subprocess.DEVNULL,timeout=15,check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError('Configured model discovery unavailable; check Comfy path/configuration and scan limits. No service started.') from exc
        if output.tell()>MAX_INVENTORY: raise ValueError('Model catalog too large')
        output.seek(0); inventory=json.load(output)
    result = catalog(inventory['files'],roots=inventory['roots'])
    result.excluded.extend(inventory.get('skipped', []))
    return result
