#!/usr/bin/env python3
"""Owner-side package install. No controller/Comfy start, stop, or configuration.
--reload explicitly reloads only the Plasma shell UI; applications stay open.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'org.troyborg.weatherhorde'

def verify_release():
    archive = ROOT/'artifacts'/f'{PACKAGE}.plasmoid'
    receipt = json.loads((ROOT/'artifacts/package-receipt.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != receipt['sha256']:
        raise RuntimeError('Release hash differs from the staged validation receipt')
    with zipfile.ZipFile(archive) as z:
        metadata = json.loads(z.read('metadata.json'))
        if (metadata['KPlugin']['Id'] != PACKAGE or metadata['KPlugin']['Version'] != '0.1.10'
                or metadata.get('X-Plasma-API-Minimum-Version') != '6.0'):
            raise RuntimeError('Unexpected package metadata')
        for name in ('libweatherpairing.so', 'libweatherpairingplugin.so', 'qmldir'):
            z.getinfo('contents/ui/WeatherHorde/LocalPairing/'+name)
        for name in z.namelist():
            path=Path(name)
            if path.is_absolute() or '..' in path.parts:
                raise RuntimeError('Unsafe package path')
    print('Release verified: Weather Horde '+metadata['KPlugin']['Version']+'; native helper bundled; '+receipt['sha256'])
    return archive

def install(reload=False):
    if pwd.getpwuid(os.getuid()).pw_name != 'troyborg':
        raise RuntimeError('Run in the troyborg KDE owner terminal, not an SSH account')
    if os.environ.get('XDG_SESSION_TYPE') not in ('wayland','x11') or not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        raise RuntimeError('A real KDE owner graphical session is required')
    archive=verify_release()
    data=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))
    if not data.is_absolute(): raise RuntimeError('XDG_DATA_HOME must be absolute')
    destination=data/'plasma/plasmoids'/PACKAGE
    operation='--upgrade' if destination.exists() else '--install'
    subprocess.run(['kpackagetool6','--type','Plasma/Applet',operation,str(archive)],check=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if (destination/name).read_bytes()!=z.read(name):
                raise RuntimeError('Installed package readback mismatch: '+name)
    print('Installed package readback matches the validated release.')
    if reload:
        subprocess.run(['systemctl','--user','restart','plasma-plasmashell.service'],check=True)
        subprocess.run(['systemctl','--user','is-active','--quiet','plasma-plasmashell.service'],check=True)
        print('Plasma shell UI reloaded. Weather Horde should pair automatically within a few seconds.')
    else:
        print('Log out/in or reload the Plasma shell UI to load this version.')
    print('Controller and Comfy services were NOT restarted or changed. No GPU or wallpaper action was requested.')
    print('Check the widget for “Paired · local controller connected”. An absent controller remains disconnected and retries.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reload',action='store_true',help='Reload only the Plasma shell UI after installation')
    parser.add_argument('--verify-only',action='store_true',help='Validate the artifact without installing or reloading')
    args=parser.parse_args()
    if args.verify_only: verify_release()
    else: install(args.reload)

if __name__=='__main__':
    try: main()
    except (OSError,RuntimeError,ValueError,subprocess.CalledProcessError) as exc:
        print('Installation stopped: '+str(exc),file=sys.stderr)
        sys.exit(1)
