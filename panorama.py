"""Bounded connected-desktop geometry; no display discovery or GPU side effects."""
import io
import math
from PIL import Image
from comfy_preview import MAX_BYTES, MAX_FINAL_PIXELS


def plan_layout(targets):
    if not targets or len(targets) > 16:
        raise ValueError('Connected panorama requires active displays')
    rectangles = []
    ids = set()
    for target in targets:
        name = target['id']
        if not isinstance(name, str) or not name or name in ids:
            raise ValueError('Connected panorama requires unique outputs')
        ids.add(name)
        x, y = target.get('x'), target.get('y')
        w, h, scale = target['width'], target['height'], target.get('scale')
        if any(type(v) is not int or abs(v) > 65536 for v in (x,y)):
            raise ValueError('Connected panorama requires live logical positions')
        if any(type(v) is not int or not 64 <= v <= 16384 for v in (w,h)) or w*h > MAX_FINAL_PIXELS:
            raise ValueError('Invalid panorama output dimensions')
        if type(scale) not in (int,float) or not math.isfinite(scale) or not .5 <= scale <= 4:
            raise ValueError('Invalid panorama scale')
        rectangles.append(dict(id=name, x=x, y=y, width=w, height=h, scale=scale))
    rectangles.sort(key=lambda r:r['id'])
    left = min(r['x'] for r in rectangles)
    top = min(r['y'] for r in rectangles)
    width = max(r['x']+r['width']/r['scale'] for r in rectangles)-left
    height = max(r['y']+r['height']/r['scale'] for r in rectangles)-top
    density = max(r['scale'] for r in rectangles)
    # Padding to 64 keeps exact-aspect latent geometry feasible. Downsample the
    # shared canvas, never independently scale geometry or drop desktop gaps.
    while True:
        size = [math.ceil(width*density/64)*64, math.ceil(height*density/64)*64]
        if max(size) <= 16384 and size[0]*size[1] <= MAX_FINAL_PIXELS:
            break
        density *= .95
    if min(size) < 64:
        raise ValueError('Panorama aspect ratio unsupported')
    for r in rectangles:
        r['box'] = [(r['x']-left)*density, (r['y']-top)*density,
                    (r['x']-left+r['width']/r['scale'])*density,
                    (r['y']-top+r['height']/r['scale'])*density]
    return dict(logical_bounds=[left,top,width,height], density=density, size=size, outputs=rectangles)


def crop_master(raw, plan):
    if len(raw) > MAX_BYTES:
        raise ValueError('Panorama image too large')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or list(image.size) != plan['size'] or getattr(image,'n_frames',1) != 1:
                raise ValueError('Panorama master dimensions or format invalid')
            image.verify()
    except OSError as error:
        raise ValueError('Panorama master is not a valid image') from error
    crops = {}
    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert('RGB')
        for output in plan['outputs']:
            # KScreen physical dimensions are already oriented. Extent resampling
            # maps the logical rectangle to native pixels without a second rotation.
            crop = image.transform((output['width'],output['height']), Image.Transform.EXTENT,
                                   output['box'], resample=Image.Resampling.BICUBIC)
            stream = io.BytesIO(); crop.save(stream, 'PNG')
            crops[output['id']] = stream.getvalue()
    return crops
