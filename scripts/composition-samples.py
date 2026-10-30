#!/usr/bin/env python3
"""Regenerate documentation from offline, frozen weather; no network/GPU."""
from datetime import datetime
from pathlib import Path
import json
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scene import weather_preview, compose_for_target

location = dict(zip='52742', town='De Witt', state='Iowa', latitude=41.8267,
                longitude=-90.5237, timezone='America/Chicago')
stamp = datetime(2026,10,29,1,30,tzinfo=ZoneInfo('America/Chicago')).timestamp()
data = {'current':dict(time=stamp,temperature_2m=28,weather_code=3,is_day=0,
                       cloud_cover=100,precipitation=0)}
with patch('scene.time.time', return_value=stamp):
    base = weather_preview(location, lambda _:data, scene_kind='urban')
text = ['# Portrait composition — executed offline prompt samples\n',
        'Regenerate: `python3 scripts/composition-samples.py`. No network, GPU or live weather.\n',
        'Frozen fixture: De Witt, Iowa; 2026-10-29 01:30 America/Chicago; overcast, 28°F, 100% cloud, 0 mm precipitation.\n',
        'Guidance only: normalized fractions are measured down from the top. Generated pixels are not constrained or verified.\n']
for width,height in ((1080,1920),(3440,1440)):
    p = compose_for_target(base,width,height)
    text += [f'## {width}×{height} — {p["composition"]["profile"]}\n',
             '```json\n'+json.dumps(p['composition'],indent=2)+'\n```\n',
             '### Positive\n\n'+p['positive']+'\n',
             '### Negative\n\n'+p['negative']+'\n']
(ROOT/'PORTRAIT-COMPOSITION-SAMPLES.md').write_text('\n'.join(text))
print('Wrote PORTRAIT-COMPOSITION-SAMPLES.md from executed offline prompts')
