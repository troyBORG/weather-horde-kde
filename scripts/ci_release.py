#!/usr/bin/env python3
"""Fail-closed release policy and exact tested asset publication (no rebuild)."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ASSETS = ('org.troyborg.weatherhorde.plasmoid', 'weather-horde-controller.zip',
          'weather-horde-owner-installer.tar.gz')


def release_target(event, ref, version, sha, run_id, attempt):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid commit')
    if event != 'push':
        raise ValueError('Only push events publish')
    if ref == 'refs/heads/main' and run_id.isdigit() and attempt.isdigit():
        return f'ci-{run_id}-{attempt}-{sha[:12]}', True
    if re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', ref.removeprefix('refs/tags/')) and ref == 'refs/tags/v' + version:
        return 'v' + version, False
    raise ValueError('Not main or a metadata-matching stable version tag')


def verify_assets(directory, sha):
    expected = {*ASSETS, 'manifest.json'}
    if {p.name for p in directory.iterdir()} != expected or any(
            not p.is_file() or p.is_symlink() for p in directory.iterdir()):
        raise ValueError('Unexpected public artifact inventory')
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['commit'] != sha or set(manifest['sha256']) != set(ASSETS):
        raise ValueError('Artifact provenance mismatch')
    for name in ASSETS:
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != manifest['sha256'][name]:
            raise ValueError('Artifact digest mismatch: ' + name)
    return manifest


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def publish():
    env = os.environ
    sha = env['GITHUB_SHA']
    directory = Path('public')
    manifest = verify_assets(directory, sha)
    version = json.loads(Path('plasma-widget/org.troyborg.weatherhorde/metadata.json').read_text())['KPlugin']['Version']
    if manifest['version'] != version:
        raise ValueError('Version mismatch')
    tag, prerelease = release_target(env['GITHUB_EVENT_NAME'], env['GITHUB_REF'], version,
                                     sha, env['GITHUB_RUN_ID'], env['GITHUB_RUN_ATTEMPT'])
    repo = env['GITHUB_REPOSITORY']
    if prerelease:
        # Atomic creation: refuse existing tags, never move or overwrite them.
        gh('api', f'repos/{repo}/git/refs', '-X', 'POST', '-f', 'ref=refs/tags/' + tag, '-f', 'sha=' + sha)
    if gh('api', f'repos/{repo}/commits/{tag}', '--jq', '.sha') != sha:
        raise ValueError('Remote tag no longer points to tested commit')
    # Create first as draft. A failure leaves a draft, never a partial public release.
    # No --clobber and no update/reuse of an existing release, including on reruns.
    notes = (f'Tested commit: {sha}\nWorkflow: https://github.com/{repo}/actions/runs/'
             f'{env["GITHUB_RUN_ID"]}\n\nArch Linux x86_64 / Qt6 / Plasma6 build. '
             'No deployment. See docs/ci-releases.md for compatibility and installation limits.')
    gh('release', 'create', tag, '--repo', repo, '--verify-tag', '--draft',
       '--latest=false', '--title', ('CI ' if prerelease else 'Weather Horde ') + tag,
       '--notes', notes, *(['--prerelease'] if prerelease else []),
       *(str(directory / name) for name in (*ASSETS, 'manifest.json')))
    actual = json.loads(gh('release', 'view', tag, '--repo', repo, '--json', 'assets'))['assets']
    if {a['name']: a['size'] for a in actual} != {n: (directory / n).stat().st_size for n in (*ASSETS, 'manifest.json')}:
        raise ValueError('Uploaded asset inventory mismatch; left draft')
    # Read back uploaded bytes before making the release public.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        gh('release', 'download', tag, '--repo', repo, '--dir', tmp)
        if verify_assets(Path(tmp), sha) != manifest:
            raise ValueError('Uploaded artifact readback mismatch; left draft')
    gh('release', 'edit', tag, '--repo', repo, '--draft=false', '--latest=false')
    state = json.loads(gh('release', 'view', tag, '--repo', repo, '--json', 'isDraft,isPrerelease,tagName,url'))
    if state['isDraft'] or state['isPrerelease'] != prerelease or state['tagName'] != tag:
        raise ValueError('Publication readback mismatch')
    print(state['url'])


if __name__ == '__main__':
    publish()
