"""Real packaged QML + authenticated offline controller; no GPU/service calls."""
import json, os, subprocess, tempfile, threading, unittest, zipfile
from pathlib import Path
from weather_controller import Controller, make_server

class RecoveryQml(unittest.TestCase):
    def test_diagnose_cancel_rearm_history_and_guarded_roundtrip(self):
        subprocess.run(['cmake','-S','tests/plasma-harness','-B','artifacts/plasma-harness'],check=True,capture_output=True)
        subprocess.run(['cmake','--build','artifacts/plasma-harness'],check=True,capture_output=True)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp); c=Controller(d/'state'); calls=[]
            c.settings.update(automation_policy='force',automation_enabled=True,interval_minutes=5)
            c.last_error='No Comfy job submitted: force_consent_revoked'
            c.render_request={'state':'deferred','reason':'force_consent_revoked','prompt_id':None}
            original=c.dispatch
            def dispatch(method,path,body,scheduled=False):
                calls.append((method,path,body))
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
   if(!control("diagnoseRepairButton")){fail("REPAIR_BUTTON_MISSING");return}
   control("diagnoseRepairButton").click();step=1
  }else if(step===1){
   if(!widget.recoveryOpen || widget.forceActive){fail("DIAGNOSE_GRANTED_CONSENT");return}
   if(control("repairRearm").enabled){fail("REPAIR_RISK_NOT_REQUIRED");return}
   if(widget.statusReason.indexOf("permission")<0){fail("SAFE_GUARD_MISLEADING");return}
   control("repairRisk").click();control("repairClose").click();step=2
  }else if(step===2){
   control("diagnoseRepairButton").click();step=3
  }else if(step===3){
   if(control("repairRearm").enabled){fail("CANCEL_RETAINED_RISK");return}
   control("repairRisk").click();control("repairRearm").click();step=4
  }else if(step===4){
   if(!widget.forceActive){fail("REARM_FAILED");return}
   widget.refreshStatus();step=5
  }else if(step===5){
   if(widget.actionNotice.indexOf("force_consent_revoked")>=0){fail("HISTORICAL_ERROR_OVERWROTE_SUCCESS");return}
   if(widget.previousError.indexOf("force_consent_revoked")<0){fail("HISTORY_LOST");return}
   if(!widget.automationEnabled || widget.intervalMinutes!==5){fail("PREFERENCES_CHANGED");return}
   widget.setForceOverride(false);step=6
  }else if(step===6){
   if(widget.forceActive){fail("DISABLE_FAILED");return}
   widget.request("PUT", "/v1/settings", {automation_policy:"force"}, function(status){widget.acceptStatus(status)});step=7
  }else if(step===7){
   if(!control("repairGuarded").visible || !control("repairGuarded").enabled){fail("GUARDED_REPAIR_UNAVAILABLE");return}
   control("repairGuarded").click();step=8
  }else if(step===8){
   if(widget.forceActive || widget.consentRequired || !widget.automationEnabled){fail("GUARDED_REPAIR_FAILED");return}
   console.log("RECOVERY_QML_PASS");Qt.quit()
  }
 }}
 Timer {interval:7000;running:true;onTriggered:fail("REPAIR_TIMEOUT "+step+" "+widget.actionNotice)}
}''')
            env=os.environ|{'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            try:
                p=subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(Path('artifacts/plasma-harness/plasma-harness').resolve()),str(d/'config.json'),str(d/'test.qml')],env=env,capture_output=True,text=True,timeout=15)
                self.assertIn('RECOVERY_QML_PASS',p.stderr,p.stderr)
                self.assertNotIn('Error:',p.stderr)
                writes=[(m,p,b) for m,p,b in calls if m!='GET']
                self.assertEqual([(m,p) for m,p,b in writes],[('PUT','/v1/force-override')]*2 + [('PUT','/v1/settings'),('PUT','/v1/force-override')])
                self.assertEqual(writes[0][2],{'enabled':True,'confirmation':'I accept gaming stutter, VR disruption and GPU OOM risk'})
                self.assertTrue(c.settings['automation_enabled'])
                self.assertEqual(c.settings['interval_minutes'],5)
                self.assertFalse(c.force_status()['active'])
                self.assertIsNone(c.render_thread)
                print(p.stderr)
            finally:server.shutdown();server.server_close()
