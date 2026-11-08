"""Real packaged Plasma controls and controller HTTP; no GPU or owner bus."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import zipfile
from weather_controller import Controller, make_server
from model_catalog import PROFILES


class DaypartQml(unittest.TestCase):
    def test_checklists_save_reload_without_render_or_hydration_writes(self):
        subprocess.run(['cmake','-S','tests/plasma-harness','-B','artifacts/plasma-harness'],check=True,capture_output=True)
        subprocess.run(['cmake','--build','artifacts/plasma-harness'],check=True,capture_output=True)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp); c=Controller(d/'state',checkpoint='manual')
            c.models=[dict(id=x,**PROFILES['sdxl']) for x in ['A.safetensors','B.safetensors','C.safetensors']]
            c.save(); calls=[]; dispatch=c.dispatch
            def record(method,path,body,scheduled=False):
                calls.append((method,path,body)); return dispatch(method,path,body,scheduled=scheduled)
            c.dispatch=record
            package=d/'share/plasma/plasmoids/org.troyborg.weatherhorde'
            with zipfile.ZipFile('artifacts/org.troyborg.weatherhorde.plasmoid') as archive: archive.extractall(package)
            (d/'runtime').mkdir(mode=0o700)
            server=make_server(c,0); threading.Thread(target=server.serve_forever,daemon=True).start()
            (d/'config.json').write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}','token':c.token}))
            (d/'test.qml').write_text('''import QtQuick
Item {
 required property var widget
 property int step: 0
 function find(item,name){if(item.objectName===name)return item;for(let i=0;i<item.children.length;i++){let v=find(item.children[i],name);if(v)return v}return null}
 function control(name){return find(widget.fullRepresentationItem,name)}
 function fail(message){console.error(message);Qt.quit()}
 Component.onCompleted: widget.refreshStatus()
 Timer {interval:120;running:true;repeat:true;onTriggered:{
  if(!widget.online || widget.busy)return
  if(step===0){
   control("sceneTab").click()
   if(!control("modelModeSelector")){fail("POOL_CONTROLS_MISSING");return}
   if(widget.modelPolicy.mode==="lighting") {
    const missing=control("dayPool_2")
    if(!missing.checked || missing.text.indexOf("unavailable")<0){fail("UNAVAILABLE_CHOICE_LOST");return}
    if(widget.modelPolicy.mapping.twilight!=="day"){fail("MAPPING_NOT_PERSISTED");return}
    step=20;return
   }
   control("modelModeSelector").currentIndex=1; control("modelModeSelector").activated(1);step=1
  }else if(step>=1 && step<=5){
   const names=["dayPool_0","dayPool_1","dayPool_2","nightPool_1","nightPool_2"]
   const item=control(names[step-1]);if(!item){fail("CHECKLIST_MISSING");return}
   item.click();step++
  }else if(step===6 || step===20){
   if(widget.modelPolicy.day.join(",")!=="A.safetensors,B.safetensors,C.safetensors" || widget.modelPolicy.night.join(",")!=="B.safetensors,C.safetensors"){fail("SAVED_SETS_WRONG");return}
   if(control("daypartMappingToggle").checked){fail("MAPPING_NOT_COLLAPSED");return}
   control("daypartMappingToggle").click();step=21
  }else if(step===21){
   const names=["daytime","golden hour","blue hour","twilight","night"]
   for(let i=0;i<names.length;i++){if(!control("mapping_"+names[i]).visible){fail("MAPPING_MISSING");return}}
   if(widget.modelPolicy.mapping.twilight!=="day"){
    control("mapping_twilight").currentIndex=0;control("mapping_twilight").activated(0);step=22;return
   }
   console.log("DAYPART_POOLS_QML_PASS");Qt.quit()
  }else if(step===22){
   if(widget.modelPolicy.mapping.twilight!=="day"){fail("MAPPING_SAVE_FAILED");return}
   console.log("DAYPART_POOLS_QML_PASS");Qt.quit()
  }
 }}
 Timer {interval:9000;running:true;onTriggered:fail("DAYPART_TIMEOUT "+step+" "+widget.actionNotice)}
}''')
            env=os.environ|{'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            try:
                for attempt in range(2):
                    if attempt: c.models=c.models[:2]
                    before=len([x for x in calls if x[0]!='GET'])
                    p=subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(Path('artifacts/plasma-harness/plasma-harness').resolve()),str(d/'config.json'),str(d/'test.qml')],env=env,capture_output=True,text=True,timeout=15)
                    self.assertIn('DAYPART_POOLS_QML_PASS',p.stderr,p.stderr)
                    self.assertNotIn('Error:',p.stderr)
                    if attempt: self.assertEqual(before,len([x for x in calls if x[0]!='GET']))
                    fresh=Controller(d/'state',checkpoint='manual')
                    self.assertEqual(fresh.settings['model_policy']['day'],['A.safetensors','B.safetensors','C.safetensors'])
                    self.assertEqual(fresh.settings['model_policy']['night'],['B.safetensors','C.safetensors'])
                    self.assertEqual(fresh.checkpoint,'manual'); self.assertFalse(fresh.settings['automation_enabled'])
                    print(p.stderr)
                self.assertEqual(len([x for x in calls if x[0]=='PUT']),7)
                self.assertFalse(any(x[0]=='POST' for x in calls),calls)
                self.assertIsNone(c.render_thread)
            finally: server.shutdown();server.server_close()
