"""Deterministic export masks on the existing Earth grid; no chunk population."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi


TREE_TYPES = {'oak', 'birch', 'spruce', 'jungle', 'acacia', 'darkOak', 'swamp', 'shrub'}
PLANTS = {'GRASS', 'TALL_GRASS', 'FERN', 'LARGE_FERN', 'DANDELION', 'POPPY',
          'OXEYE_DAISY', 'BLUE_ORCHID', 'MUSHROOM_BROWN', 'DEAD_SHRUB', 'CACTUS'}


def configuration(root):
    cfg = json.loads((root / 'vegetation.json').read_text(encoding='utf-8'))
    if cfg['formatVersion'] != 1 or type(cfg['enabled']) is not bool:
        raise ValueError('invalid vegetation format or enabled flag')
    if (type(cfg['suppressInfrastructureMasks']) is not bool
            or type(cfg['infrastructureBuffer']) is not int or not 0 <= cfg['infrastructureBuffer'] <= 16):
        raise ValueError('invalid infrastructure suppression settings')
    for key in ('densityMultiplier', 'treeDensityMultiplier'):
        if not np.isfinite(cfg[key]) or not 0 <= cfg[key] <= 10:
            raise ValueError(f'{key} must be finite and in 0..10')
    if type(cfg['seed']) is not int or not -2147483648 <= cfg['seed'] <= 2147483647:
        raise ValueError('vegetation seed must be a signed 32-bit integer')
    if not 62 <= cfg['alpineFalloffStartY'] < cfg['maximumTreeY'] <= cfg['maximumPlantY'] <= 246:
        raise ValueError('vegetation elevation limits must be ordered within 62..246')
    if (type(cfg['treeGrid']) is not int or not 8 <= cfg['treeGrid'] <= 32
            or type(cfg['treeCoastBuffer']) is not int or not 0 <= cfg['treeCoastBuffer'] <= 16
            or not 0 <= cfg['maximumTreeSlopeDegrees'] <= 60):
        raise ValueError('invalid vegetation slope, coast buffer or grid')
    biomes, names = set(), set()
    kinds = set()
    variant_count = 0
    for entry in cfg['treeVariants']:
        if entry['kind'] not in TREE_TYPES or entry['kind'] in kinds:
            raise ValueError('tree variants need unique known species')
        kinds.add(entry['kind'])
        heights = entry['heights']
        if not heights or len(set(heights)) != len(heights) or any(type(h) is not int or not 1 <= h <= 16 for h in heights):
            raise ValueError('tree heights must be unique integers in 1..16')
        variant_count += len(heights)
    if not 1 <= variant_count <= 254:
        raise ValueError('tree variant masks support 1..254 definitions')
    if not 1 <= len(cfg['profiles']) <= 254:
        raise ValueError('vegetation requires 1..254 profiles')
    for profile in cfg['profiles']:
        if not profile['name'].isalnum() or profile['name'] in names:
            raise ValueError('vegetation profile names must be unique and alphanumeric')
        names.add(profile['name'])
        for biome in profile['biomes']:
            if type(biome) is not int or not 0 <= biome < 255 or biome in biomes:
                raise ValueError('vegetation biome assignments must be unique byte IDs')
            biomes.add(biome)
        for kind, allowed in (('trees', TREE_TYPES), ('plants', PLANTS)):
            weights = profile[kind]
            if set(weights) - allowed or any(type(v) is not int or not 1 <= v <= 32767 for v in weights.values()):
                raise ValueError(f'invalid 1.7.10 {kind} mix in {profile["name"]}')
        if set(profile['trees']) - kinds:
            raise ValueError('profile tree mix needs configured variants')
        for coverage, mix in (('treeCoverage', 'trees'), ('plantCoverage', 'plants')):
            if not np.isfinite(profile[coverage]) or not 0 <= profile[coverage] <= 1:
                raise ValueError(f'invalid {coverage}')
            if profile[coverage] and not profile[mix]:
                raise ValueError(f'{coverage} needs a nonempty {mix} mix')
    return cfg


def random_field(x, z, seed, salt):
    """Coordinate hash with explicitly wrapping uint32 arithmetic; tile independent."""
    with np.errstate(over='ignore'):
        h = (x.astype(np.uint32) * np.uint32(0x9E3779B1)
             ^ z.astype(np.uint32) * np.uint32(0x85EBCA77)
             ^ np.uint32(seed & 0xffffffff) ^ np.uint32(salt))
        h ^= h >> np.uint32(16)
        h *= np.uint32(0x7FEB352D)
        h ^= h >> np.uint32(15)
        h *= np.uint32(0x846CA68B)
        h ^= h >> np.uint32(16)
    return h.astype(np.float64) / 4294967296.0


def masks(biomes, heights, cover, wet, ice, x0, z0, cfg, *, near_coast, infrastructure=None):
    """Return profile-indexed tree and plant masks. Height includes halo for slopes."""
    shape = biomes.shape
    x = np.arange(shape[1], dtype=np.int64)[None, :] + x0
    z = np.arange(shape[0], dtype=np.int64)[:, None] + z0
    tree_mask, plant_mask = np.zeros(shape, np.uint8), np.zeros(shape, np.uint8)
    if not cfg['enabled']:
        return tree_mask, plant_mask
    # Natural grass is terrain 1. Sand/red sand is allowed only for arid plants.
    dry = (heights > 62) & ~wet & ~ice
    if infrastructure is not None:
        dry &= ~infrastructure
    slope = np.maximum(ndi.maximum_filter(heights, size=3, mode='nearest') - heights,
                       heights - ndi.minimum_filter(heights, size=3, mode='nearest'))
    gentle = slope <= np.tan(np.deg2rad(cfg['maximumTreeSlopeDegrees']))
    seed, grid = cfg['seed'], cfg['treeGrid']
    cell_x, cell_z = x // grid, z // grid
    # One jittered anchor per cell, with margins: neighboring trunks cannot touch.
    span = grid - 4
    anchor_x = 2 + np.floor(random_field(cell_x, cell_z, seed, 11) * span)
    anchor_z = 2 + np.floor(random_field(cell_x, cell_z, seed, 23) * span)
    anchor = (x % grid == anchor_x) & (z % grid == anchor_z)
    tree_random = random_field(cell_x, cell_z, seed, 37)
    variant_random = random_field(cell_x, cell_z, seed, 83)
    variant_ids = {}
    next_id = 1
    for entry in cfg['treeVariants']:
        variant_ids[entry['kind']] = list(range(next_id, next_id + len(entry['heights'])))
        next_id += len(entry['heights'])
    plant_random = random_field(x, z, seed, 53)
    tree_falloff = np.clip((cfg['maximumTreeY'] - heights)
                          / (cfg['maximumTreeY'] - cfg['alpineFalloffStartY']), 0, 1)
    plant_falloff = np.clip((cfg['maximumPlantY'] - heights)
                           / (cfg['maximumPlantY'] - cfg['alpineFalloffStartY']), 0, 1)
    # Coherent, gentle patches rather than a uniform salt-and-pepper field.
    patch = 0.6 + 0.8 * random_field(x // 24, z // 24, seed, 71)
    for index, profile in enumerate(cfg['profiles'], 1):
        region = np.isin(biomes, profile['biomes']) & dry
        trees = (region & (cover == 1) & gentle & ~near_coast & anchor
                 & (tree_random < np.minimum(1, profile['treeCoverage'] * cfg['densityMultiplier']
                                             * cfg['treeDensityMultiplier'] * tree_falloff * patch)))
        substrate = np.isin(cover, (5, 6)) if profile['name'] == 'arid' else cover == 1
        plants = (region & substrate & ~trees
                  & (plant_random < np.minimum(1, profile['plantCoverage'] * cfg['densityMultiplier']
                                               * plant_falloff * patch)))
        if trees.any():
            # Select species and size before export. A mutable mixed-object
            # provider is shared across WP workers and cannot guarantee repeats.
            total = sum(profile['trees'].values())
            start = 0.0
            for kind, weight in sorted(profile['trees'].items()):
                ids = variant_ids[kind]
                for position, variant_id in enumerate(ids):
                    end = start + weight / total / len(ids)
                    tree_mask[trees & (variant_random >= start) & (variant_random < end)] = variant_id
                    start = end
        plant_mask[plants] = index
    return tree_mask, plant_mask


def prepare(root, cfg, arrays, ids, shape, tile_size, output, work, handles, tiles, working_array):
    """Two byte rasters, not one full-size image per profile; bounded halo work."""
    height, climate, cover, ocean, water, ice, infrastructure = arrays
    trees = working_array(work, handles, 'vegetation-trees', shape)
    plants = working_array(work, handles, 'vegetation-plants', shape)
    counts = Counter()
    radius = cfg['treeCoastBuffer']
    for target, window, center in tiles(shape, tile_size, max(1, radius, cfg['infrastructureBuffer'])):
        h = 1 + height[window].astype(np.float64) * 253 / 65535
        sea = ocean[window].astype(bool)
        near = ndi.maximum_filter(sea, size=2 * radius + 1, mode='nearest')
        exclusion = ndi.maximum_filter(infrastructure[window], size=2 * cfg['infrastructureBuffer'] + 1).astype(bool)
        t, p = masks(ids[climate[window]], h, cover[window],
                     sea | water[window].astype(bool), ice[window].astype(bool),
                     window[1].start - shape[1] // 2, window[0].start - shape[0] // 2,
                     cfg, near_coast=near, infrastructure=exclusion)
        trees[target], plants[target] = t[center], p[center]
        counts['treeAnchors'] += int(np.count_nonzero(t[center]))
        counts['plantAnchors'] += int(np.count_nonzero(p[center]))
        counts['infrastructureExcludedColumns'] += int(np.count_nonzero(exclusion[center]))
    return trees, plants, dict(counts)


def sample(root):
    """Owner-reproducible small export inputs exercising the real placement code."""
    from PIL import Image
    cfg = configuration(root)
    shape = (128, 128 * len(cfg['profiles']))
    biomes = np.zeros(shape, np.uint8)
    cover = np.ones(shape, np.uint8)
    heights = np.full(shape, 68.0)
    for index, profile in enumerate(cfg['profiles']):
        band = np.s_[:, index * 128:(index + 1) * 128]
        biomes[band] = profile['biomes'][0]
        if profile['name'] in ('arid', 'coast'):
            cover[band] = 5
        if profile['name'] == 'water':
            heights[band] = 55
    wet = heights < 62
    near = ndi.maximum_filter(wet, size=2 * cfg['treeCoastBuffer'] + 1)
    trees, plants = masks(biomes, heights, cover, wet, np.zeros(shape, bool), 0, 0,
                          cfg, near_coast=near)
    directory = root / 'generated/vegetation-sample'
    directory.mkdir(parents=True, exist_ok=True)
    for name, array in (('height', np.rint((heights - 1) * 65535 / 253).astype(np.uint16)),
                        ('biome', biomes), ('terrain', cover), ('trees', trees), ('plants', plants)):
        Image.fromarray(array).save(directory / (name + '.png'))
    print(json.dumps({'directory': str(directory), 'treeAnchors': int(np.count_nonzero(trees)),
                      'plantAnchors': int(np.count_nonzero(plants))}, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', action='store_true', required=True)
    parser.parse_args()
    sample(Path(__file__).resolve().parents[1])
