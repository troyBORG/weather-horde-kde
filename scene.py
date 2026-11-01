"""ZIP and weather prompt previews; remote data never authorizes a render."""
from datetime import datetime, timezone
import json
import math
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

NEGATIVE = ('mirrored, duplication, bisected, twin, double, reflection, symmetrical, split scene, '
            'duplicate objects, extra horizon, extra layer, overlapping elements, two perspectives, '
            'ghosting, duplicated buildings, repetitive patterns, unnatural symmetry, overlaid images, '
            'stitched, dual image, cloned details, text, letters, watermark, logo, readable signage, '
            'CGI, painting, illustration, anime, skyscrapers, large-city skyline, mountains, dramatic '
            'cliffs, ocean, riverfront, palm trees, warped storefronts, distorted architecture, '
            'oversaturated, blurry, low resolution, visible moon')


def fetch_json(url):
    # All callers construct URLs from constant origins and validated scalar data.
    req = Request(url, headers={'User-Agent':'WeatherHordeKDE/0.1 (local preview)'})
    with urlopen(req, timeout=12) as response:
        data = response.read(1024*1024+1)
        if len(data) > 1024*1024: raise ValueError('Provider response too large')
        return json.loads(data)


def forecast(location, fetch=fetch_json):
    params = {'latitude':location['latitude'], 'longitude':location['longitude'], 'timezone':'auto',
              'current':'temperature_2m,weather_code,is_day,cloud_cover,precipitation',
              'temperature_unit':'fahrenheit', 'precipitation_unit':'mm',
              'timeformat':'unixtime', 'forecast_days':1}
    return fetch('https://api.open-meteo.com/v1/forecast?' + urlencode(params))


def resolve_zip(zip_code, fetch=fetch_json):
    if not isinstance(zip_code, str) or not re.fullmatch(r'[0-9]{5}', zip_code):
        raise ValueError('Enter exactly five US ZIP digits')
    payload = fetch('https://api.zippopotam.us/us/' + zip_code)
    result = []
    for place in payload['places'][:10]:
        lat, lon = float(place['latitude']), float(place['longitude'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Invalid coordinates')
        loc = {'zip':zip_code, 'town':str(place['place name'])[:100], 'state':str(place['state'])[:100],
               'latitude':lat, 'longitude':lon, 'source':'Zippopotam.us ZIP centroid; Open-Meteo timezone'}
        loc['timezone'] = forecast(loc, fetch)['timezone']
        ZoneInfo(loc['timezone'])
        result.append(loc)
    if not result: raise ValueError('No ZIP candidates')
    return result


def condition(code):
    if code == 0: return 'clear skies'
    if code == 1: return 'mainly clear skies'
    if code == 2: return 'partly cloudy skies'
    if code == 3: return 'overcast skies'
    if code in (45,48): return 'fog'
    if code in (51,53,55,56,57): return 'drizzle'
    if code in (61,63,65,66,67,80,81,82): return 'rain'
    if code in (71,73,75,77,85,86): return 'snowfall'
    if code in (95,96,99): return 'thunderstorms'
    raise ValueError('Unknown weather code; no factual preview available')


def solar_elevation(timestamp, latitude, longitude):
    """Approximate geometric solar altitude (NOAA fractional-year equations).

    UTC avoids local-midnight/DST and sunset-wrap errors. No refraction or terrain
    correction: this is a lighting classifier, not an exact sunrise ephemeris.
    """
    if not all(math.isfinite(x) for x in (timestamp, latitude, longitude)):
        raise ValueError('Invalid solar coordinates/time')
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Invalid solar coordinates')
    utc = datetime.fromtimestamp(timestamp, timezone.utc)
    hour = utc.hour + utc.minute / 60 + utc.second / 3600
    days = (datetime(utc.year + 1, 1, 1) - datetime(utc.year, 1, 1)).days
    gamma = 2 * math.pi / days * (utc.timetuple().tm_yday - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    angle = math.radians(((hour * 60 + eqtime + 4 * longitude) % 1440) / 4 - 180)
    lat = math.radians(latitude)
    sine = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(angle)
    return math.degrees(math.asin(max(-1, min(1, sine))))


def solar_daypart(elevation):
    """Bounded twilight, including polar day/night without fictitious events."""
    if not math.isfinite(elevation) or not -90 <= elevation <= 90:
        raise ValueError('Invalid solar elevation')
    if elevation < -18: return 'night'
    if elevation < -6: return 'twilight'
    if elevation < -0.833: return 'blue hour'
    if elevation < 6: return 'golden hour'
    return 'daytime'


PROMPT_VERSION = 'night-lunar-2'


COMPOSITION_VERSION = 'desktop-portrait-1'
FRAMING_MODES = ('auto', 'natural', 'desktop_portrait')


def compose_for_target(scene, width, height, framing='auto'):
    """Add framing to a shared weather snapshot, never mutate it or resize pixels.

    Fractions are measured down from the top, not discovered widget coordinates.
    Auto is deliberately limited to portrait streets; explicit portrait framing
    can reserve generic foreground in other scenes without introducing houses.
    """
    if framing not in FRAMING_MODES:
        raise ValueError('Invalid framing')
    if any(type(v) is not int or v <= 0 for v in (width, height)):
        raise ValueError('Invalid composition geometry')
    urban = scene.get('weather_evidence', {}).get('scene_kind') == 'urban'
    active = height > width and (framing == 'desktop_portrait' or (framing == 'auto' and urban))
    composition = {'version':COMPOSITION_VERSION, 'requested':framing,
                   'profile':'desktop_portrait' if active else 'natural',
                   'width':width, 'height':height,
                   'notice':'Prompt guidance only, not a pixel-placement constraint; no widget movement or image crop'}
    result = dict(scene, composition=composition)
    if active:
        subject = ('town roofs and street horizon' if urban else 'natural horizon and main scene features')
        foreground = ('simple road and verge' if urban else 'simple ground or clearing appropriate to the scene')
        composition.update(horizon_y_fraction=[.55, .65], quiet_foreground_fraction=[.25, .30])
        result['positive'] += (
            ' Portrait desktop composition: ground-level camera aimed slightly downward, '
            'not an overhead or aerial view; horizon near middle-to-lower third. '
            f'Place the {subject} around 55-65% down from the top; '
            'keep key focal detail above the lower third, with a rule-of-thirds balance. '
            f'Reserve the lower 25-30% for low-detail {foreground}; '
            'the foreground extends below the subject to the bottom edge. '
            'Keep soft top corners and subdued contrast behind clock and status overlays; '
            'no oversized sky. Preserve the existing weather and physically correct lighting. '
            'Do not draw widgets, clocks or interface elements.')
        result['negative'] += ', sky-dominated framing, overhead view, aerial view, interface elements'
        if urban: result['negative'] += ', tiny town at bottom edge'
    return result


def lunar_evidence(timestamp, latitude, longitude):
    """Topocentric equator-of-date, geometric altitude; offline Astronomy Engine."""
    import astronomy_vendor as astro
    if not all(math.isfinite(x) for x in (timestamp, latitude, longitude)) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Invalid lunar time/coordinates')
    t = astro.Time.Parse(datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace('+00:00','Z'))
    observer = astro.Observer(latitude, longitude, 0)
    eq = astro.Equator(astro.Body.Moon, t, observer, True, True)
    hor = astro.Horizon(t, observer, eq.ra, eq.dec, astro.Refraction.Airless)
    phase = astro.MoonPhase(t)
    fraction = astro.Illumination(astro.Body.Moon,t).phase_fraction
    label = ('new' if fraction < .02 else 'full' if fraction > .98 else
             ('waxing' if phase < 180 else 'waning') + (' crescent' if fraction < .45 else ' quarter' if fraction < .55 else ' gibbous'))
    return {'altitude_degrees':round(hor.altitude,3), 'azimuth_degrees':round(hor.azimuth,3),
            'illumination':round(fraction,5), 'phase_degrees':round(phase,3), 'phase':label,
            'calculated_at':timestamp, 'method':'Astronomy Engine 2.1.19; topocentric, geometric, observer height 0m',
            'uncertainty':'ZIP centroid not camera location; no terrain/refraction; conservative 3 degree horizon margin; sky visibility not guaranteed'}


def moon_visible(moon, cloud, opaque, daypart):
    return (moon['altitude_degrees'] > 3 and moon['illumination'] >= .02 and
            cloud is not None and cloud < 70 and not opaque and daypart in ('night','twilight','blue hour'))


def weather_preview(location, fetch=fetch_json, *, scene_kind='rural', observation=None, calendar_settings=None, calendar_context=None):
    if scene_kind not in ('rural', 'urban', 'townpark', 'woodland', 'river'):
        raise ValueError('Unknown scene kind')
    data = forecast(location, fetch)
    provider_current = dict(data['current'])
    current = dict(provider_current)
    manual = bool(observation and observation['expires_at'] > time.time() and observation['location_zip'] == location['zip'])
    if manual:
        current.update(time=observation['observed_at'], temperature_2m=observation['temperature_f'],
                       weather_code=observation['weather_code'], cloud_cover=observation['cloud_cover_percent'],
                       precipitation=observation['precipitation_mm'])
    observed = float(current['time'])
    if not math.isfinite(observed) or not -300 <= time.time()-observed <= 7200:
        raise ValueError('Weather is stale or has an invalid observation time')
    temp = current['temperature_2m']
    if type(temp) not in (int,float) or not math.isfinite(temp): raise ValueError('Invalid temperature')
    if current['is_day'] not in (0,1): raise ValueError('Missing day/night evidence')
    local = datetime.fromtimestamp(observed, ZoneInfo(location['timezone']))
    from calendar_context import resolve_calendar
    from holiday_prompt import decorate
    calendar_settings = calendar_settings or {}
    context = calendar_context if calendar_context is not None else resolve_calendar(datetime.fromtimestamp(time.time(),timezone.utc),location,calendar_settings)
    season = context['season']
    cloud = current.get('cloud_cover')
    precip = current.get('precipitation')
    for name, value, maximum in (('cloud cover', cloud, 100), ('precipitation', precip, None)):
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)
                                  or value < 0 or (maximum is not None and value > maximum)):
            raise ValueError('Invalid ' + name)
    weather = condition(current['weather_code'])
    # High measured/modelled cloud fraction wins over a conflicting clear WMO label.
    opaque = current['weather_code'] not in (0, 1, 2) or (cloud is not None and cloud >= 90)
    if current['weather_code'] in (0, 1, 2) and opaque:
        weather = 'overcast skies'
    astronomy_at = time.time()
    elevation = solar_elevation(astronomy_at, location['latitude'], location['longitude'])
    daylight = solar_daypart(elevation)
    moon = lunar_evidence(astronomy_at, location['latitude'], location['longitude'])
    visible = moon_visible(moon, cloud, opaque, daylight)
    anchor = ('Ground-level view at the town edge: a grassy verge in the foreground, '
              'gently rolling Iowa farmland in the midground, low deciduous tree lines on the horizon.')
    if location['zip'] != '52742':
        anchor = 'A single coherent ground-level landscape; no named landmarks or invented skyline.'
    if scene_kind == 'urban':
        anchor = ('Ground-level view along a quiet low-rise small-town street, modest roofs, '
                  'deciduous street trees and spaced utility wires; no invented landmarks. ')
    if scene_kind == 'townpark':
        anchor = 'A quiet small-town park, grass and deciduous trees, a simple path and occasional localized path lamps; no named landmarks.'
    if scene_kind == 'river':
        anchor = 'Ground-level view from a grassy riverbank, a gently winding river in the midground and low deciduous trees along the far bank; no invented landmarks, mountains or skyline.'
    if scene_kind == 'woodland':
        anchor = 'A deciduous woodland edge, irregular tree silhouettes and a natural clearing; no buildings or invented landmarks.'
    lighting = {
        'daytime': 'Natural daytime illumination, physically consistent shadows. ',
        'golden hour': ('Low sun behind cloud cover, soft diffuse light and subdued colors. ' if opaque else
                        'Warm low-angle sunlight and long grounded shadows. '),
        'blue hour': 'Cool ambient blue-hour illumination, subdued ground detail, lamps beginning to dominate. ',
        'twilight': 'Very dim sky with faint residual solar light, mostly dark ground. ',
        'night': '',
    }[daylight]
    negative = NEGATIVE
    if daylight == 'night':
        lighting = ('A deep night photograph, physically dark sky and dark ground silhouettes, '
                    'restrained exposure, only localized artificial light pools where lamps are present. ')
        if opaque:
            lighting += ('Opaque cloud cover, dim cool gray to brownish gray clouds from diffuse artificial skyglow, '
                         'low contrast cloud texture, unlit terrain remains dark. ')
            negative += ', stars, star trails, Milky Way'
        negative += ', sunset, sunrise, dusk, twilight, orange horizon, solar horizon glow, golden hour, daylight, brightly lit landscape'
    if visible:
        negative = negative.replace(', visible moon', '')
        lighting += f"A small {moon['phase']} moon above the horizon, only in open sky, never oversized; subdued lunar illumination. "
    weather_visual = {
        'clear skies': 'Unbroken open sky. ',
        'mainly clear skies': 'Mostly open sky with isolated small clouds. ',
        'partly cloudy skies': 'Broken cloud patches separated by open sky. ',
        'overcast skies': 'Continuous opaque cloud ceiling and soft diffuse illumination. ',
        'fog': 'Fog obscures distant details, visibility fades with distance. ',
        'drizzle': 'Fine drizzle and lightly wet surfaces. ',
        'rain': 'Rain streaks where illuminated, wet surfaces with restrained light glints. ',
        'snowfall': 'Falling snow visible where illuminated; ground accumulation is unspecified. ',
        'thunderstorms': 'Dense storm clouds and rain, wet surfaces; lightning is not assumed. ',
    }[weather]
    evidence = {'source':'Open-Meteo model current conditions', 'manual_override':False,
                'weather_code':current['weather_code'], 'temperature_f':temp, 'scene_kind':scene_kind,
                'cloud_cover_percent':current.get('cloud_cover'),
                'precipitation_mm':current.get('precipitation'),
                'observed_at':observed, 'age_seconds':round(time.time()-observed, 1),
                'freshness':'within accepted window (-300 to 7200 seconds)',
                'timezone':location['timezone'], 'local_time':local.isoformat(),
                'provider_is_day':current['is_day'], 'daypart':daylight,
                'solar_elevation_degrees':round(elevation, 3),
                'solar_method':'NOAA approximate geometric elevation; no terrain/refraction correction'}
    evidence.update(lunar=moon, moon_visibility_permitted=visible, prompt_version=PROMPT_VERSION,
                    geography_notice='Weather-inspired regional composition, not landmark reconstruction')
    if manual:
        evidence.update(source='Manual user observation', manual_override=True, expires_at=observation['expires_at'],
                        provider_current=provider_current)
    positive = (f"Photorealistic weather-inspired landscape near {location['town']}, {location['state']}, "
                f"during {season} at {daylight}. {anchor} {weather.capitalize()}, {temp:g} degrees F. "
                f"{lighting}{weather_visual}One perspective, one horizon, natural proportions, no readable signs.")
    return decorate({'positive':positive, 'negative':negative, 'weather_evidence':evidence, 'observed_at':observed, 'weather':weather,
            'temperature_f':temp, 'season':season, 'time_of_day':daylight,
            'moon_policy':'permitted above horizon in open sky' if visible else 'omitted: horizon, phase, daylight or weather visibility gate',
            'prompt_version':PROMPT_VERSION, 'image_url':'',
            'notice':'Prompt/geometry preview only — no image rendered and no wallpaper changed'}, context, calendar_settings)
