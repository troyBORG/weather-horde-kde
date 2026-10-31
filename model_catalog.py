"""Offline Comfy folder_paths discovery, bounded safetensors header inspection.
No model deserialization, GPU initialization, model downloads or HTTP endpoints.
Only this reviewed photo-workflow subset is offered; architecture is checked
from tensor shapes, never inferred from the filename. Unknown/ckpt withheld.
"""
import json, os, struct, subprocess
from pathlib import Path

from portable_paths import comfy_root
COMFY = comfy_root()
REVIEWED = {'natvisNaturalVision_v27.safetensors','absolutereality.safetensors',
            'juggernautXL_ragnarokBy.safetensors','albedobaseXL_V31Large.safetensors','sd_xl_base_1.0.safetensors'}
PROFILES = {
    'sd15':dict(architecture='sd15',native_resolution=512,max_pixels=393216,min_free_mib=11264,steps=24,cfg=6.0),
    'sdxl':dict(architecture='sdxl',native_resolution=1024,max_pixels=1048576,min_free_mib=12288,steps=28,cfg=5.5),
}


def inspect_model(path):
    path=Path(path)
    if path.suffix != '.safetensors': raise ValueError('Only safe tensor headers reviewed; no pickle loading')
    with path.open('rb') as stream:
        length=struct.unpack('<Q',stream.read(8))[0]
        if not 2 <= length <= 8*1024*1024: raise ValueError('Unbounded model header')
        header=json.loads(stream.read(length))
    metadata=str(header.get('__metadata__',{})).lower()
    if any(word in metadata for word in ('pony','illustrious','flux','z-image','z_image')): raise ValueError('Unreviewed model family')
    prefix='model.diffusion_model.'
    if header.get(prefix+'input_blocks.0.0.weight',{}).get('shape') != [320,4,3,3]: raise ValueError('Unsupported UNet')
    if 'first_stage_model.decoder.conv_out.weight' not in header: raise ValueError('Embedded VAE required')
    contexts={value['shape'][-1] for key,value in header.items() if key.startswith(prefix) and key.endswith('attn2.to_k.weight')}
    if contexts == {2048} and 'conditioner.embedders.1.model.text_projection' in header: kind='sdxl'
    elif contexts == {768} and any(k.startswith('cond_stage_model.transformer.text_model.') for k in header): kind='sd15'
    else: raise ValueError('Unsupported conditioning architecture')
    return dict(PROFILES[kind])


def catalog(discovered):
    result=[]
    for identifier,path in sorted(discovered.items()):
        if identifier not in REVIEWED: continue
        try: profile=inspect_model(path)
        except (OSError,ValueError,KeyError,TypeError,struct.error): continue
        result.append(dict(id=identifier,**profile))
    return result


def discover_models():
    code='import folder_paths,utils.extra_config,json; utils.extra_config.load_extra_path_config("extra_model_paths.yaml"); print(json.dumps({n:folder_paths.get_full_path("checkpoints",n) for n in folder_paths.get_filename_list("checkpoints")}))'
    proc=subprocess.run([str(COMFY/'.venv/bin/python'),'-c',code],cwd=COMFY,
                        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=15,check=True)
    if len(proc.stdout)>1024*1024: raise ValueError('Model catalog too large')
    return catalog(json.loads(proc.stdout))
