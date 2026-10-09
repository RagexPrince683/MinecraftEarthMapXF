# XenoFactions Earth WorldPainter pipeline

This pipeline generates a conservative **Minecraft Forge 1.7.10** WorldPainter
project from the repository's Earth sources. `world.js` remains the unchanged
upstream reference. `tools/preprocess_xenoearth.py` prepares the authoritative
terrain inputs; `world_xenofactions_core.js` applies them to the project. The
general and dedicated scale scripts are lightweight launchers; the backup script
is an unused historical reference. See [the terrain audit](TERRAIN_PIPELINE_AUDIT.md)
for the complete source-to-project trace, measurements and cleanup tradeoffs.

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

The Python source validator checks the source contract. Use the WorldPainter
preflight, sample export and Anvil scan below to check the installed exporter.

## Profiles and outputs

The Run Script dialog exposes `profile` and `preflightOnly`; users do not edit the
source. The default is deliberately the small `smoke` profile.

| Profile | Scale | Source images | Resize | Dimensions |
|---|---:|---:|---:|---:|
| `smoke` (default) | 1:16000 | 10k | 25% | 2,688 × 1,344 |
| `earth8000` | 1:8000 | 10k | 50% | 5,376 × 2,688 |
| `earth4000` | 1:4000 | 10k | 100% | 10,752 × 5,376 |
| `earth2000` | 1:2000 | 20k | 100% | 21,504 × 10,752 |
| `production` | 1:1000 | 40k | 100% | 43,008 × 21,504 |

`preview` remains a backward-compatible alias for the single canonical
`earth4000` configuration. Generate either by running the general
`world_xenofactions.js` script and entering a profile name, or by running
`world_xenofactions_1_8000.js`, `world_xenofactions_1_4000.js`, or
`world_xenofactions_1_2000.js` directly. The launchers load the core using the
Nashorn `load(URL)` function with a `java.io.File` child of WorldPainter's
injected `scriptDir`; they never depend on the process working directory.

The relative pixel area quadruples at each step: 1:8000 has 1/4 the area of
1:4000, 1:4000 has 1/4 the area of 1:2000, and 1:2000 has 1/4 the area of
1:1000. No particular project or exported-save file size is implied.

The canonical bounds and spawn points are:

| Profile | Bounds (X, Z inclusive) | Spawn (X, Z) |
|---|---|---:|
| `earth8000` | -2,688..2,687; -1,344..1,343 | 553, -57 |
| `earth4000` | -5,376..5,375; -2,688..2,687 | 1,105, -114 |
| `earth2000` | -10,752..10,751; -5,376..5,375 | 2,210, -228 |

Preprocessing consumes `HeightMap10k.png`, `BiomeMap10k.png`,
`WaterMap10k.png`, `Ice10k.png`, and `globecover10k.png` for the 10k profiles;
`earth2000` uses the corresponding complete 20k images. Only `production` uses
the split 40k GlobCover inputs. WorldPainter consumes the five prepared PNGs
under `generated/terrain/<profile>/`, at 100% with the original profile's
centered shift. There is no second resize. Outputs are uniquely named
`earth_1-<scale>_xenofactions_1.7.10_<canonical-profile>.world` and
`xenoearth-profile-<canonical-profile>.json` under `generated/`.

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
python -m pip install -r tools/terrain-requirements.txt
python -m unittest discover -s tools -p "test_*.py" -v
python tools/validate_xenoearth_source.py .
python tools/preprocess_xenoearth.py --profile=smoke
wpscript world_xenofactions.js --profile=smoke --preflightOnly
wpscript world_xenofactions.js --profile=smoke
```

Use Python 3.10 or newer with NumPy, Pillow 11.1 or newer and SciPy for preprocessing.
The Pillow minimum preserves unsigned 16-bit PNG decoding (the
[11.1 decoder](https://github.com/python-pillow/Pillow/blob/11.1.0/src/PIL/PngImagePlugin.py)
uses `I;16` for grayscale 16-bit inputs). Python
does not run inside WorldPainter; the script remains compatible with Java 8
Nashorn. Preparing another profile uses the same `--profile` value as its
WorldPainter launcher. `preview` resolves to `earth4000` in both tools. Run
preprocessing before using the GUI as well.

API preflight validates configuration, source files and image dimensions; verifies
the prepared manifest and SHA-256 fingerprints of inputs, processing code and
derived PNGs; resolves
the legacy Anvil platform; loads Rivers and every built-in layer; constructs every
selected-profile filter; and exits before constructing the world. Success ends
with `XenoEarth WorldPainter API preflight: PASS`.

In the GUI, choose **Tools → Run Script…**, select the general launcher and enter
a profile, or select a dedicated scale launcher. First enable **API preflight
only**. After PASS, run again with that box cleared. Progress appears in the Run
Script Output panel and identifies the active stage:

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

**Error:** `prepare terrain first` or `stale or changed terrain input`

Run `python tools/preprocess_xenoearth.py --profile=<profile>` and retry.
Regenerate after changing source assets,
`terrain-processing.json`, `vegetation.json`, the core, vegetation implementation,
preprocessing code or the source validator.
No raw-raster fallback is used. A failed preparation does not publish a complete
manifest. Keep enough free disk space for the ignored working arrays.

**Error:**
`No default layer named "Deciduous Forest" exists and no world specified`

**Cause:**
The script used a Java class/description-style name rather than the exact
WorldPainter layer name.

**Fix:**
Use `"Deciduous"` and `"Pine"`, not `"Deciduous Forest"` or `"Pine Forest"`.

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
| Earth terrain | Enabled | Normalized, piecewise processed 16-bit height; safe target floor 4 and peaks 246 |
| Bathymetry | Enabled | Separate shelf/slope/abyss/trench curve; source ocean topology preserved |
| Oceans | Enabled | Sea level 62; Deep Ocean floor cutoff 42; shallow sand through y=61 |
| Rivers | Enabled | Cleaned water mask + unchanged `Rivers.layer`; short tiny inland fragments removed; inland mask receives biome 7; ocean overlap cleared |
| Climate biomes | Enabled | Discrete majority/component cleanup; only 1.7.10 IDs; real coast gates beach tags |
| Ice | Enabled | Original sampled ice footprint; Frozen Ocean only underwater, built-in Frost on the full footprint |
| Surface materials | Enabled | Cleaned GlobCover classes, water-aware sand, bounded coastal beaches, legacy built-in terrain |
| Trees | Enabled | Native custom object layers; natural leaf decay; biome-specific species and density |
| Plants | Enabled | Native custom Plants layers; grass, ferns, flowers, mushrooms, desert shrubs/cactus |
| Caves / Caverns / Chasms / Ravines | **Disabled** | Must also be disabled at export |
| Ores / Resources | **Disabled** | No ore image or layer is loaded |
| Lava | **Disabled** | Must also be disabled at export |
| Structures | **Disabled** | Must also be disabled at export |
| Cities / Streets / Borders / Portals | **Disabled** | No objects generated; existing city/street masks suppress vegetation |
| Minecraft population | **Disabled** | Never mark chunks for Populate |

### Vegetation configuration

`vegetation.json` controls vegetation for every scale launcher. After editing it,
rerun preprocessing and generate a new project. Vegetation is already present in
the exported save; Minecraft Populate must stay off. Keep **make all leaves
persistent / leaves persist OFF** when exporting. Intact trees have naturally
supported leaves; removing their supporting logs allows normal game leaf decay.
Existing saves require a new export to receive these changes.

| Profile | Biomes | Vegetation |
|---|---|---|
| Forest / birch / roofed | 4,132 / 27 / 29 | Oak-birch / birch / dark oak; moderate ground cover |
| Plains | 1,129 | Grass, sparse flowers, very sparse oak trees |
| Taiga | 5,30,32,160,161 | Spruce, ferns and grass |
| Jungle | 21,22,23,149,151 | Denser jungle trees, low shrubs, tall grass and ferns |
| Savanna | 35,36 | Widely spaced acacias, sparse grass |
| Arid | 2,17,37,130 | Sparse dead shrubs and cactus on sand; no trees |
| Swamp | 6,134 | Oak-like swamp trees, grass, ferns, blue orchids, occasional mushrooms |
| Alpine | 3,131 | Sparse spruce and ground cover, fading with height |
| Tundra | 12,13,140 | Very sparse grass on exposed grass substrate; no trees |
| Coast / water | 16,26 / 0,7,10,24 | No terrestrial vegetation |

Controls include `enabled`, `seed`, `densityMultiplier`, `treeDensityMultiplier`,
each profile's `treeCoverage` and `plantCoverage`, weighted species/plant mixes,
`maximumTreeSlopeDegrees` (35), `alpineFalloffStartY` (120), `maximumTreeY` (175),
`maximumPlantY` (200), `treeCoastBuffer` (4 blocks), and `treeGrid` (8 blocks).
`treeCoverage` is the fraction of grid cells requesting a tree; `plantCoverage`
is the fraction of eligible columns requesting a plant. Exporter collision and
substrate rules may reject candidates. Multipliers of zero disable their category.

Placement uses the final cleaned biome, terrain, water and ice data. It avoids
water/ice, unsuitable substrates, steep tree positions, beaches, and low coastal
tree positions. Tree positions are spaced and jittered; ground cover forms gentle
patches. The seed pins both placement and native WorldPainter export randomness,
so regenerating/exporting unchanged inputs with the same WorldPainter version
gives the same vegetation. Tree shapes use only legacy vanilla logs and natural
leaves; reeds/lilies and modern plants are not included.

`suppressInfrastructureMasks` (true) uses the existing `Cities<scale>k.png` and
`street<scale>k.png` solely to exclude vegetation, without enabling their object
layers. `infrastructureBuffer` defaults to 3 blocks. Thin mask features survive
smaller exports. These masks are required and fingerprinted when suppression is
enabled. They describe mapped infrastructure, not future in-game player buildings.

For a small sample covering all profiles, run:

```bash
python tools/vegetation.py --sample
wpscript world_xenofactions_vegetation_sample.js
python tools/export-validation/vegetation_scan.py generated/vegetation-sample/export/XenoEarthVegetationSample --size 1664 128
```

The sample saves its editable project and export under
`generated/vegetation-sample/`. See `tools/export-validation/README.md` for the
scan's scope and the final in-game checklist.

## Terrain processing and diagnostics

`terrain-processing.json` is the single configuration for vertical curves and
cleanup thresholds. Height samples are normalized around 61.5*257 using the
measured resolution-dependent encoding, then mapped separately above and below
sea level. This is a visually exaggerated Minecraft interpretation, not a metre
conversion. Lowering sea level would reduce the available ocean depth, so it
remains 62. Encoded height precision and WorldPainter's fractional storage can
introduce sub-block rounding around curve anchors.

Climate and surface cleanup require 7 categorical votes in a 3x3 window, or a
connected component smaller than 12 / 8 columns with at least 60% neighboring
boundary support for a replacement. Eight-connectivity retains diagonal features.
Two columns near ocean are protected from that categorical cleanup. No RGB
colors are interpolated. Inland water components smaller than 6 columns are
removed only when their span is also below 6 and they are detached from the
ocean/shore; long thin rivers and mouths remain. No river gaps are bridged.

Beaches occupy up to two landward columns beside the unchanged ocean, require
surface y<=66, local 3x3 **land** relief<=4, no ice and a connected beach area of at least
four columns. Cold beaches use existing cold-biome/snow materials. Inland beach
climate tags are replaced using nearby regional climate, with explicit plains or
tundra fallback when none lies within 12 columns. Large desert and snow cover
is preserved. Dry pixels classified as water cover no longer automatically get
sand outside arid climate; unsupported isolated sand/snow receives a regional
fallback. Elevation averages only same-side neighbors within 2.5 Y blocks, blends
by 0.5 and moves a column by at most 0.75 blocks. It cannot cross sea level or
the safe vertical range, and does not blur ridges with distant valley heights.

A two-column shelf ramp beside lowland coasts softens source-quantization steps:
only ocean floors already within 14 blocks of sea level and beside land at y<=66
are eligible. The nearest shallow ocean column rises to at least y=60, the next
to at least y=58. Land, sea ownership, deep water and high coastal cliffs remain
unchanged. This local reinterpretation does not stretch or move coastlines.

Generated `diagnostics.json` contains native-source height histograms summarized
as percentiles, predicted final land/ocean percentiles, median and maximum depths,
clamp fractions, representative range rectangles, coast-ownership checks,
isolated-pixel counts and cleanup counts. The smoke profile additionally performs
an exact global run-length component census; `--census` requests it at larger
scales. Climate component keys reference the supplied RGB/biome-ID palette.
Regions crossing tile boundaries are merged for that census, rather than counted
as separate tile fragments. These are raster measurements, not chunk exports.

Working arrays take approximately 21 bytes per final column: about 76 MB for
smoke, 1.2 GB for earth4000, 4.9 GB for earth2000 and 19.4 GB for production,
plus derived PNGs. Arrays are disk-backed and removed on success or failure.
Pillow still decodes one native image at a time: production's 16-bit height image
alone is about 1.85 GB uncompressed. OS page-cache use is additional; preprocessing
does not promise a small fixed total RAM footprint. Tile halos cover cleanup
radii and component diameters, including across original GlobCover split seams.

## Mandatory export checklist

The script sets Populate off, removes Populate/Resources/Caves/Caverns/Chasms
layer data, disables default resources and generated structures, disables the
goodies chest, keeps bedrock, and leaves natural leaf persistence unchanged.
Check the following settings when exporting, especially after manually editing
the project. **The source project alone is not an export validation**:

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
for 1.7.10. Built-in Biomes, Frost, Deciduous, Pine, Jungle, and Swamp layers are also used. The inspected but disabled layers are:

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
