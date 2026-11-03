"""Navigate real Plasma pages and make authenticated settings roundtrips; no GPU."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from weather_controller import Controller, make_server

class WidgetNavigation(unittest.TestCase):
    def test_tabs_disclosures_and_layout_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            c = Controller(d/'state')
            c.displays = [{'id':'LEFT','width':1080,'height':1920,'orientation':'portrait'}]
            writes = []
            dispatch = c.dispatch
            def record_dispatch(method, path, body, scheduled=False):
                if method == 'PUT' and path == '/v1/settings':
                    writes.append(dict(body))
                return dispatch(method, path, body, scheduled=scheduled)
            c.dispatch = record_dispatch
            server = make_server(c, 0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            package = Path('plasma-widget/org.troyborg.weatherhorde').resolve()
            shutil.copytree(package, d/'share/plasma/plasmoids'/package.name)
            (d/'runtime').mkdir(mode=0o700)
            original = dict(c.settings)
            script = '''import QtQuick
Item {
 required property var widget
 property int step: 0
 property int capture: 0
 function find(item,name) { if(item.objectName===name)return item; for(let i=0;i<item.children.length;i++){let v=find(item.children[i],name);if(v)return v} return null }
 function control(name) { return find(widget.fullRepresentationItem,name) }
 function fail(message) { console.error(message); Qt.quit() }
 function page(index) { const tab=control(["wallpaperTab","scheduleTab","sceneTab","advancedTab"][index]); tab.click() }
 Component.onCompleted: widget.refreshStatus()
 Timer { interval:150; running:true; repeat:true; onTriggered: {
  if(!widget.online || widget.busy)return
  if(step===0){
   if(control("sectionTabs").currentIndex!==0 || !control("wallpaperPage").visible || control("scenePage").visible){fail("BAD_DEFAULT_PAGE");return}
   if(!control("connectedPanoramaToggle").visible || widget.connectedPanorama){fail("LAYOUT_NOT_DEFAULT_OFF");return}
   const layout=control("connectedPanoramaToggle"); layout.currentIndex=1; layout.activated(1); step=1
  }else if(step===1 && widget.connectedPanorama){
   const layout=control("connectedPanoramaToggle"); layout.currentIndex=0; layout.activated(0); step=2
  }else if(step===2 && !widget.connectedPanorama){
   page(1); step=3
  }else if(step===3){
   if(!control("schedulePage").visible || control("wallpaperPage").visible){fail("SCHEDULE_NOT_EXCLUSIVE");return}
   const interval=control("scheduleInterval"); interval.currentIndex=3; interval.activated(3); step=4
  }else if(step===4 && widget.intervalMinutes===30){
   page(2);step=5
  }else if(step===5){
   if(!control("sceneSelector").visible || control("schedulePage").visible){fail("SCENE_NOT_VISIBLE");return}
   page(3);step=6
  }else if(step===6){
   for(const name of ["pairing","observation","seed","testing","diagnostics"]){if(control(name+"Disclosure").checked){fail("ADVANCED_NOT_COLLAPSED");return}}
   if(control("runtimeBuildIdentity").visible){fail("RAW_DETAILS_VISIBLE");return}
   control("diagnosticsDisclosure").checked=true;step=7
  }else if(step===7){
   if(!control("runtimeBuildIdentity").visible || widget.runtimeBuild.length!==64 || control("widgetBuildIdentity").text.indexOf("sections-1")<0){fail("BUILD_ID_MISSING");return}
   control("diagnosticsDisclosure").checked=false;page(CAPTURE_PAGE);step=8
  }else if(step===8){
   const reason=control("persistentSafetyReason"); const tabs=control("sectionTabs")
   if(!reason.visible || reason.height<=0 || tabs.y+tabs.height>widget.fullRepresentationItem.height){fail("PERSISTENT_STATUS_CLIPPED");return}
   console.log("WIDGET_NAVIGATION_PASS");Qt.quit()
  }
 }}
 Timer {interval:10000;running:true;onTriggered:fail("NAVIGATION_TIMEOUT "+step)}
}'''
            env = os.environ | {'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            try:
                for index, name in enumerate(('wallpaper','schedule','scene','advanced')):
                    with self.subTest(page=name):
                        (d/'test.qml').write_text(script.replace('CAPTURE_PAGE', str(index)))
                        (d/'config.json').write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}','token':c.token,'screenshot':str(Path(f'artifacts/widget-{name}.png').resolve())}))
                        p = subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(Path('artifacts/plasma-harness/plasma-harness').resolve()),str(d/'config.json'),str(d/'test.qml')], env=env,capture_output=True,text=True,timeout=20)
                        self.assertEqual(p.returncode,0,p.stderr)
                        self.assertIn('WIDGET_NAVIGATION_PASS',p.stderr,p.stderr)
                        self.assertNotIn('Error:',p.stderr)
                        print(p.stderr)
                self.assertEqual(writes, [
                    {'connected_panorama': True}, {'connected_panorama': False},
                    {'interval_minutes': 30},
                ] * 4, 'Navigation/disclosures must not save preferences')
                self.assertFalse(c.settings['connected_panorama'])
                self.assertEqual(c.settings['interval_minutes'],30)
                for key in ('automation_enabled','automation_kind','automation_target'):
                    self.assertEqual(c.settings[key],original[key])
            finally:
                server.shutdown()
                server.server_close()
