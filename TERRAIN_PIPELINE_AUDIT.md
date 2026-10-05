# Earth terrain pipeline audit and processing design

Audit of the local repository, 2026-10-01, before changing the generator.
The governing principle is **preserve regional geography; reinterpret
sub-Minecraft-scale raster detail**. All existing profile dimensions, crop,
projection, coordinate origin, scale, spawn and export restrictions are retained.

## Original authoritative path

The general and dedicated launchers load `world_xenofactions_core.js` through
Nashorn's `load(URL)`. `world.js` is the upstream reference, not a dependency of
the XenoFactions generator; the backup script is also not called. Preflight checks
dimensions, resolves legacy Anvil and layers, and constructs filters. Generation
then imports height, assigns climate, assigns GlobCover terrain, classifies
oceans, applies rivers, ice and vegetation, and saves a `.world` plus manifest.
It does not export Minecraft chunks. Declared `groundMaterialMode`,
`vegetationSeed` and custom-terrain compatibility registry do not drive the
current generation path. Vegetation density and slope filters do.

### Assets, coordinates and interpolation

Upstream README records a 43200 x 21600 canvas cropped symmetrically to
43008 x 21504. Köppen categories are canvas-cropped without RGB interpolation.
GlobCover originally lacks Antarctica, receives southern padding, is reduced
by three without antialiasing, then cropped. NASA elevation and bathymetry were
combined, bicubic-upscaled and blurred **before these committed assets were
made**. The raw NASA rasters, compositing formula, blur kernel and editable
source project are absent, so neither metre calibration nor recovery of lost
ridgelines can be established from this repository. Natural Earth ice images
were resized and posterized. Smaller asset creation is undocumented, but measured
heights demonstrate resolution-dependent vertical encoding.

| Profile | Source dimensions | Applied scale | Final dimensions |
|---|---|---|---|
| smoke | 10752 x 5376 | 25% | 2688 x 1344 |
| earth8000 | 10752 x 5376 | 50% | 5376 x 2688 |
| earth4000 / preview | 10752 x 5376 | 100% | 10752 x 5376 |
| earth2000 | 21504 x 10752 | 100% | 21504 x 10752 |
| production | 43008 x 21504 | 100% | 43008 x 21504 |

Every application uses the same centered shift: `-width/2, -height/2`.
Production GlobCover is assembled from NW, NE-west, NE-east, SW, SE tiles at
source offsets (0,0), (21504,0), (32256,0), (0,10752), (21504,10752).
The full `globecover40k.png` is not authoritative in the original core.
`OceanBiomeMap`, `Mask`, cities, roads, borders, ores, portals, modern custom
terrains and upstream mesa/swamp layers are not used by this core.

WorldPainter v2.27.0 source was inspected directly:
[ImportHeightMapOp](https://github.com/Captain-Chaos/WorldPainter/blob/v2.27.0/WorldPainter/WPCore/src/main/java/org/pepsoft/worldpainter/tools/scripts/ImportHeightMapOp.java),
[MappingOp](https://github.com/Captain-Chaos/WorldPainter/blob/v2.27.0/WorldPainter/WPCore/src/main/java/org/pepsoft/worldpainter/tools/scripts/MappingOp.java),
[BitmapHeightMap](https://github.com/Captain-Chaos/WorldPainter/blob/v2.27.0/WorldPainter/WPCore/src/main/java/org/pepsoft/worldpainter/heightMaps/BitmapHeightMap.java),
[TransformingHeightMap](https://github.com/Captain-Chaos/WorldPainter/blob/v2.27.0/WorldPainter/WPCore/src/main/java/org/pepsoft/worldpainter/heightMaps/TransformingHeightMap.java),
[BicubicHeightMap](https://github.com/Captain-Chaos/WorldPainter/blob/v2.27.0/WorldPainter/WPCore/src/main/java/org/pepsoft/worldpainter/heightMaps/BicubicHeightMap.java),
[HeightMapImporter](https://github.com/Captain-Chaos/WorldPainter/blob/v2.27.0/WorldPainter/WPCore/src/main/java/org/pepsoft/worldpainter/importing/HeightMapImporter.java), and
[Terrain](https://github.com/Captain-Chaos/WorldPainter/blob/v2.27.0/WorldPainter/WPCore/src/main/java/org/pepsoft/worldpainter/Terrain.java).
Height import casts to BitmapHeightMap. Reduced height imports use bounded
bicubic interpolation with a half-pixel offset. Color applications use discrete
nearest samples; grayscale applications use the bitmap's selected raster band.
The apparently enabled `smoothScaling` local in MappingOp does not wrap the map
in an interpolator. Unknown RGB colors are skipped, leaving earlier/default
values. HeightMapImporter maps the supplied range linearly and clamps to build
limits, not to the requested `toLevels` endpoints. Initial terrain/theme can
depend on WorldPainter's configured heightmap theme and randomly chosen seed;
this matters where the original script leaves pixels unmapped. Terrain indices
1, 5, 6, 40 mean bare grass, sand, red sand, deep snow, respectively.

## What each original stage actually writes

* **Height:** unsigned 16-bit samples; maps 0..65535 to y=1..254, water 62,
  build 0..255. Before import, values below the assumed source sea 15801 are
  linearly expanded by 2.05 around that value and clamped at zero. No land
  transform or spatial cleanup. This assumes meaningful use of the full 16-bit
  domain and a common vertical scale, neither of which is true.
* **Climate:** 36 exact RGB mappings to 1.7.10 biome IDs. Black becomes Ocean.
  No mode, region or boundary processing. The unexpected color (150,150,0) is
  omitted: 544 pixels at 10k and 3055 at 20k. Cfa/Cfb share biome 132; Dsa/Dsb
  share 36 but have different existing vegetation rules, so retain climate
  categories rather than merging everything by biome ID.
* **GlobCover:** green, dark red/podzol, gray/bare and teal/swamp all become
  bare grass. Yellow sand, orange mixed sand/grass and blue water become pure
  sand. Red becomes red sand; white becomes deep snow. (230,230,230) is omitted
  (2388 pixels at 10k, 9591 at 20k); production also contains unmapped (170,170,170).
  No land/water or climate consistency test.
  The core intentionally does not load upstream custom terrain mixtures.
* **Oceans:** black climate below `62-round(sourceScale*0.65)` becomes Deep
  Ocean. Sand is applied between that floor and `62-round(sourceScale*0.30)`.
  These bands change with source resolution, not final scale or a physical
  shelf definition. Very shallow coast pixels are omitted. Deep floors are
  subsequently sanded only where the river/water mask overlaps them.
* **Water:** indexed binary WaterMap has raster indices 0/1 and includes the
  ocean as well as inland waters. Every value 1..255 sets Rivers.layer and biome
  7 on dry columns y>=63. Every nonzero coastal overlap below sea level clears
  the river layer. The same mask restores sand in the ocean bands. There is no
  minimum feature area, confidence threshold or connectivity check. A tiny
  source fragment survives as a custom river-layer column, not necessarily a
  one-block exported lake: the serialized Rivers.layer controls final channel
  excavation and geometry.
* **Ice:** indexed 0/1 mask assigns biome 10 to **all** positive pixels, including
  land, and separately assigns Frost. This overwrites polar land climates with
  Frozen Ocean. No deep-frozen ID (not valid for 1.7.10) is added.
* **Vegetation:** exact source climate colors select Deciduous/Pine/Jungle/Swamp
  at density 3. Filters require land, y>=62, slope<=35 degrees and no river
  layer. Rules do not inspect GlobCover. There is no new population, resource,
  cave or structure generation. Preserve these rules and layer settings;
  processed climate should become their input so removed speckles cannot grow
  isolated incompatible trees. Existing WorldPainter/export randomness is
  distinct from deterministic preprocessing.

## Measured elevation, not assumed Earth metres

Every pixel of all three heightmaps and climate maps was checked. Height<15934
matches black climate **exactly**, with zero mismatches at all resolutions.
Thus the ocean ends at sample 61*257=15677; land starts at 62*257=15934.
Use the separating boundary 61.5*257, not a sea threshold reverse-derived from
an arbitrary Minecraft range. All samples are multiples of 257: these are
8-bit levels expanded into a 16-bit PNG, not genuine 16-bit elevation precision.

| Source | Pixels | Distinct levels | Encoded min/max | Old ocean median y | Old highest land y |
|---|---:|---:|---|---:|---:|
| 10k | 57,802,752 | 61 | 48..108 times 257 | 46.78 | 108.15 |
| 20k | 231,211,008 | 123 | 35..157 times 257 | 34.58 | 156.77 |
| 40k | 924,844,032 | 246 | 9..254 times 257 | 8.14 | 253.01 |

Old deepest floor: y=34.58 (10k), 8.14 (20k), 1 after clipping (40k).
The reported roughly 55-block deepest ocean fits the 20k source. The production
map has the opposite related failure: 32.3968% of ocean columns clip to y=1. These are
calculated column heights from measured source distributions, not measured
Minecraft exports. The old 16-bit LUT adds less than .002 blocks of rounding.
At 10k, height-import bicubic interpolation cannot create taller mountains than
the local source maxima. Representative Himalaya rectangle maxima are encoded
108/157/254; Andes 104/152/250; Alps 88/121/185; Rockies 93/126/190.
Those rectangles include foothills and water; they are not surveyed summit
points. Coordinates use the upstream canvas's 3*sourceScale pixels per degree,
then the documented symmetric crop.

The normalized relief `(sample/257 - 61.5)*40/sourceScale` yields similar extrema
across resolutions: oceans -54/-53/-52.5; peaks 186/191/192.5. This is a measured
encoding correction, **not an XY change or a claimed metre conversion**.

## Artifact causes and safest interventions

| Artifact | Confirmed producing stage | Treatment and expected effect | Over-cleaning risk |
|---|---|---|---|
| Tiny biomes and thin slivers | Unfiltered exact climate pixels; nearest reduction can alias categories | Strict local categorical majority plus replacement of small connected regions with a dominant neighboring category; retain shoreline and regional boundaries | Small real climate enclaves and narrow mountain belts; protect coastal land and require strong support |
| Invalid/abrupt climate colors | Unexpected source category skipped; valid RGB is not blended by WP | Explicitly map the known omission; no RGB blur; clean discrete labels only | Color distance is not climate distance; do not invent a general nearest-color classifier |
| Sand/red sand/snow speckling | GlobCover category errors and mixed-class-to-pure-sand conversion applied literally | Clean final surface classes, preserve large desert/snow regions; treat water class as sand only in actual water; tiny inconsistencies disappear | Real dunes, exposed rock and glaciers differ legitimately from regional climate; avoid blanket biome-to-material replacement |
| Tiny water and broken rivers | Every nonzero WaterMap pixel becomes a river; nearest reduction can disconnect it | Remove only short, tiny disconnected inland components; preserve long thin streams and coastal connections; do not close gaps speculatively | Real ponds disappear below the explicit area limit; no automatic joining of separate drainage basins |
| Random beaches | Sand is treated as cover, not coastline; source beach biomes can survive inland | Keep desert sands; generate a narrow landward band from unchanged ocean topology, gated by elevation and local relief; replace inland beach climate with nearby regional climate | Rocky/steep coasts should receive no forced beach; snow coasts remain cold |
| Compressed mountains / shallow or flattened seas | Resolution-dependent encoded relief, one linear full-domain mapping, constant ocean multiplier | Normalize encoded relief and apply separate monotone land/ocean piecewise curves; retain broad relief rank and allocate safe Y headroom | Exaggeration steepens slopes and affects the existing vegetation slope gate; do not globally smooth mountains |
| Frozen Ocean on polar land | Ice step overwrites every positive-mask biome | Limit biome 10 assignment to submerged columns; keep Frost footprint | Intentional snow terrain is separate from ice coverage and must remain |

## Processing architecture chosen before implementation

Use one Python stage with NumPy/Pillow plus SciPy's compiled connected-component
and morphology operations. The latter is justified by nearly a billion production
pixels: Python per-pixel flood fills are unsuitable. Source decoding is sequential;
working arrays are disk-backed under ignored `generated/`. Local processing uses
tiles and sufficient halos, with no per-tile percentile calibration or random
noise. Production surface processing crosses original GlobCover part boundaries.

1. Read the authoritative assets, validate type, palette and dimensions, and
   reduce onto the **existing** final grid. Keep WP's nearest categorical sample
   coordinates and bounded bicubic height behavior for reduced profiles.
2. Keep an immutable ocean/land topology from the source heights. Normalize
   height encoding, then use monotone curves for shelves, slopes, abyssal plains,
   trenches, lowlands, hills, ranges and peaks. Encode the result back into a
   true 16-bit derived image for the existing WP y=1..254 mapping.
3. Clean climate labels and surface labels separately, protecting shore topology.
   Retain a strict majority's existing discrete color; never average RGB.
   Component thresholds are in **final Minecraft columns**, not source pixels.
4. Remove only small short inland water components, protecting diagonal channels
   and ocean mouths. Ice remains a separate binary footprint.
5. Reconcile water-cover terrain and beach tags against the unchanged ocean,
   cleaned water, height and climate. Apply slope-aware, bounded height cleanup
   within the same land/water side; no unconstrained blur or erosion.
6. Write derived inputs, configuration/source fingerprints and diagnostics;
   WorldPainter requires that complete profile bundle, imports at 100% and
   performs the existing layer applications and save/export-safety operations.
   The new data is authoritative; no silent fallback to raw rasters.

Keep sea level **62**. It allows at most 61 blocks to the existing lower surface
limit, or 58 to a safe floor at y=4. Lowering it to 48 would reduce safe maximum
depth to 44 while adding just 14 above-water blocks. The measured ocean problem
needs better use of the current allocation, not less allocation. Reserve top
headroom for peaks and existing vegetation. Curves use encoded relief anchors,
not a per-map quantile stretch, so all profiles retain a consistent interpretation.

Validation should cover whole-map source/final percentiles, clip fractions,
unchanged coast ownership, component/isolated-pixel counts and representative
range statistics. A component census must distinguish complete global regions
from tile fragments. These are raster diagnostics; WP API preflight, project
creation, exporter behavior and Forge 1.7.10 visual acceptance remain separate.

## Implemented pass and observed validation

The design above is implemented in `tools/preprocess_xenoearth.py`, configured by
`terrain-processing.json`. Every height, climate, surface, water and ice input
used by the shared WorldPainter core now terminates at the prepared bundle.
Original raster references in the core only validate sources and fingerprints;
the upstream and backup generators remain intentionally unused references.
All five production GlobCover parts were decoded and their palettes checked;
both RGB and indexed parts use the same exact categorical decoder. Unknown new
categories fail preparation instead of inheriting an arbitrary WP theme.

The implemented local coast pass adds two details established during native-grid
validation. The last 10k ocean level otherwise maps to roughly y=54.7, creating
a quantization step beside lowlands. Only already-shallow floor (within 14 blocks
of sea level), within two columns of land at y<=66, receives a bounded ramp to
y>=60/58 at distances one/two. Deep water and land remain unchanged. Beach slope
uses **land** relief, excluding bathymetry: including the seabed incorrectly
rejects flat beaches. Tiny disconnected beach masks below four columns are
discarded without removing the land itself.

Both complete Earth preprocessing passes below were executed locally. These
numbers describe prepared rasters and predict WP import; no `.world` creation or
Minecraft export was executed here.

| Measurement | smoke (3,612,672 columns) | earth4000 (57,802,752 columns) |
|---|---:|---:|
| Final land min / max Y | 63.00 / 240.05 | 63.67 / 240.52 |
| Final ocean floor min / median Y | 4.00 / 16.00 | 4.00 / 16.00 |
| Median / deepest ocean depth | 46.00 / 58.00 | 46.00 / 58.00 |
| Terrain at Y<=2 or Y>=253 | 0% | 0% |
| Changed source coast ownership | 0 | 0 |
| Tiny climate components replaced | 3,745 | 25,404 |
| Tiny surface components replaced | 5,169 | 72,726 |
| Tiny inland water components removed | 9,940 | 18,237 |
| Isolated climate pixels, before -> after | 10,586 -> 3,688 | 52,639 -> 14,203 |
| Isolated surface pixels, before -> after | 19,418 -> 2,794 | 210,869 -> 12,137 |
| Isolated water pixels, before -> after | 8,445 -> 2,237 | 25,848 -> 19,944 |

The smoke global 8-connected census counts climate regions 18,832 -> 9,132,
surface regions 31,856 -> 6,976, and inland water regions 13,787 -> 3,847.
Climate regions refer to RGB categories (legend in the diagnostic JSON), keeping
vegetation distinctions even where two categories map to the same Minecraft
biome. Retained tiny shoreline components and long thin water features are
intentional conservative exceptions. The source ocean/ice footprints are not
subject to component removal.

Preprocessing used Pillow 12.3.0; dependencies require Pillow 11.1 or newer for
unsigned 16-bit PNG decoding. Existing source validation and all 25 existing tests
pass. Real-data comparisons
of 256/512-column tile processing against an untiled pass found zero mismatches
for categorical climate, water, bounded elevation and the shelf ramp. Java 8
Nashorn loaded the core and verified both prepared manifests, source/derived
fingerprints and dimensions. Java ImageIO read the smoke height as unsigned
16-bit and found zero unmapped climate colors. These Java checks used only the
input-loading helpers, not a simulated WorldPainter generation.

The source-height and coast audits covered all 10k, 20k and 40k input pixels.
Full 20k/40k cleanup runs, real WorldPainter 2.27.0 API preflight and project
generation, legacy export checks and representative Forge 1.7.10 play/visual
acceptance remain necessary. Start with coast/river junctions, Arctic ice,
continental shelves, Mariana, Himalaya, Andes, Alps and Rockies. The taller
relief intentionally changes slopes; existing vegetation slope rejection can
therefore apply more often. Inspect roads/buildability separately before tuning
the explicit curves or cleanup sizes for a server's preferred terrain style.
