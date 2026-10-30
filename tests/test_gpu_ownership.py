import unittest
from unittest.mock import patch
from safety import decide

class OwnershipTests(unittest.TestCase):
    def test_verified_own_load_only_does_not_mask_other_clients_or_game(self):
        good={'processes':['kwin_wayland','python'], 'complete':True,'age':0,'sample_gap':10,
              'utilization':[90,95],'free_mib':16000,'gpu_clients':['/usr/bin/kwin_wayland','/venv/bin/python'],
              'gpu_pids':[10,20], 'owned_pid':20, 'client_sm':{10:1,20:95},
              'previous_client_sm':{10:2,20:90}, 'previous_owned_pid':20, 'owned_active':True, 'previous_owned_active':True}
        self.assertEqual(decide(good),'safe')
        for delta, expected in [({'owned_pid':None},'unknown'),({'previous_owned_pid':None},'gpu_busy'),
             ({'client_sm':{20:95}},'unknown'),({'client_sm':{10:50,20:45},'previous_client_sm':{10:40,20:50}},'gpu_busy'),
             ({'gpu_clients':['kwin_wayland','python','python'],'gpu_pids':[10,20,30]},'unknown'),
             ({'processes':['Resonite','python']},'game_active'),({'processes':['vrserver','python']},'vr_active'),
             ({'client_sm':{10:1,20:0}},'unknown'),
             ({'client_sm':{10:1,20:95,30:0}},'unknown'),
             ({'complete':False},'unknown'),({'free_mib':1000},'insufficient_vram')]:
            with self.subTest(delta=delta): self.assertEqual(decide(good|delta),expected)

    def test_collector_preserves_identity_and_missing_pmon_defers(self):
        import os
        import subprocess
        from safety import collect
        from types import SimpleNamespace
        transport=SimpleNamespace(owned_gpu_pid=lambda:20,owned_gpu_active=True)
        usage=['0 10 G 1 0 0 0 0 0 kwin\n0 20 C 95 0 0 0 0 0 python']
        def run(args,**kwargs):
            if args[:2]==['ps','-eo']: out='kwin_wayland\npython'
            elif args[:2]==['ps','-C']: out=str(os.getuid())
            elif '-q' in args: out='<nvidia_smi_log><gpu><processes><process_info><pid>10</pid><process_name>kwin_wayland</process_name></process_info><process_info><pid>20</pid><process_name>python</process_name></process_info></processes></gpu></nvidia_smi_log>'
            elif 'pmon' in args: out=usage[0]
            else: out='95, 16000'
            return subprocess.CompletedProcess(args,0,stdout=out)
        prior={'at':90,'util':90,'client_sm':{10:1,20:90},'owned_pid':20,'owned_active':True}
        with patch('safety.subprocess.run',side_effect=run), patch('safety.time.monotonic',return_value=100):
            decision,sample=collect(prior,transport)
            self.assertEqual(decision['decision'],'safe')
            self.assertEqual(sample['owned_pid'],20)
            usage[0]='0 10 G - - - - - - kwin\n0 20 C 95 0 0 0 0 0 python'
            self.assertEqual(collect(prior,transport)[0]['decision'],'unknown')

    def test_transport_ownership_requires_exclusive_owned_queue_and_listener(self):
        from comfy_preview import ComfyTransport
        t=ComfyTransport(); t.owned.add('ours'); t.active_job='ours'
        row=[1,'ours',{}, {'client_id':t.client_id},['9']]
        with patch('comfy_preview.listener_identity',return_value=(20,100,123)), patch.object(t,'request',return_value={'queue_running':[row],'queue_pending':[]}):
            self.assertEqual(t.owned_gpu_pid(),20)
        with patch('comfy_preview.listener_identity',return_value=None): self.assertIsNone(t.owned_gpu_pid())
        with patch('comfy_preview.listener_identity',return_value=(20,100,124)), patch.object(t,'request',return_value={'queue_running':[row],'queue_pending':[]}):
            self.assertIsNone(t.owned_gpu_pid()) # PID reuse / server restart
        t.listener=None
        for queue in [{'queue_running':[row,[2,'foreign',{}, {},[]]],'queue_pending':[]},
                      {'queue_running':[[1,'ours',{}, {'client_id':'foreign'},[]]],'queue_pending':[]}]:
            with patch('comfy_preview.listener_identity',return_value=(20,100,123)), patch.object(t,'request',return_value=queue):
                self.assertIsNone(t.owned_gpu_pid())
