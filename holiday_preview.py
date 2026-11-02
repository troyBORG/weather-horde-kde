"""Offline illustrative weather fixture, never an image-generation request."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from scene import weather_preview, compose_for_target
from holiday_settings import validate_settings


def fixture_preview(day, location, *, scene='urban', width=1080, height=1920, settings=None, theme_override=None):
    validate_settings({'holiday_preview_date':day})
    if not day: raise ValueError('Preview date required')
    instant=datetime.combine(date.fromisoformat(day),time(12),ZoneInfo(location['timezone']))
    location=dict(location)
    location.setdefault('zip','00000'); location.setdefault('town','Offline fixture'); location.setdefault('state','Illustrative location')
    data={'current':{'time':instant.timestamp(),'temperature_2m':65,'weather_code':3,'is_day':1,'cloud_cover':100,'precipitation':0}}
    preferences={'holiday_themes':True,'seasonal_themes':True}|(settings or {})
    from calendar_context import resolve_calendar, load_catalog
    import hashlib
    context=resolve_calendar(instant,location,preferences)
    if theme_override is not None:
        if theme_override not in {e['theme_id'] for e in load_catalog()['events'] if e['theme_id']}: raise ValueError('Unknown preview theme')
        context.update(selected_theme=theme_override,selection_reason='manual offline preview override',context_hash=hashlib.sha256((context['context_hash']+'preview:'+theme_override).encode()).hexdigest())
    result=weather_preview(location,lambda _:data,scene_kind=scene,calendar_settings=preferences,calendar_context=context,now_utc=instant)
    result['weather_evidence']['source']='Declared offline fixture: 65 F, overcast, no precipitation; NOT live weather'
    result['fixture_weather']=True
    result['notice']='Offline date preview only; no networking, GPU, apply, system clock or scheduler changes'
    return compose_for_target(result,width,height)
