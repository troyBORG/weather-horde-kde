"""Exact packaged QML, authenticated GET refresh and explicit selection; no GPU."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch, Mock
from weather_controller import Controller, make_server
from model_catalog import Catalog, PROFILES


class ModelDiscoveryQml(unittest.TestCase):
    def test_packaged_discover_roundtrip(self):
        subprocess.run(['cmake','-S','tests/plasma-harness','-B','artifacts/plasma-harness'],check=True,capture_output=True)
        subprocess.run(['cmake','--build','artifacts/plasma-harness'],check=True,capture_output=True)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);c=Controller(d/'state',checkpoint='saved.safetensors');c.enforce_models=True
            c.transport=Mock();c.save();before=(c.root/'settings.json').read_bytes()
            calls=[];dispatch=c.dispatch
            def record(method,path,body,scheduled=False):
                calls.append((method,path));return dispatch(method,path,body,scheduled=scheduled)
            c.dispatch=record
            result=Catalog();result.append(dict(id='folder/renamed.safetensors',**PROFILES['sdxl']))
            result.excluded=[dict(id='unsupported.safetensors',reason='Unsupported architecture')]
            package=d/'share/plasma/plasmoids/org.troyborg.weatherhorde'
            with zipfile.ZipFile('artifacts/org.troyborg.weatherhorde.plasmoid') as archive:archive.extractall(package)
            (d/'runtime').mkdir(mode=0o700)
            server=make_server(c,0);threading.Thread(target=server.serve_forever,daemon=True).start()
            (d/'config.json').write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}','token':c.token}))
            (d/'test.qml').write_text('''import QtQuick
Item {
 required property var widget
 property int step: 0
 function find(item,name){if(item.objectName===name)return item;for(let i=0;i<item.children.length;i++){let v=find(item.children[i],name);if(v)return v}return null}
 function control(name){return find(widget.fullRepresentationItem,name)}
 function fail(message){console.error(message);Qt.quit()}
 Component.onCompleted: widget.refreshStatus()
 Timer {interval:100;running:true;repeat:true;onTriggered:{
  if(!widget.online || widget.busy)return
  if(step===0){
   control("sceneTab").click()
   if(!control("discoverModelsButton")){fail("DISCOVER_MISSING");return}
   control("discoverModelsButton").click();step=1
  }else if(step===1 && widget.localModels.length===1){
   if(widget.selectedCheckpoint!=="saved.safetensors" || control("modelSelector").currentIndex!==-1){fail("SELECTION_CHANGED");return}
   if(control("modelExclusionsToggle").checked){fail("EXCLUSIONS_NOT_COLLAPSED");return}
   control("modelExclusionsToggle").click();step=2
  }else if(step===2){
   if(!control("modelExclusionsText").visible || control("modelExclusionsText").text.indexOf("Unsupported architecture")<0){fail("REASONS_MISSING");return}
   console.log("MODEL_DISCOVERY_QML_PASS");Qt.quit()
  }
 }}
 Timer {interval:7000;running:true;onTriggered:fail("MODEL_DISCOVERY_TIMEOUT "+step+" "+widget.actionNotice)}
}''')
            env=os.environ|{'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            try:
                with patch('model_catalog.discover_models',return_value=result):
                    p=subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(Path('artifacts/plasma-harness/plasma-harness').resolve()),str(d/'config.json'),str(d/'test.qml')],env=env,capture_output=True,text=True,timeout=15)
                self.assertIn('MODEL_DISCOVERY_QML_PASS',p.stderr,p.stderr)
                self.assertNotIn('Error:',p.stderr)
                self.assertIn(('GET','/v1/models/refresh'),calls)
                self.assertFalse(any(method!='GET' for method,path in calls),calls)
                self.assertEqual(before,(c.root/'settings.json').read_bytes())
                self.assertEqual(c.checkpoint,'saved.safetensors')
                self.assertEqual(c.transport.mock_calls,[])
                print(p.stderr)
            finally:server.shutdown();server.server_close()
