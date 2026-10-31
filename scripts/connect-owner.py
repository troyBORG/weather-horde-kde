#!/usr/bin/env python3
"""Start preview-only Weather Horde in the real Plasma owner's session.
No render requests, wallpaper commands, Comfy restarts or privilege changes.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import pwd
import socket
import subprocess
import time
from urllib.request import Request, build_opener, ProxyHandler

REPO = Path(__file__).resolve().parents[1]
CHECKPOINT = 'natvisNaturalVision_v27.safetensors'
sys.path.insert(0, str(REPO))
from portable_paths import require_owner as require_configured_owner, comfy_root
from displays import discover
from comfy_preview import ComfyTransport, build_workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-previews', action='store_true',
                        help='Explicitly configure guarded manual Comfy previews; not required for pairing')
    parser.add_argument('--manual-pairing', action='store_true',
                        help='Explicit fallback: copy token locally for older widgets')
    args = parser.parse_args()
    require_configured_owner()
    displays, error = discover()
    if error or not displays:
        raise RuntimeError('No live owner-session outputs: ' + (error or 'no active outputs'))
    print('Live native displays: ' + ', '.join(f"{d['id']} {d['width']}x{d['height']} scale={d['scale']}" for d in displays))
    transport = None
    if args.image_previews:
        transport = ComfyTransport()
        contract = transport.request('/object_info/CheckpointLoaderSimple')['CheckpointLoaderSimple']['input']['required']['ckpt_name']
        models = contract[0] if isinstance(contract[0], list) else contract[1]['options']
        if CHECKPOINT not in models:
            raise RuntimeError('Approved checkpoint missing from live ComfyUI.')
        for d in displays:
            workflow = build_workflow(CHECKPOINT, 'preflight only; not submitted', '', d['width'], d['height'], 0)
            transport.validate_upscaler(workflow)
        print('Live ComfyUI checkpoint/upscaler contracts verified read-only. No GPU work submitted.')
    root = Path.home()/'.local/state/weather-horde-kde'
    if (root/'inflight.json').exists():
        raise RuntimeError('Existing unresolved render journal; reconcile its owned job before deployment.')
    unit = 'weather-horde-kde.service'
    state = subprocess.run(['systemctl','--user','is-active',unit], capture_output=True, text=True).stdout.strip()
    existing = state == 'active'
    if state not in ('inactive','unknown','failed','active'):
        raise RuntimeError('Owner controller is transitioning; retry later. State: '+state)
    if not existing:
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1',8734))
            except OSError:
                raise RuntimeError('Port 8734 is occupied; refusing to stop or replace its owner.')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise RuntimeError('Controller state directory must be owned by you and private (0700).')
    command = ['systemd-run','--user','--collect','--unit=weather-horde-kde',
               '--description=Weather Horde guarded image previews (no wallpaper application)',
               '--property=Type=exec','--property=Restart=on-failure','--property=RestartSec=10',
               '--property=NoNewPrivileges=yes','--property=UMask=0077',
               '--property=PartOf=graphical-session.target','--working-directory='+str(REPO)]
    command.append('--setenv=WEATHER_HORDE_COMFY_ROOT='+str(comfy_root()))
    for name in ('WEATHER_HORDE_OWNER','XDG_RUNTIME_DIR','XDG_SESSION_TYPE','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','XDG_CURRENT_DESKTOP'):
        if name in os.environ:
            command.append('--setenv='+name+'='+os.environ[name])
    command += ['/usr/bin/python3',str(REPO/'weather_controller.py'),'--state-dir',str(root),
                '--automation-off']
    if args.image_previews:
        command += ['--preview-checkpoint',CHECKPOINT]
    if not existing:
        subprocess.run(command, check=True)
    opener = build_opener(ProxyHandler({}))
    def request(method='GET', body=None):
        token = (root/'token').read_text().strip()
        req = Request('http://127.0.0.1:8734/v1/'+('status' if method=='GET' else 'settings'),
                      method=method, data=None if body is None else json.dumps(body).encode(),
                      headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with opener.open(req, timeout=5) as response:
            return json.load(response)
    status = None
    for _ in range(25):
        try:
            status = request()
            if status['displays']:
                break
        except (OSError, ValueError):
            pass
        time.sleep(1)
    if not status or not status['displays']:
        raise RuntimeError('Service started but live outputs are not verified; inspect systemctl --user status weather-horde-kde.')
    if not status['preview_only'] or status['apply_enabled']:
        raise RuntimeError('Existing service is not preview-only; refusing to pair.')
    request('PUT', {'automation_enabled': False})
    status = request()
    if not (status['preview_only'] and (existing or status['render_enabled'] == args.image_previews) and not status['apply_enabled'] and not status['automation_enabled']):
        raise RuntimeError('Unexpected live safety configuration; do not use Generate.')
    receipt = {'authenticated_status':status, 'service_started':not existing,
               'checkpoint':CHECKPOINT if args.image_previews and not existing else None,
               'comfy_same_owner_verified':transport.owned_gpu_pid() is not None if transport else None,
               'wallpaper_changed':False,'gpu_submitted':False}
    (root/'connection-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (root/'connection-receipt.json').chmod(0o600)
    print('Owner controller connected; native displays verified; ' +
          ('manual image previews configured; rendering still subject to guards.' if status['render_enabled'] else 'prompt-only mode; GPU rendering disabled.'))
    if existing:
        print('Existing owner service authenticated and retained without restart; startup mode unchanged.')
    if status['render_enabled'] and not args.image_previews:
        print('Existing render configuration was not revalidated; same-owner Comfy and complete activity evidence remain required.')
    print('Preview only. Automation OFF. Wallpaper application unavailable. Guard: '+status['guard']['decision'])
    if args.image_previews and not receipt['comfy_same_owner_verified']:
        print('RENDER BLOCKER: existing ComfyUI is not verifiably owned by this user. It was NOT stopped or migrated. Same-owner Comfy deployment is still required; do not bypass the guard.')
    if args.manual_pairing:
        try:
            subprocess.run(['wl-copy','--type','text/plain'],input=(root/'token').read_bytes(),check=True,timeout=5)
            print('Session token copied locally. Paste into Weather Horde Session token, then click Pair. Do not paste it in chat. Clear your clipboard after pairing.')
        except (OSError, subprocess.SubprocessError):
            print('Clipboard unavailable. Copy the token locally from '+str(root/'token')+' into the widget; never send it in chat.')
    else:
        print('Weather Horde 0.1.4 pairs automatically from your private local token. No clipboard step is needed.')
    print('This owner service runs for this graphical session (not enabled at boot). Receipt: '+str(root/'connection-receipt.json'))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Connection stopped: '+str(exc), file=sys.stderr)
        sys.exit(1)
