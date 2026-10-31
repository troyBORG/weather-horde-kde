"""Conservative activity policy. Missing evidence is never permission."""
import math
import os
import re
import shlex
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

VR = ('vrcompositor', 'vrserver', 'wivrn', 'alvr', 'monado', 'openvr')
GAMES = ('resonite', 'driftwood', 'horizonxi', 'pol.exe', 'ffxi', 'wineserver', '.exe')


def gpu_client_name(reported):
    """NVIDIA may report argv, not a path. Never match an argument's basename.

    shlex is parsing only (nothing is executed). Unquoted paths with spaces
    remain ambiguous and are not reconstructed by searching for allowed names.
    """
    if not isinstance(reported, str) or any(ord(c) < 32 for c in reported):
        return 'unknown'
    try:
        args = shlex.split(reported)
    except ValueError:
        return 'unknown'
    return diagnostic_name(args[0]) if args else 'unknown'


def diagnostic_name(executable):
    # Status contains a short basename, never argv, full paths or environment.
    name = Path(executable).name
    return name if re.fullmatch(r'[A-Za-z0-9_.+-]{1,64}', name) else 'unknown'


# Installed package/launcher contracts, intentionally version-specific. A runtime
# upgrade needs re-verification, never a wildcard electron allowlist.
ELECTRON_RUNTIME = '/usr/lib/electron43/electron'
ELECTRON_APPS = {'/usr/lib/element/app.asar': 'Element',
                 '/usr/lib/obsidian/app.asar': 'Obsidian'}
INSTALL_UID = 0


def electron_app_identity(pid, proc=Path('/proc')):
    """Bounded same-owner Electron ancestry, fail closed on any missing evidence.

    This is app classification, not a sandbox against malicious same-UID code.
    Never infer identity from NVIDIA argv, user-data-dir, or executable basename.
    """
    import stat

    def installed(path):
        path = Path(path)
        for item in (path, *path.parents):
            meta = item.lstat()
            if (stat.S_ISLNK(meta.st_mode) or meta.st_uid not in (0, INSTALL_UID)
                    or meta.st_mode & 0o022):
                raise ValueError('untrusted installation')
        if not stat.S_ISREG(path.stat().st_mode): raise ValueError('not regular')
        meta = path.stat()
        return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns)

    def bounded(path, limit):
        with path.open('rb') as stream: data = stream.read(limit+1)
        if len(data) > limit: raise ValueError('oversized evidence')
        return data

    def sample(number):
        path = proc/str(number)
        owner = path.stat().st_uid
        if owner != os.getuid(): raise ValueError('foreign owner')
        raw = bounded(path/'stat', 4096)
        fields = raw.rsplit(b')', 1)[1].split()
        if int(raw.split(b' ', 1)[0]) != number: raise ValueError('pid mismatch')
        parent, birth = int(fields[1]), int(fields[19])
        if birth <= 0: raise ValueError('invalid start')
        executable = os.readlink(path/'exe')
        # Deleted/replaced runtimes are not verified by this app-specific policy.
        if executable != ELECTRON_RUNTIME: raise ValueError('wrong runtime')
        meta = (path/'exe').stat()
        binary = (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns)
        if binary != runtime: raise ValueError('replaced runtime')
        raw_args = bounded(path/'cmdline', 16384)
        if not raw_args.endswith(b'\0'): raise ValueError('truncated argv')
        args = tuple(os.fsdecode(a) for a in raw_args[:-1].split(b'\0'))
        return owner, parent, birth, executable, binary, args

    try:
        if type(pid) is not int or pid <= 1: return None
        runtime = installed(ELECTRON_RUNTIME)
        chain = {}; current = pid
        for depth in range(6):
            if current <= 1 or current in chain: return None
            evidence = sample(current); chain[current] = evidence
            args = evidence[-1]
            # The installed launcher execs electron APP as argv[1]. No search
            # through arbitrary flags or user arguments for a matching string.
            if len(args) >= 2 and args[1] in ELECTRON_APPS:
                app = args[1]; app_meta = installed(app)
                if any(a.startswith('--type=') for a in args[2:]): return None
                if any(sample(n) != value for n, value in reversed(tuple(chain.items()))): return None
                if installed(ELECTRON_RUNTIME) != runtime or installed(app) != app_meta: return None
                return ELECTRON_APPS[app]
            types = [a for a in args[1:] if a.startswith('--type=')]
            if types != (['--type=gpu-process'] if depth == 0 else ['--type=zygote']): return None
            current = evidence[1]
        return None
    except (OSError, ValueError, IndexError, TypeError):
        return None


def gpu_client_identity(pid, reported):
    """Prefer the kernel's executable for this NVIDIA PID over mutable argv.

    Cross-UID /proc access can be denied. Keep the existing name policy as an
    explicitly labelled fallback, not proof of ownership. Only the separately
    verified Comfy listener may receive the owned-PID exemption.
    """
    try:
        executable = os.readlink(Path('/proc')/str(pid)/'exe')
    except OSError:
        return {'pid': pid, 'name': gpu_client_name(reported), 'source': 'nvidia_argv'}
    # Linux appends this exact marker to an unlinked running executable after
    # package replacement. Strip once, and only from the kernel readlink result;
    # arbitrary NVIDIA argv must never receive this normalization.
    if executable == ELECTRON_RUNTIME:
        app = electron_app_identity(pid)
        if app:
            return {'pid': pid, 'name': app, 'source': 'proc_electron_ancestry'}
    executable = executable.removesuffix(' (deleted)')
    return {'pid': pid, 'name': diagnostic_name(executable), 'source': 'proc_exe'}


def vram_eligibility(evidence):
    """Hard resource gate independent of incomplete activity telemetry."""
    free = evidence.get('free_mib')
    observed = evidence.get('observed_at', 0)
    if (type(free) not in (int, float) or not math.isfinite(free) or free < 0
            or type(observed) not in (int, float) or not 0 <= time.time()-observed <= 15):
        return 'vram_unavailable'
    return 'safe' if free >= 8192 + 3072 else 'insufficient_vram'


def decide(snapshot):
    return assess(snapshot)[0]


def assess(snapshot):
    try:
        if snapshot['complete'] is not True: return 'unknown', 'graphical_owner_visibility'
        if not 0 <= snapshot['age'] <= 15: return 'unknown', 'stale_evidence'
        names = snapshot['processes']
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
            return 'unknown', 'process_visibility'
        if any(p in n.lower() for n in names for p in VR): return 'vr_active', 'vr_process_detected'
        if any(p in n.lower() for n in names for p in GAMES): return 'game_active', 'game_process_detected'
        # Native basenames retain the existing policy. Generic Electron requires
        # separately verified same-owner ancestry; labels alone are not allowed.
        allowed = {'kwin_wayland', 'Xwayland', 'plasmashell', 'krunner', 'Discord',
                   'steam', 'steamwebhelper', 'brave', 'Telegram', 'soffice.bin',
                   'wordcraft', 'kate'}
        clients = snapshot.get('gpu_clients', [])
        pids = snapshot.get('gpu_pids', [None]*len(clients))
        owned = snapshot.get('owned_pid')
        if len(pids) != len(clients): return 'unknown', 'gpu_client_visibility'
        verified_apps = {(i.get('pid'), i.get('name'))
                         for i in snapshot.get('gpu_client_identities', [])
                         if isinstance(i, dict) and i.get('source') == 'proc_electron_ancestry'
                         and i.get('name') in ('Element', 'Obsidian')}
        if any(gpu_client_name(n) not in allowed and (pid, n) not in verified_apps
               and (owned is None or pid != owned)
               for n,pid in zip(clients,pids)): return 'unknown', 'unrecognized_gpu_client'
        samples = snapshot['utilization']
        if len(samples) != 2 or not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 100 for v in samples):
            return 'unknown', 'utilization_unavailable'
        if not 10 <= snapshot['sample_gap'] <= 30: return 'unknown', 'sampling_window'
        if (owned is not None and snapshot.get('owned_active') is True
                and snapshot.get('previous_owned_pid') == owned
                and snapshot.get('previous_owned_active') is True):
            # Aggregate engine utilization cannot be subtracted arithmetically.
            # Instead require complete numeric per-client engine evidence at BOTH
            # samples, and conservatively sum all non-owned clients.
            residual = []
            for index, key in enumerate(('previous_client_sm','client_sm')):
                usage = snapshot.get(key,{})
                if (set(pids) != set(usage) or
                    any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 100 for v in usage.values())):
                    return 'unknown', 'active_client_counters_unavailable'
                if samples[index] >= 30 and sum(usage.values()) < samples[index]-5:
                    return 'unknown', 'unexplained_gpu_load'  # unexplained aggregate load is not ours
                residual.append(min(100, sum(v for pid,v in usage.items() if pid != owned)))
            samples = residual
        if min(samples) >= 30: return 'gpu_busy', 'sustained_utilization'
        free = snapshot['free_mib']
        if type(free) not in (int, float) or not math.isfinite(free) or free < 0: return 'unknown', 'vram_unavailable'
        if free < 8192 + 3072: return 'insufficient_vram', 'vram_reserve'
        return 'safe', 'checks_passed'
    except (KeyError, TypeError, ValueError):
        return 'unknown', 'malformed_evidence'


def collect(previous=None, transport=None):
    """Read commands, never environment/secrets; cross-user visibility is incomplete.

    Native games not matching a configured pattern cannot be proven absent under
    another UID. Thus one user's controller cannot declare another user's session safe.
    """
    now = time.monotonic()
    try:
        names = subprocess.run(['ps', '-eo', 'comm='], capture_output=True, text=True,
                               check=True, timeout=5).stdout.splitlines()
        rows = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.free',
                               '--format=csv,noheader,nounits'], capture_output=True,
                              text=True, check=True, timeout=5).stdout.strip().splitlines()
        if len(rows) != 1: raise ValueError('Ambiguous GPU')
        utilization, free = [int(x.strip()) for x in rows[0].split(',')]
        xml = subprocess.run(['nvidia-smi', '-q', '-x'], capture_output=True, text=True, check=True, timeout=5).stdout
        tree = ET.fromstring(xml)
        groups = tree.findall('./gpu/processes')
        if len(groups) != 1: raise ValueError('Missing GPU process visibility')
        entries = groups[0].findall('process_info')
        clients = [p.findtext('process_name') for p in entries]
        pids = [int(p.findtext('pid')) for p in entries]
        if any(not n or n == 'N/A' for n in clients): raise ValueError('Unknown GPU client')
        identities = [gpu_client_identity(pid, name) for pid, name in zip(pids, clients)]
        clients = [identity['name'] for identity in identities]
        owned = transport.owned_gpu_pid() if transport is not None else None
        active = bool(transport is not None and transport.owned_gpu_active)
        usage = {}
        if owned is not None and active:
            # '-' / missing process rows are UNKNOWN, never zero.
            report = subprocess.run(['nvidia-smi','pmon','-c','1','-s','u'],
                capture_output=True,text=True,check=True,timeout=5).stdout
            for line in report.splitlines():
                fields = line.split()
                if not fields or fields[0].startswith('#'): continue
                if len(fields) >= 10 and fields[0] == '0' and fields[1].isdigit():
                    counters = fields[3:9]  # SM, memory, encoder, decoder, JPEG, OFA
                    if all(v.isdigit() for v in counters):
                        usage[int(fields[1])] = max(map(int,counters))
        # Only inspect graphical process ownership, not its private environment.
        owners = subprocess.run(['ps', '-C', 'plasmashell', '-o', 'uid='],
                                capture_output=True, text=True, check=True, timeout=5).stdout.split()
        complete = owners == [str(os.getuid())]
        prior = previous or {'at': now, 'util': utilization}
        snap = {'processes': names, 'gpu_clients': clients, 'complete': complete, 'utilization': [prior['util'], utilization],
                'free_mib': free, 'sample_gap': now-prior['at'], 'age': 0,
                'gpu_pids':pids, 'gpu_client_identities':identities, 'owned_pid':owned, 'owned_active':active,
                'client_sm':usage, 'previous_client_sm':prior.get('client_sm',{}),
                'previous_owned_pid':prior.get('owned_pid'), 'previous_owned_active':prior.get('owned_active',False)}
        # Positive game evidence can block even with incomplete visibility.
        known = assess(snap | {'complete': True})
        decision, reason = known if known[0] in ('game_active', 'vr_active') else assess(snap)
        return {'decision': decision, 'reason': reason, 'sample_gap_seconds': round(snap['sample_gap'], 1),
                'observed_at': time.time(), 'free_mib': free,
                'visibility_complete': complete, 'gpu_client_identities': identities,
                'owned_gpu_pid':owned, 'owned_gpu_active':active}, {'at': now, 'util': utilization, 'client_sm':usage, 'owned_pid':owned, 'owned_active':active}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError, subprocess.SubprocessError):
        return {'decision': 'unknown', 'reason': 'collector_read_failed', 'observed_at': time.time(), 'visibility_complete': False}, None
