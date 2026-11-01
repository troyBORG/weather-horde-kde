#!/usr/bin/env python3
"""Install persistent graphical-session controller as the configured owner, with saved Auto unchanged.
Refuses a running controller: never kills a job to deploy. No direct GPU/apply calls.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portable_paths import require_owner as require_configured_owner, trusted_source_uids, comfy_root
UNIT = 'weather-horde-kde.service'
ENV_KEYS = ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS',
            'XDG_SESSION_TYPE','XDG_CURRENT_DESKTOP','XDG_DATA_DIRS','LANG')
AUTO_KEYS = ('automation_enabled','automation_kind','automation_target','interval_minutes')
STAGE = 'arguments'


def failure_details(exc, stage):
    """Only fixed labels and numeric evidence; never exception text/paths/argv."""
    kinds = (PermissionError, FileNotFoundError, FileExistsError, BlockingIOError,
             OSError, ValueError, RuntimeError, ImportError,
             subprocess.CalledProcessError, subprocess.TimeoutExpired)
    kind = next((t.__name__ for t in kinds if isinstance(exc, t)), 'Exception')
    # Preserve these subclasses before their OSError/ValueError parents.
    if isinstance(exc, subprocess.CalledProcessError): kind = 'CalledProcessError'
    if isinstance(exc, subprocess.TimeoutExpired): kind = 'TimeoutExpired'
    result = {'stage': stage, 'exception': kind}
    if isinstance(exc, OSError) and isinstance(exc.errno, int): result['errno'] = exc.errno
    if isinstance(exc, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
        cmd = exc.cmd
        label = 'other'
        if isinstance(cmd, (list, tuple)):
            if len(cmd) >= 3 and cmd[:2] == ['systemctl', '--user'] and cmd[2] in {
                'show', 'is-active', 'is-enabled', 'disable', 'enable', 'daemon-reload', 'import-environment', 'start'}:
                label = 'systemctl:' + cmd[2]
            elif cmd[:3] == ['systemd-analyze', '--user', 'verify']: label = 'systemd-analyze:verify'
            elif cmd == ['kscreen-doctor', '-j']: label = 'kscreen-doctor:json'
        result['command'] = label
        if isinstance(exc, subprocess.CalledProcessError): result['returncode'] = exc.returncode
    frames = []
    tb = exc.__traceback__
    while tb:
        if tb.tb_frame.f_code.co_filename == __file__:
            frames.append(tb.tb_lineno)
        tb = tb.tb_next
    result['installer_lines'] = frames[-5:]
    return result


def readonly_audit(event, args):
    """Defense in depth for diagnostic CLI; not a sandbox for hostile code."""
    if event == 'open':
        mode, flags = args[1:3]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise PermissionError('Read-only diagnostic refused a write')
    if event in {'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.chmod', 'os.chown',
                 'os.symlink', 'os.link', 'os.truncate', 'os.utime', 'os.system',
                 'socket.connect', 'socket.connect_ex'}:
        raise PermissionError('Read-only diagnostic refused mutation/network')
    if event == 'subprocess.Popen':
        argv = args[1]
        allowed = isinstance(argv, list) and (
            (argv[:2] == ['systemctl', '--user'] and len(argv) > 2 and argv[2] in {'show', 'is-active', 'is-enabled'})
            or argv == ['kscreen-doctor', '-j'])
        if not allowed: raise PermissionError('Read-only diagnostic refused command')


def quote(value):
    value = str(value)
    if any(ord(c)<32 for c in value): raise ValueError('Control character in service argument')
    return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%').replace('$','$$')+'"'


def render_unit(argv):
    return ('[Unit]\nDescription=Weather Horde guarded graphical-session controller\n'
            'After=graphical-session.target\nRequisite=graphical-session.target\n'
            'PartOf=graphical-session.target\nStartLimitIntervalSec=120\nStartLimitBurst=3\n\n'
            '[Service]\nType=exec\nWorkingDirectory='+str(ROOT).replace('%','%%')+'\n'
            'ExecStart='+ ' '.join(map(quote,argv))+'\n'
            'Environment=PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1\n'
            'Environment='+quote('WEATHER_HORDE_COMFY_ROOT='+str(comfy_root())).replace('$$', '$')+'\n'
            'Restart=on-failure\nRestartSec=15\nTimeoutStopSec=30\n'
            'NoNewPrivileges=true\nUMask=0077\n\n'
            '[Install]\nWantedBy=graphical-session.target\n')


def command(args, settings, state):
    checkpoint = settings.get('checkpoint') or args.preview_checkpoint
    if not checkpoint: raise ValueError('Saved checkpoint missing: specify --preview-checkpoint explicitly')
    argv = ['/usr/bin/python3',str(ROOT/'weather_controller.py'),'--state-dir',str(state),
            '--preview-checkpoint',checkpoint,'--comfy-idle-seconds',str(args.comfy_idle_seconds)]
    if args.manual_wallpapers: argv.append('--manual-wallpapers')
    if args.managed_comfy: argv.append('--managed-comfy')
    if settings.get('automation_kind')=='image_wallpaper' and not args.manual_wallpapers:
        raise ValueError('Saved image-wallpaper Auto requires --manual-wallpapers')
    return argv


def requested_settings(raw, restore, enable_catchup=False):
    settings=json.loads(raw)
    if type(settings.get('automation_enabled')) is not bool:
        raise ValueError('Saved automation consent missing; refusing defaults')
    if settings.get('interval_minutes') not in (30,60,120,240,480,720,1440):
        raise ValueError('Invalid saved interval')
    if restore:
        if not settings.get('location'): raise ValueError('Confirm location in widget before restoring Auto')
        settings.update(automation_enabled=True, automation_kind='image_wallpaper',
                        automation_target='all', interval_minutes=30)
    if enable_catchup: settings['catch_up_refresh'] = True
    return settings


def run(*args, check=True):
    return subprocess.run(list(args),check=check,capture_output=True,text=True,timeout=30)


def ctl(*args, check=True): return run('systemctl','--user',*args,check=check)


def props():
    result=ctl('show',UNIT,'--property=LoadState,ActiveState,SubState,MainPID,Transient,FragmentPath,DropInPaths',check=False)
    data=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if not data or result.returncode not in (0,1): raise RuntimeError('Cannot inspect owner user manager')
    return data


def controller_running(proc=Path('/proc')):
    for process in proc.iterdir():
        if not process.name.isdecimal(): continue
        try:
            if process.stat().st_uid!=os.getuid(): continue
            with (process/'cmdline').open('rb') as stream: raw=stream.read(65537)
            if len(raw)>65536: raise RuntimeError('Oversized same-owner process evidence')
            if any(Path(os.fsdecode(arg)).name=='weather_controller.py' for arg in raw.split(b'\0') if arg):
                return True
        except FileNotFoundError: continue  # exited during bounded observation
        except PermissionError: raise RuntimeError('Unreadable same-owner process; cannot prove controller stopped')
    return False


def require_stopped():
    # Never stop/reset a live unit. Collected transient definitions can lag exit;
    # wait for collection BEFORE writing a persistent unit or reloading manager.
    for _ in range(50):
        p=props()
        if p.get('DropInPaths'): raise RuntimeError('Existing unit drop-ins require review; nothing installed')
        if p.get('ActiveState') not in ('inactive','failed') or p.get('MainPID')!='0':
            raise RuntimeError('Controller active/transitioning: no restart attempted; retry only after safely idle and owner-stopped')
        if p.get('Transient')!='yes': break
        time.sleep(.2)
    else: raise RuntimeError('Transient unit not collected; nothing installed')
    if controller_running(): raise RuntimeError('Lingering owner controller process; no deployment attempted')
    for family, address in ((socket.AF_INET,('127.0.0.1',8734)),(socket.AF_INET6,('::1',8734))):
        with socket.socket(family) as sock:
            if family==socket.AF_INET6: sock.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
            sock.bind(address)
    if (Path.home()/'.local/state/weather-horde-kde/inflight.json').exists():
        raise RuntimeError('Unresolved render journal: no deployment attempted')
    return p


def safe_path(path, owners, directory=False):
    for p in (path,*path.parents):
        meta=p.lstat()
        if stat.S_ISLNK(meta.st_mode) or meta.st_uid not in owners or meta.st_mode & 0o022:
            raise RuntimeError('Unsafe path; permissions unchanged: '+str(p))
    if directory and not path.is_dir(): raise RuntimeError('Not a directory: '+str(path))


def private_read(path):
    safe_path(path,(0,os.getuid()))
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        st=os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600 or st.st_nlink!=1:
            raise RuntimeError('Expected private regular file: '+str(path))
        return stream.read()


def atomic(path, data):
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        if path.read_bytes()!=data: raise RuntimeError('File readback failed')
    finally:
        if os.path.exists(name): os.unlink(name)


def api(token):
    request=Request('http://127.0.0.1:8734/v1/status',headers={'Authorization':'Bearer '+token})
    with build_opener(ProxyHandler({})).open(request,timeout=5) as response: return json.load(response)


def verify_status(status, expected, argv, revision):
    if status.get('catch_up_refresh',False)!=expected.get('catch_up_refresh',False): raise RuntimeError('Catch-up policy mismatch')
    if status.get('source_revision')!=revision: raise RuntimeError('Loaded source revision mismatch')
    if any(status.get(k)!=expected.get(k) for k in AUTO_KEYS): raise RuntimeError('Automation settings mismatch')
    if (not status.get('displays') or status.get('testing_override',{}).get('active') is not False
        or status.get('render_enabled') is not True
        or status.get('apply_enabled')!=('--manual-wallpapers' in argv)
        or status.get('comfy_service',{}).get('managed')!=('--managed-comfy' in argv)):
        raise RuntimeError('Capability/display/override verification failed')
    if status.get('checkpoint')!=argv[argv.index('--preview-checkpoint')+1]:
        raise RuntimeError('Checkpoint mismatch')
    deadline=status.get('next_eligible_at',0)
    if not time.time()<deadline<=time.time()+expected['interval_minutes']*60+5:
        raise RuntimeError('Scheduled deadline not verified')


def restore_backup(backup, destination, state):
    manifest=json.loads(private_read(backup/'manifest.json'))
    ctl('disable',UNIT)
    if manifest['had_unit']: atomic(destination,private_read(backup/'old-unit.service'))
    elif destination.exists(): destination.unlink()
    atomic(state/'settings.json',private_read(backup/'settings.json'))
    ctl('daemon-reload')
    if manifest['enabled']: ctl('enable',UNIT)
    if destination.exists() and destination.read_bytes()!=private_read(backup/'old-unit.service'):
        raise RuntimeError('Rollback unit verification failed')
    enabled=ctl('is-enabled',UNIT,check=False).stdout.strip()=='enabled'
    if enabled!=manifest['enabled']: raise RuntimeError('Rollback enablement verification failed')
    print('Rollback verified; controller remains stopped. Backup retained. No GPU/Plasma/Comfy commands.')


def main():
    global STAGE
    STAGE = 'arguments'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-checkpoint')
    parser.add_argument('--manual-wallpapers',action='store_true')
    parser.add_argument('--managed-comfy',action='store_true')
    parser.add_argument('--comfy-idle-seconds',type=int,default=300)
    parser.add_argument('--restore-30min-generate-apply-all',action='store_true',
                        help='Explicit consent: Auto ON, image_wallpaper, all monitors, 30 minutes; retains location/model/scene')
    parser.add_argument('--enable-catch-up-refresh',action='store_true',
                        help='Opt in to overdue unlock/game catch-up and locked-session pause; preserve Auto/mode/scope/interval')
    parser.add_argument('--rollback',type=Path,help='Restore one installer backup, only while controller stopped')
    parser.add_argument('--diagnose-before-backup', action='store_true',
                        help='Run exact preflight read-only; stop BEFORE backup creation or installation')
    args=parser.parse_args()
    if args.diagnose_before_backup:
        if args.rollback: parser.error('Diagnostic mode cannot perform rollback')
        sys.dont_write_bytecode = True
        sys.addaudithook(readonly_audit)
    STAGE = 'configured-owner'
    require_configured_owner()
    STAGE = 'session'
    os.umask(0o077)
    if not 30<=args.comfy_idle_seconds<=86400: raise ValueError('Invalid Comfy idle timeout')
    if not os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_RUNTIME_DIR')!='/run/user/'+str(os.getuid()):
        raise RuntimeError('Run inside the owner Wayland graphical session')
    if ctl('is-active','graphical-session.target',check=False).stdout.strip()!='active':
        raise RuntimeError('Owner graphical-session.target not active')
    STAGE = 'trusted-source'
    trusted=trusted_source_uids()
    for path in [*ROOT.glob('*.py'), Path(__file__).resolve()]: safe_path(path,trusted)
    sys.path.insert(0,str(ROOT))
    STAGE = 'imports'
    from receipt_lock import state_lock
    from weather_controller import SOURCE_REVISION
    STAGE = 'state-path'
    state=Path.home()/'.local/state/weather-horde-kde'
    safe_path(state,(0,os.getuid()),True)
    if stat.S_IMODE(state.stat().st_mode)!=0o700: raise RuntimeError('State must remain 0700')
    STAGE = 'unit-path'
    destination=Path.home()/'.config/systemd/user'/UNIT
    safe_path(destination.parent,(0,os.getuid()),True)
    if destination.exists() or destination.is_symlink():
        safe_path(destination,(0,os.getuid()))
        if destination.stat().st_uid!=os.getuid(): raise RuntimeError('Existing unit must be owner-owned')
    if (destination.parent/(UNIT+'.d')).exists(): raise RuntimeError('Existing service drop-ins require review')
    # Serialize with new controllers/recovery tools; old controllers also excluded
    # by unit/process/listener checks. No forced stop, no Auto pause/reset.
    STAGE = 'state-lock'
    with state_lock(state,exclusive=True):
        STAGE = 'stopped-controller'
        require_stopped()
        if args.rollback:
            backup=args.rollback.absolute()
            if backup.parent!=state or not backup.name.startswith('controller-install-'):
                raise RuntimeError('Rollback must name a private controller-install backup')
            safe_path(backup,(os.getuid(),0),True)
            restore_backup(backup,destination,state)
            return
        STAGE = 'display-discovery'
        from displays import discover
        displays,error=discover()
        if error or not displays: raise RuntimeError('Owner live display discovery failed')
        STAGE = 'read-settings'
        raw=private_read(state/'settings.json')
        STAGE = 'settings-and-command'
        settings=requested_settings(raw,args.restore_30min_generate_apply_all,args.enable_catch_up_refresh)
        if args.restore_30min_generate_apply_all and not args.manual_wallpapers:
            raise ValueError('Explicit Auto restore requires --manual-wallpapers')
        argv=command(args,settings,state)
        STAGE = 'managed-comfy-load'
        if args.managed_comfy:
            if ctl('show','weather-horde-comfy.service','-p','LoadState','--value').stdout.strip()!='loaded':
                raise RuntimeError('Install reviewed on-demand Comfy unit first; no Comfy start attempted')
        STAGE = 'read-token'
        token=private_read(state/'token').decode().strip()
        if not 32<=len(token)<=4096: raise RuntimeError('Invalid private authentication material')
        STAGE = 'enablement'
        enabled=ctl('is-enabled',UNIT,check=False).stdout.strip()
        if enabled not in ('enabled','disabled','not-found',''): raise RuntimeError('Unexpected existing unit enablement')
        STAGE = 'backup-create'
        if args.diagnose_before_backup:
            print(json.dumps({'stage': STAGE, 'ok': True, 'enablement': enabled,
                              'stopped_before_write': True,
                              'note': 'Backup creation permissions, quota and free space NOT tested'}))
            return
        backup=Path(tempfile.mkdtemp(prefix='controller-install-',dir=state))
        STAGE = 'backup-write'
        atomic(backup/'settings.json',raw)
        atomic(backup/'manifest.json',json.dumps({'had_unit':destination.exists(),'enabled':enabled=='enabled'}).encode())
        if destination.exists(): atomic(backup/'old-unit.service',destination.read_bytes())
        new=render_unit(argv).encode()
        atomic(backup/UNIT,new)
        STAGE = 'unit-verify'
        run('systemd-analyze','--user','verify',str(backup/UNIT))
        print('Private rollback backup: '+str(backup),flush=True)
        try:
            STAGE = 'install-unit-and-settings'
            require_stopped()
            atomic(destination,new)
            if args.restore_30min_generate_apply_all or args.enable_catch_up_refresh:
                atomic(state/'settings.json',json.dumps(settings,indent=2).encode())
            elif private_read(state/'settings.json')!=raw:
                raise RuntimeError('Settings changed concurrently')
            STAGE = 'daemon-reload'
            ctl('daemon-reload')
            p=props()
            if p.get('Transient')!='no' or p.get('FragmentPath')!=str(destination):
                raise RuntimeError('Persistent definition not loaded; transient race refused')
            STAGE = 'enable-unit'
            ctl('enable',UNIT)
            link=destination.parent/'graphical-session.target.wants'/UNIT
            if not link.is_symlink() or link.resolve()!=destination or ctl('is-enabled',UNIT).stdout.strip()!='enabled':
                raise RuntimeError('Graphical target enablement not verified')
            STAGE = 'import-environment'
            ctl('import-environment',*[k for k in ENV_KEYS if os.environ.get(k)])
            atomic(backup/'launch.json',json.dumps({'argv':argv,'source_revision':SOURCE_REVISION}).encode())
        except Exception:
            # No service start has been requested; restore only if still stopped.
            require_stopped()
            restore_backup(backup,destination,state)
            raise
    # Release exclusive state lock before service obtains shared runtime lock.
    STAGE = 'start-unit'
    ctl('start',UNIT)
    STAGE = 'runtime-verification'
    status=None
    for _ in range(45):
        try:
            status=api(token)
            verify_status(status,settings,argv,SOURCE_REVISION)
            break
        except (OSError,ValueError,RuntimeError): time.sleep(1)
    else: raise RuntimeError('Owner runtime verification failed; service not forcibly stopped; backup retained')
    p=props()
    if p.get('ActiveState')!='active' or p.get('Transient')!='no' or p.get('FragmentPath')!=str(destination):
        raise RuntimeError('Persistent running service identity not verified')
    expected_raw = json.dumps(settings,indent=2).encode() if args.restore_30min_generate_apply_all or args.enable_catch_up_refresh else raw
    if private_read(state/'settings.json')!=expected_raw:
        raise RuntimeError('Saved settings bytes changed unexpectedly')
    receipt={k:status[k] for k in (*AUTO_KEYS,'source_revision','service_version','next_eligible_at','render_enabled','apply_enabled')}
    receipt.update(enabled=True,target='graphical-session.target',managed_comfy=status['comfy_service']['managed'],
                   testing_override=False,guard_decision=status.get('guard',{}).get('decision'),
                   verified='Authenticated backend; enabled target link; NOT UI reconnect or completed render/apply')
    STAGE = 'receipt-write'
    atomic(backup/'receipt.json',json.dumps(receipt,indent=2).encode())
    print(json.dumps(receipt,indent=2))
    print('Login persistence installed. Saved Auto may run when due (including opted-in catch-up), through existing guards. No forced generation/apply or Plasma restart.')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        # Never print raw HTTP bodies, credentials, subprocess argv or settings.
        print('Controller install stopped: '+json.dumps(failure_details(exc, STAGE), sort_keys=True),file=sys.stderr)
        sys.exit(1)
