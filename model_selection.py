"""Pure checkpoint policy. Caller supplies frozen solar evidence and live IDs."""

DAYPARTS = ('daytime', 'golden hour', 'blue hour', 'twilight', 'night')


def defaults():
    # Suggestions are not consent: both saved pools start empty.
    return {'version': 1, 'mode': 'single', 'day': [], 'night': [],
            'mapping': dict(zip(DAYPARTS, ('day', 'day', 'night', 'night', 'night')))}


def merge_policy(current, update):
    """Validate a partial edit without aliasing any saved lists or mapping."""
    import copy
    if not isinstance(update, dict) or set(update) - set(defaults()):
        raise ValueError('Invalid model policy fields')
    result = copy.deepcopy(current)
    for key, value in update.items():
        if key == 'mapping':
            if not isinstance(value, dict) or set(value) - set(DAYPARTS):
                raise ValueError('Mapping must use the five solar dayparts')
            result['mapping'].update(value)
        else:
            result[key] = copy.deepcopy(value)
    if type(result['version']) is not int or result['version'] != 1:
        raise ValueError('Unsupported model policy version')
    if result['mode'] not in ('single', 'lighting'):
        raise ValueError('Choose single or lighting model mode')
    for pool in ('day', 'night'):
        values = result[pool]
        if not isinstance(values, list) or any(not isinstance(x, str) or not x or any(ord(c)<32 for c in x) for x in values):
            raise ValueError('Model pools require exact nonempty checkpoint identifiers')
        result[pool] = list(dict.fromkeys(values))
    if set(result['mapping']) != set(DAYPARTS) or any(x not in ('day', 'night') for x in result['mapping'].values()):
        raise ValueError('Map each solar daypart to day or night')
    return result


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
