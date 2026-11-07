"""Packaged Plasma controls against authenticated fixture controller; no GPU."""
import json, os, subprocess, tempfile, threading, unittest, zipfile
from pathlib import Path
from weather_controller import Controller, make_server

class ForcedRefreshQml(unittest.TestCase):
    def test_separate_force_consent_and_disable_roundtrip(self):
        subprocess.run(['cmake','-S','tests/plasma-harness','-B','artifacts/plasma-harness'],check=True,capture_output=True)
        subprocess.run(['cmake','--build','artifacts/plasma-harness'],check=True,capture_output=True)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);c=Controller(d/'state');calls=[]
            c.settings['interval_minutes']=5
            original=c.dispatch
            def dispatch(method,path,body,scheduled=False):
                if method!='GET': calls.append((method,path,body))
                return original(method,path,body,scheduled=scheduled)
            c.dispatch=dispatch
            package=d/'share/plasma/plasmoids/org.troyborg.weatherhorde'
            with zipfile.ZipFile('artifacts/org.troyborg.weatherhorde.plasmoid') as z:z.extractall(package)
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
   control("scheduleTab").click()
   if(!control("forceDisclosure")){fail("FORCE_MISSING");return}
   control("forceDisclosure").click();step=1
  }else if(step===1){
   if(control("forceToggle").enabled){fail("RISK_NOT_REQUIRED");return}
   control("forceRisk").click(); widget.forceSupported=false
   if(control("forceToggle").enabled){fail("CAPABILITY_NOT_REQUIRED");return}
   widget.refreshStatus();step=2
  }else if(step===2){
   if(!control("forceToggle").enabled){fail("FORCE_NOT_ENABLED");return}
   control("forceToggle").click();step=3
  }else if(step===3 && widget.forceActive){
   if(widget.statusTitle.indexOf("Force")<0){fail("FORCE_TILE_MISSING");return}
   if(widget.refreshSummary.indexOf("Last verified wallpaper change")<0 || control("forceStatus").text.indexOf("Next attempt")<0){fail("FORCE_RECEIPTS_MISSING");return}
   if(widget.automationEnabled || widget.overrideActive){fail("IMPLICIT_AUTO_OR_TESTING");return}
   if(control("forceStatus").text.indexOf("Force")<0){fail("STATUS_MISSING");return}
   if(widget.forceNextAttempt!==0){fail("DISABLED_HAS_ATTEMPT");return}
   widget.request("GET", "/v1/status", undefined, function(status) {
    status.next_eligible_at=600
    status.refresh_timing={state:"retry_wait",cadence_due_at:600,retry_due_at:360,next_attempt_at:360}
    widget.acceptStatus(status)
    if(widget.forceNextAttempt!==360 || control("forceStatus").text.indexOf("retry_wait")<0){fail("RETRY_DEADLINE_WRONG");return}
    status.refresh_timing={state:"action_required",cadence_due_at:600,retry_due_at:null,next_attempt_at:null,reason:"Retry budget exhausted"}
    widget.acceptStatus(status)
    if(widget.forceNextAttempt!==0 || control("forceStatus").text.indexOf("action_required")<0){fail("BLOCK_HAS_ATTEMPT");return}
    widget.refreshStatus()
    if(!widget.busy || !widget.activeRequest){fail("NO_BUSY_REQUEST");return}
    if(!control("forceToggle").enabled){fail("BUSY_DISABLE_INACCESSIBLE");return}
    control("forceToggle").click()
    if(!widget.forceDisablePending || widget.actionNotice.indexOf("queued")<0){fail("BUSY_DISABLE_NOT_QUEUED");return}
    step=4
   });step=30
  }else if(step===4 && !widget.forceActive){
   console.log("FORCED_REFRESH_QML_PASS");Qt.quit()
  }
 }}
 Timer {interval:7000;running:true;onTriggered:fail("FORCE_TIMEOUT "+step+" "+widget.actionNotice)}
}''')
            env=os.environ|{'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            try:
                p=subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(Path('artifacts/plasma-harness/plasma-harness').resolve()),str(d/'config.json'),str(d/'test.qml')],env=env,capture_output=True,text=True,timeout=15)
                self.assertIn('FORCED_REFRESH_QML_PASS',p.stderr,p.stderr)
                self.assertNotIn('Error:',p.stderr)
                self.assertEqual([(m,p) for m,p,b in calls],[('PUT','/v1/force-override')]*2)
                self.assertEqual(calls[0][2],{'enabled':True,'confirmation':'I accept gaming stutter, VR disruption and GPU OOM risk'})
                self.assertFalse(c.settings['automation_enabled'])
                self.assertEqual(c.settings['interval_minutes'],5)
                self.assertFalse(c.force_status()['active'])
                print(p.stderr)
            finally:server.shutdown();server.server_close()
