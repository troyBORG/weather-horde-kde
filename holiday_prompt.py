"""Bounded local motif composition; source-page prose never enters prompts."""
import json
from pathlib import Path


def decorate(scene, context, settings):
    result=dict(scene,calendar_context=context,season=context['season'],season_method=context['season_method'],
                holiday_ids=context['event_ids'],selected_theme=context['selected_theme'],
                theme_strength=context['theme_strength'],theme_catalog_version=context['catalog_version'],
                calendar_local_date=context['local_date'],calendar_timezone=context['timezone'],
                calendar_context_hash=context['context_hash'],calendar_valid_until_utc=context['valid_until_utc'])
    if settings.get('seasonal_themes',False) and context['season']:
        result['positive']+=' Plausible local '+context['season']+' vegetation and restrained seasonal palette; actual temperature and precipitation evidence take precedence.'
    if context['selected_theme']:
        try:
            data=json.loads(Path(__file__).with_name('holiday_themes.json').read_text())
            theme=data['themes'][context['selected_theme']]
            key='urban' if scene['weather_evidence']['scene_kind']=='urban' else 'natural'
            fragment=theme[key]
            if not isinstance(fragment,str) or not 0<len(fragment)<=300: raise ValueError('Unbounded motif')
            intensity = 'Barely noticeable accent: ' if context['theme_strength']=='subtle' else 'Restrained balanced accent: '
            result['positive']+=' Artistic decoration only: '+intensity+fragment+'. Keep the motif small and above the lower third; preserve existing weather, lighting and scene geometry. No readable banners or portraits.'
        except (OSError,ValueError,KeyError,TypeError):
            result['calendar_notice']='Theme data unavailable; ordinary weather scene only'
    return result
