"""One-monitor wallpaper transactions; explicit manual or guarded opt-in schedule.

The prior wallpaper plugin and all its nested settings are captured and restored.
Unselected desktops are read back without writing their plugin or settings.
Plasma screen numbers are NOT KScreen IDs. Match unique live logical geometry,
then compare activity/containment/config again within the write script.
"""
import copy
import time
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from PIL import Image
from displays import discover


def atomic_json(path, value):
    tmp=path.with_suffix('.tmp')
    with open(tmp,'w') as f:
        os.chmod(tmp,0o600); json.dump(value,f); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)


def canonical_snapshot(snapshot):
    """Only migrate the exact image schema field formerly read as QString.

    Do not coerce arbitrary numeric strings, identities, geometry or other plugins.
    Top-level fill already used a typed default in the legacy adapter.
    """
    result=copy.deepcopy(snapshot)
    if result.get('plugin')=='org.kde.image':
        for row in result.get('settings',[]):
            if row.get('group')==['General']:
                value=row.get('values',{}).get('FillMode')
                if type(value) is str and value in tuple(str(i) for i in range(7)):
                    row['values']['FillMode']=int(value)
    return result


def same_snapshot(a,b):
    # JSON comparison also distinguishes bool from int, unlike Python equality.
    return json.dumps(canonical_snapshot(a),sort_keys=True)==json.dumps(canonical_snapshot(b),sort_keys=True)


class WallpaperManager:
    def __init__(self, root, backend):
        self.root=Path(root)
        self.backend=backend
        self.journal=self.root/'wallpaper-restore.json'

    def available(self):
        if not self.journal.exists(): return []
        return list(json.loads(self.journal.read_text()))

    def apply(self, display, identifier, guard):
        if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):
            raise ValueError('Select a validated preview')
        folder=self.root/'renders'/identifier
        record=json.loads((folder/'metadata.json').read_text())
        image=folder/'image.png'
        if (record.get('id') != identifier or record.get('quarantined') is not False
                or display['id'] not in record.get('targets',[])
                or (record['width'],record['height']) != (display['width'],display['height'])):
            raise ValueError('Preview target, native dimensions or quarantine check failed')
        if hashlib.sha256(image.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Preview integrity check failed')
        with Image.open(image) as decoded:
            if decoded.size != (display['width'],display['height']) or decoded.format!='PNG':
                raise ValueError('Native image validation failed')
            decoded.verify()
        before=self.backend.snapshot(display)
        if not before.get('plugin'): raise ValueError('Original wallpaper plugin unavailable')
        after=(self.backend.replacement(display,before,image.resolve().as_uri())
               if hasattr(self.backend,'replacement') else dict(before,plugin='org.kde.image',image=image.resolve().as_uri(),fill=1))
        journal=json.loads(self.journal.read_text()) if self.journal.exists() else {}
        if journal.get(display['id'],{}).get('state')=='pending':
            raise ValueError('Unreconciled wallpaper transaction; use Restore previous first')
        journal[display['id']]={'before':before,'after':after,'state':'pending'}
        if guard()!='safe': raise ValueError('Activity guard blocks wallpaper changes; override does not apply')
        atomic_json(self.journal,journal) # durable rollback before external mutation
        if guard()!='safe': raise ValueError('Activity changed before wallpaper write')
        self.backend.replace(display,before,after)
        if self.backend.snapshot(display)!=after:
            raise ValueError('Wallpaper readback failed; restore receipt retained')
        journal[display['id']]['state']='applied'; atomic_json(self.journal,journal)
        return {'state':'applied','target':display['id'],'preview_id':identifier,'verified':True}

    def reconcile_pending(self, display, commit=False):
        """DP-2 receipt-only recovery. Caller MUST exclude concurrent writers.

        No wallpaper writes, no journal deletion, original snapshots retained.
        Read-only by default. Owner CLI requires controller stopped for commit.
        """
        if display.get('id')!='DP-2': raise ValueError('Reconciliation is limited to DP-2')
        raw=self.journal.read_bytes()
        journal=json.loads(raw); entry=journal.get('DP-2')
        if not entry or entry.get('state')!='pending': raise ValueError('No pending DP-2 receipt')
        current=self.backend.snapshot(display)
        expected=[display['x'],display['y'],display['width']/display['scale'],display['height']/display['scale']]
        identity=('desktop','activity','screen','geometry')
        valid=all(k in current for k in identity) and current['geometry']==expected
        valid=valid and all(all(k in entry[side] and entry[side][k]==current[k] for k in identity) for side in ('before','after'))
        match=next((side for side in ('after','before') if valid and same_snapshot(current,entry[side])),None)
        report={'target':'DP-2','state':'pending','match':match,'identity_geometry_match':valid,
                'before':entry['before'],'after':entry['after'],'current':current,'verified':False}
        if not commit: return report
        if not match: raise ValueError('DP-2 differs from known receipt or identity/geometry; receipt preserved')
        if self.journal.read_bytes()!=raw or not same_snapshot(self.backend.snapshot(display),current):
            raise ValueError('DP-2 changed during reconciliation; receipt preserved')
        backup=self.root/('wallpaper-restore.dp2-'+str(time.time_ns())+'.json')
        with backup.open('xb') as stream:
            os.chmod(backup,0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        entry['state']='applied' if match=='after' else 'reconciled_before'
        entry['reconciliation']={'matched':match,'schema':'image-General-FillMode-int-v1'}
        atomic_json(self.journal,journal)
        if json.loads(self.journal.read_text())!=journal:
            raise ValueError('Reconciliation receipt readback failed')
        report.update(state=entry['state'],verified=True)
        return report

    def accept_current(self, display, expected_current, expected_receipt, *, confirmed=False):
        """Retire ONLY DP-2 pending history; caller holds exclusive owner lock.

        Never writes Plasma. Acceptance is bound to the freshly reviewed snapshot
        and exact journal bytes. Historical state lives in a private durable archive.
        """
        if not confirmed: raise ValueError('Explicit accept-current confirmation required')
        if display.get('id')!='DP-2': raise ValueError('Only DP-2 may be retired')
        raw=self.journal.read_bytes()
        if raw!=expected_receipt: raise ValueError('Receipt changed; preserved')
        journal=json.loads(raw); entry=journal.get('DP-2',{})
        if entry.get('state')!='pending': raise ValueError('No pending DP-2 receipt')
        current=self.backend.snapshot(display)
        expected=[display['x'],display['y'],display['width']/display['scale'],display['height']/display['scale']]
        if (not current.get('activity') or not current.get('plugin') or
                any(k not in current for k in ('desktop','activity','screen','geometry','settings','image','fill')) or
                type(current.get('screen')) is not int or current['screen']<0 or
                current.get('desktop') is None or current.get('geometry')!=expected or
                any(any(entry.get(side,{}).get(k)!=current.get(k) for k in ('activity','screen','geometry'))
                    for side in ('before','after'))):
            raise ValueError('Activity or DP-2 mapping differs; preserved')
        exact=lambda a,b: json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)
        if not exact(current,expected_current): raise ValueError('Current wallpaper changed; preserved')
        import tempfile
        archive=Path(tempfile.mkdtemp(prefix='dp2-accepted-',dir=self.root))
        for name,data in [('journal.json',raw),('current.json',json.dumps(current).encode())]:
            fd=os.open(archive/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
        fd=os.open(archive,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        baseline={'state':'accepted_current','before':current,'after':current,
                  'reconciliation':{'action':'accept-current','archive':archive.name}}
        # Replace only the DP-2 JSON value, retaining every other byte (DP-3
        # ordering, whitespace, numeric representations and history included).
        text=raw.decode();decoder=json.JSONDecoder();pos=text.index('{')+1;span=None;seen=set()
        while True:
            while text[pos].isspace(): pos+=1
            if text[pos]=='}': break
            key,end=decoder.raw_decode(text,pos)
            if key in seen: raise ValueError('Duplicate journal key; preserved')
            seen.add(key);pos=end
            while text[pos].isspace(): pos+=1
            if text[pos]!=':': raise ValueError('Invalid journal; preserved')
            pos+=1
            while text[pos].isspace(): pos+=1
            start=pos;_,pos=decoder.raw_decode(text,pos)
            if key=='DP-2': span=(start,pos)
            while text[pos].isspace(): pos+=1
            if text[pos]=='}': break
            if text[pos]!=',': raise ValueError('Invalid journal; preserved')
            pos+=1
        if span is None: raise ValueError('Missing DP-2; preserved')
        updated=(text[:span[0]]+json.dumps(baseline)+text[span[1]:]).encode()
        # Check again AFTER archival I/O, just before the atomic receipt replace.
        # Plasma cannot be locked by this process; no external wallpaper writes
        # are made, even if the owner changes it after this final snapshot.
        if self.journal.read_bytes()!=raw or not exact(self.backend.snapshot(display),current):
            raise ValueError('State changed during acceptance; preserved')
        fd,tmp=tempfile.mkstemp(prefix='.dp2-receipt-',dir=self.root)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(updated);stream.flush();os.fsync(stream.fileno())
            os.replace(tmp,self.journal)
            fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        if self.journal.read_bytes()!=updated: raise ValueError('Receipt readback failed')
        return {'target':'DP-2','state':'accepted_current','verified':True,'archive':str(archive)}

    def restore(self, display, guard):
        journal=json.loads(self.journal.read_text()) if self.journal.exists() else {}
        entry=journal.get(display['id'])
        if not entry: raise ValueError('No previous wallpaper for selected monitor')
        current=self.backend.snapshot(display)
        before=canonical_snapshot(entry['before'])
        if not any(same_snapshot(current,entry[side]) for side in ('before','after')):
            raise ValueError('Wallpaper or activity changed externally; refusing to overwrite it')
        if guard()!='safe': raise ValueError('Activity guard blocks restoration')
        if not same_snapshot(current,before):
            self.backend.replace(display,current,before)
        if not same_snapshot(self.backend.snapshot(display),before):
            raise ValueError('Restore readback failed; receipt retained')
        del journal[display['id']]; atomic_json(self.journal,journal)
        return {'state':'restored','target':display['id'],'verified':True}


# This function returns only current-activity desktops, not unrelated activities.
SNAPSHOT_JS='''
function pluginSettings(d,plugin) {
  var result=[];
  function visit(group) {
    d.currentConfigGroup=["Wallpaper",plugin].concat(group);
    var keys=d.configKeys.slice().sort(), groups=d.configGroups.slice().sort(), values={};
    keys.forEach(function(k){
      // Applet.readConfig defaults to QString, not the stored QVariant type.
      // Use the image schema type for our numeric write/readback contract.
      values[k]=(plugin==="org.kde.image" && group.length===1 && group[0]==="General" && k==="FillMode")
        ? d.readConfig(k,2) : d.readConfig(k);
    });
    result.push({group:group,values:values});
    groups.forEach(function(g){visit(group.concat([g]))});
  }
  visit([]); return result;
}
function snapshot(d,plugin) {
  plugin=typeof plugin==="string" ? plugin : d.wallpaperPlugin;
  var g=screenGeometry(d.screen), settings=pluginSettings(d,plugin);
  d.currentConfigGroup=["Wallpaper",plugin,"General"];
  return {desktop:d.id,activity:currentActivity(),screen:d.screen,
    geometry:[g.x,g.y,g.width,g.height],plugin:plugin,
    image:d.readConfig("Image",""),fill:d.readConfig("FillMode",2),settings:settings};
}
function canonical(x) {
  if (Array.isArray(x)) return x.map(canonical);
  if (x && typeof x==="object") {var out={};Object.keys(x).sort().forEach(function(k){out[k]=canonical(x[k])});return out;}
  return x;
}
function same(a,b){return JSON.stringify(canonical(a))===JSON.stringify(canonical(b));}
'''

class PlasmaBackend:
    def evaluate(self, script):
        displays,error=discover()
        if error or not displays: raise ValueError('Owning graphical session unavailable: '+error)
        owners=subprocess.run(['ps','-C','plasmashell','-o','uid='],capture_output=True,text=True,check=True).stdout.split()
        if owners!=[str(os.getuid())]: raise ValueError('Plasma owner does not match controller')
        try:
            result=subprocess.run(['qdbus6','org.kde.plasmashell','/PlasmaShell',
                'org.kde.PlasmaShell.evaluateScript',script],capture_output=True,text=True,check=True,timeout=10)
        except subprocess.CalledProcessError as exc:
            # str(CalledProcessError) exposes the entire JS/config payload but
            # omits the useful DBus rejection. Return a bounded action error.
            reason=(exc.stderr or exc.stdout or 'No DBus error detail').splitlines()[0]
            reason=re.sub(r'file://\S+|/(?:home|mnt)/[^\s\"\']+', '[path]', reason)
            raise ValueError('Plasma scripting failed (exit '+str(exc.returncode)+'): '+reason[:300]) from None
        except subprocess.TimeoutExpired:
            raise ValueError('Plasma scripting timed out; reconcile saved wallpaper transaction before retrying') from None
        return json.loads(result.stdout.strip())

    def snapshot(self, display):
        current,error=discover()
        live=next((d for d in current if d['id']==display['id']),None)
        if error or live is None or any(live.get(k)!=display.get(k) for k in ('width','height','scale','x','y')):
            raise ValueError('Output geometry changed or unavailable')
        rows=self.evaluate(SNAPSHOT_JS+'print(JSON.stringify(desktopsForActivity(currentActivity()).filter(function(d){return d.screen>=0}).map(snapshot)));')
        if any(type(display.get(k)) not in (int,float) for k in ('x','y')):
            raise ValueError('Live output position unavailable')
        expected=[display['x'],display['y'],display['width']/display['scale'],display['height']/display['scale']]
        matches=[r for r in rows if len(r.get('geometry',[]))==4 and all(abs(a-b)<=1 for a,b in zip(r['geometry'],expected))]
        if len(matches)!=1: raise ValueError('No unique live Plasma monitor mapping; mirrored/ambiguous outputs unsupported')
        return matches[0]

    def replacement(self, display, before, uri):
        target=self.evaluate(SNAPSHOT_JS+'print(JSON.stringify(snapshot(desktopById('+str(before['desktop'])+'),"org.kde.image")));')
        target['image']=uri;target['fill']=1
        general=next((r for r in target['settings'] if r['group']==['General']),None)
        if general is None:
            general={'group':['General'],'values':{}};target['settings'].append(general)
            target['settings'].sort(key=lambda r:r['group'])
        general['values'].update(Image=uri,FillMode=1)
        return target

    def replace(self, display, expected, replacement):
        if self.snapshot(display)!=expected: raise ValueError('Desktop changed before mutation')
        script=SNAPSHOT_JS+'''
var expected=EXPECTED, replacement=REPLACEMENT;
// Match the owner-proven Plasma API, but never assume screen 0 is left.
// expected.screen was resolved from live unique connector geometry.
var d=desktopForScreen(expected.screen,0);
if (!d || d.id!==expected.desktop || !same(snapshot(d),expected)) throw new Error("Desktop changed");
var others=desktopsForActivity(currentActivity()).filter(function(x){return x.screen>=0 && x.id!==d.id}).map(function(x){return snapshot(x)});
// Delete only extra keys in the selected plugin/containment, never global groups.
pluginSettings(d,replacement.plugin).forEach(function(row){
  var wanted=replacement.settings.filter(function(r){return same(r.group,row.group)})[0];
  Object.keys(row.values).forEach(function(key){
    if (wanted && Object.prototype.hasOwnProperty.call(wanted.values,key)) return;
    var cfg=new ConfigFile("plasma-org.kde.plasma.desktop-appletsrc","Containments");
    [String(d.id),"Wallpaper",replacement.plugin].concat(row.group).forEach(function(g){cfg=new ConfigFile(cfg,g)});
    cfg.deleteEntry(key);
  });
});
// Select the plugin BEFORE writing its Image group (owner working script).
d.wallpaperPlugin=replacement.plugin;
replacement.settings.forEach(function(row){
  d.currentConfigGroup=["Wallpaper",replacement.plugin].concat(row.group);
  Object.keys(row.values).forEach(function(k){d.writeConfig(k,row.values[k])});
});
d.currentConfigGroup=["Wallpaper",replacement.plugin,"General"];
d.reloadConfig();
var afterOthers=desktopsForActivity(currentActivity()).filter(function(x){return x.screen>=0 && x.id!==d.id}).map(function(x){return snapshot(x)});
if(!same(others,afterOthers)) throw new Error("Unselected desktop changed during transaction");
print(JSON.stringify(snapshot(d)));
'''.replace('EXPECTED',json.dumps(expected)).replace('REPLACEMENT',json.dumps(replacement))
        if self.evaluate(script)!=replacement: raise ValueError('Plasma script readback failed')
