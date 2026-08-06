/*
 * Supported XenoFactions WorldPainter source pipeline (Phase 1).
 * Minecraft 1.7.10 only. The upstream implementation remains in world.js.
 */

// ----------------------------- Configuration ------------------------------
var path = "C:/Users/Owner/Documents/Downloads/bullshit/XFMAP/MinecraftEarthMapXF/";
var targetMinecraftVersion = "1.7.10";
var scale = 10;
var resize = 100;
var groundMaterialMode = "globecover";

var minimumSurfaceY = 1;
var maximumSurfaceY = 254;
var seaLevel = 62;

var generateVegetation = true;
var generateRivers = true;
var generateIce = true;

var generateCaves = false;
var generateCaverns = false;
var generateChasms = false;
var generateRavines = false;
var generateOres = false;
var generateResources = false;
var generateLava = false;
var generateStructures = false;
var generateCities = false;
var generateStreets = false;
var generateBorders = false;
var generatePortals = false;
var allowMinecraftPopulation = false;

var vegetationSeed = 68317010;
var vegetationDensity = 3; // Conservative WorldPainter layer intensity (0..15).
var maximumVegetationSlope = 35;

var LEGACY_ANVIL_MAP_FORMAT = "org.pepsoft.anvil";
var LOWER_BUILD_LIMIT = 0;
var UPPER_BUILD_LIMIT = 256;

// Central compatibility registry. No custom terrain is enabled until its entire
// material stack is safe. Built-in terrain numbers used below are not slots.
var CUSTOM_TERRAIN_COMPATIBILITY = {
    // Intentionally empty: see README_XENOFactions.md for inspected replacements.
};

// Vanilla 1.7.10 biome IDs used by this profile. Mutated IDs are named using
// their 1.7.10 names, not modern aliases.
var ALLOWED_BIOME_IDS = {
    0: "Ocean", 1: "Plains", 2: "Desert", 3: "Extreme Hills", 4: "Forest",
    5: "Taiga", 6: "Swampland", 7: "River", 10: "Frozen Ocean",
    12: "Ice Plains", 13: "Ice Mountains", 16: "Beach", 17: "Desert Hills",
    21: "Jungle", 22: "Jungle Hills", 23: "JungleEdge", 24: "Deep Ocean",
    26: "Cold Beach", 27: "Birch Forest", 29: "Roofed Forest",
    30: "Cold Taiga", 32: "Mega Taiga", 35: "Savanna", 36: "Savanna Plateau",
    37: "Mesa", 129: "Sunflower Plains", 130: "Desert M",
    131: "Extreme Hills M", 132: "Flower Forest", 134: "Swampland M",
    140: "Ice Plains Spikes", 149: "Jungle M", 151: "JungleEdge M",
    160: "Mega Spruce Taiga", 161: "Mega Spruce Taiga Hills"
};

var BIOME_MAPPINGS = [
    [0,0,255,149], [0,120,255,21], [70,170,250,23], [255,0,0,2],
    [255,150,150,17], [245,165,0,35], [255,220,100,130], [255,255,0,1],
    [200,200,0,129], [150,255,150,151], [100,200,100,22], [50,150,50,131],
    [200,255,80,132], [100,255,80,132], [50,200,0,3], [255,0,255,36],
    [200,0,200,36], [150,50,150,30], [150,100,150,161], [170,175,255,6],
    [90,120,220,134], [75,80,180,32], [50,0,135,160], [0,255,255,4],
    [55,200,255,29], [0,125,125,5], [0,70,95,13], [178,178,178,12],
    [102,102,102,140], [200,200,200,16], [220,220,220,26], [255,100,0,37],
    [0,0,0,0], [255,20,0,2], [255,170,150,17], [255,255,100,130]
];

// Thresholds are derived from the configured sea level.
var SHALLOW_OCEAN_THRESHOLD = seaLevel - Math.round(scale * 0.30);
var DEEP_OCEAN_THRESHOLD = seaLevel - Math.round(scale * 0.65);
var RIVER_THRESHOLD = seaLevel + 1;
var LAND_THRESHOLD = seaLevel;

function fail(message) { throw new Error("XenoFactions configuration error: " + message); }
function file(relative) { return new java.io.File(path + relative); }
function requireFile(relative) {
    var f = file(relative);
    if (!f.isFile()) fail("required input is missing: " + f.getPath());
    return f;
}
function imageSize(relative, expectedWidth, expectedHeight) {
    var f = requireFile(relative);
    var stream = javax.imageio.ImageIO.createImageInputStream(f);
    if (stream === null) fail("cannot read image header: " + relative);
    var readers = javax.imageio.ImageIO.getImageReaders(stream);
    if (!readers.hasNext()) { stream.close(); fail("unsupported image: " + relative); }
    var reader = readers.next(); reader.setInput(stream, true, true);
    var width = reader.getWidth(0), height = reader.getHeight(0);
    reader.dispose(); stream.close();
    if (width !== expectedWidth || height !== expectedHeight) {
        fail(relative + " is " + width + " x " + height + "; expected " + expectedWidth + " x " + expectedHeight);
    }
}
function validateConfiguration() {
    if (targetMinecraftVersion !== "1.7.10") fail("targetMinecraftVersion must be 1.7.10");
    if (scale !== 10 && scale !== 20 && scale !== 40) fail("scale must be 10, 20, or 40");
    if (resize <= 0) fail("resize must be greater than zero");
    var configuredDimensions = {10:[10752,5376], 20:[21504,10752], 40:[43008,21504]}[scale];
    if ((configuredDimensions[0] * resize / 100) % 512 !== 0 || (configuredDimensions[1] * resize / 100) % 512 !== 0) {
        fail("resize must keep both output dimensions on 512-block region boundaries");
    }
    if (groundMaterialMode !== "globecover" && groundMaterialMode !== "biomes") fail("groundMaterialMode must be globecover or biomes");
    if (minimumSurfaceY < 1) fail("minimumSurfaceY must be at least 1");
    if (maximumSurfaceY > 254) fail("maximumSurfaceY must be at most 254");
    if (minimumSurfaceY >= seaLevel) fail("minimumSurfaceY must be below seaLevel");
    if (seaLevel >= maximumSurfaceY) fail("seaLevel must be below maximumSurfaceY");
    if (vegetationDensity < 0 || vegetationDensity > 15) fail("vegetationDensity must be from 0 through 15");
    if (maximumVegetationSlope < 0 || maximumVegetationSlope > 90) fail("maximumVegetationSlope must be from 0 through 90");
    for (var i = 0; i < BIOME_MAPPINGS.length; i++) {
        wp.checkForInterrupt();
        if (!ALLOWED_BIOME_IDS.hasOwnProperty(BIOME_MAPPINGS[i][3])) fail("unsupported biome ID " + BIOME_MAPPINGS[i][3]);
    }

    var dims = {10:[10752,5376], 20:[21504,10752], 40:[43008,21504]}[scale];
    var suffix = String(scale) + "k.png";
    imageSize("images/HeightMap" + suffix, dims[0], dims[1]);
    imageSize("images/BiomeMap" + suffix, dims[0], dims[1]);
    imageSize("images/WaterMap" + suffix, dims[0], dims[1]);
    imageSize("images/Ice" + suffix, dims[0], dims[1]);
    if (scale === 40) {
        imageSize("images/globecover1_40k.png", 21504, 10752);
        imageSize("images/globecover2a_40k.png", 10752, 10752);
        imageSize("images/globecover2b_40k.png", 10752, 10752);
        imageSize("images/globecover3_40k.png", 21504, 10752);
        imageSize("images/globecover4_40k.png", 21504, 10752);
    } else imageSize("images/globecover" + suffix, dims[0], dims[1]);
    if (generateRivers) requireFile("layer/Rivers.layer");
}

validateConfiguration();

var suffix = String(scale) + "k.png";
var westShift = -Math.round(537.6 * scale * (resize / 100));
var northShift = -Math.round(268.8 * scale * (resize / 100));
var heightMap = wp.getHeightMap().fromFile(path + "images/HeightMap" + suffix).go();
java.lang.System.out.println("Creating project with required map format " + LEGACY_ANVIL_MAP_FORMAT
    + ", build limits " + LOWER_BUILD_LIMIT + ".." + (UPPER_BUILD_LIMIT - 1) + ", and water level " + seaLevel + ".");
var mapFormat = wp.getMapFormat()
    .withId(LEGACY_ANVIL_MAP_FORMAT)
    .go();

var world = wp.createWorld()
    .fromHeightMap(heightMap)
    .scale(resize)
    .shift(westShift, northShift)
    .fromLevels(0, 65535)
    .toLevels(minimumSurfaceY, maximumSurfaceY)
    .withMapFormat(mapFormat)
    .withLowerBuildLimit(LOWER_BUILD_LIMIT)
    .withUpperBuildLimit(UPPER_BUILD_LIMIT)
    .withWaterLevel(seaLevel)
    .go();
heightMap = null;
world.setSpawnPoint(new java.awt.Point(Math.round(110.5 * scale), -Math.round(11.4 * scale)));

var biomesLayer = wp.getLayer().withName("Biomes").go();
var biomeMap = wp.getHeightMap().fromFile(path + "images/BiomeMap" + suffix).go();
var biomeApplication = wp.applyHeightMap(biomeMap).toWorld(world).scale(resize)
    .shift(westShift, northShift).applyToLayer(biomesLayer);
for (var b = 0; b < BIOME_MAPPINGS.length; b++) {
    wp.checkForInterrupt();
    var m = BIOME_MAPPINGS[b]; biomeApplication = biomeApplication.fromColour(m[0],m[1],m[2]).toLevel(m[3]);
}
biomeApplication.go();

function applyGlobCover(map, shiftX, shiftZ) {
    wp.applyHeightMap(map).toWorld(world).scale(resize).shift(shiftX, shiftZ).applyToTerrain()
        .fromColour(0,255,0).toTerrain(1)       // grass
        .fromColour(255,255,0).toTerrain(5)     // sand (verified replacement for custom mix)
        .fromColour(255,255,255).toTerrain(40)  // deep snow
        .fromColour(127,0,0).toTerrain(1)       // podzol forests: safe grass fallback
        .fromColour(255,0,0).toTerrain(6)       // red sand
        .fromColour(150,150,150).toTerrain(1)   // rocky mosaic: safe grass fallback
        .fromColour(255,127,0).toTerrain(5)     // sand/grass mosaic: safe sand fallback
        .fromColour(0,127,127).toTerrain(1)     // swamp surface
        .fromColour(0,148,255).toTerrain(5)     // ocean and river bed
        .go();
}
if (groundMaterialMode === "globecover") {
    if (scale === 40) {
        var globecoverParts = [
            ["globecover1_40k.png", westShift, northShift],
            ["globecover2a_40k.png", 0, northShift],
            ["globecover2b_40k.png", -westShift / 2, northShift],
            ["globecover3_40k.png", westShift, 0],
            ["globecover4_40k.png", 0, 0]
        ];
        for (var gp = 0; gp < globecoverParts.length; gp++) {
            wp.checkForInterrupt();
            var globecoverMap = wp.getHeightMap().fromFile(path + "images/" + globecoverParts[gp][0]).go();
            applyGlobCover(globecoverMap, globecoverParts[gp][1], globecoverParts[gp][2]);
            globecoverMap = null;
        }
    } else {
        var globecoverMap = wp.getHeightMap().fromFile(path + "images/globecover" + suffix).go();
        applyGlobCover(globecoverMap, westShift, northShift); globecoverMap = null;
    }
}

var shallowOceanFilter = wp.createFilter().aboveLevel(DEEP_OCEAN_THRESHOLD).belowLevel(SHALLOW_OCEAN_THRESHOLD).onlyOnBiome(0).go();
var initialDeepOceanFilter = wp.createFilter().aboveLevel(minimumSurfaceY).belowLevel(DEEP_OCEAN_THRESHOLD).onlyOnBiome(0).go();
wp.applyHeightMap(biomeMap).toWorld(world).scale(resize).shift(westShift,northShift)
    .applyToLayer(biomesLayer).withFilter(initialDeepOceanFilter).fromColour(0,0,0).toLevel(24).go();
var deepOceanFilter = wp.createFilter().aboveLevel(minimumSurfaceY).belowLevel(DEEP_OCEAN_THRESHOLD).onlyOnBiome(24).go();
// Built-in sand (5) is used for both ocean floor bands; no unverified custom terrain is loaded.
wp.applyHeightMap(biomeMap).toWorld(world).scale(resize).shift(westShift,northShift)
    .applyToTerrain().withFilter(shallowOceanFilter).fromColour(0,0,0).toTerrain(5).go();

var riverMask = null;
var riverLayer = null;
if (generateRivers) {
    riverMask = wp.getHeightMap().fromFile(path + "images/WaterMap" + suffix).go();
    riverLayer = wp.getLayer().fromFile(path + "layer/Rivers.layer").go();
    var inlandRiverFilter = wp.createFilter().aboveLevel(RIVER_THRESHOLD).belowLevel(maximumSurfaceY)
        .exceptOnBiome(0).exceptOnBiome(24).exceptOnBiome(10).go();
    var oceanRiverMaskOverlapFilter = wp.createFilter().aboveLevel(minimumSurfaceY).belowLevel(seaLevel).go();
    wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift)
        .applyToLayer(riverLayer).withFilter(inlandRiverFilter).fromLevel(0).toLevel(0).fromLevels(1,255).toLevel(1).go();
    wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift)
        .applyToLayer(biomesLayer).withFilter(inlandRiverFilter).fromLevels(1,255).toLevel(7).go();
    // Explicitly erase ground-cover river data and restore the ocean floor wherever
    // the mask reaches water, so it cannot raise a water surface across an ocean.
    wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift)
        .applyToLayer(riverLayer).withFilter(oceanRiverMaskOverlapFilter).fromLevels(1,255).toLevel(0).go();
    wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift)
        .applyToTerrain().withFilter(deepOceanFilter).fromLevels(1,255).toTerrain(5).go();
    wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift)
        .applyToTerrain().withFilter(shallowOceanFilter).fromLevels(1,255).toTerrain(5).go();
    riverMask = null;
}

if (generateIce) {
    var iceMask = wp.getHeightMap().fromFile(path + "images/Ice" + suffix).go();
    wp.applyHeightMap(iceMask).toWorld(world).scale(resize).shift(westShift,northShift)
        .applyToLayer(biomesLayer).fromLevels(1,255).toLevel(10).go();
    var frostLayer = wp.getLayer().withName("Frost").go();
    wp.applyHeightMap(iceMask).toWorld(world).scale(resize).shift(westShift,northShift)
        .applyToLayer(frostLayer).fromLevel(0).toLevel(0).fromLevels(1,255).toLevel(1).go();
    iceMask = null;
}

// Offline vegetation uses shared, built-in WorldPainter layers. Their exporters
// perform object placement before Minecraft runs; population remains forbidden.
if (generateVegetation) {
    var vegetationFilterBuilder = wp.createFilter().aboveLevel(seaLevel)
        .belowLevel(maximumSurfaceY).belowDegrees(maximumVegetationSlope)
        .exceptOnBiome(0).exceptOnBiome(24).exceptOnBiome(10);
    if (riverLayer !== null) vegetationFilterBuilder = vegetationFilterBuilder.exceptOnLayer(riverLayer);
    var vegetationFilter = vegetationFilterBuilder.go();
    var vegetationRules = [
        ["Deciduous Forest", [[0,255,255],[200,255,80],[100,255,80],[255,255,0],[200,200,0]]], // forest/birch/plains
        ["Deciduous Forest", [[55,200,255],[170,175,255]]], // roofed forest/swamp
        ["Pine Forest", [[0,125,125],[75,80,180],[50,0,135],[150,50,150],[150,100,150]]], // taiga/mega/cold
        ["Jungle", [[0,0,255],[0,120,255],[70,170,250],[150,255,150],[100,200,100]]], // jungle
        ["Deciduous Forest", [[245,165,0],[255,0,255]]], // savanna (built-in layer is conservative fallback)
        ["Swamp", [[90,120,220]]] // swamp plants; desert intentionally has no tree layer
    ];
    for (var vr = 0; vr < vegetationRules.length; vr++) {
        wp.checkForInterrupt();
        var vegetationLayer = wp.getLayer().withName(vegetationRules[vr][0]).go();
        wp.checkForInterrupt();
        var veg = wp.applyHeightMap(biomeMap).toWorld(world).scale(resize).shift(westShift,northShift)
            .applyToLayer(vegetationLayer).withFilter(vegetationFilter);
        for (var c = 0; c < vegetationRules[vr][1].length; c++) {
            wp.checkForInterrupt();
            var colour = vegetationRules[vr][1][c];
            veg = veg.fromColour(colour[0],colour[1],colour[2]).toLevel(vegetationDensity);
        }
        veg.go();
    }
}

biomeMap = null; riverMask = null; riverLayer = null;

var denominator = Math.round(40 / scale * 1000);
var outputName = "earth_1-" + denominator + "_xenofactions_1.7.10" + (resize === 100 ? "" : "_resize-" + resize) + ".world";
var baseDimensions = {10:[10752,5376], 20:[21504,10752], 40:[43008,21504]}[scale];
var outputWidth = Math.round(baseDimensions[0] * resize / 100);
var outputHeight = Math.round(baseDimensions[1] * resize / 100);
var profile = {
    formatVersion: 1, targetMinecraftVersion: targetMinecraftVersion,
    scale: denominator, width: outputWidth, height: outputHeight,
    minimumX: -outputWidth / 2, maximumX: outputWidth / 2 - 1,
    minimumZ: -outputHeight / 2, maximumZ: outputHeight / 2 - 1,
    minimumSurfaceY: minimumSurfaceY, maximumSurfaceY: maximumSurfaceY,
    seaLevel: seaLevel, projection: "equirectangular", populationMode: "pregenerated",
    caves: generateCaves, ores: generateOres, lava: generateLava,
    structures: generateStructures, vegetation: generateVegetation
};
var profileWriter = new java.io.FileWriter(path + "xenoearth-profile.json");
profileWriter.write(JSON.stringify(profile, null, 2) + "\n"); profileWriter.close();
java.lang.System.out.println("\n*** REQUIRED MANUAL EXPORT CHECKLIST (NOT SCRIPT-CONTROLLABLE) ***");
java.lang.System.out.println("The project already uses legacy Anvil and build limits 0..255. Disable Populate; Resources; Caves, Caverns and Chasms; Structures; and lava lakes/pockets. Disable any other underground pockets or ravine generator. Keep bottomless world OFF so y=0 exports as bedrock.");
java.lang.System.out.println("vegetationSeed=" + vegetationSeed + " records reproducibility; this WorldPainter API does not expose a verified per-layer seed setter.");
wp.saveWorld(world).toFile(path + outputName).go();
world = null;
