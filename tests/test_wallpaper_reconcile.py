import copy, json, tempfile, unittest
from pathlib import Path
from wallpaper import WallpaperManager, atomic_json

DISPLAY={'id':'DP-2','x':0,'y':0,'width':1080,'height':1920,'scale':1}
class Backend:
    def __init__(self):
        self.value={'desktop':12,'activity':'fixture','screen':1,'geometry':[0,0,1080,1920], 'plugin':'org.kde.image','image':'file:///private.png','fill':1,'settings':[{'group':['General'],'values':{'Image':'file:///private.png','FillMode':1}}]}
        self.right={'image':'file:///user-applied-right.png'}
        self.writes=[]
    def snapshot(self,display): return copy.deepcopy(self.value)
    def replace(self,*args): self.writes.append(args); raise AssertionError('Reconcile must never write wallpaper')

class ReconcileTests(unittest.TestCase):
    def setup_case(self,root):
        b=Backend(); m=WallpaperManager(root,b)
        old=copy.deepcopy(b.value);old['settings'][0]['values']['FillMode']='1'
        before=copy.deepcopy(old);before['image']='file:///old.png';before['settings'][0]['values']['Image']=before['image']
        journal={'DP-2':{'state':'pending','before':before,'after':old},'DP-3':{'state':'applied','before':{'private':'right-old'},'after':copy.deepcopy(b.right)}}
        atomic_json(m.journal,journal)
        return m,b,journal
    def test_restore_accepts_known_legacy_fillmode_only(self):
        with tempfile.TemporaryDirectory() as d:
            m,b,j=self.setup_case(d)
            def replace(display,expected,replacement):
                b.value=copy.deepcopy(replacement)
                b.value['settings'][0]['values']['FillMode']=int(b.value['settings'][0]['values']['FillMode'])
            b.replace=replace
            self.assertEqual(m.restore(DISPLAY,lambda:'safe')['state'],'restored')
            self.assertEqual(json.loads(m.journal.read_text())['DP-3'],j['DP-3'])

    def test_legacy_pending_after_reconciles_without_wallpaper_write(self):
        with tempfile.TemporaryDirectory() as d:
            m,b,j=self.setup_case(d); raw=m.journal.read_bytes();right=copy.deepcopy(b.right)
            report=m.reconcile_pending(DISPLAY)
            self.assertEqual(report['match'],'after');self.assertEqual(m.journal.read_bytes(),raw)
            result=m.reconcile_pending(DISPLAY,commit=True)
            self.assertTrue(result['verified']);updated=json.loads(m.journal.read_text())
            self.assertEqual(updated['DP-2']['state'],'applied')
            self.assertEqual(updated['DP-2']['before'],j['DP-2']['before'])
            self.assertEqual(updated['DP-3'],j['DP-3']);self.assertEqual(b.right,right);self.assertEqual(b.writes,[])
            self.assertTrue(list(Path(d).glob('wallpaper-restore.dp2-*.json')))

    def test_pending_blocks_apply_then_reconciled_apply_preserves_right(self):
        import hashlib
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            m,b,j=self.setup_case(d);right=copy.deepcopy(b.right)
            identifier='a'*32;folder=Path(d)/'renders'/identifier;folder.mkdir(parents=True)
            Image.new('RGB',(1080,1920),'navy').save(folder/'image.png')
            atomic_json(folder/'metadata.json',{'id':identifier,'quarantined':False,'targets':['DP-2'],'width':1080,'height':1920,'sha256':hashlib.sha256((folder/'image.png').read_bytes()).hexdigest()})
            with self.assertRaisesRegex(ValueError,'Unreconciled wallpaper transaction'):
                m.apply(DISPLAY,identifier,lambda:'safe')
            self.assertEqual(b.writes,[])
            m.reconcile_pending(DISPLAY,commit=True)
            def replace(display,expected,replacement):
                self.assertEqual(display['id'],'DP-2');self.assertEqual(b.value,expected)
                b.value=copy.deepcopy(replacement);b.writes.append(display['id'])
            b.replace=replace
            self.assertEqual(m.apply(DISPLAY,identifier,lambda:'safe')['state'],'applied')
            self.assertEqual(b.writes,['DP-2']);self.assertEqual(b.right,right)
            self.assertEqual(json.loads(m.journal.read_text())['DP-3'],j['DP-3'])

    def test_refuses_external_changes_and_keeps_exact_receipt(self):
        for field,value in [('image','file:///external.png'),('desktop',99),('activity','other'),('screen',0),('geometry',[1,0,1080,1920]),('fill',True),('plugin','org.kde.slideshow')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                m,b,j=self.setup_case(d);raw=m.journal.read_bytes();b.value[field]=value
                with self.assertRaisesRegex(ValueError,'preserved'): m.reconcile_pending(DISPLAY,commit=True)
                self.assertEqual(m.journal.read_bytes(),raw);self.assertEqual(b.writes,[])
    def test_before_match_preserves_receipt_without_restore(self):
        with tempfile.TemporaryDirectory() as d:
            m,b,j=self.setup_case(d);b.value=copy.deepcopy(j['DP-2']['before'])
            b.value['settings'][0]['values']['FillMode']=1
            self.assertEqual(m.reconcile_pending(DISPLAY,commit=True)['state'],'reconciled_before')
            self.assertEqual(json.loads(m.journal.read_text())['DP-3'],j['DP-3'])
    def test_no_general_string_coercion(self):
        from wallpaper import same_snapshot
        for value in ['01','1.0',True,' 1','7']:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as d:
                m,b,j=self.setup_case(d);j['DP-2']['after']['settings'][0]['values']['FillMode']=value
                self.assertFalse(same_snapshot(b.value,j['DP-2']['after']))
    def test_racing_snapshot_refused(self):
        with tempfile.TemporaryDirectory() as d:
            m,b,j=self.setup_case(d);raw=m.journal.read_bytes();original=b.snapshot
            def snapshot(display):
                result=original(display);b.value['image']='file:///external.png';return result
            b.snapshot=snapshot
            with self.assertRaisesRegex(ValueError,'changed'): m.reconcile_pending(DISPLAY,commit=True)
            self.assertEqual(m.journal.read_bytes(),raw)

if __name__=='__main__': unittest.main()
