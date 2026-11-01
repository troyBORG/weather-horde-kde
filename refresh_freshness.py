"""Automatic apply freshness, separate from image integrity/geometry gates."""
import math


def result_fresh(scene, now, interval, daypart, calendar_context=None):
    stamp = scene.get('observed_at')
    return ((calendar_context is None or scene.get('calendar_context_hash') == calendar_context['context_hash']) and type(stamp) in (int, float) and math.isfinite(stamp) and
            0 <= now - stamp <= min(interval, 3600) and
            scene.get('weather_evidence', {}).get('daypart') == daypart)
