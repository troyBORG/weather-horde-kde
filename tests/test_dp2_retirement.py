import copy, json, os, tempfile, unittest
from pathlib import Path
import test_wallpaper_reconcile as fixtures
DISPLAY=fixtures.DISPLAY

class RetirementTests(unittest.TestCase):
    setup_case=fixtures.ReconcileTests.setup_case
    def test_recreated_containment_requires_explicit_accept_and_archives(self):
        with tempfile.TemporaryDirectory() as d:
            m,b,j=self.setup_case(d)
            b.value.update(desktop=128,image='file:///chosen-static.png',fill=2)
            raw=m.journal.read_bytes(); current=copy.deepcopy(b.value)
            with self.assertRaises(ValueError): m.reconcile_pending(DISPLAY,commit=True)
            with self.assertRaises(ValueError):
                m.accept_current(DISPLAY,current,raw)
            result=m.accept_current(DISPLAY,current,raw,confirmed=True)
            self.assertTrue(result['verified'])
            new=json.loads(m.journal.read_bytes())
            self.assertEqual(new['DP-2']['state'],'accepted_current')
            self.assertEqual(new['DP-2']['before'],current)
            self.assertEqual(new['DP-2']['after'],current)
            self.assertEqual(new['DP-3'],j['DP-3'])
            self.assertEqual(m.journal.read_bytes().split(b'"DP-3":')[1],raw.split(b'"DP-3":')[1])
            archive=Path(result['archive'])
            self.assertEqual((archive/'journal.json').read_bytes(),raw)
            self.assertEqual(json.loads((archive/'current.json').read_bytes()),current)
            self.assertEqual(archive.stat().st_mode & 0o777,0o700)
            for p in archive.iterdir(): self.assertEqual(p.stat().st_mode & 0o777,0o600)
            self.assertEqual(b.writes,[])

    def test_drift_during_acceptance_retains_exact_journal(self):
        for phase in ('before','second-snapshot','journal'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as d:
                m,b,j=self.setup_case(d);b.value['desktop']=128
                raw=m.journal.read_bytes();expected=copy.deepcopy(b.value)
                if phase=='before': b.value['image']='file:///drift.png'
                if phase=='journal':
                    m.journal.write_bytes(raw+b' ')
                if phase=='second-snapshot':
                    original=b.snapshot;calls=[]
                    def snapshot(display):
                        calls.append(1)
                        if len(calls)==2: b.value['image']='file:///drift.png'
                        return original(display)
                    b.snapshot=snapshot
                saved=m.journal.read_bytes()
                with self.assertRaisesRegex(ValueError,'changed'):
                    m.accept_current(DISPLAY,expected,raw,confirmed=True)
                self.assertEqual(m.journal.read_bytes(),saved);self.assertEqual(b.writes,[])

    def test_missing_identity_refused(self):
        with tempfile.TemporaryDirectory() as d:
            m,b,j=self.setup_case(d)
            del b.value['screen']
            for side in ('before','after'): del j['DP-2'][side]['screen']
            m.journal.write_text(json.dumps(j));raw=m.journal.read_bytes()
            with self.assertRaises(ValueError):
                m.accept_current(DISPLAY,copy.deepcopy(b.value),raw,confirmed=True)
            self.assertEqual(m.journal.read_bytes(),raw)

    def test_activity_geometry_connector_or_nonpending_refused(self):
        for field,value in [('activity','other'),('geometry',[9,0,1080,1920]),('screen',0),('state','applied'),('connector','DP-3')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                m,b,j=self.setup_case(d);display=copy.deepcopy(DISPLAY)
                if field=='connector': display['id']=value
                elif field=='state':
                    j['DP-2']['state']=value;m.journal.write_text(json.dumps(j))
                else: b.value[field]=value
                raw=m.journal.read_bytes()
                with self.assertRaises(ValueError):
                    m.accept_current(display,copy.deepcopy(b.value),raw,confirmed=True)
                self.assertEqual(m.journal.read_bytes(),raw);self.assertEqual(b.writes,[])

if __name__=='__main__': unittest.main()
