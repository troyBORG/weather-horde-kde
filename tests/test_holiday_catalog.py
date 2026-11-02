import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class CatalogTests(unittest.TestCase):
    def test_complete_attributed_inventory(self):
        path = ROOT / 'holiday_catalog.json'
        self.assertTrue(path.exists(), 'versioned holiday catalog missing')
        catalog = json.loads(path.read_text())
        self.assertEqual(catalog['schema_version'], 1)
        events = catalog['events']
        self.assertEqual(len({e['id'] for e in events}), len(events))
        federal = [e for e in events if any(c['category']=='federal_public_holiday' for c in e['classifications'])]
        self.assertEqual(len(federal), 11)
        for category, count in [('legal_public_holiday',10), ('paid_employee_holiday',9)]:
            self.assertEqual(sum(any(c['jurisdiction']=='US-IA' and c['category']==category for c in e['classifications']) for e in events), count)
        sections = {c['section'] for e in events for c in e['classifications'] if c['jurisdiction']=='US-IA'}
        self.assertEqual(sections, {'1C.'+str(i) for i in range(1,18)})
        for e in events:
            self.assertRegex(e['id'], r'^[a-z][a-z0-9_]+$')
            self.assertIn(e['rule']['kind'], ('fixed','nth_weekday','last_weekday','nearest_weekday','on_or_before','offset','week'))
            self.assertIn(e['observed_policy'], ('none','nearest_weekday'))
            self.assertIsInstance(e['default_enabled'], bool)
            for c in e['classifications']:
                self.assertTrue(c['source_url'].startswith('https://'))
                self.assertTrue(c['section'])
        for receipt in catalog['sources']:
            self.assertRegex(receipt['sha256'], r'^[a-f0-9]{64}$')
            self.assertTrue(receipt['retrieved_at'])
            self.assertTrue(receipt['version'])
