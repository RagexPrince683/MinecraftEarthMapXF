#!/usr/bin/env python3
"""Prepare authoritative terrain inputs before WorldPainter applies layers.

No source image is modified. Disk-backed working arrays and haloed local passes
bound processing allocations; Pillow decodes one native asset at a time.
See TERRAIN_PIPELINE_AUDIT.md.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import tempfile

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from validate_xenoearth_source import PROFILES, PROFILE_ALIASES, required_images
import vegetation

Image.MAX_IMAGE_PIXELS = None  # Only dimension-checked repository rasters are read.
CONNECTIVITY = np.ones((3, 3), dtype=np.uint8)
SURFACE_COLORS = {
    (0, 255, 0): 1, (255, 255, 0): 5, (255, 255, 255): 40,
    (127, 0, 0): 1, (255, 0, 0): 6, (150, 150, 150): 1,
    (255, 127, 0): 5, (0, 127, 127): 1, (0, 148, 255): 5,
    (230, 230, 230): 1, (170, 170, 170): 1,
}
AREA_BOUNDS = (1, 3, 7, 15, 63, 255, 1023, 4095, 16383)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(root, path):
    return {'path': path.relative_to(root).as_posix(), 'sha256': sha256(path)}


def configuration(root):
    cfg = json.loads((root / 'terrain-processing.json').read_text())
    if cfg['formatVersion'] != 1 or cfg['seaLevel'] != 62:
        raise ValueError('processing format must be 1 and sea level must be 62')
    if cfg['sourceSeaSample'] != 61.5 * 257 or cfg['sourceSampleQuantum'] != 257:
        raise ValueError('source encoding must match the audited rasters')
    if cfg['referenceSourceScale'] != 40:
        raise ValueError('source vertical normalization must use reference scale 40')
    if not 1 < cfg['minimumFloorY'] < cfg['seaLevel'] < cfg['maximumPeakY'] < 254:
        raise ValueError('vertical curve needs safe floor and peak headroom')
    for key in ('oceanCurve', 'landCurve'):
        curve = np.asarray(cfg[key], dtype=float)
        if curve.ndim != 2 or curve.shape[1] != 2 or len(curve) < 2:
            raise ValueError(f'{key} must contain relief/Y pairs')
        if not np.isfinite(curve).all() or not (np.diff(curve, axis=0) > 0).all():
            raise ValueError(f'{key} must be finite and strictly increasing')
    if (cfg['oceanCurve'][-1] != [0, 62] or cfg['landCurve'][0] != [0, 62]
            or cfg['oceanCurve'][0][1] != cfg['minimumFloorY']
            or cfg['landCurve'][-1][1] != cfg['maximumPeakY']):
        raise ValueError('curves must meet at sea level and use the safe limits')
    if not cfg['minimumFloorY'] < cfg['deepOceanFloorY'] < cfg['shallowOceanFloorY'] < 62:
        raise ValueError('ocean classification bands are invalid')
    radius = cfg['categoricalMajorityRadius']
    if radius not in (0, 1, 2) or not ((2 * radius + 1)**2 / 2 < cfg['categoricalMajorityVotes'] <= (2 * radius + 1)**2):
        raise ValueError('categorical votes must be a strict majority of the window')
    for key in ('biomeMinimumArea', 'surfaceMinimumArea', 'waterMinimumArea',
                'waterPreserveSpan', 'coastProtectionRadius', 'beachRadius',
                'beachMinimumArea', 'beachContextRadius', 'coastalShelfRadius', 'elevationRadius', 'tileSize'):
        if type(cfg[key]) is not int or cfg[key] < 0:
            raise ValueError(f'{key} must be a nonnegative integer')
    if not 64 <= cfg['tileSize'] <= 2048 or cfg['elevationRadius'] > 2:
        raise ValueError('tile size must be 64..2048 and elevation radius 0..2')
    if cfg['beachContextRadius'] < cfg['beachRadius']:
        raise ValueError('beach context must cover the beach width')
    if not 0.5 < cfg['componentBoundarySupport'] <= 1:
        raise ValueError('component replacement needs dominant boundary support')
    if not 0 <= cfg['elevationBlend'] <= 1:
        raise ValueError('elevation blend must be 0..1')
    for key in ('elevationMaximumNeighborDelta', 'elevationMaximumAdjustment', 'beachMaximumRelief'):
        if not np.isfinite(cfg[key]) or cfg[key] < 0:
            raise ValueError(f'{key} must be finite and nonnegative')
    if not 62 <= cfg['beachMaximumY'] < cfg['snowMinimumY'] <= cfg['maximumPeakY']:
        raise ValueError('beach and snow height gates are invalid')
    if not (cfg['coastalShelfRadius'] <= 8
            and 0 < cfg['coastalShelfDepthPerColumn']
            and cfg['coastalShelfDepthPerColumn'] * cfg['coastalShelfRadius'] <= cfg['coastalShelfMaximumDepth'] < 62 - cfg['minimumFloorY']
            and 62 <= cfg['coastalShelfMaximumLandY'] <= cfg['beachMaximumY']):
        raise ValueError('coastal shelf gates must stay within the shallow, lowland band')
    return cfg


def climate_table(root):
    source = (root / 'world_xenofactions_core.js').read_text(encoding='utf-8')
    block = re.search(r'var BIOME_MAPPINGS\s*=\s*\[(.*?)\n\];', source, re.S)
    if not block:
        raise ValueError('core BIOME_MAPPINGS missing')
    rows = [tuple(map(int, row)) for row in re.findall(
        r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', block[1])]
    colors = [row[:3] for row in rows]
    if len(set(colors)) != len(colors) or len(rows) > 255:
        raise ValueError('climate palette must have unique RGB entries')
    return colors, np.array([row[3] for row in rows], dtype=np.uint8)


def working_array(work, handles, name, shape, dtype='uint8'):
    array = np.memmap(work / (name + '.bin'), mode='w+', shape=shape, dtype=dtype)
    # ExitStack closes these even on failure, before Windows removes the workdir.
    handles.callback(array._mmap.close)
    return array


def checked_image(path, dimensions):
    image = Image.open(path)
    if image.size != dimensions:
        image.close()
        raise ValueError(f'{path.name}: expected {dimensions}, got {image.size}')
    return image


def discrete_decode(image, palette):
    """Decode exact colors through a short palette, never an RGB distance filter."""
    entries = image.getcolors(256)
    if entries is None:
        raise ValueError('categorical image has more than 256 colors')
    if image.mode == 'P':
        rgb_palette = image.getpalette()
        lookup = np.zeros(256, np.uint8)
        for _, index in entries:
            color = tuple(rgb_palette[3 * index:3 * index + 3])
            if color not in palette:
                raise ValueError(f'unexpected categorical RGB {color}')
            lookup[index] = palette[color]
        return lambda patch: lookup[np.asarray(patch)]
    if image.mode != 'RGB':
        raise ValueError(f'expected RGB or palette categories, got {image.mode}')
    packed = lambda color: (color[0] << 16) | (color[1] << 8) | color[2]
    entries = sorted((packed(color), palette[color]) for _, color in entries)
    keys = np.array([key for key, _ in entries], np.uint32)
    values = np.array([value for _, value in entries], np.uint8)

    def decode(patch):
        rgb = np.asarray(patch, dtype=np.uint32)
        key = (rgb[:, :, 0] << 16) | (rgb[:, :, 1] << 8) | rgb[:, :, 2]
        return values[np.searchsorted(keys, key)]
    return decode


def ingest_categories(path, dimensions, destination, step, palette, offset=(0, 0)):
    with checked_image(path, dimensions) as image:
        decode = discrete_decode(image, palette)
        ox, oy = offset
        # Existing profiles all reduce by an integral factor at the pixel origin.
        for y in range(0, image.height, step * 128):
            patch = image.crop((0, y, image.width, min(y + step * 128, image.height)))
            data = decode(patch)[::step, ::step]
            dy = oy // step + y // step
            destination[dy:dy + len(data), ox // step:ox // step + data.shape[1]] = data


def ingest_binary(path, dimensions, destination, step):
    with checked_image(path, dimensions) as image:
        if image.mode != 'P' or any(index not in (0, 1) for _, index in image.getcolors(256)):
            raise ValueError(f'{path.name}: expected audited binary palette indices 0/1')
        for y in range(0, image.height, step * 128):
            data = np.asarray(image.crop((0, y, image.width, min(y + step * 128, image.height))))[::step, ::step]
            destination[y // step:y // step + len(data)] = data


def ingest_height(path, dimensions, raw, ocean, step):
    hist = np.zeros(65536, np.int64)
    with checked_image(path, dimensions) as image:
        if image.mode not in ('I;16', 'I;16B', 'I;16L'):
            raise ValueError('height source must be unsigned 16-bit')
        image.load()
        for y in range(0, image.height, 128):
            data = np.asarray(image.crop((0, y, image.width, min(y + 128, image.height))))
            hist += np.bincount(data.ravel(), minlength=65536)
        xs = np.arange(raw.shape[1]) * step
        if step == 1:
            for y in range(0, image.height, 128):
                data = np.asarray(image.crop((0, y, image.width, min(y + 128, image.height))))
                raw[y:y + len(data)] = data
                ocean[y:y + len(data)] = data < 62 * 257
        else:
            # Match v2.27.0 BicubicHeightMap's signed half-pixel shift and
            # Catmull-Rom interpolation; constrain to its four central corners.
            weights = np.array([-0.0625, 0.5625, 0.5625, -0.0625], np.float32)
            for y in range(raw.shape[0]):
                sy = y * step
                ys = np.clip(sy + np.arange(-2, 2), 0, image.height - 1)
                patch = np.asarray(image.crop((0, int(ys.min()), image.width, int(ys.max()) + 1)))
                grid = np.stack([patch[row - ys.min(), np.clip(xs[:, None] + np.arange(-2, 2), 0, image.width - 1)] for row in ys])
                result = np.einsum('i,ijk,k->j', weights, grid, weights)
                result = np.clip(result, grid[1:3, :, 1:3].min(axis=(0, 2)), grid[1:3, :, 1:3].max(axis=(0, 2)))
                # At coordinate zero WP applies no half-pixel offset.
                result[0] = (patch[ys - ys.min(), 0] @ weights) if y else patch[0, 0]
                if y == 0:
                    row_grid = patch[0, np.clip(xs[:, None] + np.arange(-2, 2), 0, image.width - 1)]
                    result = np.clip(row_grid @ weights, row_grid[:, 1:3].min(axis=1), row_grid[:, 1:3].max(axis=1))
                    result[0] = patch[0, 0]
                raw[y] = result
                nearest = np.asarray(image.crop((0, sy, image.width, sy + 1)))[0, xs]
                ocean[y] = nearest < 62 * 257
    if np.any(np.flatnonzero(hist) % 257):
        raise ValueError('source encoding changed: found genuine non-8-bit-expanded samples; re-audit required')
    return hist


def tiles(shape, size, halo):
    height, width = shape
    for y in range(0, height, size):
        for x in range(0, width, size):
            y1, x1 = min(y + size, height), min(x + size, width)
            ey, ex = max(0, y - halo), max(0, x - halo)
            window = np.s_[ey:min(height, y1 + halo), ex:min(width, x1 + halo)]
            center = np.s_[y - ey:y1 - ey, x - ex:x1 - ex]
            yield np.s_[y:y1, x:x1], window, center


def coast_protection(ocean, radius):
    return ndi.maximum_filter(ocean, size=2 * radius + 1, mode='nearest').astype(bool)


def strict_majority(data, domain, protected, radius, votes):
    if radius == 0:
        return data.copy()
    # A numerical median is a valid mode candidate ONLY when it has an actual
    # strict majority of categorical votes. Never use an unverified median ID.
    size = 2 * radius + 1
    candidate = ndi.median_filter(data, size=size, mode='nearest')
    padded = np.pad(data, radius, mode='edge')
    eligible = np.pad(domain, radius, mode='edge')
    support = np.zeros(data.shape, np.uint8)
    for dy in range(size):
        for dx in range(size):
            support += ((padded[dy:dy + len(data), dx:dx + data.shape[1]] == candidate)
                        & eligible[dy:dy + len(data), dx:dx + data.shape[1]])
    return np.where(domain & ~protected & (support >= votes), candidate, data).astype(np.uint8)


def clean_categories(data, domain, protected, minimum, cfg, center, counters, prefix):
    cleaned = strict_majority(data, domain, protected, cfg['categoricalMajorityRadius'], cfg['categoricalMajorityVotes'])
    counters[prefix + 'MajorityPixels'] += int(np.count_nonzero(cleaned[center] != data[center]))
    result = cleaned.copy()
    width = int(data.max()) + 1
    for category in np.unique(cleaned[domain]):
        labels, count = ndi.label((cleaned == category) & domain, CONNECTIVITY)
        if not count:
            continue
        areas = np.bincount(labels.ravel(), minlength=count + 1)
        small = (areas < minimum) & (areas > 0)
        small[0] = False
        # Boundary-touching regions may continue beyond the halo; never guess.
        small[np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1], labels[protected])))] = False
        selected = np.flatnonzero(small)
        if not len(selected):
            continue
        votes = np.zeros((count + 1, width), np.int32)
        padded_labels = np.pad(labels, 1)
        padded_data = np.pad(cleaned, 1)
        padded_domain = np.pad(domain, 1)
        for dy in range(3):
            for dx in range(3):
                neighbor = padded_labels[dy:dy + len(data), dx:dx + data.shape[1]]
                valid = small[labels] & (neighbor != labels) & padded_domain[dy:dy + len(data), dx:dx + data.shape[1]]
                ids = labels[valid]
                colors = padded_data[dy:dy + len(data), dx:dx + data.shape[1]][valid]
                np.add.at(votes, (ids, colors), 1)
        winner = votes.argmax(axis=1)
        support = votes.sum(axis=1)
        replace = small & (support > 0) & (votes.max(axis=1) >= support * cfg['componentBoundarySupport'])
        replacement = np.full(count + 1, category, np.uint8)
        replacement[replace] = winner[replace]
        mask = replace[labels]
        result[mask] = replacement[labels[mask]]
        changed_ids = np.unique(labels[center][mask[center]])
        # A complete component's first raster pixel belongs to exactly one tile.
        first = ndi.minimum(np.arange(labels.size).reshape(labels.shape), labels, changed_ids)
        yy, xx = np.unravel_index(first.astype(np.int64), labels.shape)
        owned = ((yy >= center[0].start) & (yy < center[0].stop)
                 & (xx >= center[1].start) & (xx < center[1].stop))
        counters[prefix + 'RegionsRemoved'] += int(owned.sum())
    counters[prefix + 'ComponentPixels'] += int(np.count_nonzero(result[center] != cleaned[center]))
    return result


def clean_water(data, ocean, cfg, center, counters):
    wet = data.astype(bool) | ocean.astype(bool)
    labels, count = ndi.label(wet, CONNECTIVITY)
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    small = (areas < cfg['waterMinimumArea']) & (areas > 0)
    small[0] = False
    protected = coast_protection(ocean, 1)
    small[np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1], labels[protected])))] = False
    bounds = ndi.find_objects(labels)
    for label in np.flatnonzero(small):
        box = bounds[label - 1]
        if max(part.stop - part.start for part in box) >= cfg['waterPreserveSpan']:
            small[label] = False
    removed = small[labels]
    ids = np.unique(labels[center][removed[center]])
    first = ndi.minimum(np.arange(labels.size).reshape(labels.shape), labels, ids)
    yy, xx = np.unravel_index(np.asarray(first, dtype=np.int64), labels.shape)
    owned = ((yy >= center[0].start) & (yy < center[0].stop)
             & (xx >= center[1].start) & (xx < center[1].stop))
    counters['waterRegionsRemoved'] += int(owned.sum())
    counters['waterPixelsRemoved'] += int(removed[center].sum())
    return (wet & ~removed).astype(np.uint8)


def height_curve(raw, ocean, scale, cfg):
    relief = (raw.astype(np.float64) - cfg['sourceSeaSample']) / cfg['sourceSampleQuantum'] * cfg['referenceSourceScale'] / scale
    land = np.asarray(cfg['landCurve'])
    sea = np.asarray(cfg['oceanCurve'])
    result = np.where(ocean, np.interp(relief, sea[:, 0], sea[:, 1]), np.interp(relief, land[:, 0], land[:, 1]))
    # Continuous interpolation must never change the nearest source coast owner.
    return np.where(ocean, np.minimum(result, cfg['seaLevel'] - 1), np.maximum(result, cfg['seaLevel'] + 1)).astype(np.float32)


def smooth_height(height, ocean, cfg):
    radius = cfg['elevationRadius']
    if not radius or not cfg['elevationBlend']:
        return height
    hp = np.pad(height, radius, mode='edge')
    op = np.pad(ocean, radius, mode='edge')
    total = height.astype(np.float64).copy()
    weight = np.ones(height.shape, np.float64)
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            if dy == radius and dx == radius:
                continue
            neighbor = hp[dy:dy + len(height), dx:dx + height.shape[1]]
            same_side = op[dy:dy + len(height), dx:dx + height.shape[1]] == ocean
            delta = np.abs(neighbor - height)
            accepted = same_side & (delta <= cfg['elevationMaximumNeighborDelta'])
            total += neighbor * accepted
            weight += accepted
    change = np.clip((total / weight - height) * cfg['elevationBlend'],
                     -cfg['elevationMaximumAdjustment'], cfg['elevationMaximumAdjustment'])
    result = height + change
    return np.where(ocean, np.clip(result, cfg['minimumFloorY'], 61), np.clip(result, 63, cfg['maximumPeakY'])).astype(np.float32)


def soften_coastal_shelf(height, ocean, cfg):
    """Reinterpret shallow coastal quantization without touching deep/steep coasts.

    The 10k source's last ocean level becomes about seven blocks deep under the
    normalized curve. A narrow shelf ramp removes that artificial shoreline step.
    Water ownership and all land heights remain unchanged.
    """
    lowland = ~ocean & (height <= cfg['coastalShelfMaximumLandY'])
    shallow = ocean & (height >= cfg['seaLevel'] - cfg['coastalShelfMaximumDepth'])
    result = height.copy()
    for distance in range(cfg['coastalShelfRadius'], 0, -1):
        near = ndi.maximum_filter(lowland, size=2 * distance + 1, mode='nearest')
        floor = cfg['seaLevel'] - distance * cfg['coastalShelfDepthPerColumn']
        eligible = shallow & near
        result[eligible] = np.maximum(result[eligible], min(floor, cfg['seaLevel'] - 1))
    return result


def percentiles(hist, convert=lambda values: values):
    total = int(hist.sum())
    if not total:
        return {'count': 0}
    cumulative = hist.cumsum()
    occupied = np.flatnonzero(hist)
    percentages = (1, 10, 25, 50, 75, 90, 99, 99.9)
    levels = [occupied[0], *[np.searchsorted(cumulative, total * p / 100) for p in percentages], occupied[-1]]
    numbers = np.asarray(convert(np.asarray(levels)), dtype=float)
    return {'count': total, **dict(zip(('min', 'p1', 'p10', 'p25', 'p50', 'p75', 'p90', 'p99', 'p99.9', 'max'), np.round(numbers, 4).tolist()))}


def isolated_pixels(data, domain):
    padded = np.pad(data, 1, mode='edge')
    dp = np.pad(domain, 1, mode='edge')
    same = np.zeros(data.shape, bool)
    for dy in range(3):
        for dx in range(3):
            if dy != 1 or dx != 1:
                same |= ((padded[dy:dy + len(data), dx:dx + data.shape[1]] == data)
                         & dp[dy:dy + len(data), dx:dx + data.shape[1]])
    return domain & ~same


def component_census(data, ocean=None, water=False):
    """Exact global 8-connected run-length census, with only active rows retained.

    Unlike a tile census, regions crossing seams are counted and sized once.
    Python run merging is optional for larger profiles; it is automatic for smoke.
    """
    previous, props = [], {}
    serial = 0
    census = {}
    for y in range(data.shape[0]):
        row = np.asarray(data[y], dtype=np.int16).copy()
        if ocean is not None:
            row[np.asarray(ocean[y], dtype=bool)] = -1
        if water:
            row[row == 0] = -1
        cuts = np.r_[0, np.flatnonzero(row[1:] != row[:-1]) + 1, len(row)]
        parent = {key: key for key in props}

        def find(key):
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        current = []
        cursor = 0
        for x0, end in zip(cuts[:-1], cuts[1:]):
            value = int(row[x0])
            if value < 0:
                continue
            x1 = int(end - 1)
            x0 = int(x0)
            serial += 1
            key = serial
            parent[key] = key
            props[key] = [value, x1 - x0 + 1]
            while cursor < len(previous) and previous[cursor][1] < x0 - 1:
                cursor += 1
            scan = cursor
            while scan < len(previous) and previous[scan][0] <= x1 + 1:
                px0, px1, pvalue, pkey = previous[scan]
                if pvalue == value and px1 >= x0 - 1:
                    other = find(pkey)
                    root = find(key)
                    if other != root:
                        parent[other] = root
                        props[root][1] += props.pop(other)[1]
                scan += 1
            current.append((x0, x1, value, key))
        previous = [(x0, x1, value, find(key)) for x0, x1, value, key in current]
        active = {run[3] for run in previous}
        for key in list(props):
            if key not in active:
                value, area = props.pop(key)
                add_component(census, value, area)
    for value, area in props.values():
        add_component(census, value, area)
    return census


def add_component(census, category, area):
    entry = census.setdefault(str(category), {'regions': 0, 'pixels': 0, 'largest': 0, 'areaBins': [0] * (len(AREA_BOUNDS) + 1)})
    entry['regions'] += 1
    entry['pixels'] += area
    entry['largest'] = max(entry['largest'], area)
    entry['areaBins'][int(np.searchsorted(AREA_BOUNDS, area))] += 1


def save_png(path, array, palette=None):
    image = Image.fromarray(np.asarray(array))
    if palette is not None:
        image = image.convert('P')
        image.putpalette([part for color in palette for part in color] + [0] * (768 - 3 * len(palette)))
    image.save(path)
    image.close()


def prepare(root, profile, census_requested=False):
    cfg = configuration(root)
    scale, resize, effective, width, height = PROFILES[profile]
    step = 100 // resize
    if step * resize != 100:
        raise ValueError('profile no longer has integral native sampling; re-audit required')
    dimensions = (width * step, height * step)
    shape = (height, width)
    colors, ids = climate_table(root)
    decode_climate = {color: i for i, color in enumerate(colors)}
    decode_climate[(150, 150, 0)] = decode_climate[(200, 200, 0)]
    ocean_category = decode_climate[(0, 0, 0)]
    output = root / 'generated' / 'terrain' / profile
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'manifest.json'
    manifest_path.unlink(missing_ok=True)  # Publish the new complete bundle last.
    input_paths = [root / rel for rel in required_images(scale)]
    input_paths += [root / 'world_xenofactions_core.js', root / 'terrain-processing.json', Path(__file__).resolve(), root / 'tools/validate_xenoearth_source.py']
    vegetation_cfg = vegetation.configuration(root)
    if set(ids) - {b for p in vegetation_cfg['profiles'] for b in p['biomes']}:
        raise ValueError('every mapped climate biome needs a vegetation profile')
    input_paths += [root / 'vegetation.json', root / 'world_xenofactions_vegetation.js', root / 'tools/vegetation.py']
    infrastructure_paths = ([root / f'images/{name}{scale}k.png' for name in ('Cities', 'street')]
                            if vegetation_cfg['suppressInfrastructureMasks'] else [])
    input_paths += infrastructure_paths
    sources = [fingerprint(root, path) for path in input_paths]
    counters = Counter()
    with tempfile.TemporaryDirectory(prefix='work-', dir=output) as directory, ExitStack() as handles:
        work = Path(directory)
        raw = working_array(work, handles, 'source-height', shape, 'float32')
        ocean = working_array(work, handles, 'ocean', shape)
        climate = working_array(work, handles, 'source-climate', shape)
        cover = working_array(work, handles, 'source-surface', shape)
        water = working_array(work, handles, 'source-water', shape)
        ice = working_array(work, handles, 'ice', shape)
        cover_water = working_array(work, handles, 'cover-water', shape)
        infrastructure = working_array(work, handles, 'vegetation-infrastructure', shape)
        infrastructure[:] = 0
        # Original masks use black=off, positive red-channel values=on.
        # Max-pool instead of point sampling so thin roads survive smaller exports.
        for path in infrastructure_paths:
            with checked_image(path, dimensions) as image:
                for target, window, center in tiles(shape, cfg['tileSize'], 0):
                    ys, xs = target
                    patch = image.crop((xs.start*step, ys.start*step, xs.stop*step, ys.stop*step)).convert('RGB')
                    data = np.asarray(patch)[:, :, 0] > 0
                    data = data.reshape(ys.stop-ys.start, step, xs.stop-xs.start, step).any(axis=(1,3))
                    infrastructure[target] |= data
        print(f'[{profile}] Decode native sources onto unchanged {width} x {height} grid', flush=True)
        histogram = ingest_height(root / f'images/HeightMap{scale}k.png', dimensions, raw, ocean, step)
        ingest_categories(root / f'images/BiomeMap{scale}k.png', dimensions, climate, step, decode_climate)
        for dest, name in ((water, 'WaterMap'), (ice, 'Ice')):
            ingest_binary(root / f'images/{name}{scale}k.png', dimensions, dest, step)
        cover_paths = [(root / f'images/globecover{scale}k.png', dimensions, (0, 0))]
        if scale == 40:
            cover_paths = [(root / ('images/' + name), dims, offset) for name, dims, offset in (
                ('globecover1_40k.png', (21504, 10752), (0, 0)),
                ('globecover2a_40k.png', (10752, 10752), (21504, 0)),
                ('globecover2b_40k.png', (10752, 10752), (32256, 0)),
                ('globecover3_40k.png', (21504, 10752), (0, 10752)),
                ('globecover4_40k.png', (21504, 10752), (21504, 10752)))]
        # Decode each original part once for both semantic representations.
        packed_surface_palette = {color: terrain | (128 if color == (0, 148, 255) else 0)
                                  for color, terrain in SURFACE_COLORS.items()}
        for path, dims, offset in cover_paths:
            ingest_categories(path, dims, cover, step, packed_surface_palette, offset)
        for target, window, center in tiles(shape, cfg['tileSize'], 0):
            cover_water[target] = cover[target] >> 7
            cover[target] &= 127
        mismatch = 0
        for target, window, center in tiles(shape, cfg['tileSize'], 0):
            mismatch += int(np.count_nonzero((climate[target] == ocean_category) != ocean[target].astype(bool)))
        if mismatch:
            raise ValueError(f'height/climate coast topology changed: {mismatch} columns disagree')
        mapped = working_array(work, handles, 'mapped-height', shape, 'float32')
        for target, window, center in tiles(shape, cfg['tileSize'], 0):
            mapped[target] = height_curve(raw[target], ocean[target], scale, cfg)
        cleaned_climate = working_array(work, handles, 'clean-climate', shape)
        cleaned_cover = working_array(work, handles, 'clean-cover', shape)
        cleaned_water = working_array(work, handles, 'clean-water', shape)
        # A component of <=N columns cannot reach N+1 columns away. Combined
        # pass halos cover component diameter plus prior majority and shore gates.
        halo = max(cfg['biomeMinimumArea'], cfg['surfaceMinimumArea'], cfg['waterMinimumArea']) + cfg['categoricalMajorityRadius'] + cfg['coastProtectionRadius'] + 2
        print(f'[{profile}] Discrete climate, surface and water cleanup (halo {halo})', flush=True)
        for target, window, center in tiles(shape, cfg['tileSize'], halo):
            sea = ocean[window].astype(bool)
            protected = coast_protection(sea, cfg['coastProtectionRadius'])
            cleaned_climate[target] = clean_categories(climate[window], ~sea, protected, cfg['biomeMinimumArea'], cfg, center, counters, 'biome')[center]
            cleaned_cover[target] = clean_categories(cover[window], ~sea, protected, cfg['surfaceMinimumArea'], cfg, center, counters, 'surface')[center]
            cleaned_water[target] = clean_water(water[window], sea, cfg, center, counters)[center]
        final_height = working_array(work, handles, 'height', shape, 'uint16')
        final_climate = working_array(work, handles, 'climate', shape)
        final_cover = working_array(work, handles, 'terrain', shape)
        print(f'[{profile}] Coast, surface consistency and bounded elevation pass', flush=True)
        halo = max(cfg['beachContextRadius'], cfg['beachRadius'] + cfg['beachMinimumArea'] + 1,
                   cfg['coastalShelfRadius'] + cfg['elevationRadius']) + 2
        for target, window, center in tiles(shape, cfg['tileSize'], halo):
            sea = ocean[window].astype(bool)
            h = smooth_height(mapped[window], sea, cfg)
            coastal = soften_coastal_shelf(h, sea, cfg)
            counters['coastalShelfColumnsRaised'] += int(np.count_nonzero(coastal[center] > h[center]))
            h = coastal
            c = cleaned_climate[window].copy()
            terrain = cleaned_cover[window].copy()
            wet = cleaned_water[window].astype(bool)
            cold = np.isin(ids[c], (12, 13, 26, 30, 140))
            arid = np.isin(ids[c], (2, 17, 35, 36, 37, 130))
            near = coast_protection(sea, cfg['beachRadius']) & ~sea
            # Beach slope is the land's relief, not its drop to the seabed.
            local_max = ndi.maximum_filter(np.where(sea, -np.inf, h), size=3, mode='nearest')
            local_min = ndi.minimum_filter(np.where(sea, np.inf, h), size=3, mode='nearest')
            relief = local_max - local_min
            beach = near & (h <= cfg['beachMaximumY']) & (relief <= cfg['beachMaximumRelief']) & ~ice[window].astype(bool)
            beach_labels, count = ndi.label(beach, CONNECTIVITY)
            beach_areas = np.bincount(beach_labels.ravel(), minlength=count + 1)
            tiny_beach = beach_areas < cfg['beachMinimumArea']
            tiny_beach[0] = False
            tiny_beach[np.unique(np.concatenate((beach_labels[0], beach_labels[-1], beach_labels[:, 0], beach_labels[:, -1])))] = False
            beach &= ~tiny_beach[beach_labels]
            original_beach = np.isin(ids[c], (16, 26)) & ~sea
            regional = ~sea & ~original_beach
            if regional.any():
                distance, nearest = ndi.distance_transform_edt(~regional, return_indices=True)
                nearest_c = c[tuple(nearest)]
                fallback = np.where(cold, decode_climate[(178, 178, 178)], decode_climate[(255, 255, 0)])
                c[original_beach] = np.where(distance <= cfg['beachContextRadius'], nearest_c, fallback)[original_beach]
            else:
                c[original_beach] = np.where(cold, decode_climate[(178, 178, 178)], decode_climate[(255, 255, 0)])[original_beach]
            dry_water_cover = cover_water[window].astype(bool) & ~sea & ~wet & ~arid
            terrain[dry_water_cover] = 1
            counters['dryWaterCoverPixelsReplaced'] += int(dry_water_cover[center].sum())
            # Tiny incoherent red-sand/snow pixels already went through discrete
            # cleanup. Retain large real dunes/glaciers instead of repainting a
            # biome wholesale. A single unsupported snow pixel is still removed.
            unsupported_snow = (terrain == 40) & ~cold & (h < cfg['snowMinimumY']) & ~sea
            isolated_snow = isolated_pixels(terrain, ~sea) & unsupported_snow
            terrain[isolated_snow] = 1
            counters['unsupportedIsolatedSnowPixelsReplaced'] += int(isolated_snow[center].sum())
            terrain[sea] = 5
            terrain[beach & ~cold] = 5
            terrain[beach & cold] = 40
            c[sea] = ocean_category
            c[beach & ~cold] = decode_climate[(200, 200, 200)]
            c[beach & cold] = decode_climate[(220, 220, 220)]
            inland_beach_sand = original_beach & ~beach & ~arid & (terrain == 5)
            terrain[inland_beach_sand] = np.where(cold, 40, 1)[inland_beach_sand]
            counters['unsupportedBeachSandPixelsReplaced'] += int(inland_beach_sand[center].sum())
            isolated_sand = isolated_pixels(terrain, ~sea) & np.isin(terrain, (5, 6)) & ~arid & ~beach
            terrain[isolated_sand] = np.where(cold, 40, 1)[isolated_sand]
            counters['unsupportedIsolatedSandPixelsReplaced'] += int(isolated_sand[center].sum())
            counters['beachColumns'] += int(beach[center].sum())
            encoded = np.rint((h - 1) * 65535 / 253).astype(np.uint16)
            final_height[target] = encoded[center]
            final_climate[target] = c[center]
            final_cover[target] = terrain[center]
        print(f'[{profile}] Whole-map diagnostics', flush=True)
        land_hist, ocean_hist = np.zeros(65536, np.int64), np.zeros(65536, np.int64)
        before, after = Counter(), Counter()
        coast_mismatch = 0
        for target, window, center in tiles(shape, cfg['tileSize'], 1):
            sea = ocean[target].astype(bool)
            encoded = final_height[target]
            land_hist += np.bincount(encoded[~sea], minlength=65536)
            ocean_hist += np.bincount(encoded[sea], minlength=65536)
            expected = 1 + encoded.astype(float) * 253 / 65535
            coast_mismatch += int(np.count_nonzero((expected < 62) != sea))
            domain = ~ocean[window].astype(bool)
            for key, a, b in (('biome', climate, final_climate), ('surface', cover, final_cover), ('water', water, cleaned_water)):
                d = domain & (a[window] > 0) if key == 'water' else domain
                before[key] += int(isolated_pixels(a[window], d)[center].sum())
                d = domain & (b[window] > 0) if key == 'water' else domain
                after[key] += int(isolated_pixels(b[window], d)[center].sum())
        if coast_mismatch:
            raise ValueError(f'processing changed {coast_mismatch} coast owners')
        to_y = lambda q: 1 + q * 253 / 65535
        source_q = np.arange(65536)
        old_y = to_y(source_q)
        old_y = np.where(source_q < round(65535 * 61 / 253), np.maximum(1, 62 - (62 - old_y) * 2.05), old_y)
        report = {
            'profile': profile, 'dimensions': [width, height], 'configuration': cfg,
            'sourceHeight': percentiles(histogram),
            'sourceLand': percentiles(np.where(source_q >= 62 * 257, histogram, 0)),
            'sourceOcean': percentiles(np.where(source_q < 62 * 257, histogram, 0)),
            'oldSourceMappedLandY': percentiles(np.where(source_q >= 62 * 257, histogram, 0), lambda q: old_y[q]),
            'oldSourceMappedOceanY': percentiles(np.where(source_q < 62 * 257, histogram, 0), lambda q: old_y[q]),
            'oldOceanClampPercent': round(100 * histogram[(source_q < 62 * 257) & (old_y <= 1)].sum() / histogram[:62 * 257].sum(), 6),
            'finalLandY': percentiles(land_hist, to_y), 'finalOceanFloorY': percentiles(ocean_hist, to_y),
            'oceanDepthAtMedianFloor': round(62 - percentiles(ocean_hist, to_y)['p50'], 4),
            'deepestOceanDepth': round(62 - percentiles(ocean_hist, to_y)['min'], 4),
            'nearVerticalClampsPercent': round(100 * (land_hist + ocean_hist)[(to_y(source_q) <= 2) | (to_y(source_q) >= 253)].sum() / (width * height), 6),
            'coastOwnershipMismatches': coast_mismatch,
            'isolatedPixelsBefore': dict(before), 'isolatedPixelsAfter': dict(after),
            'cleanupCounts': dict(counters),
            'componentAreaUpperBounds': list(AREA_BOUNDS) + ['unbounded'],
            'climatePalette': {str(i): {'rgb': list(color), 'biomeId': int(ids[i])} for i, color in enumerate(colors)},
            'diagnosticScope': 'Whole native-source height histogram; whole final-grid rasters. Y values predict WP import, not exported chunks. Biome component census uses climate palette categories so distinct vegetation rules remain distinct. Component removal counts use complete halo regions with unique tile ownership.',
        }
        # Range rectangles retain the source canvas/crop georeferencing.
        report['representativeRanges'] = {}
        for label, box in {'Himalaya': (70, 25, 100, 38), 'Andes': (-80, -55, -65, 10), 'Alps': (5, 43, 17, 49), 'Rockies': (-125, 30, -105, 60), 'Mariana': (140, 10, 148, 25)}.items():
            lon0, lat0, lon1, lat1 = box
            pixels_per_degree = 3 * scale / step
            xs = slice(int(width / 2 + lon0 * pixels_per_degree), int(width / 2 + lon1 * pixels_per_degree))
            ys = slice(int(height / 2 - lat1 * pixels_per_degree), int(height / 2 - lat0 * pixels_per_degree))
            h = np.bincount(final_height[ys, xs].ravel(), minlength=65536)
            report['representativeRanges'][label] = percentiles(h, to_y)
        if census_requested or profile == 'smoke':
            print(f'[{profile}] Exact global component census', flush=True)
            report['globalComponents'] = {}
            for key, a, b, binary in (('biome', climate, final_climate, False), ('surface', cover, final_cover, False), ('water', water, cleaned_water, True)):
                report['globalComponents'][key] = {'before': component_census(a, ocean, binary), 'after': component_census(b, ocean, binary)}
        print(f'[{profile}] Deterministic vegetation masks', flush=True)
        trees, plants, vegetation_counts = vegetation.prepare(
            root, vegetation_cfg, (final_height, final_climate, final_cover, ocean, cleaned_water, ice, infrastructure),
            ids, shape, cfg['tileSize'], output, work, handles, tiles, working_array)
        report['vegetation'] = {'configuration': vegetation_cfg, **vegetation_counts}
        assets = {}
        for name, array, palette in (('height', final_height, None), ('biome', final_climate, colors), ('terrain', final_cover, None), ('water', cleaned_water, None), ('ice', ice, None), ('trees', trees, None), ('plants', plants, None)):
            target = output / (name + '.png')
            save_png(target, array, palette)
            assets[name] = fingerprint(root, target)
        report_path = output / 'diagnostics.json'
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        manifest = {'formatVersion': 1, 'profile': profile, 'width': width, 'height': height,
                    'sourceScale': scale, 'sourceResize': resize, 'effectiveScale': effective,
                    'seaLevel': 62, 'minimumFloorY': cfg['minimumFloorY'], 'maximumPeakY': cfg['maximumPeakY'],
                    'deepOceanFloorY': cfg['deepOceanFloorY'], 'shallowOceanFloorY': cfg['shallowOceanFloorY'],
                    'sources': sources, 'assets': assets}
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('finalLandY', 'finalOceanFloorY', 'deepestOceanDepth', 'nearVerticalClampsPercent', 'cleanupCounts')}, indent=2), flush=True)
    print(f'Prepared {manifest_path}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--profile', choices=(*PROFILES, *PROFILE_ALIASES), default='smoke')
    parser.add_argument('--census', action='store_true', help='Exact global component census (automatic for smoke; adds run-merging time on large profiles)')
    args = parser.parse_args()
    prepare(args.root.resolve(), PROFILE_ALIASES.get(args.profile, args.profile), args.census)


if __name__ == '__main__':
    main()
