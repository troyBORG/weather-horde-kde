"""Runtime status/layout regression in the actual Plasma containment."""
import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path

class StatusUxTests(unittest.TestCase):
    def test_desktop_and_compact_status(self):
        build=Path('artifacts/plasma-harness').resolve()
        subprocess.run(['cmake','-S','tests/plasma-harness','-B',str(build)],check=True,capture_output=True)
        subprocess.run(['cmake','--build',str(build)],check=True,capture_output=True)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); package=Path('plasma-widget/org.troyborg.weatherhorde').resolve()
            shutil.copytree(package,d/'share/plasma/plasmoids'/package.name)
            (d/'runtime').mkdir(mode=0o700)
            (d/'config.json').write_text(json.dumps({'base':'http://127.0.0.1:1','token':'','desktop':True,'screenshot':str(Path('artifacts/status-ux.png').resolve())}))
            (d/'test.qml').write_text('''import QtQuick
Item {
 required property var widget
 function check(ok, message) { if (!ok) throw new Error(message) }
 function label(item, name) {
   if (item.objectName === name) return item
   for (let i=0; i<item.children.length; ++i) { let found=label(item.children[i],name); if(found) return found }
   return null
 }
 function status(guard, state, enabled) {
   widget.acceptStatus({state:state,guard:{decision:guard,observed_at:Date.now()/1000},automation_enabled:enabled,interval_minutes:60,render_enabled:true})
 }
 Timer { interval: 500; running:true; onTriggered: {
 try {
   check(widget.preferredRepresentation === widget.compactRepresentation, "desktop must start compact, not giant full panel")
   check(!widget.expanded, "desktop initially closed")
   let launcher=label(widget,"compactLauncher")
   check(launcher && launcher.visible,"readable compact launcher")
   launcher.clicked()
   check(widget.expanded,"click opens full controls")
   opened.start()
 } catch(e) { console.error(e); Qt.quit() }
 } }
 Timer { id:opened; interval:300; onTriggered: {
 try {
   check(widget.statusTitle === "Not paired", "unpaired")
   let toggle=label(widget.fullRepresentationItem,"testingOverrideToggle")
   let warning=label(widget.fullRepresentationItem,"testingOverrideRisk")
   check(toggle && toggle.visible && !toggle.checked && toggle.width>100,"override default OFF visible")
   check(warning && warning.visible && warning.text.indexOf("OOM")>=0 && warning.text.indexOf("stutter")>=0,"explicit risk confirmation visible")
   widget.controllerToken="x".repeat(40)
   check(widget.statusTitle === "Disconnected", "disconnected")
   status("game_active","idle",false)
   check(widget.statusTitle === "Paused — game detected", "game takes precedence over automation off")
   check(widget.automationSummary.indexOf("off")>=0, "automation remains visible")
   warning.checked=true
   check(!widget.overrideActive && !toggle.enabled,"risk checkbox alone cannot enable legacy override")
   warning.checked=false
   let title=label(widget.fullRepresentationItem,"expandedStatusTitle")
   check(title && title.visible && title.width>200 && title.height>10, "expanded status visible and sized")
   check(title.text === widget.statusTitle, "expanded text")
   for (let row of [["vr_active","Paused — VR detected"],["unknown","Monitoring unknown"],["gpu_busy","Paused — GPU busy"],["insufficient_vram","Paused — low VRAM"]]) {
      status(row[0],"idle",false); check(widget.statusTitle===row[1],row[0])
   }
   for (let serviceState of ["stopped","starting","ready","busy","stopping","failed"]) {
      widget.acceptStatus({state:"idle",guard:{decision:"safe"},interval_minutes:60,render_enabled:true,comfy_service:{managed:true,state:serviceState,reason:"fixture reason",owned:false}})
      let serviceLabel=label(widget.fullRepresentationItem,"comfyServiceStatus")
      check(serviceLabel && serviceLabel.visible && serviceLabel.text.indexOf(serviceState)>=0,"service lifecycle visible: "+serviceState)
   }
   widget.acceptStatus({state:"quarantined",guard:{decision:"safe"},interval_minutes:60,render_enabled:true,quarantine:{decision:"game_active",reason:"game_process_detected",at:1700000000},render_request:{state:"quarantined",reason:"historical game_active",prompt_id:"fixture-job"}})
   check(widget.statusReason.indexOf("game_active")>=0 && widget.statusReason.indexOf("Current guard: safe")>=0,"historical quarantine distinct from current guard")
   let action=label(widget.fullRepresentationItem,"monitorActionNotice")
   check(action && action.visible && action.text.indexOf("fixture-job")>=0,"prompt ID visible beside Apply controls")
   widget.acceptStatus({state:"idle",guard:{decision:"safe"},automation_enabled:true,interval_minutes:60,catch_up_refresh:true,refresh:{pending:["TEST"],waiting_reason:"settling",settling_seconds:40,retry_seconds:0,last_success:{image_wallpaper:{TEST:1700000000}}}})
   check(widget.refreshSummary.indexOf("40s")>=0 && widget.refreshSummary.indexOf("TEST")>=0,"pending target and grace visible")
   check(label(widget.fullRepresentationItem,"catchupRefreshToggle").checked,"catchup consent visible")
   widget.acceptStatus({state:"idle",guard:{decision:"safe"},interval_minutes:60,seasonal_themes:true,holiday_themes:true,theme_strength:"subtle",holiday_date_mode:"actual",holiday_preset:"mainstream_iowa",calendar:{season:"autumn",selected_theme:"halloween",local_date:"2026-10-31",timezone:"America/Chicago",events:[],valid_until_utc:"2026-11-01T05:00:00+00:00"}})
   check(label(widget.fullRepresentationItem,"holidayThemesToggle").checked,"holiday setting visible")
   check(label(widget.fullRepresentationItem,"seasonalThemesToggle").checked,"season setting visible")
   check(widget.calendarSummary.indexOf("halloween")>=0 && widget.calendarSummary.indexOf("2026-10-31")>=0,"local theme date visible")
   check(label(widget.fullRepresentationItem,"holidayStrengthSelector").currentIndex===0,"subtle intensity roundtrip")
   widget.online=false
   check(widget.refreshSummary.indexOf("last known")>=0,"disconnected freshness not live")
   status("safe","idle",false); check(widget.statusTitle==="Automation off","off")
   status("safe","idle",true); check(widget.statusTitle==="Idle — ready","ready")
   status("safe","queued",false); check(widget.statusTitle==="Queued — image preview","queued")
   status("safe","rendering",false); check(widget.statusTitle==="Rendering — image preview","rendering")
   status("game_active","rendering_guard_blocked",false)
   check(widget.statusReason.indexOf("in flight")>=0,"never claim active GPU work stopped")
   status("safe","blocked_preview_only",false); check(widget.statusTitle==="Preview only","preview")
   widget.lastStatusCheck=Date.now()-120000; check(widget.statusTitle==="Monitoring unknown","stale blocks ready")
   check(widget.checkSummary.indexOf("stale")>=0,"stale text")
   widget.acceptStatus({state:"idle",guard:{decision:"game_active"},automation_enabled:false,interval_minutes:60,render_enabled:true,api_version:1,capabilities:{testing_override:true},testing_override:{active:true,remaining_seconds:600}})
   check(toggle.checked,"server-confirmed override ON")
   check(widget.statusTitle.indexOf("Testing override")>=0,"override prominent")
   let countdown=label(widget.fullRepresentationItem,"testingOverrideCountdown")
   check(countdown && countdown.visible && countdown.text.indexOf("600")>=0,"visible countdown")
   widget.clockNow=widget.lastStatusCheck+601000
   check(!toggle.checked,"countdown expires OFF")
   status("game_active","idle",false)
   check(!toggle.checked,"missing backend support fails OFF")
   widget.preferredRepresentation=widget.compactRepresentation
   label(widget,"compactLauncher").clicked()
   check(!widget.expanded,"second click closes full controls")
   later.start()
 } catch(e) { console.error(e); Qt.quit() }
 } }
 Timer { id:later; interval:500; onTriggered: {
 try {
   let title=label(widget,"compactStatusTitle")
   check(title && title.visible && title.width>80 && title.height>10,"compact readable label")
   check(title.text===widget.statusTitle,"compact text")
   let reason=label(widget,"compactReason")
   check(reason && reason.visible && reason.height>10,"compact blocking reason readable")
   check(title.width <= widget.width,"title fits tile")
   finish.start()
 } catch(e) {console.error(e);Qt.quit()}
 } }
 Timer {id:finish;interval:500;onTriggered:{ console.log("STATUS_UX_PASS"); Qt.quit() }}
}''')
            env=os.environ|{'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            p=subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(build/'plasma-harness'),str(d/'config.json'),str(d/'test.qml')],env=env,capture_output=True,text=True,timeout=20)
            output=p.stdout+p.stderr
            self.assertEqual(p.returncode,0,output)
            self.assertIn('STATUS_UX_PASS',output)
            for line in output.splitlines():
                self.assertTrue(line.startswith(('kf.windowsystem: Could not find any platform plugin','Failed to create wl_display',"kf.plasma.quick: Couldn't create KWindowShadow",'This plugin does not support setting window masks','PLASMA_PACKAGE_ROOT_PASS','qml: STATUS_UX_PASS')),line)
            print(output)
