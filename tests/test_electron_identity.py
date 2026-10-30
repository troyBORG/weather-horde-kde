"""Synthetic proc fixtures; no owner bus, tokens, GPU work or app launch."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import safety

class ElectronIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path.home()); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.proc=self.root/'proc'; self.proc.mkdir()
        self.runtime=self.root/'electron'; self.runtime.write_text('runtime fixture')
        self.app=self.root/'app.asar'; self.app.write_text('app fixture')
        self.make(10,11,['electron','--type=gpu-process','--user-data-dir=/private/Element'])
        self.make(11,12,['electron','--type=zygote'])
        self.make(12,1,['electron',str(self.app)])
        self.addCleanup(patch.stopall)
        patch.object(safety,'ELECTRON_APPS',{str(self.app):'Element'},create=True).start()
        patch.object(safety,'ELECTRON_RUNTIME',str(self.runtime),create=True).start()
        patch.object(safety,'INSTALL_UID',os.getuid(),create=True).start()
    def make(self,pid,parent,args):
        p=self.proc/str(pid); p.mkdir(exist_ok=True)
        if not (p/'exe').exists(): (p/'exe').symlink_to(self.runtime)
        (p/'stat').write_text(f'{pid} (electron) '+' '.join(['S',str(parent)]+['0']*17+['12345']))
        (p/'cmdline').write_bytes(b'\0'.join(os.fsencode(a) for a in args)+b'\0')
    def identity(self):
        return getattr(safety,'electron_app_identity',lambda *a,**k:None)(10,proc=self.proc)
    def test_verified_element_ancestry(self):
        self.assertEqual(self.identity(),'Element')
