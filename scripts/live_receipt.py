"""Read-only live status + transient ZIP lookup; no confirmation, GPU, or apply."""
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene import weather_preview

root=Path(__file__).resolve().parents[1]
token=(Path.home()/'.local/state/weather-horde-kde-preview/token').read_text().strip()
def request(path,method='GET',body=None):
    r=Request('http://127.0.0.1:8734'+path,method=method,
              headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},
              data=None if body is None else json.dumps(body).encode())
    with urlopen(r,timeout=40) as response: return json.load(response)
status=request('/v1/status')
assert status['apply_enabled'] is False and status['render_enabled'] is False
assert status['automation_enabled'] is False and status['location'] is None
lookup=request('/v1/location/lookup','POST',{'zip':'52742'})
candidate=lookup['candidates'][0]
# A provider preview of the suggestion does NOT save it as the user's location.
preview=weather_preview(candidate)
status_after=request('/v1/status')
assert status_after['location'] is None
receipt={'status_url':'http://127.0.0.1:8734/v1/status','authenticated':True,
         'status':status_after,'zip_lookup':{k:v for k,v in candidate.items() if k!='confirmation_id'},
         'live_weather_preview':preview,
         'listener':subprocess.check_output(['ss','-ltnp','sport = :8734'],text=True),
         'service':subprocess.check_output(['systemctl','--user','show','weather-horde-preview.service','-p','ActiveState','-p','SubState','-p','MainPID'],text=True)}
(root/'artifacts/live-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
