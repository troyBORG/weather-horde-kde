#!/usr/bin/env python3
"""Owner-only DP-2 acceptance and like-for-like transient controller relaunch.
Never applies wallpaper, submits GPU work, or restarts Comfy/Plasma.
Do not use widget actions or change displays/wallpapers during this command.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parents[1]
UNIT='weather-horde-kde.service'
ENV_KEYS=('HOME','PATH','LANG','LC_ALL','XDG_RUNTIME_DIR','XDG_SESSION_TYPE',
          'WAYLAND_DISPLAY','DISPLAY','DBUS_SESSION_BUS_ADDRESS','XDG_CURRENT_DESKTOP',
          'XDG_DATA_DIRS','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','QT_QPA_PLATFORM')


def recover(io):
    original=io.identity()
    io.idle(io.status())
    io.pause()
    io.idle(io.status())
    io.backup(original)
    status=io.status()
    io.idle(status)
    if status.get('automation_enabled') is not False:
        raise RuntimeError('Automation changed during recovery; nothing stopped')
    if io.identity()!=original:
        raise RuntimeError('Controller identity changed; nothing stopped')
    io.stop(original)
    failure=None
    try:
        io.accept()
    except BaseException as exc:
        failure=exc
    finally:
        try:
            io.launch(original)
        except BaseException as restart_error:
            if failure is not None: raise failure from restart_error
            raise
    if failure is not None:
        print('DP-2 acceptance failed; controller relaunched and authenticated with original capabilities. Automation remains OFF.',file=sys.stderr)
        raise failure
    io.verify(original)


def require_idle(status, journal):
    if journal or status.get('state') not in {'idle','preview_ready','image_preview_ready','deferred','failed','quarantined','wallpapers_applied','applied','restored','blocked_preview_only'}:
        raise RuntimeError('Active or unverifiable controller job; retry when idle')


def validate_argv(argv, state):
    if len(argv)<2 or Path(argv[0]).resolve()!=Path('/usr/bin/python3').resolve() or Path(argv[1])!=ROOT/'weather_controller.py':
        raise RuntimeError('Unexpected controller executable')
    flags={'--automation-off','--manual-wallpapers','--managed-comfy'}
    values={'--state-dir','--port','--preview-checkpoint','--comfy-idle-seconds'}
    seen=set();i=2
    while i<len(argv):
        key=argv[i]
        if key in seen or key not in flags|values: raise RuntimeError('Unknown/duplicate controller argument')
        seen.add(key);i+=1
        if key in values:
            if i==len(argv) or argv[i].startswith('--'): raise RuntimeError('Missing controller argument')
            value=argv[i];i+=1
            if key=='--state-dir' and Path(value)!=state: raise RuntimeError('Unexpected state directory')
            if key=='--port' and value!='8734': raise RuntimeError('Unexpected API port')
            if key=='--comfy-idle-seconds' and (not value.isdecimal() or not 30<=int(value)<=86400): raise RuntimeError('Unexpected Comfy timeout')
    return argv


def launch_command(original):
    command=['systemd-run','--user','--collect','--unit=weather-horde-kde','--expand-environment=no',
             '--property=Type=exec','--property=Restart=on-failure','--property=RestartSec=10',
             '--property=UMask=0077','--property=NoNewPrivileges=yes',
             '--property=PartOf=graphical-session.target','--working-directory='+str(ROOT)]
    command += ['--setenv='+k+'='+v for k,v in original['env'].items()]
    command += original['argv']
    if '--automation-off' not in original['argv']: command.append('--automation-off')
    return command


def private_read(path):
    for directory in path.parents:
        st=directory.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid not in (0,os.getuid()) or st.st_mode & 0o022:
            raise RuntimeError('Unsafe private state ancestor')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600 or st.st_nlink!=1:
            raise RuntimeError('Unsafe private state file')
        with os.fdopen(fd,'rb',closefd=False) as stream: return stream.read()
    finally: os.close(fd)


class OwnerIO:
    def __init__(self):
        if pwd.getpwuid(os.getuid()).pw_name!='troyborg':
            raise RuntimeError('Run in troyborg KDE terminal; no cross-user access')
        sys.path.insert(0,str(ROOT))
        self.state=Path.home()/'.local/state/weather-horde-kde'
        self.token=private_read(self.state/'token').decode().strip()
        self.opener=build_opener(ProxyHandler({}))
        from weather_controller import SOURCE_REVISION
        self.revision=SOURCE_REVISION
        spec=importlib.util.spec_from_file_location('rollout',ROOT/'scripts/rollout-owner.py')
        self.rollout=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.rollout)
        from comfy_preview import ComfyTransport
        self.transport=ComfyTransport()

    def api(self, path='/v1/status', body=None):
        req=Request('http://127.0.0.1:8734'+path,method='GET' if body is None else 'PUT',
                    data=None if body is None else json.dumps(body).encode(),
                    headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with self.opener.open(req,timeout=10) as response: return json.load(response)

    def status(self): return self.api()

    def idle(self,status):
        require_idle(status,(self.state/'inflight.json').exists())
        queue=self.rollout.idle_queue(self.transport)
        if queue.get('queue_running')!=[] or queue.get('queue_pending')!=[]:
            raise RuntimeError('Comfy queue busy or unverifiable')

    def pause(self):
        self.api('/v1/settings',{'automation_enabled':False})
        if self.status().get('automation_enabled') is not False: raise RuntimeError('Automation did not pause')

    def properties(self):
        result=subprocess.run(['systemctl','--user','show',UNIT,'--property=LoadState,ActiveState,SubState,MainPID,Transient,ControlGroup'],capture_output=True,text=True,timeout=10)
        props=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        if result.returncode not in (0,1) or not props: raise RuntimeError('Cannot verify owner unit')
        return props

    def identity(self):
        props=self.properties()
        if props.get('Transient')!='yes' or props.get('ActiveState')!='active' or props.get('SubState')!='running':
            raise RuntimeError('Expected running transient owner controller')
        pid=int(props.get('MainPID','0'));process=Path('/proc')/str(pid)
        if pid<=0 or process.stat().st_uid!=os.getuid(): raise RuntimeError('Controller PID owner mismatch')
        argv=[os.fsdecode(x) for x in (process/'cmdline').read_bytes().split(b'\0') if x]
        validate_argv(argv,self.state)
        if (process/'exe').resolve()!=Path(argv[0]).resolve(): raise RuntimeError('Controller executable mismatch')
        if (process/'cwd').resolve()!=ROOT: raise RuntimeError('Unexpected working directory')
        if '0::'+props['ControlGroup'] not in (process/'cgroup').read_text().splitlines(): raise RuntimeError('Controller cgroup mismatch')
        env=dict(os.fsdecode(x).split('=',1) for x in (process/'environ').read_bytes().split(b'\0') if b'=' in x)
        if any(env.get(k) for k in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD','LD_LIBRARY_PATH')):
            raise RuntimeError('Custom interpreter environment requires manual review')
        selected={k:v for k,v in env.items() if k in ENV_KEYS or k in ('PYTHONUNBUFFERED','PYTHONDONTWRITEBYTECODE')}
        for k in ('XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','WAYLAND_DISPLAY'):
            if not selected.get(k) or selected[k]!=os.environ.get(k): raise RuntimeError('Owner graphical session mismatch')
        start=(process/'stat').read_text().rsplit(')',1)[1].split()[19]
        identity={'pid':pid,'start':start,'argv':argv,'env':selected,'cgroup':props['ControlGroup']}
        if self.properties()!=props: raise RuntimeError('Unit changed during inspection')
        return identity

    def backup(self,original):
        # Existing private root only; no permission repairs and no token copy.
        st=self.state.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700:
            raise RuntimeError('State root must be private')
        self.backup_dir=Path(tempfile.mkdtemp(prefix='dp2-recovery-',dir=self.state))
        data={'launch.json':json.dumps(original,indent=2).encode(),
              'journal.json':private_read(self.state/'wallpaper-restore.json')}
        if (self.state/'settings.json').exists(): data['settings.json']=private_read(self.state/'settings.json')
        for name,raw in data.items():
            fd=os.open(self.backup_dir/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
        self.before=json.loads(data['journal.json'])
        if self.before.get('DP-2',{}).get('state')!='pending': raise RuntimeError('No pending DP-2 receipt')

    def stop(self,original):
        if self.identity()!=original: raise RuntimeError('Controller identity changed immediately before stop')
        # Only this exact owner unit; never Comfy, Plasma, process-name kills.
        subprocess.run(['systemctl','--user','stop',UNIT],check=True,timeout=45)

    def absent(self):
        props=self.properties()
        return props.get('LoadState')=='not-found' and props.get('ActiveState')=='inactive'

    def accept(self):
        # Helper independently checks process/listener absence and exclusive lock.
        subprocess.run(['/usr/bin/python3',str(ROOT/'scripts/reconcile-dp2-owner.py'),'--accept-current'],check=True,timeout=60)

    def launch(self,original):
        for _ in range(50):
            if self.absent(): break
            time.sleep(.2)
        else: raise RuntimeError('Old transient unit not collected; refusing replacement')
        subprocess.run(launch_command(original),check=True,timeout=20)
        # Authenticate on failure paths too: restarting means verified running.
        for _ in range(30):
            try:
                status=self.status()
                if status.get('source_revision')==self.revision and status.get('displays'):
                    self.verify_status(original,status)
                    return
            except (OSError,ValueError): pass
            time.sleep(1)
        raise RuntimeError('Relaunched controller did not authenticate expected revision')

    def verify_status(self,original,status):
        argv=original['argv']
        if (status.get('automation_enabled') is not False or status.get('testing_override',{}).get('active') is not False
            or status.get('render_enabled')!=('--preview-checkpoint' in argv)
            or status.get('capabilities',{}).get('manual_apply')!=('--manual-wallpapers' in argv)
            or status.get('comfy_service',{}).get('managed')!=('--managed-comfy' in argv)):
            raise RuntimeError('Relaunched controller capability/safety mismatch')
        current=self.identity()
        expected=argv if '--automation-off' in argv else argv+['--automation-off']
        if current['argv']!=expected or current['env']!=original['env']:
            raise RuntimeError('Relaunched controller launch identity mismatch')
        if private_read(self.state/'token').decode().strip()!=self.token: raise RuntimeError('Token changed')

    def verify(self,original):
        status=self.status()
        if status.get('source_revision')!=self.revision: raise RuntimeError('Revision changed')
        self.verify_status(original,status)
        after=json.loads(private_read(self.state/'wallpaper-restore.json'))
        entry=after.get('DP-2',{})
        if entry.get('state')!='accepted_current' or entry.get('before')!=entry.get('after'):
            raise RuntimeError('DP-2 accepted baseline missing')
        if {k:v for k,v in after.items() if k!='DP-2'}!={k:v for k,v in self.before.items() if k!='DP-2'}:
            raise RuntimeError('Unselected receipt changed')
        print('DP-2 current wallpaper accepted. Controller authenticated; original generation, managed-Comfy and manual-Apply capabilities preserved. Automation OFF; override OFF. No wallpaper/GPU actions.')
        print('Private recovery backup: '+str(self.backup_dir))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    recover(OwnerIO())


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('DP-2 recovery failed ('+type(exc).__name__+'). No GPU/wallpaper test requested. Check systemctl --user status weather-horde-kde.service; private backup retains launch configuration.',file=sys.stderr)
        sys.exit(1)
