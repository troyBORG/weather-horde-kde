"""Actual Plasma controls + authenticated ephemeral controller, no GPU."""
import json, os, shutil, subprocess, tempfile, threading, unittest, time
from pathlib import Path
from unittest.mock import patch
from weather_controller import Controller, make_server
from test_night_realism import LOCATION
from model_catalog import PROFILES

class SceneQml(unittest.TestCase):
    def test_controls_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp); c=Controller(d/'state',checkpoint='old.safetensors');c.settings['location']=LOCATION
            c.displays=[{'id':'LEFT','width':1080,'height':1920,'orientation':'portrait'}]
            c.models=[dict(id='fixture.safetensors',**PROFILES['sdxl'])]
            c.refresh_models=lambda:c.models
            server=make_server(c,0); threading.Thread(target=server.serve_forever,daemon=True).start()
            package=Path('plasma-widget/org.troyborg.weatherhorde').resolve()
            shutil.copytree(package,d/'share/plasma/plasmoids'/package.name)
            (d/'runtime').mkdir(mode=0o700)
            (d/'config.json').write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}','token':c.token,'screenshot':str(Path('artifacts/scene-rotation-controls.png').resolve())}))
            (d/'test.qml').write_text('''import QtQuick
Item {
 required property var widget
 property int step: 0
 function find(item,name) {if(item.objectName===name)return item;for(let i=0;i<item.children.length;i++){let v=find(item.children[i],name);if(v)return v}return null}
 function fail(message){console.error(message);Qt.quit()}
 Component.onCompleted: widget.refreshStatus()
 Timer {interval:100;running:true;repeat:true;onTriggered:{
  if(!widget.online || widget.busy)return
  if(step===0){
   const per=find(widget.fullRepresentationItem,"monitorSceneSelector")
   if(!per || !widget.rotationSupported){fail("MONITOR_SCENE_CONTROL_MISSING");return}
   find(widget.fullRepresentationItem,"sceneSelector").currentIndex=5
   find(widget.fullRepresentationItem,"sceneSelector").activated(5);step=20
  }else if(step===20 && widget.sceneKind==="random"){
   const target=find(widget.fullRepresentationItem,"sceneMonitorSelector")
   target.currentIndex=0;target.activated(0)
   const per=find(widget.fullRepresentationItem,"monitorSceneSelector")
   per.currentIndex=5;per.activated(5);step=21
  }else if(step===21 && widget.sceneOverrides.LEFT==="river"){
   const per=find(widget.fullRepresentationItem,"monitorSceneSelector")
   per.currentIndex=0;per.activated(0);step=22
  }else if(step===22 && !widget.sceneOverrides.LEFT){
   const scene=find(widget.fullRepresentationItem,"sceneSelector")
   const obs=find(widget.fullRepresentationItem,"observationEnable")
   const model=find(widget.fullRepresentationItem,"modelSelector")
   if(!scene || !obs || !model || !scene.enabled){fail("SCENE_CONTROLS_MISSING");return}
   const framing=find(widget.fullRepresentationItem,"framingSelector")
   if(!framing || !framing.enabled){fail("FRAMING_CONTROL_MISSING");return}
   framing.currentIndex=2; framing.activated(2);step=10
  }else if(step===10 && widget.framingMode==="desktop_portrait"){
   find(widget.fullRepresentationItem,"sceneSelector").currentIndex=2
   find(widget.fullRepresentationItem,"sceneSelector").activated(2);step=1
  }else if(step===1 && widget.sceneKind==="woodland"){
   find(widget.fullRepresentationItem,"observationEnable").clicked();step=2
  }else if(step===2 && widget.observationActive){
   if(widget.weatherSource.indexOf("Manual")<0){fail("SOURCE_NOT_VISIBLE");return}
   widget.saveSettings({checkpoint:"fixture.safetensors",comparison_seed:123});step=3
  }else if(step===3 && widget.selectedCheckpoint==="fixture.safetensors"){
   widget.setObservation({enabled:false});step=4
  }else if(step===4 && !widget.observationActive){
   if(widget.promptVersion!=="night-lunar-2"){fail("PROMPT_VERSION_MISSING");return}
   widget.acceptStatus({state:"idle",interval_minutes:60,capabilities:{},guard:{decision:"unknown"}})
   if(find(widget.fullRepresentationItem,"monitorSceneSelector").enabled || find(widget.fullRepresentationItem,"sceneSelector").enabled || find(widget.fullRepresentationItem,"framingSelector").enabled){fail("OLD_BACKEND_ENABLED");return}
   widget.refreshStatus()
   step=5
  }else if(step===5 && widget.sceneSupported){
   widget.fullRepresentationItem.contentItem.contentY=find(widget.fullRepresentationItem,"sceneControlsGroup").y
   step=6
  }else if(step===6){
   const options=find(widget.fullRepresentationItem,"calendarOptionsToggle")
   if(!options){fail("CALENDAR_OPTIONS_MISSING");return}
   options.checked=true
   const toggle=find(widget.fullRepresentationItem,"holidayThemesToggle")
   toggle.checked=true;toggle.clicked();step=30
  }else if(step===30 && widget.calendarSettings.holiday_themes===true){
   const strength=find(widget.fullRepresentationItem,"holidayStrengthSelector")
   strength.currentIndex=0;strength.activated(0);step=31
  }else if(step===31 && widget.calendarSettings.theme_strength==="subtle"){
   find(widget.fullRepresentationItem,"holidayPreviewDate").text="2026-10-31"
   find(widget.fullRepresentationItem,"holidayPreviewButton").clicked();step=32
  }else if(step===32 && widget.previewText.indexOf("fixture_weather")>=0){
   if(widget.automationEnabled){fail("THEMES_ENABLED_AUTO");return}
   console.log("SCENE_QML_PASS");Qt.quit()
  }
 }}
 Timer {interval:10000;running:true;onTriggered:fail("SCENE_TIMEOUT "+step+" "+widget.actionNotice)}
}''')
            env=os.environ|{'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            try:
                p=subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(Path('artifacts/plasma-harness/plasma-harness').resolve()),str(d/'config.json'),str(d/'test.qml')],env=env,capture_output=True,text=True,timeout=20)
                self.assertIn('SCENE_QML_PASS',p.stderr,p.stderr)
                self.assertNotIn('Error:',p.stderr)
                self.assertEqual(c.settings['scene_kind'],'woodland')
                self.assertEqual(c.settings['framing'],'desktop_portrait')
                self.assertEqual(c.settings['comparison_seed'],123)
                self.assertFalse(c.observation_status()['active'])
                print(p.stderr)
            finally:server.shutdown();server.server_close()
