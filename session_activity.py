"""Bounded owner-session ScreenSaver polling; no bus borrowing or watcher.

Re-introspect on every observation so bus/locker restart cannot reuse stale
capabilities. No subscriptions means no duplicate handlers to clean up.
"""
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

SERVICE = 'org.freedesktop.ScreenSaver'
OBJECT = '/ScreenSaver'


def owner_query(method):
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    wayland = os.environ.get('WAYLAND_DISPLAY', '')
    if (runtime != '/run/user/' + str(os.getuid()) or not wayland or
            not os.environ.get('DBUS_SESSION_BUS_ADDRESS') or
            Path(runtime).stat().st_uid != os.getuid() or
            not (Path(runtime)/wayland).is_socket()):
        raise OSError('Owning graphical session unavailable')
    return subprocess.run(['qdbus6', SERVICE, OBJECT, method],
                          capture_output=True, text=True, check=True, timeout=3).stdout.strip()


class SessionActivity:
    def __init__(self, query=owner_query):
        self.query = query
        self.unlocked = None

    def poll(self):
        self.unlocked = None
        try:
            xml = self.query('org.freedesktop.DBus.Introspectable.Introspect')
            if len(xml) > 65536:
                return None
            root = ET.fromstring(xml)
            methods = root.findall("./interface[@name='org.freedesktop.ScreenSaver']/method[@name='GetActive']")
            if not any([(a.get('type'), a.get('direction')) for a in m.findall('arg')] == [('b', 'out')] for m in methods):
                return None
            result = self.query(SERVICE + '.GetActive')
            if result in ('true', 'false'):
                self.unlocked = result == 'false'
        except (OSError, ValueError, ET.ParseError, subprocess.SubprocessError):
            pass
        return self.unlocked
