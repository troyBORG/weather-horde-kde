#!/usr/bin/env python3
"""Generate immutable owner delivery from clean committed source + built package.
Run only in an isolated build tree. Output must not exist. No deployment occurs.
"""
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile


def build(output):
    root = Path(__file__).resolve().parents[1]
    if output.exists(): raise RuntimeError('Output exists; immutable deliveries are never overwritten')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root).strip():
        raise RuntimeError('Commit reviewed source before packaging')
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    source = subprocess.check_output(['git','archive','HEAD'],cwd=root)
    version = json.loads((root/'plasma-widget/org.troyborg.weatherhorde/metadata.json').read_text())['KPlugin']['Version']
    package = root/'artifacts/org.troyborg.weatherhorde.plasmoid'
    receipt = json.loads((root/'artifacts/package-receipt.json').read_text())
    if hashlib.sha256(package.read_bytes()).hexdigest() != receipt['sha256'] or not receipt['readback_matches_source']:
        raise RuntimeError('Build receipt mismatch')
    output.mkdir(mode=0o700)
    archive = output/'source.tar.gz'
    with tarfile.open(fileobj=io.BytesIO(source)) as original, tarfile.open(archive,'w:gz') as target:
        for member in original:
            if not (member.isfile() or member.isdir()): raise RuntimeError('Unsupported source object')
            member.mode = 0o755 if member.isdir() else 0o644
            member.uid = member.gid = 0; member.uname = member.gname = ''
            target.addfile(member, original.extractfile(member) if member.isfile() else None)
        for path in (package, root/'artifacts/package-receipt.json'):
            data = path.read_bytes(); info = tarfile.TarInfo(str(path.relative_to(root)))
            info.size = len(data); info.mode = 0o644
            target.addfile(info, io.BytesIO(data))
    bootstrap = output/'owner-bootstrap.py'
    bootstrap.write_bytes((root/'scripts/owner-bootstrap.py').read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    boot_digest = hashlib.sha256(bootstrap.read_bytes()).hexdigest()
    name = 'weather-horde-'+version+'-installer-'+revision[:12]
    wrapper = '#!/usr/bin/env bash\nset -euo pipefail\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\n'
    wrapper += "printf '%s  %s\\n' "+shlex.quote(boot_digest)+" owner-bootstrap.py | sha256sum --check --status\n"
    wrapper += 'exec python3 -B ./owner-bootstrap.py --archive ./source.tar.gz --sha256 '+digest+' --version '+shlex.quote(version)+' --candidate-name '+shlex.quote(name)+' "$@"\n'
    (output/'OWNER-DEPLOY.sh').write_text(wrapper)
    (output/'OWNER-DEPLOY.sh').chmod(0o700)
    (output/'delivery.json').write_text(json.dumps({'git_commit':revision,'version':version,'candidate_name':name,'archive_sha256':digest,'bootstrap_sha256':boot_digest},indent=2)+'\n')
    print(output)
    print(digest)


if __name__ == '__main__': build(Path(sys.argv[1]).absolute())
