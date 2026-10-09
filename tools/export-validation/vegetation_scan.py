"""Read a small legacy Anvil export and verify vegetation; never modify the save.

This is a vegetation acceptance scan, not the complete Earth terrain/structure
validator described in README.md. Memory use scales with the selected export.
"""
import argparse
import gzip
import hashlib
import io
import json
import struct
import zlib
from collections import Counter, deque
from pathlib import Path


class NBT:
    def __init__(self, data):
        self.stream = io.BytesIO(data)

    def read(self, length):
        if length < 0 or length > 64 * 1024 * 1024:
            raise ValueError('invalid NBT length')
        data = self.stream.read(length)
        if len(data) != length:
            raise ValueError('truncated NBT')
        return data

    def number(self, fmt):
        return struct.unpack('>' + fmt, self.read(struct.calcsize('>' + fmt)))[0]

    def string(self):
        return self.read(self.number('H')).decode('utf-8')

    def payload(self, tag, depth=0):
        if depth > 64:
            raise ValueError('NBT nesting limit')
        if tag in (1, 2, 3, 4, 5, 6):
            return self.number({1:'b', 2:'h', 3:'i', 4:'q', 5:'f', 6:'d'}[tag])
        if tag == 7:
            return self.read(self.number('i'))
        if tag == 8:
            return self.string()
        if tag == 9:
            child, length = self.number('B'), self.number('i')
            if length < 0 or length > 1000000:
                raise ValueError('invalid NBT list length')
            return [self.payload(child, depth+1) for _ in range(length)]
        if tag == 10:
            result = {}
            while True:
                child = self.number('B')
                if child == 0:
                    return result
                name = self.string()
                if name in result:
                    raise ValueError('duplicate NBT key')
                result[name] = self.payload(child, depth+1)
        if tag in (11, 12):
            length = self.number('i')
            if length < 0 or length > 1000000:
                raise ValueError('invalid NBT array length')
            return [self.number('i' if tag == 11 else 'q') for _ in range(length)]
        raise ValueError('unknown NBT tag ' + str(tag))

    def root(self):
        if self.number('B') != 10:
            raise ValueError('chunk NBT root must be a compound')
        self.string()
        result = self.payload(10)
        if self.stream.read(1):
            raise ValueError('trailing chunk NBT data')
        return result


def chunks(directory):
    for path in sorted((directory / 'region').glob('r.*.*.mca')):
        parts = path.stem.split('.')
        rx, rz = int(parts[1]), int(parts[2])
        with path.open('rb') as stream:
            size = path.stat().st_size
            header = stream.read(8192)
            if len(header) != 8192 or size % 4096:
                raise ValueError(f'{path.name}: invalid region size/header')
            used = {0, 1}
            for index in range(1024):
                location = int.from_bytes(header[index*4:index*4+4], 'big')
                if not location:
                    continue
                offset, sectors = location >> 8, location & 255
                if offset < 2 or not sectors or (offset+sectors)*4096 > size:
                    raise ValueError(f'{path.name} slot {index}: invalid sector range')
                occupied = set(range(offset, offset+sectors))
                if occupied & used:
                    raise ValueError(f'{path.name} slot {index}: overlapping sectors')
                used |= occupied
                stream.seek(offset * 4096)
                length = int.from_bytes(stream.read(4), 'big')
                compression = stream.read(1)
                if not 1 < length <= sectors * 4096 - 4:
                    raise ValueError(f'{path.name} slot {index}: invalid payload size')
                data = stream.read(length-1)
                if compression == b'\x02':
                    decoder = zlib.decompressobj()
                    data = decoder.decompress(data, 64*1024*1024+1)
                    if len(data) > 64*1024*1024 or not decoder.eof:
                        raise ValueError('oversized or truncated chunk')
                elif compression == b'\x01':
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                        data = compressed.read(64*1024*1024+1)
                    if len(data) > 64*1024*1024:
                        raise ValueError('oversized chunk')
                else:
                    raise ValueError('unsupported legacy chunk compression')
                level = NBT(data).root()['Level']
                expected = (rx*32 + index%32, rz*32 + index//32)
                if (level['xPos'], level['zPos']) != expected:
                    raise ValueError(f'{path.name} slot {index}: chunk coordinates disagree')
                yield expected, level


def nibble(data, index):
    return (data[index//2] >> (4 * (index & 1))) & 15


def neighbours(p):
    x, y, z = p
    return ((x+1,y,z),(x-1,y,z),(x,y+1,z),(x,y-1,z),(x,y,z+1),(x,y,z-1))


def scan(directory, expected_size=None):
    leaves, logs, seen = {}, {}, set()
    counts, species, biomes = Counter(), Counter(), Counter()
    errors = []
    digest = hashlib.sha256()
    for (cx, cz), level in chunks(directory):
        if (cx,cz) in seen:
            raise ValueError('duplicate chunk')
        seen.add((cx,cz))
        counts['chunks'] += 1
        if level.get('TerrainPopulated') != 1:
            errors.append(f'chunk {cx},{cz} is not populated')
        if len(level.get('Biomes', b'')) != 256:
            errors.append(f'chunk {cx},{cz} has invalid biome array')
        biomes.update(level.get('Biomes', b''))
        if level.get('TileEntities') or level.get('Entities'):
            errors.append(f'chunk {cx},{cz} contains entities/tile entities')
        section_y = set()
        for section in sorted(level['Sections'], key=lambda s:s['Y']):
            sy = section['Y']
            if not 0 <= sy < 16 or sy in section_y:
                raise ValueError('invalid/duplicate section Y')
            section_y.add(sy)
            block, data, add = section['Blocks'], section['Data'], section.get('Add')
            if len(block) != 4096 or len(data) != 2048 or add is not None and len(add) != 2048:
                raise ValueError('invalid section arrays')
            digest.update(struct.pack('>iii', cx,cz,sy))
            digest.update(block); digest.update(data); digest.update(add or bytes(2048))
            for i, low_id in enumerate(block):
                block_id = low_id | ((nibble(add, i) << 8) if add else 0)
                meta = nibble(data, i)
                p = (cx*16+(i&15), sy*16+(i>>8), cz*16+((i>>4)&15))
                if block_id in (18,161):
                    leaves[p] = (block_id,meta)
                    counts['leaves'] += 1
                    if meta & 4:
                        errors.append(f'persistent leaf at {p}')
                    counts['checkDecayLeaves' if meta & 8 else 'idleNaturalLeaves'] += 1
                    if block_id == 161 and (meta & 3) > 1:
                        errors.append(f'invalid leaves2 species at {p}')
                    species[f'{block_id}:{meta & 3}'] += 1
                elif block_id in (17,162):
                    logs[p] = (block_id,meta)
                    counts['logs'] += 1
                    if block_id == 162 and (meta & 3) > 1:
                        errors.append(f'invalid log2 species at {p}')
                elif block_id in (31,32,37,38,39,40,81,175):
                    counts[f'plant_{block_id}:{meta}'] += 1
                elif block_id in (10,11,14,15,16,21,56,73,74,129):
                    errors.append(f'unwanted ore/lava {block_id} at {p}')
                elif block_id >= 176 or block_id in (165,166,167,168,169):
                    errors.append(f'post-1.7.10 or extended block {block_id} at {p}')
    if expected_size:
        width,height = expected_size
        expected = {(x,z) for x in range(width//16) for z in range(height//16)}
        if seen != expected:
            errors.append(f'chunk footprint differs: missing {len(expected-seen)}, extra {len(seen-expected)}')
    # Multi-source six-face flood, exactly matching the legacy four-step range.
    queue = deque((p,0) for p in logs)
    supported = set(logs)
    while queue:
        p,distance = queue.popleft()
        if distance == 4:
            continue
        for q in neighbours(p):
            if q in leaves and q not in supported:
                supported.add(q); queue.append((q,distance+1))
    unsupported = set(leaves) - supported
    counts['unsupportedLeaves'] = len(unsupported)
    errors.extend(f'unsupported leaf at {p}' for p in sorted(unsupported)[:20])
    if not leaves or not logs:
        errors.append('export has no complete trees')
    # Species need not match for GAME support, but they must match our tree objects.
    mismatched = set()
    for leaf_id, meta in {(i,m & 3) for i,m in leaves.values()}:
        log_id = 17 if leaf_id == 18 else 162
        queue = deque((p,0) for p,(i,m) in logs.items() if i == log_id and (m & 3) == meta)
        matching = {p for p,_ in queue}
        while queue:
            p,distance = queue.popleft()
            if distance == 4:
                continue
            for q in neighbours(p):
                if q in leaves and q not in matching:
                    matching.add(q); queue.append((q,distance+1))
        mismatched |= {p for p,(i,m) in leaves.items() if i == leaf_id and (m & 3) == meta and p not in matching}
    counts['speciesWithoutMatchingLogPath'] = len(mismatched)
    errors.extend(f'leaf species lacks matching log path at {p}' for p in sorted(mismatched)[:20])
    return {'passed':not errors, 'counts':dict(counts), 'leafSpecies':dict(species),
            'biomes':dict(biomes), 'blockDataSHA256':digest.hexdigest(), 'errors':errors[:50]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world', type=Path)
    parser.add_argument('--size', type=int, nargs=2, metavar=('WIDTH','HEIGHT'))
    args = parser.parse_args()
    try:
        result = scan(args.world, args.size)
    except (ValueError,OSError,KeyError,zlib.error,EOFError) as exc:
        result = {'passed':False, 'errors':[str(exc)]}
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
