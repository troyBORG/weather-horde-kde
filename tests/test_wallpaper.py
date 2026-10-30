import copy, io, tempfile, unittest, time
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from weather_controller import Controller
from comfy_preview import PreviewStore

class Backend:
    def __init__(self):
        self.value={'desktop':12,'activity':'fixture','screen':0,'geometry':[0,0,64,128], 'plugin':'org.kde.image','image':'file:///previous.png','fill':2}
        self.writes=[]
    def snapshot(self, display): return copy.deepcopy(self.value)
    def replace(self, display, expected, replacement):
        if self.value != expected: raise ValueError('Desktop changed')
        self.value=copy.deepcopy(replacement); self.writes.append(copy.deepcopy(replacement))

class WallpaperTests(unittest.TestCase):
    def setup_controller(self, d):
        from wallpaper import WallpaperManager
        backend=Backend()
        c=Controller(d, checkpoint='fixture',render_guard=lambda:'safe')
        c.wallpaper=WallpaperManager(Path(d), backend)
        c.displays=[{'id':'DP-1','width':64,'height':128,'scale':1,'x':0,'y':0}]
        data=io.BytesIO(); Image.new('RGB',(64,128),'navy').save(data,'PNG')
        c.image_preview=c.store.save(data.getvalue(),(64,128),{'targets':['DP-1']})
        return c,backend

    def test_explicit_apply_and_restore_readback(self):
        with tempfile.TemporaryDirectory() as d:
            c,b=self.setup_controller(d)
            old=copy.deepcopy(b.value)
            body={'target':'DP-1','preview_id':c.image_preview['id'],'confirmation':'Apply this validated preview'}
            result=c.dispatch('POST','/v1/apply',body)
            self.assertEqual(result['state'],'applied')
            self.assertNotEqual(b.value['image'],old['image'])
            self.assertTrue(c.status()['restore_available'])
            self.assertEqual(c.dispatch('POST','/v1/restore',{'target':'DP-1','confirmation':'Restore previous wallpaper'})['state'],'restored')
            self.assertEqual(b.value,old)
            self.assertEqual(len(b.writes),2)

    def test_fail_closed_unconfirmed_unknown_mismatch_quarantine_and_tamper(self):
        for kind in ('confirmation','all','wrongtarget','size','quarantine','tamper','busy','changed'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                c,b=self.setup_controller(d)
                body={'target':'DP-1','preview_id':c.image_preview['id'],'confirmation':'Apply this validated preview'}
                if kind=='confirmation': body.pop('confirmation')
                if kind=='all': body['target']='all'
                if kind=='wrongtarget': c.displays[0]['id']='DP-2'; body['target']='DP-2'
                if kind=='size': c.displays[0]['width']=128
                if kind=='quarantine':
                    import json
                    p=Path(d)/'renders'/body['preview_id']/'metadata.json'
                    record=json.loads(p.read_text());record['quarantined']=True;p.write_text(json.dumps(record))
                if kind=='tamper': (Path(d)/'renders'/body['preview_id']/'image.png').write_bytes(b'invalid')
                if kind in ('guard','override'): c.render_guard=lambda:'unknown'
                if kind=='override': c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})
                if kind=='busy': c.render_lock.acquire()
                if kind=='changed':
                    def refuse(*args): raise ValueError('Desktop changed')
                    b.replace=refuse
                with self.assertRaises(ValueError): c.dispatch('POST','/v1/apply',body)
                self.assertEqual(b.writes,[])

    def test_dynamic_plugin_and_complete_settings_restore(self):
        with tempfile.TemporaryDirectory() as d:
            c,b=self.setup_controller(d)
            b.value.update(plugin='org.example.daynight', image='', settings=[{'group':['General'],'values':{'Day':'file:///day.jpg','Night':'file:///night.jpg','Transition':900}}])
            before=copy.deepcopy(b.value)
            c.dispatch('POST','/v1/apply',{'target':'DP-1','preview_id':c.image_preview['id'],'confirmation':'Apply this validated preview'})
            self.assertEqual(b.value['plugin'],'org.kde.image')
            c.dispatch('POST','/v1/restore',{'target':'DP-1','confirmation':'Restore previous wallpaper'})
            self.assertEqual(b.value,before)

    def test_readback_failure_never_claims_applied(self):
        with tempfile.TemporaryDirectory() as d:
            c,b=self.setup_controller(d)
            b.replace=lambda *args:None
            with self.assertRaisesRegex(ValueError,'readback'):
                c.dispatch('POST','/v1/apply',{'target':'DP-1','preview_id':c.image_preview['id'],'confirmation':'Apply this validated preview'})
            self.assertNotEqual(c.state,'applied')
