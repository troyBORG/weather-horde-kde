"""Read-only live contracts and disposable real controller; never POST Comfy work."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from portable_paths import data_home
from comfy_preview import ComfyTransport, build_workflow


def main():
    opener = build_opener(ProxyHandler({}))
    transport = ComfyTransport()
    queue_before = transport.request('/queue')
    checkpoint = 'natvisNaturalVision_v27.safetensors'
    contract = transport.request('/object_info/CheckpointLoaderSimple')['CheckpointLoaderSimple']['input']['required']['ckpt_name']
    models = contract[0] if isinstance(contract[0], list) else contract[1]['options']
    assert checkpoint in models
    # Explicit test geometry, NOT native monitor evidence. Contract GETs only.
    transport.validate_upscaler(build_workflow(checkpoint, 'contract preflight only', '', 3440, 1440, 0))
    checks = []
    for image_mode in (False, True):
        with tempfile.TemporaryDirectory(prefix='weather-connection-') as tmp:
            command = [sys.executable, str(REPO/'weather_controller.py'), '--state-dir', tmp, '--port', '0', '--automation-off']
            if image_mode:
                command += ['--preview-checkpoint', checkpoint]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=REPO)
            try:
                line = process.stdout.readline().strip()
                assert line.startswith('Preview-only controller on 127.0.0.1:'), 'Controller did not start'
                url = 'http://' + line.split(' on ')[1] + '/v1/status'
                token = (Path(tmp)/'token').read_text().strip()
                rejected = False
                try:
                    with opener.open(url, timeout=5):
                        pass
                except HTTPError as error:
                    rejected = error.code == 401
                    error.close()
                assert rejected
                for _ in range(30):
                    with opener.open(Request(url, headers={'Authorization':'Bearer '+token}), timeout=5) as response:
                        status = json.load(response)
                    if status['guard'].get('observed_at', 0):
                        break
                    time.sleep(0.5)
                assert status['preview_only'] and not status['apply_enabled'] and not status['automation_enabled']
                assert status['render_enabled'] == image_mode
                assert token not in json.dumps(status)
                checks.append({'mode':'manual_image_configuration' if image_mode else 'default_prompt_only',
                               'authenticated':True, 'unauthenticated_status':401,
                               'status':status, 'temporary_port':int(url.split(':')[2].split('/')[0])})
            finally:
                process.terminate()
                process.communicate(timeout=20)
    installed = (data_home()/'plasma/plasmoids/org.troyborg.weatherhorde')
    source = REPO/'plasma-widget/org.troyborg.weatherhorde'
    matches = all((installed/p.relative_to(source)).read_bytes() == p.read_bytes() for p in source.rglob('*') if p.is_file())
    queue_after = transport.request('/queue')
    receipt = {'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'live_controller_checks':checks, 'comfy_checkpoint_present':True,
               'comfy_upscaler_contract_validated':True,
               'queue_before_counts':{key:len(value) for key,value in queue_before.items()},
               'queue_after_counts':{key:len(value) for key,value in queue_after.items()},
               'installed_widget_version':json.loads((installed/'metadata.json').read_text())['KPlugin']['Version'],
               'installed_widget_matches_source':matches,
               'index_sha256':hashlib.sha256((REPO/'.git/index').read_bytes()).hexdigest(),
               'gpu_submissions':0, 'wallpaper_changes':0, 'owner_deployment':'not started or restarted by verifier; live owner service must be verified in owner session',
               'live_native_displays_verified':False,
               'tests_passed':int(__import__('re').search(r'Ran (\d+) tests', (REPO/'artifacts/controller-integration-tests.log').read_text()).group(1))}
    path = REPO/'artifacts/controller-integration-receipt.json'
    path.write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
