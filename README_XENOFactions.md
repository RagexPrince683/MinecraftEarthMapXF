# XenoFactions Earth source profile (Phase 1)

This fork profile turns the upstream Earth sources into a deliberately conservative
WorldPainter project for **Minecraft Forge 1.7.10**. It prepares terrain, bathymetry,
water, climate biomes, ice, and offline vegetation before Minecraft sees a chunk.
It does not modify the separate Xenofactions repository.

## Compatibility and sizing

Use a current **WorldPainter 2.x release which still offers the legacy Minecraft
1.7.10/Anvil export platform**. The script deliberately does not guess a platform
setter: the installed release must expose that platform in Export World. A first
small test export is required before the full project is trusted.

Supported source scales are `10` (1:4000, 10,752 × 5,376), `20` (1:2000,
21,504 × 10,752), and `40` (1:1000, **43,008 × 21,504**). Scale 40 is the default.
All dimensions are multiples of 512, use the upstream equirectangular projection,
and retain longitude 0 / latitude 0 at the center. With `resize = 100`, expect at
least the upstream-observed 19.1 GB working set plus headroom; 24–32 GB available
to WorldPainter is recommended. This estimate varies by WorldPainter/JVM version
and the enabled vegetation exporters.

## Run the pipeline

1. Clone the complete repository. Preserve the `images/`, `layer/`, and `terrain/`
   trees beside the script.
2. Edit `path` at the top of `world_xenofactions.js`. Use `/`, and include the
   trailing slash, for example `C:/WorldPainter/Script/`.
3. Leave the target at `1.7.10`; select scale `10`, `20`, or `40`. Keep the default
   terrain-surface range `1..254` and sea level 62. The script selects the legacy
   `org.pepsoft.anvil` map format and fails clearly if the installed WorldPainter
   does not provide it.
4. Run the source check: `python3 tools/validate_xenoearth_source.py .`.
5. In WorldPainter choose **Tools → Run Script…**, select
   `world_xenofactions.js`, and run it. Do not use `world.js` for XenoFactions;
   that file is retained only as the upstream reference.
6. Scale 40 writes `earth_1-1000_xenofactions_1.7.10.world` and regenerates
   `xenoearth-profile.json` from the active configuration. Other scales receive
   the corresponding denominator; resized projects include a resize suffix.

The script reads image headers before world creation, maps the full 16-bit source
range to y=1..254, and creates an Anvil project with build limits 0 through 255
(API upper limit 256) and water at the configured `seaLevel`. This reserves y=0
for the exported bedrock floor and never places a terrain surface at y=0 or y=255.
It releases large maps after their final use and loads each used external layer
once. Long section/rule loops call `wp.checkForInterrupt()`, allowing clean user
cancellation. `vegetationSeed` records the intended deterministic seed.
The inspected scripting surface provides no verified per-layer seed setter, so the
script does not invent one; deterministic export behavior must be confirmed in the
chosen WorldPainter release.

## Features

| Feature | State | Source/export behavior |
|---|---:|---|
| Earth terrain | Enabled | `HeightMap…png`, mapped to y=1..254 |
| Bathymetry | Enabled | Combined 16-bit height source |
| Oceans | Enabled | Sea level 62; shallow/deep thresholds derive from it |
| Rivers | Enabled | `WaterMap…png` + verified `Rivers.layer`; inland mask columns receive River biome ID 7, while ocean overlap is erased and its sand floor restored |
| Climate biomes | Enabled | `BiomeMap…png`; only 1.7.10 IDs |
| Ice | Enabled | `Ice…png`, Frozen Ocean + built-in Frost |
| Surface materials | Enabled | GlobCover masks and legacy built-in terrain |
| Trees | Enabled | Shared built-in forest layers, offline |
| Plants | Enabled | Built-in Jungle/Swamp vegetation and Frost exporters, offline |
| Caves / Caverns / Chasms / Ravines | **Disabled** | Must also be disabled at export |
| Ores / Resources | **Disabled** | No ore image or layer is loaded |
| Lava | **Disabled** | Must also be disabled at export |
| Structures | **Disabled** | Must also be disabled at export |
| Cities / Streets / Borders / Portals | **Disabled** | Assets preserved, never loaded |
| Minecraft population | **Disabled** | Never mark chunks for Populate |

One shared vegetation filter excludes mapped river channels, Ocean (0), Deep Ocean
(24), Frozen Ocean (10), surfaces at or below `seaLevel`, and slopes above
`maximumVegetationSlope` (default 35 degrees). Gentle river-bank land and actual
swamp land remain eligible. Vegetation rules group compatible climates to control memory: deciduous/birch/
roofed/plains, taiga/mega-taiga/cold terrain, jungle, savanna, and swamp. Desert,
beach, permanent snow, and ocean columns intentionally receive no normal-tree
rule; ice receives Frost. Intensities are conservative. Built-in object exporters
perform their own attachment/slope checks, avoiding objects which float or cut
deeply. Phase 1 does not claim every optional plant type is present: cactus,
reeds, lilies, and biome-specific flower mixes require a separately inspected,
1.7.10-safe plant/object layer before they may be enabled.

## Mandatory export checklist

The repository's inspected script API calls cover world creation, height mapping,
filters, layers, terrain application, spawn, and project save. No verified calls
were found for the following export settings. Consequently the script prints this
checklist prominently and **the source project alone is not an export validation**:

The map format, build limits, and water level are already set by the script and are
therefore not manual checklist items.

1. Turn **Populate / allow Minecraft to populate terrain OFF**. Chunks must not be
   marked for later vanilla decoration.
2. Turn **Resources OFF** (including underground pockets/deposits).
3. Turn **Caves, Caverns, Chasms, and any Ravines OFF**.
4. Turn **Structures OFF** (villages, mineshafts, strongholds, temples, etc.).
5. Turn **lava lakes and lava pockets OFF**.
6. Disable every other underground pocket or custom underground layer.
7. Keep **bottomless world OFF** and use normal bedrock so y=0 is reserved for
   bedrock. Do not export terrain above y=254.
8. Do not enable any resource, object, or layer not documented by this profile.

Opening a 1.12.2 save directly in Forge 1.7.10 is unsafe: the newer save may
contain block states, IDs, metadata, entities, and NBT schemas the older server
cannot interpret. Export directly to the legacy platform, then perform the Phase 2
Anvil scan described in `tools/export-validation/README.md` **before** opening it
with the modpack. The later Xenofactions world provider must have an empty
`populate` implementation; that provider belongs in the other repository and is
not implemented here.

## Inspected source definitions

`Rivers.layer` is the sole external layer kept in the executable profile. It is a
two-block ground-cover cut using vanilla water (ID 9, level metadata 0) and is safe
for 1.7.10. Built-in Biomes, Frost, Deciduous Forest, Pine Forest, Jungle, and
Swamp layers are also used. The inspected but disabled layers are:

| Definition(s) | What it can place | Decision |
|---|---|---|
| `Mesa.layer` | hardened clay colours, red sand, red sandstone, stone | Disabled; contains post-1.7 red sandstone |
| `Swamp.layer` | water and grass | Disabled external definition; built-in Swamp vegetation is used |
| `Borders.layer` | iron bars and cobblestone | Disabled |
| `Cities.layer` | cobblestone | Disabled |
| `street.layer` | grass path | Disabled; path block is post-1.7 |
| all `ore/*.layer` | underground ore/block, clay, sand, red-sand pockets | Disabled |
| all `portal/*.layer` | oriented End portal frames | Disabled |

No custom terrain slot is enabled. This is the central compatibility record for
all upstream terrain definitions and their 1.7.10 replacements (metadata is 0
unless noted):

| Slot in upstream | File | Inspected material stack | 1.7.10 status / profile replacement |
|---:|---|---|---|
| 1 | `Custom_Mesa.terrain` | hardened clay and stained hardened clay colours (IDs 172/159 metadata colours), red sand (12:1), red sandstone, stone (1:0) | Unsafe due red sandstone; built-in red sand/grass fallback |
| 2 | `Deep_Ocean_Floor.terrain` | sand 12:0, clay 82:0, dirt 3:0, gravel 13:0, bone block | Unsafe due bone block; built-in sand 12:0 |
| 3 | `Deep_Snow.terrain` | snow block 80:0, stone 1:0 | Safe, but not loaded; built-in deep snow |
| 4 | `Ocean_Floor.terrain` | sand 12:0, clay 82:0, dirt 3:0, gravel 13:0 | Safe, but not loaded; built-in sand 12:0 |
| 5 | `stone_sand_gravel_grass_block.terrain` | gravel 13:0, sand 12:0, dirt 3:0, grass 2:0 | Safe, but not loaded; built-in grass |
| 6 | `Red_Sand_Red_Sanstone_Mix.terrain` | red sand 12:1, red sandstone | Unsafe; built-in red sand 12:1 |
| 7 | `Sand_Sanstone_Mix.terrain` | sand 12:0, sandstone 24:0 | Safe, but not loaded; built-in sand |
| 8 | `Snow_Surface.terrain` | snow block 80:0, snow layers 78 metadata 1–7 | Safe, but not loaded; built-in Frost/deep snow |
| 9 | `Taiga_Floor.terrain` | grass 2:0, coarse dirt 3:1, podzol 3:2 | Safe in 1.7.10, but not loaded; built-in grass |
| 10 | `Sand_Gras_Mix.terrain` | sand 12:0, grass 2:0 | Safe, but not loaded; built-in sand |
| 11 | `Swamp.terrain` | water 9:0, grass 2:0 | Safe, but not loaded; built-in grass |

The table is based on the complete GZIP/Java-serialization material identities in
each supplied definition, not numeric IDs alone. Modern serialization names were
translated to the intended legacy block and metadata only where the block existed.

## Outputs, attribution, and repository hygiene

Generated `*.world` projects, `exports/`, `generated/`, and
`validation-reports/` are ignored and must not be committed. Minecraft saves and
`.mca` files belong under those ignored directories. `xenoearth-profile.json` is
the checked source contract for the default run, not a generated world.

This work preserves the upstream MIT license and attribution to Mattias Brennecke
(2019). Data sources remain those listed in `README.md`: NASA Visible Earth
elevation and bathymetry; ESA GlobCover; Köppen-Geiger climate data; NASA sea
surface temperature; Natural Earth/shadedrelief cities and ice; USGS mineral
deposits; Geofabrik street data; and © OpenStreetMap contributors. Preserve those
credits in any redistribution.
