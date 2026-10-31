"""Automatic apply freshness, separate from image integrity/geometry gates."""
import math


def result_fresh(scene, now, interval, daypart):
    stamp = scene.get('observed_at')
    return (type(stamp) in (int, float) and math.isfinite(stamp) and
            0 <= now - stamp <= min(interval, 3600) and
            scene.get('weather_evidence', {}).get('daypart') == daypart)
