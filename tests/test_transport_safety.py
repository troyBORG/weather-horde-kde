import unittest
from unittest.mock import patch
from comfy_preview import ComfyTransport, build_workflow


class TransportSafetyTests(unittest.TestCase):
    def test_queue_busy_and_final_guard_block_without_post(self):
        for queue,guard in [({'queue_running':[[0,'other']], 'queue_pending':[]},'safe'), ({'queue_running':[], 'queue_pending':[]},'game_active')]:
            t=ComfyTransport(guard=lambda:guard)
            with patch.object(t,'request',return_value=queue) as request:
                with self.assertRaises(ValueError): t.queue({})
                self.assertEqual(request.call_args_list[0].args,('/queue',))
                self.assertEqual(request.call_count,1)
                self.assertFalse(t.uncertain)

    @patch('comfy_preview.listener_identity',return_value=(123,1000,1))
    def test_ambiguous_post_is_never_retried(self, _identity):
        t=ComfyTransport()
        with patch.object(t,'request',side_effect=[{'queue_running':[],'queue_pending':[]},TimeoutError('ambiguous')]) as request:
            with self.assertRaises(TimeoutError): t.queue({})
            with self.assertRaisesRegex(ValueError,'Ambiguous'): t.queue({})
            self.assertEqual(request.call_count,2)

    def test_only_owned_pending_id_is_deleted_never_global_interrupt(self):
        t=ComfyTransport(); t.owned.add('ours')
        with patch.object(t,'request',return_value={'queue_running':[[0,'other']], 'queue_pending':[[1,'ours'],[2,'not-ours']]}) as request:
            with self.assertRaises(ValueError): t.cancel_pending('not-ours')
            t.cancel_pending('ours')
            self.assertEqual(request.call_args.args,('/queue',{'delete':['ours']}))
        with patch.object(t,'request',return_value={'queue_running':[[0,'ours']], 'queue_pending':[]}) as request:
            t.cancel_pending('ours')
            self.assertEqual(request.call_count,1)

    def test_output_descriptor_and_remote_url_rejected(self):
        for url in ['https://127.0.0.1:8188','http://example.com:8188','http://127.0.0.1:8188/x','http://user@127.0.0.1:8188']:
            with self.assertRaises(ValueError): ComfyTransport(url)
        t=ComfyTransport(); t.owned.add('ours')
        for filename,folder,kind in [('../secret.png','','output'),('file.png','../private','output'),('file.png','','input')]:
            h={'status':{'status_str':'success','completed':True},'outputs':{'9':{'images':[{'filename':filename,'subfolder':folder,'type':kind}]}}}
            with patch.object(t,'history',return_value=h),patch.object(t,'request') as request:
                with self.assertRaises(ValueError): t.image('ours')
                request.assert_not_called()

    def test_native_geometry_never_silently_resized_or_cropped(self):
        for size in [(1080,1920),(1920,1080)]:
            graph=build_workflow('approved','prompt','negative',*size,1)
            self.assertEqual((graph['10']['inputs']['width'],graph['10']['inputs']['height']),size)
            self.assertEqual(graph['10']['inputs']['crop'],'disabled')
        with self.assertRaises(ValueError): build_workflow('approved','prompt','negative',65,128,1)
        graph=build_workflow('approved','prompt','negative',64,128,1)
        self.assertEqual(graph['4']['inputs']['width'],64)
        self.assertEqual(graph['4']['inputs']['height'],128)

if __name__ == '__main__': unittest.main()
