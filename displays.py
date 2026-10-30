"""Live kscreen JSON only. Saved output configuration is NOT live evidence."""
import json
import math
import os
from pathlib import Path
import subprocess


def base_size(width, height, budget=1500000):
    if width*height <= budget and width % 8 == 0 and height % 8 == 0:
        return width, height
    # Exact aspect ratio and multiples of eight, not independent rounding.
    gcd = math.gcd(width, height)
    a, b = width//gcd, height//gcd
    step = math.lcm(8//math.gcd(a,8), 8//math.gcd(b,8))
    multiplier = min(gcd, math.isqrt(budget//(a*b)))//step*step
    if multiplier < 1: raise ValueError('No exact-aspect base fits budget')
    return a*multiplier, b*multiplier


def parse_outputs(payload):
    result = []
    for o in payload['outputs']:
        if o['connected'] is not True or o['enabled'] is not True: continue
        mode = next(m for m in o['modes'] if str(m['id']) == str(o['currentModeId']))
        w, h = mode['size']['width'], mode['size']['height']
        if any(type(v) is not int or not 64 <= v <= 16384 for v in (w,h)):
            raise ValueError('Invalid physical mode')
        rotation = o['rotation']
        if rotation not in (1,2,4,8): raise ValueError('Unknown rotation')
        if rotation in (2,8): w,h = h,w
        scale = o['scale']
        if type(scale) not in (int,float) or not math.isfinite(scale) or not .5 <= scale <= 4:
            raise ValueError('Invalid scale')
        bw,bh = base_size(w,h)
        result.append({'id':o['name'], 'connector':o['name'],
                       'x':o.get('pos',{}).get('x'), 'y':o.get('pos',{}).get('y'), 'width':w, 'height':h,
                       'effective_width':w, 'effective_height':h, 'scale':scale,
                       'orientation':'portrait' if h>w else 'landscape', 'primary':o.get('priority')==1,
                       'base_width':bw, 'base_height':bh, 'needs_upscale':(bw,bh)!=(w,h)})
    if not result or len({x['id'] for x in result}) != len(result):
        raise ValueError('No unique active displays')
    return result


def discover(env=None):
    env = os.environ if env is None else env
    try:
        runtime = env.get('XDG_RUNTIME_DIR', '')
        wayland = env.get('WAYLAND_DISPLAY', '')
        if (env.get('XDG_SESSION_TYPE') != 'wayland' or not runtime or not wayland
                or not env.get('DBUS_SESSION_BUS_ADDRESS')
                or Path(runtime).stat().st_uid != os.getuid()
                or not (Path(runtime)/wayland).is_socket()):
            return [], 'Run controller in the owning graphical Wayland session; no history fallback'
        result = subprocess.run(['kscreen-doctor', '-j'], env=dict(env), capture_output=True,
                                text=True, check=True, timeout=5)
        return parse_outputs(json.loads(result.stdout)), ''
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
        return [], 'Live graphical display detection unavailable or malformed'
