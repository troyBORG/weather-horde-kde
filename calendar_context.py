"""Pure injected-clock calendar resolver; runtime never fetches holiday sources."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import calendar
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def load_catalog():
    return json.loads((ROOT/'holiday_catalog.json').read_text())


def occurrence(rule, year):
    kind = rule['kind']
    if kind == 'fixed':
        if rule['month']==2 and rule['day']==29 and not calendar.isleap(year): return None
        return date(year, rule['month'], rule['day'])
    if kind in ('offset','week'):
        base = occurrence(rule['base'], year)
        if base is None: return None
        return base + timedelta(days=rule['days']) if kind=='offset' else base-timedelta(days=(base.weekday()-rule['week_start'])%7)
    if kind == 'nth_weekday':
        first = date(year, rule['month'], 1)
        result = first + timedelta(days=(rule['weekday']-first.weekday()) % 7 + 7*(rule['n']-1))
        return result if result.month == rule['month'] else None
    if kind == 'last_weekday':
        end = date(year, rule['month'], calendar.monthrange(year, rule['month'])[1])
        return end - timedelta(days=(end.weekday()-rule['weekday']) % 7)
    if kind in ('nearest_weekday','on_or_before'):
        base = date(year,rule['month'],rule['day'])
        delta = (rule['weekday']-base.weekday()) % 7
        if delta > (3 if kind == 'nearest_weekday' else 0): delta -= 7
        return base + timedelta(days=delta)
    raise ValueError('Unknown date rule')


def resolve_calendar(now_utc, location, settings, catalog=None):
    if now_utc.tzinfo is None: raise ValueError('Calendar requires an aware instant')
    result = dict(local_date=None,timezone=location.get('timezone'),season=None,season_method='meteorological',
                  event_ids=[],events=[],selected_theme=None,selection_reason='no theme',valid_until_utc=None,
                  catalog_version=None,notice='',theme_strength=settings.get('theme_strength','balanced'))
    try:
        zone = ZoneInfo(location.get('timezone',''))
        local = now_utc.astimezone(zone)
    except (ZoneInfoNotFoundError,ValueError,TypeError):
        result['notice']='Calendar timezone unresolved; confirm location timezone'
        result['context_hash']=hashlib.sha256(result['notice'].encode()).hexdigest()
        return result
    season = ('winter','spring','summer','autumn')[(local.month % 12)//3]
    if location.get('latitude',0)<0: season = {'winter':'summer','spring':'autumn','summer':'winter','autumn':'spring'}[season]
    boundary = datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),zone).astimezone(timezone.utc)
    result.update(local_date=local.date().isoformat(),season=season,valid_until_utc=boundary.isoformat())
    events=[]
    subdivision = settings.get('calendar_subdivision') or location.get('subdivision_code','')
    country = location.get('country_code','')
    digest='unavailable'
    try:
        catalog=load_catalog() if catalog is None else catalog
        if catalog['schema_version'] != 1: raise ValueError('schema')
        digest=hashlib.sha256(json.dumps(catalog,sort_keys=True).encode()).hexdigest()
        result['catalog_version']=catalog['version']
        ids=set()
        for event in catalog['events']:
            if event['id'] in ids: raise ValueError('duplicate ID')
            ids.add(event['id'])
            scopes=[c['jurisdiction'] for c in event['classifications']]
            if country!='US' or ('US' not in scopes and 'US-'+subdivision not in scopes): continue
            for year in (local.year-1,local.year,local.year+1):
                actual=occurrence(event['rule'],year)
                if actual is None: continue
                selected_date=actual
                if settings.get('holiday_date_mode','actual')=='observed' and event['observed_policy']=='nearest_weekday':
                    selected_date+=timedelta(days=-1 if actual.weekday()==5 else 1 if actual.weekday()==6 else 0)
                duration=7 if event['rule']['kind']=='week' else 1
                if selected_date <= local.date() < selected_date+timedelta(days=duration):
                    # Show only classifications applicable to the chosen jurisdiction.
                    events.append(dict(event,classifications=[c for c in event['classifications'] if c['jurisdiction'] in ('US','US-'+subdivision)],actual_date=actual.isoformat(),occurrence_kind='observed' if actual!=selected_date else 'actual'))
        candidates=[e for e in events if e['theme_id'] and (e['default_enabled'] or e['id'] in settings.get('enabled_holidays',[])) and e['id'] not in settings.get('disabled_holidays',[])]
        priorities=settings.get('holiday_priorities',{})
        candidates.sort(key=lambda e:(-priorities.get(e['id'],e['priority']),e['id']))
        if candidates and settings.get('holiday_themes',False):
            chosen=candidates[0]
            result.update(selected_theme=chosen['theme_id'],selection_reason=('explicit priority' if chosen['id'] in priorities else 'default priority')+' then stable ID')
        result.update(events=events,event_ids=[e['id'] for e in events])
    except (OSError,ValueError,KeyError,TypeError,OverflowError):
        result.update(events=[],event_ids=[],selected_theme=None,notice='Holiday catalog unavailable or invalid; ordinary weather/season only')
    # Metadata-only observances and ordinary dates do not schedule needless GPU work.
    identity=[season if settings.get('seasonal_themes',True) else None,result['selected_theme'],result['theme_strength'],
              digest,zone.key,country,subdivision,location.get('latitude'),location.get('longitude')]
    result['context_hash']=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    return result
