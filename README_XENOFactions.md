# XenoFactions Earth WorldPainter pipeline

This pipeline generates a conservative **Minecraft Forge 1.7.10** WorldPainter
project from the repository's Earth sources. `world.js` remains the unchanged
upstream reference. The supported script is `world_xenofactions.js`.

## Required WorldPainter version

**WorldPainter 2.27.0 is the currently tested API target.** The script calls
`wp.getVersion()`, rejects versions older than 2.27.0 numerically (including
2.7.18), and warns for an unverified version. WorldPainter 2.7.18 cannot provide
the JavaScript `ScriptEngine` expected by this execution path and fails with a
null-engine `NullPointerException` before the map logic can run.

The scripting calls were audited against the `v2.27.0` implementations of
`ScriptingContext.java`, `CreateFilterOp.java`, `ImportHeightMapOp.java`,
`GetPlatformOp.java`, `MappingOp.java`, `GetLayerOp.java`, `GetHeightMapOp.java`,
and `SaveWorldOp.java`. In particular, `withMapFormat` receives the `Platform`
returned by `getMapFormat().withId(...).go()`, each filter has no more than one
`onlyOn...` and one `exceptOn...` condition, and all operation builders terminate
with `go()` at the point required by that API.

> This development environment did not contain WorldPainter or `wpscript`, so the
> real 2.27.0 preflight and smoke generation remain owner-run checks. The Python
> source validator is not represented as a substitute for those runtime checks.

## Profiles and outputs

The Run Script dialog exposes `profile` and `preflightOnly`; users do not edit the
source. The default is deliberately the small `smoke` profile.

| Profile | Source | Resize | Effective scale | Output dimensions | Project |
|---|---:|---:|---:|---:|---|
| `smoke` (default) | 10 | 25% | 1:16000 | 2,688 × 1,344 | `generated/earth_1-16000_xenofactions_1.7.10_smoke.world` |
| `preview` | 10 | 100% | 1:4000 | 10,752 × 5,376 | `generated/earth_1-4000_xenofactions_1.7.10_preview.world` |
| `production` | 40 | 100% | 1:1000 | 43,008 × 21,504 | `generated/earth_1-1000_xenofactions_1.7.10_production.world` |

Each run writes `generated/xenoearth-profile-<profile>.json`. The tracked root
`xenoearth-profile.json` is the production source contract and is never
regenerated. Partial edge region files are valid: dimensions need only be positive
whole blocks aligned to 16-block chunks, not 512-block regions.

The script uses WorldPainter's `scriptDir` binding and safe Java `File` children,
so it automatically locates `images/` and `layer/` beside itself regardless of the
clone location. There is no path to edit. The `generated/` directory is created
on demand.

## Run and verify

From a shell with WorldPainter 2.27.0's `wpscript` on `PATH`:

```bash
python -m unittest discover -s tools -p "test_*.py" -v
python tools/validate_xenoearth_source.py .
wpscript world_xenofactions.js --profile=smoke --preflightOnly
wpscript world_xenofactions.js --profile=smoke
```

API preflight validates configuration, source files and image dimensions; resolves
the legacy Anvil platform; loads Rivers and every built-in layer; constructs every
selected-profile filter; and exits before loading the main heightmap. Success ends
with `XenoEarth WorldPainter API preflight: PASS`.

In the GUI, choose **Tools → Run Script…**, select `world_xenofactions.js`, select
**smoke**, and first enable **API preflight only**. After PASS, run again with that
box cleared. Progress identifies the active stage:

1. Preflight
2. Importing heightmap
3. Applying biomes
4. Applying surface terrain
5. Applying oceans
6. Applying rivers
7. Applying ice
8. Applying vegetation
9. Saving project

An exception immediately after a stage label belongs to that stage and is left
intact for diagnosis; the script does not broadly catch and obscure WorldPainter
exceptions.

## Troubleshooting

| Symptom | Root cause | Resolution |
|---|---|---|
| `NullPointerException: ... scriptEngine is null` | Obsolete WorldPainter 2.7.18 has no usable engine for this script path. | Install WorldPainter 2.27.0 and rerun preflight. |
| `ClassCastException: Cannot cast java.lang.String to ... Platform` | A format ID string was passed to `withMapFormat()`. | Current script resolves `org.pepsoft.anvil` through `getMapFormat()` and passes its returned `Platform`. |
| `resize must keep both output dimensions on 512-block region boundaries` | Old validation incorrectly rejected legal partial edge regions and its own scale-10 resize. | Current profiles require only positive, integral, 16-block-aligned dimensions. |
| `Only one or "except on" condition may be specified` | Old river and vegetation builders chained multiple `exceptOnBiome` calls and then a layer exclusion. | Rivers use one `onlyOnLand`; vegetation uses one `onlyOnLand` and, when rivers exist, one `exceptOnLayer`. |

## Manual visual/export checklist

1. Open `generated/earth_1-16000_xenofactions_1.7.10_smoke.world` in WorldPainter
   2.27.0 and confirm dimensions 2,688 × 1,344, water level 62, plausible coastlines,
   deep/shallow ocean, inland river channels, frozen areas, terrain colours, and
   vegetation confined to land and absent from river channels.
2. Select a small representative area containing coast, river, ice, and vegetation.
3. Export only that selection using legacy **Minecraft 1.2–1.12 / Anvil** settings.
4. Disable Populate, Resources, Caves, Caverns, Chasms, Ravines, Structures, lava
   lakes/pockets, and every unlisted underground generator. Keep bottomless world
   off and normal bedrock enabled.
5. Run the Phase 2 checks in `tools/export-validation/README.md` before opening the
   save in Forge 1.7.10. Do not treat successful project creation as proof that an
   export is safe.

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

The vegetation filter uses WorldPainter 2.27.0's `onlyOnLand()` condition, excludes the Rivers layer when rivers are enabled,
and limits placement to surfaces above `seaLevel` and slopes no steeper than
`maximumVegetationSlope` (default 35 degrees). A separate legal filter without
`exceptOnLayer()` is constructed when rivers are disabled. Gentle river-bank land
and actual swamp land remain eligible. Vegetation rules group compatible climates to control memory: deciduous/birch/
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
