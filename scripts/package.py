"""Build and validate package in an isolated root, never install into live Plasma."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

root=Path(__file__).resolve().parents[1]
artifacts=root/'artifacts'
artifacts.mkdir(exist_ok=True)
package=root/'plasma-widget/org.troyborg.weatherhorde'
# Build only the narrow same-user QML plugin with the installed Qt toolchain.
build=artifacts/'native-pairing'
subprocess.run(['cmake','-S',str(root/'native-pairing'),'-B',str(build)],check=True)
subprocess.run(['cmake','--build',str(build)],check=True)
subprocess.run([str(build/'pairing-test')],check=True)
archive=artifacts/'org.troyborg.weatherhorde.plasmoid'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for file in sorted(package.rglob('*')):
        if file.is_file(): z.write(file,file.relative_to(package))
# kpackagetool6 upgrade discovery may ignore an isolated packageroot. Always
# validate in a fresh project-local root; retain previous staged packages.
import tempfile
validation=Path(tempfile.mkdtemp(prefix='package-root-',dir=artifacts))
operation='--install'
command=['kpackagetool6','--type','Plasma/Applet','--packageroot',str(validation),operation,str(archive)]
p=subprocess.run(command,capture_output=True,text=True,check=True)
receipt={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
         'validation_root':str(validation),'command':command,'output':p.stdout+p.stderr,'live_plasma_installed':False}
for file in package.rglob('*'):
    if file.is_file():
        target=validation/package.name/file.relative_to(package)
        assert target.read_bytes()==file.read_bytes(),target
receipt['readback_matches_source']=True
(artifacts/'package-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
