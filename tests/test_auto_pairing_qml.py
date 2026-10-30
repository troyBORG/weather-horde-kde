"""Real Plasma loader + native plugin + private fixtures, no owner credentials."""
import json, os, shutil, subprocess, tempfile, threading, time, unittest
from pathlib import Path
from weather_controller import Controller, make_server

class AutoPairingQmlTests(unittest.TestCase):
    def test_missing_and_unsafe_token_fail_closed_then_manual_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); state=d/'state'; state.mkdir(mode=0o700)
            (state/'weather-horde-kde').mkdir(mode=0o700)
            package=Path('plasma-widget/org.troyborg.weatherhorde').resolve()
            shutil.copytree(package,d/'share/plasma/plasmoids'/package.name)
            (d/'runtime').mkdir(mode=0o700)
            (d/'config.json').write_text(json.dumps({'base':'http://127.0.0.1:1','desktop':False}))
            (d/'test.qml').write_text('''import QtQuick
Item {
 required property var widget
 Component.onCompleted: {widget.reconnectMinimumMs=100; widget.reconnectMaximumMs=400; widget.refreshStatus()}
 Timer { interval:1200; running:true; onTriggered: {
   if(widget.controllerToken.length || widget.online || widget.reconnectDelayMs>400 || widget.statusTitle!=="Not paired") {
      console.error("UNSAFE_PAIRING"); Qt.quit(); return
   }
   if(!widget.pairingReader) {console.error("HELPER_MISSING"); Qt.quit(); return}
   if(widget.pairingReader && widget.connectionSummary.indexOf("waiting for")>=0) {console.error("PAIRING_REASON_HIDDEN"); Qt.quit(); return}
   function find(item, name) { if(item.objectName===name) return item; for(let i=0;i<item.children.length;i++) {let found=find(item.children[i],name); if(found) return found} return null }
   const renderer=find(widget,"rendererSummary")
   if(!renderer || renderer.text.indexOf("not verified")<0) {console.error("UNPAIRED_RENDER_STATE_INVENTED"); Qt.quit(); return}
   widget.pairManually("x".repeat(40))
   if(!widget.manualPairing || widget.controllerToken.length!==40) {console.error("MANUAL_FALLBACK_FAILED"); Qt.quit(); return}
   console.log("UNPAIRED_SAFE_PASS"); Qt.quit()
 } }
}''')
            build=Path('artifacts/plasma-harness').resolve()
            env=os.environ|{'XDG_STATE_HOME':str(state),'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            command=['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(build/'plasma-harness'),str(d/'config.json'),str(d/'test.qml')]
            for mode in ('missing','world-readable','unsafe-ancestor','helper-unavailable'):
                with self.subTest(mode=mode):
                    if mode=='world-readable':
                        token=state/'weather-horde-kde/token'
                        token.write_text('x'*43); token.chmod(0o644)
                    if mode=='unsafe-ancestor':
                        token.chmod(0o600)
                        state.chmod(0o777)
                        test=d/'test.qml'
                        test.write_text(test.read_text().replace('   widget.pairManually', '   if(widget.connectionSummary.indexOf("group/world-writable")<0) {console.error("UNSAFE_ANCESTOR_REASON_MISSING"); Qt.quit(); return}\n   widget.pairManually'))
                    if mode=='helper-unavailable':
                        state.chmod(0o700)
                        test=d/'test.qml'
                        test.write_text('\n'.join(line for line in test.read_text().splitlines() if 'UNSAFE_ANCESTOR_REASON_MISSING' not in line))
                        shutil.move(d/'share/plasma/plasmoids'/package.name/'contents/ui/WeatherHorde',d/'removed-helper')
                        test=d/'test.qml'
                        test.write_text(test.read_text().replace('if(!widget.pairingReader)', 'if(widget.pairingReader)'))
                    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('UNPAIRED_SAFE_PASS',result.stderr)
                    self.assertNotIn('Error:',result.stderr)

    def test_auto_pair_missing_controller_restart_and_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); state=d/'state'; state.mkdir(mode=0o700)
            c=Controller(state/'weather-horde-kde')
            server=make_server(c,port=0)
            port=server.server_port
            # Initially bound but not serving; no user input to pair.
            package=Path('plasma-widget/org.troyborg.weatherhorde').resolve()
            shutil.copytree(package,d/'share/plasma/plasmoids'/package.name)
            (d/'runtime').mkdir(mode=0o700)
            (d/'config.json').write_text(json.dumps({'base':f'http://127.0.0.1:{port}','desktop':False,'screenshot':str(Path('artifacts/auto-pairing-ux.png').resolve())}))
            (d/'test.qml').write_text('''import QtQuick
Item {
 required property var widget
 property int step: 0
 function label(item) {
   if(item.objectName === "connectionSummary") return item
   for(let i=0;i<item.children.length;++i) {let found=label(item.children[i]); if(found) return found}
   return null
 }
 Component.onCompleted: {
   if (widget.connectionSummary === undefined) {console.error("AUTO_PAIRING_MISSING"); Qt.quit(); return}
   widget.reconnectMinimumMs=100; widget.reconnectMaximumMs=500
   widget.statusTimeoutMs=600; widget.statusPollMs=500; widget.refreshStatus()
 }
 Timer {interval:100; running:true; repeat:true; onTriggered: {
   if (step===0 && widget.online) {step=1; console.log("AUTO_CONNECTED")}
   else if(step===1 && !widget.online) {step=2; console.log("AUTO_DISCONNECTED")}
   else if(step===2 && widget.online) {
     if(widget.overrideActive || widget.automationEnabled) {console.error("safety changed"); Qt.quit(); return}
     if(widget.connectionSummary.indexOf("Paired")<0) {console.error("missing paired label"); Qt.quit(); return}
     const view=label(widget)
     if(!view || !view.visible || view.width<200 || view.height<10 || view.text!==widget.connectionSummary) {
       console.error("PAIRING_LABEL_NOT_VISIBLE"); Qt.quit(); return
     }
     console.log("AUTO_RECONNECTED_PASS"); Qt.quit()
   }
 } }
 Timer {interval:14000; running:true; onTriggered:{console.error("AUTO_TIMEOUT",step); Qt.quit()} }
}''')
            build=Path('artifacts/plasma-harness').resolve()
            subprocess.run(['cmake','-S','tests/plasma-harness','-B',str(build)],check=True,capture_output=True)
            subprocess.run(['cmake','--build',str(build)],check=True,capture_output=True)
            env=os.environ|{'XDG_STATE_HOME':str(state),'XDG_DATA_HOME':str(d/'share'),'XDG_CONFIG_HOME':str(d/'config'),'XDG_CACHE_HOME':str(d/'cache'),'XDG_RUNTIME_DIR':str(d/'runtime'),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'}
            command=['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(build/'plasma-harness'),str(d/'config.json'),str(d/'test.qml')]
            p=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            start=threading.Timer(1.2,server.serve_forever); start.daemon=True; start.start()
            output=[]; restarted=None
            try:
                for line in p.stdout:
                    output.append(line)
                    if 'AUTO_CONNECTED' in line:
                        server.shutdown(); server.server_close(); start.join()
                    if 'AUTO_DISCONNECTED' in line:
                        import secrets
                        token=secrets.token_urlsafe(32)
                        (state/'weather-horde-kde/token').write_text(token)
                        c.token=token
                        restarted=make_server(c,port=port)
                        threading.Thread(target=restarted.serve_forever,daemon=True).start()
                p.wait(timeout=20)
            finally:
                if p.poll() is None: p.kill(); p.wait()
                if start.is_alive(): server.shutdown(); start.join()
                server.server_close()
                if restarted: restarted.shutdown(); restarted.server_close()
            p.stdout.close()
            text=''.join(output)
            self.assertEqual(p.returncode,0,text)
            self.assertIn('AUTO_RECONNECTED_PASS',text,text)
            self.assertNotIn('Error:',text)
            self.assertNotIn(c.token,text)
            self.assertEqual(c.settings['automation_enabled'],False)
            print(text)
