"""Run ephemeral integration tests without changing any desktop service."""
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
os.chdir(root)
(root/'artifacts').mkdir(exist_ok=True)
p=subprocess.run(['python3','-m','unittest','discover','-s','tests','-v'],capture_output=True,text=True)
(root/'artifacts/test-results.log').write_text(p.stdout+p.stderr)
print(p.stdout+p.stderr)
if p.returncode: raise SystemExit(p.returncode)
for command in (['git','diff','--check'],['git','diff','--cached','--check'],
                ['systemd-analyze','--user','verify','systemd/weather-horde-kde.service']):
    subprocess.run(command,check=True)
