"""Shared installation paths; no service discovery or cross-account access.

Owner selection is explicit deployment configuration, not authentication. Kernel
UID checks and each caller's private-file/session/listener guards remain required.
"""
import os
from pathlib import Path
import pwd


def absolute_path(name, default):
    value = os.environ.get(name) or str(default)
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(name + ' must be an absolute path without traversal, surrounding whitespace or control characters')
    return path


def data_home():
    return absolute_path('XDG_DATA_HOME', Path.home()/'.local/share')


def comfy_root():
    return absolute_path('WEATHER_HORDE_COMFY_ROOT', data_home()/'ComfyUI')


def require_owner():
    name = os.environ.get('WEATHER_HORDE_OWNER', '')
    if not name:
        raise RuntimeError('Set WEATHER_HORDE_OWNER in the owner graphical terminal')
    try:
        owner = pwd.getpwnam(name)
    except KeyError:
        raise RuntimeError('Set WEATHER_HORDE_OWNER to the intended KDE owner; run in its graphical terminal') from None
    if os.getuid() == 0 or os.getuid() != owner.pw_uid:
        raise RuntimeError('Run in the configured owner graphical terminal, never root or a different account')
    return owner


def trusted_source_uids():
    # Staging-account trust is opt-in, never inferred from source ownership.
    owners = (0, os.getuid())
    name = os.environ.get('WEATHER_HORDE_STAGING_USER')
    if name:
        try:
            owners += (pwd.getpwnam(name).pw_uid,)
        except KeyError:
            raise RuntimeError('Unknown configured staging account') from None
    return owners
