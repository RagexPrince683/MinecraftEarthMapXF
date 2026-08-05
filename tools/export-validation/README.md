# Phase 2: exported Anvil validation

Phase 1 validates source configuration only. Before any exported world is opened
by Forge 1.7.10, Phase 2 must implement a real region/NBT scanner. A filename or
directory-presence check is not an exported-world validator.

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
