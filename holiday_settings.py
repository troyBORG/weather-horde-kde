"""Strict calendar preferences, independent of automation/ownership settings."""
from datetime import date
from calendar_context import load_catalog

DEFAULTS = {'seasonal_themes':False,'holiday_themes':False,'holiday_preset':'mainstream_iowa',
            'theme_strength':'balanced','holiday_date_mode':'actual','disabled_holidays':[],
            'enabled_holidays':[],'holiday_priorities':{},'calendar_subdivision':'', 'holiday_preview_date':''}


def validate_settings(body):
    for key in ('seasonal_themes','holiday_themes'):
        if key in body and type(body[key]) is not bool: raise ValueError(key+' must be boolean')
    for key,choices in [('holiday_preset',('mainstream_iowa','metadata_only')),('theme_strength',('subtle','balanced')),
                        ('holiday_date_mode',('actual','observed')),('calendar_subdivision',('', 'IA'))]:
        if key in body and body[key] not in choices: raise ValueError('Invalid '+key)
    if any(k in body for k in ('disabled_holidays','enabled_holidays','holiday_priorities')):
        ids={e['id'] for e in load_catalog()['events']}
        for key in ('disabled_holidays','enabled_holidays'):
            if key in body:
                value=body[key]
                if not isinstance(value,list) or any(not isinstance(v,str) or v not in ids for v in value) or len(value)!=len(set(value)):
                    raise ValueError('Invalid '+key)
        if 'holiday_priorities' in body:
            value=body['holiday_priorities']
            if not isinstance(value,dict) or any(k not in ids or type(v) is not int or not -1000<=v<=1000 for k,v in value.items()): raise ValueError('Invalid holiday_priorities')
    if 'holiday_preview_date' in body:
        value=body['holiday_preview_date']
        if not isinstance(value,str): raise ValueError('Invalid preview date')
        if value and (len(value)!=10 or date.fromisoformat(value).isoformat()!=value): raise ValueError('Invalid preview date')
