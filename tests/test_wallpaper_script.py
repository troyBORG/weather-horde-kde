"""Execute the exact Plasma JS adapter with explicit two-monitor API fixtures.
This is NOT a live Plasma wallpaper test; no real bus or GPU is used.
"""
import copy, json, subprocess, unittest
from unittest.mock import patch
from wallpaper import PlasmaBackend

JS='''
var fixture=FIXTURE, result;
function print(x){result=JSON.parse(x)}
function currentActivity(){return "activity"}
function screenGeometry(n){return fixture.filter(x=>x.screen===n)[0].geometry}
function wrap(o){
  return {id:o.id,screen:o.screen,currentConfigGroup:[],
    get wallpaperPlugin(){return o.plugin},set wallpaperPlugin(v){o.plugin=v},
    get configKeys(){return Object.keys(o.config[JSON.stringify(this.currentConfigGroup)]||{})},
    get configGroups(){var path=this.currentConfigGroup;return [...new Set(Object.keys(o.config).map(k=>JSON.parse(k)).filter(k=>k.length>path.length && path.every((v,i)=>v===k[i])).map(k=>k[path.length]))]},
    readConfig(k,def){var v=(o.config[JSON.stringify(this.currentConfigGroup)]||{})[k];if(k==='FillMode' && v!==undefined && def===undefined) return String(v);return v===undefined?def:v},
    writeConfig(k,v){if(o.plugin!==this.currentConfigGroup[1]) throw new Error('Select active wallpaper plugin before writing, matching owner working script');var key=JSON.stringify(this.currentConfigGroup);o.config[key]??={};o.config[key][k]=v},
    reloadConfig(){}
  }
}
function desktopsForActivity(){return fixture.map(wrap)}
function desktopById(id){return wrap(fixture.filter(x=>x.id===id)[0])}
function desktopForScreen(screen,activity){if(activity!==0) throw new Error("Expected current activity index");return wrap(fixture.filter(x=>x.screen===screen)[0])}
function ConfigFile(parent,group){
  this.path=typeof parent==='string'?[group]:parent.path.concat([group]);
  this.deleteEntry=function(key){var id=Number(this.path[1]), path=JSON.stringify(this.path.slice(2));delete fixture.filter(x=>x.id===id)[0].config[path][key]};
}
'''

class ScriptBackend(PlasmaBackend):
    def __init__(self, fixture): self.fixture=copy.deepcopy(fixture)
    def evaluate(self,script):
        source=JS.replace('FIXTURE',json.dumps(self.fixture))+script+'\nconsole.log(JSON.stringify({result:result,fixture:fixture}));'
        p=subprocess.run(['node','-e',source],capture_output=True,text=True,check=True)
        data=json.loads(p.stdout);self.fixture=data['fixture'];return data['result']

class PlasmaWallpaperScriptTests(unittest.TestCase):
    def test_left_dynamic_full_settings_restore_right_slideshow_untouched(self):
        def config(plugin,values):
            return {json.dumps(['Wallpaper',plugin,'General'],separators=(',',':')):values}
        fixture=[{'id':9,'screen':0,'geometry':{'x':1080,'y':0,'width':3440,'height':1440},'plugin':'org.kde.slideshow',
            'config':config('org.kde.slideshow',{'SlidePaths':['file:///Lucid Dream Lodge'],'SlideInterval':600,'Image':'file:///slide.jpg'})},
            {'id':12,'screen':1,'geometry':{'x':0,'y':0,'width':1080,'height':1920},'plugin':'org.example.daynight',
            'config':config('org.example.daynight',{'Day':'file:///day.jpg','Night':'file:///night.jpg','Transition':900})}]
        left={'id':'DP-2','x':0,'y':0,'width':1080,'height':1920,'scale':1}
        right={'id':'DP-3','x':1080,'y':0,'width':3440,'height':1440,'scale':1}
        b=ScriptBackend(fixture)
        with patch('wallpaper.discover',return_value=([left,right],'')):
            before=b.snapshot(left);original_right=copy.deepcopy(b.fixture[0])
            after=b.replacement(left,before,'file:///native-portrait.png')
            b.replace(left,before,after)
            self.assertEqual(b.snapshot(left),after)
            self.assertEqual(b.fixture[0],original_right)
            b.replace(left,after,before)
            self.assertEqual(b.snapshot(left),before)
            self.assertEqual(b.fixture[0],original_right)
            self.assertEqual(b.fixture[1]['config'][json.dumps(['Wallpaper','org.example.daynight','General'],separators=(',',':'))], {'Day':'file:///day.jpg','Night':'file:///night.jpg','Transition':900})
            # Ambiguous/mirrored mapping must never choose an arbitrary desktop.
            b.fixture[0]['geometry']=copy.deepcopy(b.fixture[1]['geometry'])
            with self.assertRaisesRegex(ValueError,'unique'): b.snapshot(left)
