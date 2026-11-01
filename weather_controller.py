"""Loopback, authenticated, preview-only controller. No GPU or apply adapter enabled."""
import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from displays import discover
from safety import collect
from scene import resolve_zip, weather_preview, PROMPT_VERSION, condition, fetch_json, compose_for_target, FRAMING_MODES, COMPOSITION_VERSION

import hashlib
SERVICE_VERSION = "0.1.10"
# Captured once at import: disk updates must never masquerade as a reload.
# Include local runtime modules: a safety-only fix must invalidate old handshakes.
SOURCE_REVISION = hashlib.sha256(b''.join(
    path.name.encode() + b'\0' + path.read_bytes() + b'\0'
    for path in sorted([*Path(__file__).resolve().parent.glob('*.py'), *Path(__file__).resolve().parent.glob('holiday*.json')])
)).hexdigest()

SCENE_KINDS = ('rural', 'townpark', 'woodland', 'urban', 'river')
SCENE_CHOICES = SCENE_KINDS + ('random',)

INTERVALS = (30, 60, 120, 240, 480, 720, 1440)


class Controller:
    def __init__(self, root, checkpoint=None, transport=None, render_guard=None, poll_seconds=2, managed_comfy=False, comfy_idle_seconds=300):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        token_path = self.root / 'token'
        try:
            fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as f: f.write(secrets.token_urlsafe(32))
        if token_path.stat().st_mode & 0o077:
            raise ValueError('Token permissions must be 0600')
        self.token = token_path.read_text().strip()
        if len(self.token) < 32: raise ValueError('Invalid token')
        self.lock = threading.RLock()
        self.observation = None
        self.override_deadline = 0.0
        self.override_generation = 0
        self.settings = {'automation_enabled': False, 'automation_kind': 'prompt_preview', 'automation_target':'all', 'interval_minutes': 60, 'location': None}
        from holiday_settings import DEFAULTS
        import copy
        self.settings.update(copy.deepcopy(DEFAULTS))
        self.state = 'idle'
        self.last_error = ''
        self.guard = {'decision': 'unknown', 'observed_at': 0}
        self.displays = []
        self.display_error = 'Live display detection pending'
        self.preview = None
        self.checkpoint = checkpoint
        self.models = []
        self.enforce_models = False  # run_controller enables; injected test transports stay offline
        self.model_notice = 'Refresh local models; no GPU or downloads'
        self.previous_sample = None
        self.render_guard = render_guard or self.fresh_guard
        # Manual Apply/Restore are explicit user actions, not background work.
        # Geometry/image/confirmation/transaction gates remain mandatory.
        self.wallpaper_guard = lambda: "safe"
        self.poll_seconds = poll_seconds
        self.render_thread = None
        self.job_guard = None
        self.render_lock = threading.Lock()
        self.wallpaper = None
        self.wallpaper_action = None
        self.image_preview = None
        self.render_results = []
        self.render_request = None
        self.quarantine = None
        self.previews_by_target = {}
        self.resolved_scenes = {}
        self.transport = transport
        if checkpoint:
            from comfy_preview import ComfyTransport, PreviewStore
            self.transport = transport or ComfyTransport(guard=lambda: (self.job_guard or self.render_guard)())
            self.store = PreviewStore(self.root/'renders')
            self.image_preview = self.store.latest()
            pointers = self.root/"previews-by-target.json"
            if pointers.exists():
                for target, identifier in json.loads(pointers.read_text()).items():
                    if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier): continue
                    try:
                        record = json.loads((self.root/"renders"/identifier/"metadata.json").read_text())
                        if not record.get("quarantined") and target in record.get("targets",[]): self.previews_by_target[target] = record
                    except (OSError, ValueError): pass
        self.comfy_service = None
        if managed_comfy:
            if not checkpoint: raise ValueError("Managed Comfy requires an explicit checkpoint")
            from comfy_service import ComfyService
            self.comfy_service = ComfyService(self.transport, idle_seconds=comfy_idle_seconds)
        self.candidates = {}
        if (self.root / 'settings.json').exists():
            self.settings.update(json.loads((self.root / 'settings.json').read_text()))
        # Restart/login begins a fresh saved interval, never an immediate catch-up
        # render and never the old hard-coded one-hour delay for 30-minute Auto.
        self.next_eligible_at = time.time() + self.settings['interval_minutes'] * 60
        from refresh_scheduler import RefreshScheduler
        from session_activity import SessionActivity
        self.scheduler = RefreshScheduler()
        self.session_activity = SessionActivity()
        self.last_unlocked = None
        self.refresh_started = False
        self.calendar_success = {}
        try:
            saved = json.loads((self.root/'refresh-state.json').read_text())
            self.scheduler.success = saved.get('success', {})
            self.calendar_success = saved.get('calendar_success', {})
            self.scheduler.permanent_error = saved.get('permanent_error', '')
            if self.scheduler.permanent_error:
                self.scheduler.fail(self.scheduler.permanent_error, retryable=False)
                self.last_error = self.scheduler.permanent_error
        except (OSError, ValueError):
            pass
        # Published preview receipts also survive a crash before scheduler save.
        for target, record in self.previews_by_target.items():
            stamp = record.get('generated_at')
            if type(stamp) in (int, float) and 0 < stamp <= time.time():
                self.scheduler.success.setdefault('image_preview', {})[target] = stamp
        # Recover a crash after durable compositor readback but before scheduler save.
        self.scheduler.success['image_wallpaper'] = {}
        try:
            receipts = json.loads((self.root/'wallpaper-restore.json').read_text())
            for target, receipt in receipts.items():
                stamp = receipt.get('applied_at')
                if receipt.get('state') == 'applied' and type(stamp) in (int, float) and 0 < stamp <= time.time():
                    self.scheduler.success.setdefault('image_wallpaper', {})[target] = stamp
        except (OSError, ValueError):
            pass

    def enable_reviewed_models(self):
        import subprocess
        self.enforce_models = True
        try:
            self.refresh_models()
            saved = self.settings.get('checkpoint')
            if saved in [m['id'] for m in self.models]: self.checkpoint = saved
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            self.model_notice = 'Local model discovery unavailable; rendering blocked'

    def model_gate(self):
        import math
        profile = self.selected_profile()
        if self.enforce_models and profile is None: return 'unreviewed_model'
        if profile:
            free = self.guard.get('free_mib')
            if type(free) not in (int,float) or not math.isfinite(free) or free < profile['min_free_mib']:
                return 'insufficient_model_vram'
        return 'safe'

    def refresh_models(self):
        from model_catalog import discover_models
        self.models = discover_models()
        self.model_notice = 'Comfy folder_paths + reviewed tensor headers; live node contract rechecked before submission'
        return self.models

    def selected_profile(self):
        return next((m for m in self.models if m['id'] == self.checkpoint),None)

    def observation_status(self):
        active = bool(self.observation and self.observation['expires_at'] > time.time() and
                      self.settings.get('location') and self.observation['location_zip'] == self.settings['location']['zip'])
        return {'active':active, 'source':'Manual user observation' if active else 'Open-Meteo model current conditions',
                'observation':dict(self.observation) if active else None}

    def calendar_now(self, now=None):
        from calendar_context import resolve_calendar
        from datetime import datetime, timezone
        return resolve_calendar(datetime.fromtimestamp(time.time() if now is None else now,timezone.utc),self.settings.get('location') or {},self.settings)

    def scene_preview(self, location, scene_kind=None, fetch=None, calendar_context=None):
        kwargs = {'fetch':fetch} if fetch is not None else {}
        return weather_preview(location, scene_kind=scene_kind or self.settings.get('scene_kind','rural'),
                               calendar_settings=self.settings, calendar_context=calendar_context,
                               observation=self.observation if self.observation_status()['active'] else None, **kwargs)

    def target_scene_previews(self, location, targets, *, generation=False):
        """Resolve only at generation; status/preview reads never rotate scenes.

        Group by resolved scene AND geometry, not geometry alone. Share the
        weather response across all scene variants within this batch.
        """
        responses, bases, result = {}, {}, []
        from calendar_context import resolve_calendar
        from datetime import datetime, timezone
        calendar_context = resolve_calendar(datetime.fromtimestamp(time.time(),timezone.utc),location,self.settings)
        def fetch(url):
            if url not in responses: responses[url] = fetch_json(url)
            return responses[url]
        for target in targets:
            key = target['id']
            requested = self.settings.get('scene_overrides', {}).get(key, self.settings.get('scene_kind','rural'))
            prior = self.resolved_scenes.get(key) or self.previews_by_target.get(key, {}).get('scene', {}).get('weather_evidence', {}).get('scene_kind')
            actual = requested
            provisional = False
            if requested == 'random':
                if generation:
                    actual = secrets.choice([kind for kind in SCENE_KINDS if kind != prior])
                else:
                    actual = prior if prior in SCENE_KINDS else SCENE_KINDS[0]
                    provisional = prior not in SCENE_KINDS
            if generation: self.resolved_scenes[key] = actual
            if actual not in bases: bases[actual] = self.scene_preview(location, actual, fetch, calendar_context)
            composed = compose_for_target(bases[actual], target['width'], target['height'], self.settings.get('framing', 'auto'))
            composed['scene_selection'] = {'requested':requested, 'resolved':actual, 'provisional':provisional}
            result.append({'target':target, 'scene':composed})
        return result

    def override_status(self):
        import math
        remaining = max(0.0, self.override_deadline - time.monotonic())
        return {'active': remaining > 0, 'remaining_seconds': math.ceil(remaining),
                'scope': 'manual_image_previews_only'}

    def status(self):
        with self.lock:
            return {**self.settings, 'calendar':self.calendar_now(), 'api_version': 1, 'service_version': SERVICE_VERSION,
                    'source_revision': SOURCE_REVISION, 'prompt_version':PROMPT_VERSION,
                    'catch_up_refresh': self.settings.get('catch_up_refresh', False),
                    'refresh': self.scheduler.status(time.monotonic()),
                    'models':self.models, 'model_notice':self.model_notice, 'checkpoint':self.checkpoint,
                    'comparison_seed':self.settings.get('comparison_seed'),
                    'framing':self.settings.get('framing','auto'), 'composition_version':COMPOSITION_VERSION,
                    'scene_overrides':dict(self.settings.get('scene_overrides',{})),
                    'scene_kind':self.settings.get('scene_kind','rural'), 'observation':self.observation_status(),
                    'comfy_service': self.comfy_service.status() if self.comfy_service else {'managed':False, 'state':'stopped', 'reason':'Service management not enabled'},
                    'capabilities': {'model_selection':True, 'scene_controls':True, 'scene_rotation':True, 'composition_controls':True, 'testing_override': True, 'manual_apply': self.wallpaper is not None, 'scheduled_images': bool(self.checkpoint)},
                    'apply_blocker': ('Select one monitor and a matching validated saved preview; manual Apply needs no GPU generation' if self.wallpaper else 'Owner wallpaper adapter not configured; no wallpaper changes available'),
                    'restore_available': self.wallpaper.available() if self.wallpaper else [],
                    'testing_override': self.override_status(), 'state': self.state, 'last_error': self.last_error,
                    'preview_only': self.wallpaper is None, 'render_enabled': bool(self.checkpoint), 'apply_enabled': self.wallpaper is not None,
                    'image_preview': self.image_preview, 'render_results': list(self.render_results),
                    'render_request': self.render_request,
                    'wallpaper_action': self.wallpaper_action,
                    'quarantine': self.quarantine,
                    'previews_by_target': dict(self.previews_by_target),
                    'wallpaper_guard': 'safe',
                    'guard': self.guard if time.time()-self.guard['observed_at'] <= 15 else {'decision':'unknown'},
                    'displays': self.displays, 'display_error': self.display_error,
                    'preview': self.preview, 'next_eligible_at': self.next_eligible_at,
                    'automation_scope': self.settings['automation_kind'] + '_only',
                    'location_suggestion': '52742 — DeWitt, Iowa (not yet confirmed)'}

    def manual_policy(self):
        """Freeze consent per manual job; never re-enable an expired job.

        Raw activity evidence stays visible. Identity/exclusive ownership and
        fresh known VRAM are independent hard gates, even with game evidence.
        """
        from safety import vram_eligibility
        enabled = self.override_status()['active']
        deadline, generation = self.override_deadline, self.override_generation
        receipt = {'enabled': enabled, 'used': False, 'reasons': [],
                   'confirmation': 'I accept stutter and OOM risk' if enabled else None,
                   'ttl_seconds': 600 if enabled else 0}
        def guard(startup=False):
            if enabled and (time.monotonic() >= deadline or self.override_generation != generation):
                return 'testing_override_expired'
            raw = self.startup_guard() if startup else self.render_guard()
            model_gate = self.model_gate()
            if model_gate != 'safe': return model_gate
            if not enabled: return raw
            hard = vram_eligibility(self.guard)
            if hard != 'safe': return hard
            # A stopped service cannot have a listener. Only startup eligibility
            # omits that check; ensure_ready verifies unit/listener identity and
            # the ordinary frozen guard still runs before every submission.
            if not startup and (self.transport is None or self.transport.owned_gpu_pid() is None):
                return 'unverified_comfy_ownership'
            # Expiry may have elapsed during slow telemetry/queue reads.
            if time.monotonic() >= deadline or self.override_generation != generation:
                return 'testing_override_expired'
            if raw not in ('safe', 'game_active', 'vr_active', 'gpu_busy', 'unknown'): return raw
            if raw != 'safe':
                receipt['used'] = True
                if raw not in receipt['reasons']: receipt['reasons'].append(raw)
            return 'safe'
        guard.startup = lambda: guard(startup=True)
        return guard, receipt

    def startup_guard(self):
        """Fresh hard-resource/activity evidence, independent of listener health."""
        from safety import vram_eligibility
        transport = self.transport if self.transport.owned_gpu_pid() is not None else None
        evidence, _ = collect(self.previous_sample, transport)
        with self.lock: self.guard = evidence
        hard = vram_eligibility(evidence)
        return evidence["decision"] if hard == "safe" else hard

    def fresh_guard(self):
        guard, _ = collect(self.previous_sample, self.transport)
        with self.lock: self.guard = guard
        return guard['decision']

    def render_images(self, targets, location, policy=None, auto_apply=False, refresh_id=None):
        """Serial owned preview jobs; fail closed on ambiguous transport results."""
        from comfy_preview import build_workflow, SubmissionDeferred
        import hashlib
        original_guard, override_receipt = policy or self.manual_policy()
        self.quarantine = None
        def guard():
            decision = original_guard()
            model_gate = self.model_gate()
            if model_gate != 'safe': decision = model_gate
            if decision != "safe" and self.quarantine is None:
                with self.lock:
                    self.quarantine = {"decision":decision, "reason":self.guard.get("reason", decision) if self.guard.get("decision") == decision else decision, "at":time.time()}
            return decision
        self.job_guard = guard
        job = None
        journal = self.root/'inflight.json'
        outstanding = journal.exists()
        try:
            if outstanding: raise ValueError('Unreconciled submission journal; inspect owned Comfy job before removing journal')
            if self.enforce_models:
                self.refresh_models()
                if self.model_gate() != 'safe': raise SubmissionDeferred(self.model_gate())
            if self.comfy_service:
                self.comfy_service.ensure_ready(getattr(original_guard, 'startup', self.startup_guard), existing_guard=guard)
            if self.enforce_models: self.transport.validate_checkpoint(self.checkpoint)
            target_scenes = self.target_scene_previews(location, targets, generation=True)
            groups = {}
            for entry in target_scenes:
                target, scene = entry['target'], entry['scene']
                # Include selection provenance to preserve truthful receipts.
                key = (target['width'], target['height'], scene['scene_selection']['resolved'], scene['scene_selection']['requested'])
                groups.setdefault(key, ([], scene))[0].append(target['id'])
            seed = self.settings.get('comparison_seed')
            if seed is None: seed = secrets.randbits(32)
            profile = self.selected_profile()
            workflows = []
            for key, (ids, target_scene) in groups.items():
                size = key[:2]
                target_scene.update(checkpoint=self.checkpoint, comparison_seed=seed, inference_profile=profile)
                workflow = build_workflow(self.checkpoint, target_scene['positive'], target_scene['negative'],
                                          *size, seed, profile=profile)
                workflows.append((size, ids, target_scene, workflow))
            with self.lock:
                self.preview = target_scenes[0]['scene'] | {'targets':targets, 'target_scenes':target_scenes}
            with self.lock: self.render_results = []
            for size, ids, scene, workflow in workflows:
                decision = guard()
                if decision != 'safe':
                    with self.lock:
                        self.state = 'deferred'
                        self.last_error = 'No Comfy job submitted: '+decision
                    return
                journal.write_text(json.dumps({'client_id':getattr(self.transport,'client_id','test'), 'state':'submitting'}))
                journal.chmod(0o600)
                outstanding = True
                job = self.transport.queue(workflow)
                if refresh_id: self.refresh_event('job_accepted', generation_id=refresh_id, prompt_id=job, targets=ids)
                with self.lock:
                    self.render_request = {'state':'submitted', 'reason':'Comfy accepted owned prompt', 'prompt_id':job}
                journal.write_text(json.dumps({'prompt_id':job, 'state':'queued'}))
                blocked = False
                deadline = time.monotonic()+600
                while time.monotonic() < deadline:
                    blocked = blocked or guard() != 'safe'
                    state = self.transport.inspect(job)
                    if state == 'pending' and blocked:
                        self.transport.cancel_pending(job)
                        state = self.transport.inspect(job)
                        if state == 'unknown':
                            outstanding = False
                            journal.unlink(missing_ok=True)
                            with self.lock: self.state = 'deferred'
                            return
                    if state == 'failed':
                        outstanding = False
                        journal.unlink(missing_ok=True)
                        raise ValueError('Comfy job failed; prior preview retained')
                    if state == 'complete':
                        outstanding = False
                        journal.unlink(missing_ok=True)
                        raw = self.transport.image(job)
                        blocked = blocked or guard() != 'safe'
                        metadata = {'generated_at':time.time(), 'prompt_id':job, 'testing_override':override_receipt, 'quarantine_evidence':self.quarantine, 'targets':ids, 'positive':scene['positive'],
                                    'negative':scene['negative'], 'scene':scene,
                                    'workflow_sha256':hashlib.sha256(json.dumps(workflow,sort_keys=True).encode()).hexdigest()}
                        result = self.store.save(raw,size,metadata,quarantined=blocked,guard=guard)
                        blocked = result['quarantined']
                        with self.lock:
                            self.state = 'quarantined' if blocked else 'image_preview_ready'
                            self.render_results.append({'targets':ids,'state':self.state,'id':result['id']})
                            if not blocked:
                                self.image_preview = result
                                for target in ids: self.previews_by_target[target] = result
                                from wallpaper import atomic_json
                                atomic_json(self.root/"previews-by-target.json", {target:record["id"] for target,record in self.previews_by_target.items()})
                        if refresh_id: self.refresh_event('render_complete', generation_id=refresh_id, targets=ids, quarantined=blocked, checkpoint=self.checkpoint, scene=scene.get('scene_selection'), weather_at=scene.get('observed_at'))
                        if blocked: return
                        if refresh_id and not auto_apply:
                            for target_id in ids: self.refresh_complete(target_id, refresh_id)
                        if auto_apply:
                            for target in targets:
                                if target["id"] not in ids: continue
                                if guard() != "safe": raise ValueError("Automatic apply deferred: activity or automation settings changed")
                                if refresh_id or scene.get('calendar_context_hash'):
                                    from refresh_freshness import result_fresh
                                    from scene import solar_daypart, solar_elevation
                                    instant = time.time()
                                    daypart = solar_daypart(solar_elevation(instant, location['latitude'], location['longitude']))
                                    if not result_fresh(scene, instant, self.settings['interval_minutes']*60, daypart, self.calendar_now(instant) if scene.get('calendar_context_hash') else None):
                                        raise ValueError('Stale scene: fresh weather/daypart/calendar render required')
                                try:
                                    applied = self.wallpaper.apply(target, result["id"], guard)
                                except Exception as error:
                                    if refresh_id:
                                        with self.lock:
                                            if self.scheduler.active and self.scheduler.active['generation_id'] == refresh_id:
                                                self.scheduler.fail(str(error), retryable=False)
                                                self.save_refresh()
                                    raise
                                with self.lock: self.wallpaper_action = applied
                                if refresh_id and applied.get('verified') is True:
                                    self.refresh_complete(target['id'], refresh_id, applied.get('applied_at'))
                        break
                    with self.lock: self.state = 'rendering_guard_blocked' if blocked else 'rendering'
                    time.sleep(self.poll_seconds)
                else:
                    raise ValueError('Comfy timeout; owned job retained in journal, further submissions locked')
            with self.lock:
                self.last_error = ''
                if auto_apply: self.state = 'wallpapers_applied'
        except SubmissionDeferred as error:
            outstanding = False
            journal.unlink(missing_ok=True)
            with self.lock:
                self.state = 'deferred'
                self.last_error = str(error)
        except Exception as error:
            with self.lock:
                self.state = 'failed_unreconciled' if outstanding else 'failed'
                self.last_error = str(error)
        finally:
            with self.lock:
                if self.state == 'quarantined' and self.quarantine:
                    self.last_error = 'Preview quarantined: '+self.quarantine['decision']+' ('+self.quarantine['reason']+'); current safe status cannot release it. Generate a new preview.'
                self.render_request = {'state':self.state, 'reason':self.last_error or ('Validated preview ready; wallpaper untouched' if self.state == 'image_preview_ready' else self.state), 'prompt_id':job}
            # A private receipt survives deferral/failure as well as publication.
            receipts = self.root/'job-receipts'
            try:
                receipts.mkdir(exist_ok=True, mode=0o700)
                with open(receipts/(secrets.token_hex(16)+'.json'), 'x') as f:
                    os.chmod(f.name, 0o600)
                    json.dump({'prompt_id':job, 'state':self.state,
                               'testing_override':override_receipt, 'quarantine':self.quarantine}, f)
            finally:
                with self.lock:
                    if refresh_id and self.scheduler.active and self.scheduler.active['generation_id'] == refresh_id:
                        self.refresh_event('refresh_incomplete', generation_id=refresh_id, state=self.state)
                        self.scheduler.fail('refresh_incomplete', retryable=not outstanding, monotonic_now=time.monotonic())
                        self.save_refresh()
                self.job_guard = None
                if not outstanding: self.render_lock.release()

    def save(self):
        p = self.root / 'settings.tmp'
        with open(p, 'w', encoding='utf-8') as f:
            os.chmod(p, 0o600)
            json.dump(self.settings, f)
            f.flush(); os.fsync(f.fileno())
        p.replace(self.root / 'settings.json')

    def target_displays(self, body):
        target = body.get('target', 'all')
        if not isinstance(target, str): raise ValueError('Invalid target')
        if target == 'all': return list(self.displays)
        targets = [d for d in self.displays if d['id'] == target]
        if not targets: raise ValueError('Target is not an active output')
        return targets

    def build_preview(self, body):
        targets = self.target_displays(body)
        if not self.settings['location']: raise ValueError('Look up and confirm a location first')
        self.state = 'checking_weather'
        try:
            target_scenes = self.target_scene_previews(self.settings['location'], targets)
            # No monitor: still allow a global prompt-only preview, never rotate.
            base = target_scenes[0]['scene'] if target_scenes else self.scene_preview(
                self.settings['location'], 'rural' if self.settings.get('scene_kind') == 'random' else None)
            self.preview = base | {'targets':targets, 'target_scenes':target_scenes}
            self.state = 'preview_ready'
            self.last_error = ''
            return self.preview | {'state':self.state}
        except Exception:
            self.state = 'failed'
            self.last_error = 'Weather preview unavailable; previous preview retained'
            raise

    def refresh_event(self, event, **fields):
        from wallpaper import atomic_json
        with self.lock:
            path = self.root/'refresh-events.json'
            try: events = json.loads(path.read_text())
            except (OSError, ValueError): events = []
            events.append({'at': time.time(), 'event': event, **fields})
            atomic_json(path, events[-100:])

    def save_refresh(self):
        from wallpaper import atomic_json
        atomic_json(self.root/'refresh-state.json', {'success': self.scheduler.success,
                    'pending': {k: sorted(v) for k, v in self.scheduler.pending.items()},
                    'calendar_success': self.calendar_success,
                    'permanent_error': self.scheduler.permanent_error})

    def refresh_complete(self, target, generation_id, at=None):
        with self.lock:
            if self.scheduler.complete(target, generation_id, time.time() if at is None else at):
                scene = (self.preview or {}).get('scene', self.preview or {}) if target=='prompt' else self.previews_by_target.get(target, {}).get('scene', {})
                if scene.get('calendar_context_hash'):
                    self.calendar_success.setdefault(self.scheduler.mode, {})[target] = scene['calendar_context_hash']
                self.refresh_event('apply_verified' if self.scheduler.mode == 'image_wallpaper' else 'preview_complete', generation_id=generation_id, target=target, mode=self.scheduler.mode)
                self.save_refresh()

    def reconcile_refresh(self, verified_restore=False):
        """Explicit read-only configuration check; never called by the timer."""
        if (self.render_lock.locked() and not verified_restore) or (self.root/'inflight.json').exists():
            raise ValueError('Wait for or reconcile the outstanding render')
        mode = self.settings['automation_kind']
        if not self.settings.get('location') or (mode != 'prompt_preview' and not self.checkpoint):
            raise ValueError('configuration_required')
        if mode != 'prompt_preview':
            targets = self.target_displays({'target':self.settings['automation_target']})
            if not targets: raise ValueError('No live targets')
            if self.model_gate() != 'safe': raise ValueError(self.model_gate())
            if mode == 'image_wallpaper':
                if self.wallpaper is None: raise ValueError('Wallpaper adapter not configured')
                for display in targets: self.wallpaper.preflight(display)
        self.scheduler.permanent_error = ''
        self.scheduler.retry_at = self.scheduler.failures = 0
        self.scheduler.safe_since = self.scheduler.last_observed = None
        self.last_error = ''
        self.save_refresh()

    def automatic_session_guard(self):
        if not self.settings['automation_enabled'] or self.override_status()['active']:
            return 'automation_changed'
        if (self.settings.get('catch_up_refresh', False) or self.settings.get('holiday_themes', False) or self.settings.get('seasonal_themes', False)):
            unlocked = self.session_activity.poll()
            if unlocked is not True:
                self.scheduler.observe_activity(False, unlocked, time.monotonic())
                return 'session_locked' if unlocked is False else 'session_unknown'
        return 'safe'

    def catchup_tick(self, now, monotonic_now):
        s = self.scheduler
        selected = self.settings['automation_target']
        targets = [d['id'] for d in self.displays if selected == 'all' or d['id'] == selected]
        if self.settings['automation_kind'] == 'prompt_preview': targets = ['prompt']
        s.configure(self.settings['automation_enabled'] and not self.override_status()['active'],
                    self.settings['automation_kind'], targets, self.settings['interval_minutes']*60)
        if not s.enabled:
            self.save_refresh()
            return
        unlocked = self.session_activity.poll()
        reason = 'startup' if not self.refresh_started else 'unlock' if unlocked is True and self.last_unlocked is not True else 'interval'
        self.refresh_started, self.last_unlocked = True, unlocked
        s.reconcile(now, reason)
        context = self.calendar_now(now)
        if not context['notice']:
            stale = [t for t in targets if self.calendar_success.get(s.mode, {}).get(t, context['context_hash']) != context['context_hash']]
            s.request('calendar_change', stale)
        safe = self.guard.get('decision') == 'safe' and 0 <= time.time()-self.guard.get('observed_at', 0) <= 15
        s.observe_activity(safe, unlocked, monotonic_now)
        summary = (tuple(sorted(s.pending)), s.blocker, unlocked)
        if summary != getattr(self, '_refresh_summary', None):
            self.refresh_event('coalesced_or_deferred', trigger=reason, targets=sorted(s.pending), waiting_reason=s.blocker)
            self._refresh_summary = summary
        self.save_refresh()
        if self.render_lock.locked() or (self.root/'inflight.json').exists(): return
        action = s.next_action(now, monotonic_now)
        if not action: return
        self.refresh_event('job_requested', generation_id=action['generation_id'], targets=action['targets'], mode=action['mode'])
        try:
            if not self.settings.get('location') or (action['mode'] != 'prompt_preview' and not self.checkpoint) or (action['mode'] == 'image_wallpaper' and self.wallpaper is None):
                self.last_error = 'configuration_required'
                self.state = 'failed'
                s.fail(self.last_error, retryable=False, monotonic_now=monotonic_now)
                self.save_refresh()
                return
            if action['mode'] == 'image_wallpaper':
                try:
                    for display in self.displays:
                        if display['id'] in action['targets']: self.wallpaper.preflight(display)
                except (ValueError, OSError) as error:
                    self.state, self.last_error = 'failed', str(error)
                    s.fail(self.last_error, retryable=False, monotonic_now=monotonic_now)
                    self.save_refresh()
                    return
            if action['mode'] == 'prompt_preview':
                self.build_preview({'target': selected})
                self.refresh_complete('prompt', action['generation_id'])
            else:
                result = self.dispatch('POST', '/v1/render', {'target': selected}, scheduled=True)
                if result.get('state') != 'queued':
                    s.fail(result.get('reason', 'deferred'), monotonic_now=monotonic_now)
        except Exception:
            self.state = 'failed'
            self.last_error = 'Refresh failed; confirm location, model and wallpaper configuration'
            s.fail('configuration_or_transport_failure', monotonic_now=monotonic_now)
        self.save_refresh()

    def tick(self, now=None, monotonic_now=None):
        now = time.time() if now is None else now
        with self.lock:
            if (self.settings.get('catch_up_refresh', False) or self.settings.get('holiday_themes', False) or self.settings.get('seasonal_themes', False)):
                self.catchup_tick(now, time.monotonic() if monotonic_now is None else monotonic_now)
                return
            if self.override_status()['active'] or not self.settings['automation_enabled'] or now < self.next_eligible_at: return
            self.next_eligible_at = now + self.settings['interval_minutes']*60
            try:
                if self.settings['automation_kind'] in ('image_preview','image_wallpaper'):
                    self.dispatch('POST', '/v1/render', {'target':self.settings['automation_target']}, scheduled=True)
                else:
                    self.build_preview({'target':'all'})
            except Exception:
                self.state = 'failed'
                self.last_error = 'Scheduled preview failed; confirm location and provider availability'

    def monitor(self, stop):
        previous = None
        while not stop.is_set():
            self.previous_sample = previous
            guard, previous = collect(previous, self.transport)
            displays, error = discover()
            with self.lock:
                self.guard, self.displays, self.display_error = guard, displays, error
            if self.comfy_service:
                self.comfy_service.maintain(self.render_lock.locked() or (self.root/'inflight.json').exists())
            self.tick()
            stop.wait(10)

    def dispatch(self, method, path, body, scheduled=False):
        with self.lock:
            if method == 'GET' and path == '/v1/status': return self.status()
            if method == 'POST' and path == '/v1/refresh/reconcile':
                if body != {'confirmation':'Reconcile automatic refresh'}:
                    raise ValueError('Explicit refresh reconciliation confirmation required')
                self.reconcile_refresh()
                return self.status()
            if method == 'POST' and path == '/v1/models/refresh':
                if self.render_lock.locked(): raise ValueError('Wait for current preview')
                self.refresh_models()
                return self.status()
            if method == 'PUT' and path == '/v1/testing-override':
                if set(body) - {'enabled', 'confirmation'} or type(body.get('enabled')) is not bool:
                    raise ValueError('enabled must be boolean')
                if body['enabled']:
                    if body.get('confirmation') != 'I accept stutter and OOM risk':
                        raise ValueError('Explicit stutter and OOM risk confirmation required')
                    if self.render_lock.locked(): raise ValueError('Wait for the current preview job')
                    self.settings['automation_enabled'] = False
                    self.save()
                    self.override_deadline = time.monotonic() + 600
                else:
                    self.override_deadline = 0.0
                self.override_generation += 1
                return self.status()
            if method == 'PUT' and path == '/v1/observation':
                if self.render_lock.locked(): raise ValueError('Wait for the current preview job')
                if body == {'enabled':False}:
                    self.observation = None
                    return self.status()
                import math
                required = {'observed_at','ttl_minutes','temperature_f','cloud_cover_percent','precipitation_mm','weather_code','location_zip'}
                if set(body) != required: raise ValueError('Provide the structured observation fields only')
                if not self.settings['location'] or body['location_zip'] != self.settings['location']['zip']:
                    raise ValueError('Observation must match confirmed location')
                for key,low,high in [('observed_at',time.time()-1800,time.time()+30),('ttl_minutes',1,60),
                                     ('temperature_f',-130,140),('cloud_cover_percent',0,100),('precipitation_mm',0,300)]:
                    value=body[key]
                    if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
                        raise ValueError('Invalid observation '+key)
                if type(body['weather_code']) is not int: raise ValueError('Invalid weather code')
                condition(body['weather_code'])
                expiry=body['observed_at']+body['ttl_minutes']*60
                if expiry <= time.time(): raise ValueError('Observation already expired')
                self.observation = dict(body, expires_at=expiry)
                return self.status()
            if method == 'POST' and path == '/v1/location/lookup':
                locations = resolve_zip(body.get('zip'))
                self.candidates = {secrets.token_urlsafe(24):(loc,time.time()) for loc in locations}
                return {'candidates':[loc | {'confirmation_id':key} for key,(loc,_) in self.candidates.items()]}
            if method == 'POST' and path == '/v1/calendar/preview':
                from holiday_preview import fixture_preview
                if set(body) != {'date'} or not self.settings.get('location'): raise ValueError('Confirmed location and preview date required')
                return fixture_preview(body['date'],self.settings['location'])
            if method == 'POST' and path == '/v1/preview': return self.build_preview(body)
            if method == 'PUT' and path == '/v1/settings':
                from holiday_settings import DEFAULTS, validate_settings
                validate_settings(body)
                if set(body) - set(DEFAULTS) - {'catch_up_refresh','checkpoint','comparison_seed','scene_kind','scene_overrides','framing','automation_enabled', 'automation_kind', 'automation_target', 'interval_minutes', 'location_confirmation'}: raise ValueError('Unknown setting')
                if 'catch_up_refresh' in body and type(body['catch_up_refresh']) is not bool:
                    raise ValueError('catch_up_refresh must be boolean')
                if 'comparison_seed' in body and body['comparison_seed'] is not None and (type(body['comparison_seed']) is not int or not 0 <= body['comparison_seed'] <= 4294967295): raise ValueError('Seed must be an unsigned 32-bit integer or null for random')
                if self.render_lock.locked() and any(k in body for k in ('checkpoint','comparison_seed')): raise ValueError('Wait for current preview')
                if 'checkpoint' in body:
                    if not self.checkpoint: raise ValueError('Renderer not enabled by owner')
                    if body['checkpoint'] not in [m['id'] for m in self.refresh_models()]: raise ValueError('Select a discovered reviewed checkpoint')
                if 'scene_kind' in body and body['scene_kind'] not in SCENE_CHOICES: raise ValueError('Invalid scene')
                if 'scene_overrides' in body:
                    overrides = body['scene_overrides']
                    known = {d['id'] for d in self.displays} | set(self.settings.get('scene_overrides', {}))
                    if not isinstance(overrides, dict) or any(
                        key not in known or value not in SCENE_CHOICES for key, value in overrides.items()
                    ): raise ValueError('Invalid monitor scene override')
                if 'framing' in body and body['framing'] not in FRAMING_MODES: raise ValueError('Invalid framing')
                if self.render_lock.locked() and any(k in body for k in ('scene_kind','scene_overrides','framing')): raise ValueError('Wait for current preview')
                update = dict(body)
                if 'automation_kind' in body:
                    if body['automation_kind'] not in ('prompt_preview','image_preview','image_wallpaper'):
                        raise ValueError('Invalid automation kind')
                    if body['automation_kind'] in ('image_preview','image_wallpaper') and not self.checkpoint:
                        raise ValueError('Image previews are not configured')
                if body.get('automation_kind') == 'image_wallpaper' and self.wallpaper is None:
                    raise ValueError('Wallpaper adapter not configured for automatic application')
                if 'automation_target' in body: self.target_displays({'target':body['automation_target']})
                if 'location_confirmation' in update:
                    key = update.pop('location_confirmation')
                    if not isinstance(key,str) or key not in self.candidates: raise ValueError('Confirm a specific lookup candidate')
                    loc, created = self.candidates[key]
                    if time.time()-created > 600: raise ValueError('Location lookup expired; look up again')
                    update['location'] = loc
                if 'automation_enabled' in body and type(body['automation_enabled']) is not bool:
                    raise ValueError('automation_enabled must be boolean')
                if 'interval_minutes' in body and (type(body['interval_minutes']) is not int or body['interval_minutes'] not in INTERVALS):
                    raise ValueError('Invalid interval')
                if update.get('automation_enabled') is True and self.override_status()['active']:
                    raise ValueError('Automation is paused during testing override')
                self.settings.update(update)
                if update:
                    self.scheduler.configure(False, self.settings['automation_kind'], [], self.settings['interval_minutes']*60)
                    self.refresh_started = False
                    self.save_refresh()
                if 'checkpoint' in update: self.checkpoint = update['checkpoint']
                self.next_eligible_at = time.time() + self.settings['interval_minutes']*60
                self.save()
                return self.status()
            if method == 'POST' and (path == '/v1/apply' or (path == '/v1/restore' and self.wallpaper)):
                if self.wallpaper is None: raise ValueError('Owner wallpaper adapter not configured')
                expected = 'Apply this validated preview' if path == '/v1/apply' else 'Restore previous wallpaper'
                if body.get('confirmation') != expected: raise ValueError('Explicit wallpaper confirmation required')
                if body.get('target','all') == 'all': raise ValueError('Choose one explicit monitor for wallpaper changes')
                targets = self.target_displays(body)
                if not self.render_lock.acquire(blocking=False): raise ValueError('Wait for current render before changing wallpaper')
                try:
                    if path == '/v1/apply':
                        result = self.wallpaper.apply(targets[0], body.get('preview_id'), self.wallpaper_guard)
                    else:
                        result = self.wallpaper.restore(targets[0], self.wallpaper_guard)
                    if result.get('verified') is True:
                        successes = self.scheduler.success.setdefault('image_wallpaper', {})
                        if path == '/v1/apply' and result.get('applied_at'):
                            successes[targets[0]['id']] = result['applied_at']
                        elif path == '/v1/restore':
                            successes.pop(targets[0]['id'], None)
                            # Restore owns the render lock; validate all remaining
                            # configuration/receipts before releasing a durable latch.
                            try: self.reconcile_refresh(verified_restore=True)
                            except (ValueError, OSError): pass
                        self.save_refresh()
                    self.state = result['state']
                    self.wallpaper_action = result
                    self.last_error = self.scheduler.permanent_error
                    return result
                except Exception as error:
                    self.last_error = str(error)
                    self.wallpaper_action = {'state':'failed', 'target':targets[0]['id'], 'reason':str(error), 'verified':False}
                    raise
                finally:
                    self.render_lock.release()
            if method == 'POST' and path in ('/v1/render', '/v1/restore'):
                self.target_displays(body)
                if 'force' in body and type(body['force']) is not bool: raise ValueError('force must be boolean')
                decision = self.status()['guard']['decision']
                policy = self.manual_policy() if path == '/v1/render' else None
                if scheduled:
                    expected_settings = dict(self.settings)
                    def scheduled_guard():
                        if self.settings != expected_settings or not self.settings['automation_enabled'] or self.override_status()['active']:
                            return 'automation_changed'
                        decision = self.automatic_session_guard()
                        decision = self.render_guard() if decision == 'safe' else decision
                        if decision != 'safe':
                            with self.lock: self.scheduler.observe_activity(False, True, time.monotonic())
                        return decision
                    def scheduled_startup():
                        if self.settings != expected_settings: return 'automation_changed'
                        decision = self.automatic_session_guard()
                        decision = self.startup_guard() if decision == 'safe' else decision
                        if decision != 'safe':
                            with self.lock: self.scheduler.observe_activity(False, True, time.monotonic())
                        return decision
                    scheduled_guard.startup = scheduled_startup
                    policy = (scheduled_guard, {'enabled':False, 'used':False, 'reasons':[], 'confirmation':None, 'ttl_seconds':0})
                if path == '/v1/render' and self.comfy_service and self.transport.owned_gpu_pid() is None:
                    decision = getattr(policy[0], 'startup', self.startup_guard)()
                elif policy and policy[1]['enabled']: decision = policy[0]()
                if path == '/v1/render' and self.model_gate() != 'safe': decision = self.model_gate()
                if path == '/v1/render' and decision != 'safe':
                    self.state = 'deferred'
                    self.last_error = 'No Comfy job submitted: '+decision
                    self.render_request = {'state':'deferred', 'reason':decision, 'prompt_id':None}
                    return {'state':self.state, 'reason':decision, 'prompt_id':None}
                if path == '/v1/render' and self.checkpoint:
                    targets = self.target_displays(body)
                    refresh_id = None
                    if scheduled and (self.settings.get('catch_up_refresh') or self.settings.get('holiday_themes') or self.settings.get('seasonal_themes')):
                        active = self.scheduler.active
                        if not active: return {'state':'deferred', 'reason':'No coordinator intent'}
                        refresh_id = active['generation_id']
                        targets = [t for t in targets if t['id'] in active['targets']]
                    if not targets: raise ValueError('No live targets; run from owning graphical session')
                    if not self.settings['location']: raise ValueError('Confirm a location first')
                    if not self.render_lock.acquire(blocking=False):
                        return {'state':self.state, 'reason':'A preview job is already in flight'}
                    self.state = 'queued'
                    self.last_error = ''
                    self.render_request = {'state':'queued', 'reason':'Checking eligibility/startup; not yet submitted to Comfy', 'prompt_id':None}
                    self.render_thread = threading.Thread(target=self.render_images,
                        args=(targets, dict(self.settings['location']), policy, scheduled and self.settings['automation_kind']=='image_wallpaper', refresh_id), daemon=True)
                    self.render_thread.start()
                    return {'state':'queued', 'reason':'Image preview requested; wallpaper remains untouched'}
                self.state = 'blocked_preview_only'
                return {'state': self.state, 'reason': 'GPU rendering and wallpaper changes are disabled in this build'}
            raise ValueError('Unknown endpoint')


def make_server(controller, port=8734):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, code, data):
            raw = json.dumps(data, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers(); self.wfile.write(raw)
        def handle_request(self):
            self.connection.settimeout(20)
            if self.headers.get('Origin') or self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
                return self.reply(403, {'error': 'Browser-origin requests forbidden'})
            if self.headers.get('Host') != '127.0.0.1:' + str(self.server.server_port):
                return self.reply(403, {'error': 'Invalid host'})
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + controller.token):
                return self.reply(401, {'error': 'Pair widget using local controller token'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 16384: raise ValueError('Body too large')
                if self.headers.get('Transfer-Encoding'): raise ValueError('Transfer encoding unsupported')
                if self.command != 'GET' and self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                    raise ValueError('JSON required')
                body = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(body, dict): raise ValueError('JSON object required')
                result = controller.dispatch(self.command, self.path, body)
                return self.reply(200, result)
            except (ValueError, TypeError, KeyError) as e:
                return self.reply(400, {'error': str(e)})
            except Exception:
                return self.reply(503, {'error': 'Operation unavailable; check controller environment/provider'})
        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path.home()/'.local/state/weather-horde-kde')
    parser.add_argument('--port', type=int, default=8734)
    parser.add_argument('--preview-checkpoint', help='Explicit existing standard SD/SDXL checkpoint; enables guarded manual image previews only')
    parser.add_argument('--automation-off', action='store_true',
                        help='Disable and persist automation before starting the monitor or API')
    parser.add_argument('--manual-wallpapers', action='store_true', help='Enable explicit per-monitor apply/restore; never automatic')
    parser.add_argument('--managed-comfy', action='store_true', help='Owner-installed on-demand Comfy user service')
    parser.add_argument('--comfy-idle-seconds', type=int, default=300)
    args = parser.parse_args()
    from receipt_lock import state_lock
    args.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Held throughout serving and shutdown; helper also verifies no process remains.
    with state_lock(args.state_dir,exclusive=False):
        run_controller(args)


def run_controller(args):
    controller = Controller(args.state_dir, checkpoint=args.preview_checkpoint,
                            managed_comfy=args.managed_comfy, comfy_idle_seconds=args.comfy_idle_seconds)
    if args.preview_checkpoint: controller.enable_reviewed_models()
    if args.manual_wallpapers:
        from wallpaper import WallpaperManager, PlasmaBackend
        displays, error = discover()
        if error: raise ValueError(error)
        backend = PlasmaBackend()
        for display in displays: backend.snapshot(display) # read-only capability preflight
        controller.wallpaper = WallpaperManager(args.state_dir, backend)
    server = make_server(controller, args.port)
    if args.automation_off:
        controller.settings['automation_enabled'] = False
        controller.save()
    stop = threading.Event()
    worker = threading.Thread(target=controller.monitor, args=(stop,), daemon=True)
    worker.start()
    print('Preview-only controller on 127.0.0.1:' + str(server.server_port), flush=True)
    try: server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=20)


if __name__ == '__main__': main()
