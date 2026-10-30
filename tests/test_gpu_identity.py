import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gpu_identity import listener_identity

class ListenerIdentityTests(unittest.TestCase):
    def test_socket_uid_script_and_birth_verified_without_python_blanket(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); proc=root/'proc'; proc.mkdir(); (proc/'net').mkdir()
            app=root/'ComfyUI'; app.mkdir(); (app/'main.py').write_text('# fixture')
            python=root/'python3'; python.write_text('# fixture')
            process=proc/'42'; process.mkdir(); (process/'fd').mkdir()
            (process/'fd/3').symlink_to('socket:[1234]')
            (process/'cwd').symlink_to(app); (process/'exe').symlink_to(python)
            (process/'cmdline').write_bytes(b'python3\0main.py\0--listen\000127.0.0.1\0')
            (process/'stat').write_text('42 (python3) '+' '.join(['S']+['0']*18+['12345']+['0']*5))
            def tcp(uid=os.getuid(), address='0100007F:1FFC'):
                (proc/'net/tcp').write_text('header\n0: '+address+' 00000000:0000 0A 0 0 0 '+str(uid)+' 0 1234\n')
            tcp()
            with patch('gpu_identity.COMFY_ROOT',app):
                self.assertEqual(listener_identity(8188,proc),(42,os.getuid(),12345))
                (process/'cmdline').write_bytes(b'python3\0other.py\0')
                self.assertIsNone(listener_identity(8188,proc))
                (process/'cmdline').write_bytes(b'python3\0-c\0anything\0')
                self.assertIsNone(listener_identity(8188,proc))
                (process/'cmdline').write_bytes(b'python3\0main.py\0')
                tcp(os.getuid()+1); self.assertIsNone(listener_identity(8188,proc))
                tcp(address='00000000:1FFC'); self.assertIsNone(listener_identity(8188,proc))
                tcp(); (process/'stat').write_text('malformed'); self.assertIsNone(listener_identity(8188,proc))
