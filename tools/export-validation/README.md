# Phase 2: exported Anvil validation

## Vegetation sample scan

Run `python tools/vegetation.py --sample`, then
`wpscript world_xenofactions_vegetation_sample.js`. The sample uses the production
seeded importer, tree objects, Plants layers and placement masks, with one band
for each vegetation profile. It exports directly as legacy Anvil without Populate.

```bash
python tools/export-validation/vegetation_scan.py generated/vegetation-sample/export/XenoEarthVegetationSample --size 1664 128
```

`vegetation_scan.py` reads actual region headers, compression and NBT, including
legacy Blocks/Data/Add arrays. It checks chunk footprints/population flags,
unsupported IDs, ores/lava, entities, natural leaf persistence/species, and
six-face leaf paths of at most four steps to valid logs. It also checks matching
leaf/log species paths and reports the block-data fingerprint for comparing
repeated exports. This scanner is intended for small, complete selections;
its memory use scales with the export. A cut-off selection may correctly report
unsupported leaves whose supporting logs were outside the exported area.

The optional `--builtinReference` argument to the sample WorldPainter script
exports the previous built-in forest approach at intensity 3 to
`XenoEarthVegetationReference`. It is diagnostic only and is never used by the
Earth-map launchers. It does not reproduce an owner's old save or modpack.

Final owner checks in 1.7.10:

1. Load the export without vanilla population adding terrain features.
2. Confirm vegetation is present immediately.
3. Leave intact trees loaded and confirm their foliage stays supported.
4. Remove all supporting trunk/branch logs and confirm unsupported foliage decays.
5. Check Earth-scale density and road/city/coast clearance.

Log removal can leave supported foliage while branch logs or neighbouring trees
still exist. The game checks leaves on random ticks with surrounding chunks
loaded; a successful static scan does not demonstrate the runtime decay timing.

## Full terrain acceptance (separate work)

The vegetation scanner is not the complete terrain validator below. Full Earth
acceptance still requires these checks; a filename or directory-presence check
is not an exported-world validator.

The scanner must read every `region/r.<x>.<z>.mca` 8 KiB header, validate each
location/timestamp entry and sector range, decompress chunk payloads according to
their compression byte, and parse big-endian NBT. For the 1.7.10 Anvil schema it
must inspect `Level`, `xPos`, `zPos`, `TerrainPopulated`, `Sections`, `Biomes`,
`Entities`, and `TileEntities`. Each section needs correct decoding of 4,096-byte
`Blocks`, 2,048-byte nibble `Data`, optional 2,048-byte nibble `Add`, and Y index;
the effective legacy block ID is `Blocks[i] | (AddNibble[i] << 8)` and metadata is
the corresponding `Data` nibble.

The complete scan must report, with region/chunk/section/local coordinates:

* unsupported vanilla block IDs and unsupported metadata values;
* any modded/extended block ID;
* every ore block and lava block;
* underground air not connected to an approved mapped surface-water column;
* generated structures and structure-start NBT;
* all tile entities and entities;
* biome bytes outside the approved Minecraft 1.7.10 table;
* chunks marked unpopulated (`TerrainPopulated` absent/false);
* malformed NBT, bad compression, overlapping/out-of-range sectors, and corrupt chunks;
* missing chunks inside the exact profile rectangle;
* non-bedrock/terrain below y=1 and solid terrain above y=254.

Phase 2 also needs the profile bounds, an explicit 1.7.10 block+metadata allowlist,
an ore/lava denylist, expected chunk-coordinate set, and the source water mask (or
a derived approved-water-column index) to distinguish mapped water from caves.
Only after all chunks pass may the save be copied to a Xenofactions test instance.
