from test_electron_identity import ElectronIdentityTests
from unittest.mock import patch
from pathlib import Path
import os
import safety

GOOD=dict(processes=['kwin_wayland'],complete=True,age=0,sample_gap=10,utilization=[0,0],free_mib=20000)

class ElectronPolicyTests(ElectronIdentityTests):
    def test_identity_and_policy_integration(self):
        with patch.object(safety,'electron_app_identity',return_value='Element'), patch.object(safety.os,'readlink',return_value=safety.ELECTRON_RUNTIME):
            identity=safety.gpu_client_identity(10,'electron --private=DO_NOT_REPORT')
        self.assertEqual(identity,{'pid':10,'name':'Element','source':'proc_electron_ancestry'})
        base=GOOD|{'gpu_clients':['Element'],'gpu_pids':[10],'gpu_client_identities':[identity]}
        self.assertEqual(safety.assess(base)[0],'safe')
        for change,expected in [({'utilization':[90,90]},'gpu_busy'),({'free_mib':1},'insufficient_vram'),({'processes':['Resonite']},'game_active'),({'processes':['vrserver']},'vr_active'),({'complete':False},'unknown'),({'gpu_pids':[11]},'unknown')]:
            self.assertEqual(safety.assess(base|change)[0],expected)
        self.assertEqual(safety.assess(GOOD|{'gpu_clients':['Element']})[0],'unknown')
    def test_collect_carries_verified_identity_without_private_arguments(self):
        from test_gpu_client_parsing import GPUClientParsingTests
        real=safety.electron_app_identity
        with patch.object(safety,'electron_app_identity',side_effect=lambda pid: real(10,proc=self.proc)):
            original=safety.os.readlink
            def link(path):
                return safety.ELECTRON_RUNTIME if str(path)=='/proc/424242/exe' else original(path)
            with patch.object(safety.os,'readlink',side_effect=link):
                result=GPUClientParsingTests().collect_fixture()
        self.assertEqual(result['decision'],'safe')
        self.assertEqual(result['gpu_client_identities'],[{'pid':424242,'name':'Element','source':'proc_electron_ancestry'}])
        self.assertNotIn('/private',str(result))
        self.assertNotIn('DO_NOT_REPORT',str(result))
    def test_verified_obsidian(self):
        with patch.object(safety,'ELECTRON_APPS',{str(self.app):'Obsidian'}):
            self.assertEqual(self.identity(),'Obsidian')
    def test_spoof_arguments_rejected(self):
        for args in [['electron','--user-data-dir=/private/Element'],['electron','evil.js',str(self.app)],['electron','--app='+str(self.app)],['electron',str(self.app)+'-fake'],['electron',str(self.app),'--type=gpu-process']]:
            self.make(12,1,args)
            self.assertIsNone(self.identity())
    def test_wrong_runtime_or_intermediate_process(self):
        (self.proc/'11/exe').unlink(); (self.proc/'11/exe').symlink_to('/usr/bin/python3')
        self.assertIsNone(self.identity())
        (self.proc/'11/exe').unlink(); (self.proc/'11/exe').symlink_to(self.runtime)
        self.make(11,12,['electron','evil.js']); self.assertIsNone(self.identity())
    def test_foreign_uid(self):
        with patch.object(safety.os,'getuid',return_value=os.getuid()+1): self.assertIsNone(self.identity())
    def test_missing_or_oversized_evidence(self):
        (self.proc/'11/cmdline').write_bytes(b'x'*16385); self.assertIsNone(self.identity())
        (self.proc/'11/cmdline').unlink(); self.assertIsNone(self.identity())
    def test_cycle_and_depth_bound(self):
        self.make(11,10,['electron','--type=zygote']); self.assertIsNone(self.identity())
        for n in range(11,18): self.make(n,n+1,['electron','--type=zygote'])
        self.make(18,1,['electron',str(self.app)]); self.assertIsNone(self.identity())
    def test_reused_pid_or_reparent_during_inspection(self):
        original=Path.open
        for replacement in ['12346','12345']:
            self.make(10,11,['electron','--type=gpu-process'])
            count=0
            def opened(path,*args,**kwargs):
                nonlocal count
                if path==self.proc/'10/stat':
                    count+=1
                    if count==2:
                        with original(path,'w') as f:
                            f.write('10 (electron) '+' '.join(['S','99' if replacement=='12345' else '11']+['0']*17+[replacement]))
                return original(path,*args,**kwargs)
            with patch.object(Path,'open',opened): self.assertIsNone(self.identity())
    def test_unsafe_installation(self):
        self.app.chmod(0o666); self.assertIsNone(self.identity())
    def test_unreadable_proc_never_uses_app_argument(self):
        with patch.object(safety.os,'readlink',side_effect=PermissionError):
            result=safety.gpu_client_identity(10,'/usr/lib/electron43/electron /usr/lib/element/app.asar --user-data-dir=/private/Element')
        self.assertEqual(result['name'],'electron')
        self.assertEqual(safety.assess(GOOD|{'gpu_clients':[result['name']]})[0],'unknown')
