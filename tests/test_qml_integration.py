"""Real QML -> real loopback HTTP -> controller. Providers are explicit fixtures.
Uses an OS-assigned ephemeral port; safe alongside the production controller.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from weather_controller import Controller, make_server


@unittest.skipUnless(shutil.which('cmake'), 'Plasma harness build tools unavailable on this host')
class QmlIntegrationTests(unittest.TestCase):
    def test_native_widget_calls_authenticated_controller_and_renders_full_view(self):
        location={'zip':'52742','town':'De Witt','state':'Iowa','latitude':41.8267,'longitude':-90.5237,'timezone':'America/Chicago'}
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.resolve_zip',return_value=[location]), patch('weather_controller.weather_preview',return_value={'positive':'TEST weather preview','negative':'visible moon','image_url':''}):
            c=Controller(Path(d)/'state',render_guard=lambda:'safe')
            from wallpaper import WallpaperManager
            from test_wallpaper import Backend
            backend=Backend()
            c.wallpaper=WallpaperManager(Path(d)/'renders-state',backend)
            c.wallpaper.root.mkdir()
            c.guard={'decision':'game_active','observed_at':time.time()}
            c.displays=[{'id':'DP-TEST','width':64,'height':128,'orientation':'portrait'}]
            c.display_error=''
            import io
            from PIL import Image
            from comfy_preview import PreviewStore
            image=io.BytesIO(); Image.new('RGB',(64,128),'navy').save(image,'PNG')
            c.image_preview=PreviewStore(c.wallpaper.root/'renders').save(image.getvalue(),(64,128),{'targets':['DP-TEST']})
            original_dispatch=c.dispatch
            def dispatch(method,path,body):
                if path=='/v1/testing-override' and body.get('enabled') is False:
                    c.guard={'decision':'safe','observed_at':time.time()}
                return original_dispatch(method,path,body)
            c.dispatch=dispatch
            server=make_server(c, port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            source=Path('plasma-widget/org.troyborg.weatherhorde/contents/ui/main.qml').resolve().as_uri()
            harness='''import QtQuick
import QtQuick.Controls
Item {
    required property var widget
    property int step: 0
    Component.onCompleted: widget.refreshStatus()
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (!widget || widget.busy) return
            if (step === 0 && widget.online) {
                if (widget.guardState !== "game_active") { console.error("bad guard"); Qt.quit(); return }
                step=1; widget.lookup("52742")
            } else if (step === 1 && widget.candidates.length) {
                step=2; widget.confirmLocation()
            } else if (step === 2 && widget.locationLabel.indexOf("De Witt") >= 0) {
                step=3; widget.selectedTarget="DP-TEST"; widget.preview()
            } else if (step === 3 && widget.previewText.indexOf("TEST weather preview") >= 0) {
                if (widget.previewText.indexOf("64×128") < 0) { console.error("missing target"); Qt.quit(); return }
                step=4; widget.saveSettings({"interval_minutes":120})
            } else if (step === 4 && widget.intervalMinutes === 120) {
                step=5; widget.generate()
            } else if (step === 5 && widget.controllerState === "deferred") {
                if (!widget.imagePreviewReady) { console.error("Image preview not decoded"); Qt.quit(); return }
                step=6; widget.setTestingOverride(true)
            } else if (step === 6 && widget.overrideActive) {
                if (widget.automationEnabled) { console.error("automation not paused"); Qt.quit(); return }
                step=7; widget.setTestingOverride(false)
            } else if (step === 7 && !widget.overrideActive) {
                if (!widget.applySupported) { console.error("apply capability missing"); Qt.quit(); return }
                step=8; widget.applyPreview()
            } else if (step === 8 && widget.controllerState === "applied") {
                step=9; widget.restoreWallpaper()
            } else if (step === 9 && widget.controllerState === "restored") {
                console.log("QML_HTTP_INTEGRATION_PASS"); Qt.quit()
            }
        }
    }
    Timer { interval: 12000; running: true; onTriggered: { console.error("Integration timed out at step",step,widget.actionNotice); Qt.quit() } }
}
'''.replace('SOURCE',json.dumps(source)).replace('TOKEN',json.dumps(c.token)).replace('BASE',json.dumps('http://127.0.0.1:'+str(server.server_port)))
            file=Path(d)/'integration.qml'; file.write_text(harness); file.chmod(0o600)
            config=Path(d)/'config.json'
            config.write_text(json.dumps({'token':c.token,'base':'http://127.0.0.1:'+str(server.server_port)})); config.chmod(0o600)
            package=Path('plasma-widget/org.troyborg.weatherhorde').resolve()
            shutil.copytree(package,Path(d)/'share/plasma/plasmoids'/package.name)
            build=Path('artifacts/plasma-harness').resolve()
            subprocess.run(['cmake','-S','tests/plasma-harness','-B',str(build)],check=True,capture_output=True,text=True)
            subprocess.run(['cmake','--build',str(build)],check=True,capture_output=True,text=True)
            runtime=Path(d)/'runtime'; runtime.mkdir(mode=0o700)
            try:
                p=subprocess.run(['dbus-run-session','--config-file',str(Path('tests/plasma-harness/dbus.conf').resolve()),'--',str(build/'plasma-harness'),str(config),str(file)],env=os.environ|{'XDG_DATA_HOME':str(Path(d)/'share'),'XDG_CONFIG_HOME':str(Path(d)/'config'),'XDG_CACHE_HOME':str(Path(d)/'cache'),'XDG_RUNTIME_DIR':str(runtime),'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1','QT_LOGGING_RULES':'*.debug=false;qml.debug=true;*.warning=true;*.critical=true'},capture_output=True,text=True,timeout=20)
                output=p.stdout+p.stderr
                self.assertEqual(p.returncode,0,output)
                self.assertIn('PLASMA_PACKAGE_ROOT_PASS',output,output)
                self.assertIn('QML_HTTP_INTEGRATION_PASS',output,output)
                self.assertNotIn('Error:',output)
                self.assertNotIn('not the root QML item',output)
                allowed=('kf.windowsystem: Could not find any platform plugin',
                         'Failed to create wl_display (No such file or directory)',
                         "kf.plasma.quick: Couldn't create KWindowShadow",
                         'PLASMA_PACKAGE_ROOT_PASS','qml: QML_HTTP_INTEGRATION_PASS')
                for line in output.splitlines():
                    self.assertTrue(line.startswith(allowed), 'Unexpected Qt diagnostic: '+line)
                self.assertEqual(c.settings['interval_minutes'],120)
                self.assertEqual(c.state,'restored')
                self.assertEqual(len(backend.writes),2)
                print(output.strip())
            finally:
                server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__': unittest.main()
