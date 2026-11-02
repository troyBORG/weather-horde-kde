"""Parsed workflow security contract, not substring-only YAML checks."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_checks_and_release_security_contract(self):
        path = ROOT / '.github/workflows/ci.yml'
        self.assertTrue(path.exists(), 'CI workflow missing')
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']), {'push', 'pull_request'})
        self.assertEqual(workflow['on']['push']['branches'], ['**'])
        self.assertEqual(workflow['on']['push']['tags'], ['v*'])
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        checks, release = workflow['jobs']['checks'], workflow['jobs']['release']
        self.assertEqual(release['needs'], 'checks')
        self.assertEqual(release['permissions'], {'contents': 'write'})
        self.assertEqual(release['if'], "github.event_name == 'push' && (github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v'))")
        self.assertEqual(release['concurrency']['cancel-in-progress'], 'false')
        self.assertNotIn('permissions', checks)
        for job in workflow['jobs'].values():
            self.assertIn('timeout-minutes', job)
            for step in job['steps']:
                if 'uses' in step:
                    self.assertRegex(step['uses'], r'^[\w-]+/[\w-]+@[0-9a-f]{40}$')
                    if step['uses'].startswith('actions/checkout@'):
                        self.assertEqual(step['with']['persist-credentials'], 'false')
        upload = next(s for s in checks['steps'] if s.get('uses', '').startswith('actions/upload-artifact@'))
        download = next(s for s in release['steps'] if s.get('uses', '').startswith('actions/download-artifact@'))
        self.assertEqual(upload['with']['name'], download['with']['name'])
        self.assertEqual(upload['with']['path'], 'public/')
        self.assertEqual(upload['with']['if-no-files-found'], 'error')
        self.assertIn('--network none', '\n'.join(s.get('run', '') for s in checks['steps']))
        self.assertNotIn('GH_TOKEN', str(checks))
