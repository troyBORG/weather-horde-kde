"""Pure checkpoint policy. Caller supplies frozen solar evidence and live IDs."""

DAYPARTS = ('daytime', 'golden hour', 'blue hour', 'twilight', 'night')


def defaults():
    # Suggestions are not consent: both saved pools start empty.
    return {'version': 1, 'mode': 'single', 'day': [], 'night': [],
            'mapping': dict(zip(DAYPARTS, ('day', 'day', 'night', 'night', 'night')))}


def resolve(daypart, policy, eligible, checkpoint, previous=None, rng=None):
    if policy['mode'] == 'lighting':
        result = {'checkpoint': None, 'pool': None, 'daypart': daypart, 'reason': ''}
        if daypart not in DAYPARTS:
            return result | {'reason': 'Unknown solar daypart; cannot select a model pool'}
        pool = policy['mapping'][daypart]
        result['pool'] = pool
        choices = list(dict.fromkeys(x for x in policy[pool] if x in eligible))
        if not choices:
            return result | {'reason': f'{pool.title()} pool has no eligible live checkpoint; edit pool or Discover models'}
        alternatives = [x for x in choices if x != previous]
        if rng is None:
            import secrets
            rng = secrets
        return result | {'checkpoint': rng.choice(alternatives or choices)}
    return {'checkpoint': checkpoint if checkpoint in eligible else None,
            'pool': 'single', 'daypart': daypart,
            'reason': '' if checkpoint in eligible else 'Selected checkpoint unavailable'}
