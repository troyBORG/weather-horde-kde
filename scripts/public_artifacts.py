"""Allowlisted public runtime inventory; build receipts stay private."""
from pathlib import Path

PLUGIN = Path('contents/ui/WeatherHorde/LocalPairing')
RUNTIME = frozenset(('qmldir', 'weatherpairing.qmltypes',
                     'libweatherpairing.so', 'libweatherpairingplugin.so'))


def package_files(package):
    for file in sorted(package.rglob('*')):
        relative = file.relative_to(package)
        if file.is_file() and (PLUGIN not in relative.parents or
                               relative.parent == PLUGIN and file.name in RUNTIME):
            yield file


def public_receipt(receipt):
    return {key: receipt[key] for key in ('sha256', 'bytes', 'readback_matches_source')} | {
        'live_plasma_installed': False}
