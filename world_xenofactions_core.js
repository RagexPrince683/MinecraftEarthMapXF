var sourceRoot = new java.io.File(scriptDir);

function log(message) {
    var text = String(message);

    try {
        print(text);
    } catch (error) {
        java.lang.System.out.println(text);
    }
}

function file(relativePath) {
    return new java.io.File(sourceRoot, relativePath);
}

function absolutePath(relativePath) {
    return file(relativePath).getAbsolutePath();
}


var targetMinecraftVersion = "1.7.10";

var PROFILES = {
    smoke: {
        name: "smoke",
        sourceScale: 10,
        resize: 25,
        effectiveScale: 16000,
        width: 2688,
        height: 1344
    },

    earth8000: {
        name: "earth8000",
        sourceScale: 10,
        resize: 50,
        effectiveScale: 8000,
        width: 5376,
        height: 2688
    },

    earth4000: {
        name: "earth4000",
        sourceScale: 10,
        resize: 100,
        effectiveScale: 4000,
        width: 10752,
        height: 5376
    },

    earth2000: {
        name: "earth2000",
        sourceScale: 20,
        resize: 100,
        effectiveScale: 2000,
        width: 21504,
        height: 10752
    },

    production: {
        name: "production",
        sourceScale: 40,
        resize: 100,
        effectiveScale: 1000,
        width: 43008,
        height: 21504
    }
};


var PROFILE_ALIASES = {
    preview: "earth4000"
};


var SOURCE_DIMENSIONS = {
    10: [10752, 5376],
    20: [21504, 10752],
    40: [43008, 21504]
};


var selectedProfileName;
var runPreflightOnly;

var groundMaterialMode = "globecover";

var minimumSurfaceY = 1;
var maximumSurfaceY = 254;
var seaLevel = 62;


// Derived inputs are prepared once on the existing final grid.
var applicationResize = 100;


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
var vegetationDensity = 3;
var maximumVegetationSlope = 35;

var LEGACY_ANVIL_MAP_FORMAT = "org.pepsoft.anvil";

var LOWER_BUILD_LIMIT = 0;
var UPPER_BUILD_LIMIT = 256;


var BUILTIN_LAYER_NAMES = {
    biomes: "Biomes",
    frost: "Frost",
    deciduous: "Deciduous",
    pine: "Pine",
    jungle: "Jungle",
    swamp: "Swamp"
};


var CUSTOM_TERRAIN_COMPATIBILITY = {};


var ALLOWED_BIOME_IDS = {
    0: "Ocean",
    1: "Plains",
    2: "Desert",
    3: "Extreme Hills",
    4: "Forest",
    5: "Taiga",
    6: "Swampland",
    7: "River",
    10: "Frozen Ocean",
    12: "Ice Plains",
    13: "Ice Mountains",
    16: "Beach",
    17: "Desert Hills",
    21: "Jungle",
    22: "Jungle Hills",
    23: "JungleEdge",
    24: "Deep Ocean",
    26: "Cold Beach",
    27: "Birch Forest",
    29: "Roofed Forest",
    30: "Cold Taiga",
    32: "Mega Taiga",
    35: "Savanna",
    36: "Savanna Plateau",
    37: "Mesa",
    129: "Sunflower Plains",
    130: "Desert M",
    131: "Extreme Hills M",
    132: "Flower Forest",
    134: "Swampland M",
    140: "Ice Plains Spikes",
    149: "Jungle M",
    151: "JungleEdge M",
    160: "Mega Spruce Taiga",
    161: "Mega Spruce Taiga Hills"
};


var BIOME_MAPPINGS = [
    [0, 0, 255, 149],
    [0, 120, 255, 21],
    [70, 170, 250, 23],
    [255, 0, 0, 2],

    [255, 150, 150, 17],
    [245, 165, 0, 35],
    [255, 220, 100, 130],
    [255, 255, 0, 1],

    [200, 200, 0, 129],
    [150, 255, 150, 151],
    [100, 200, 100, 22],
    [50, 150, 50, 131],

    [200, 255, 80, 132],
    [100, 255, 80, 132],
    [50, 200, 0, 3],
    [255, 0, 255, 36],

    [200, 0, 200, 36],
    [150, 50, 150, 30],
    [150, 100, 150, 161],
    [170, 175, 255, 6],

    [90, 120, 220, 134],
    [75, 80, 180, 32],
    [50, 0, 135, 160],
    [0, 255, 255, 4],

    [55, 200, 255, 29],
    [0, 125, 125, 5],
    [0, 70, 95, 13],
    [178, 178, 178, 12],

    [102, 102, 102, 140],
    [200, 200, 200, 16],
    [220, 220, 220, 26],
    [255, 100, 0, 37],

    [0, 0, 0, 0],

    [255, 20, 0, 2],
    [255, 170, 150, 17],
    [255, 255, 100, 130]
];


function fail(message) {
    throw new Error(
        "XenoFactions configuration error: " + message
    );
}


/*
 * Require a complete, current preprocessing bundle before constructing a world.
 * Hashes cover original assets, processing configuration/code and derived PNGs.
 * Never silently fall back to the obsolete raw-raster terrain path.
 */
function verifyTerrainFingerprint(entry) {
    var input = requireFile(entry.path);
    var digest = java.security.MessageDigest.getInstance("SHA-256");
    var stream = new java.io.BufferedInputStream(
        new java.io.FileInputStream(input)
    );
    var buffer = new (Java.type("byte[]"))(131072);

    try {
        var count;
        while ((count = stream.read(buffer)) !== -1) {
            wp.checkForInterrupt();
            digest.update(buffer, 0, count);
        }
    } finally {
        stream.close();
    }

    var actual = String(new java.math.BigInteger(1, digest.digest()).toString(16));
    while (actual.length < 64) {
        actual = "0" + actual;
    }
    if (actual !== entry.sha256) {
        fail("stale or changed terrain input: " + entry.path
            + "; rerun tools/preprocess_xenoearth.py --profile=" + config.name);
    }
}


function processedAssetPath(terrain, name) {
    return absolutePath(terrain.assets[name].path);
}


function loadProcessedTerrain(config) {
    var manifestRelativePath = "generated/terrain/" + config.name + "/manifest.json";
    if (!file(manifestRelativePath).isFile()) {
        fail("prepare terrain first: python tools/preprocess_xenoearth.py --profile="
            + config.name);
    }
    var text = new java.lang.String(
        java.nio.file.Files.readAllBytes(file(manifestRelativePath).toPath()),
        java.nio.charset.StandardCharsets.UTF_8
    );
    var terrain = JSON.parse(String(text));
    if (terrain.formatVersion !== 1 || terrain.profile !== config.name
            || terrain.width !== config.width || terrain.height !== config.height
            || terrain.sourceScale !== config.sourceScale
            || terrain.sourceResize !== config.resize
            || terrain.effectiveScale !== config.effectiveScale
            || terrain.seaLevel !== seaLevel
            || !(terrain.minimumFloorY > minimumSurfaceY
                && terrain.minimumFloorY < seaLevel
                && terrain.maximumPeakY > seaLevel
                && terrain.maximumPeakY < maximumSurfaceY)
            || !(terrain.deepOceanFloorY > terrain.minimumFloorY
                && terrain.deepOceanFloorY < terrain.shallowOceanFloorY
                && terrain.shallowOceanFloorY < seaLevel)) {
        fail("invalid processed terrain contract: " + manifestRelativePath);
    }
    var expectedSources = requiredAssetNames(config).concat([
        "world_xenofactions_core.js", "terrain-processing.json",
        "tools/preprocess_xenoearth.py", "tools/validate_xenoearth_source.py"
    ]);
    if (!terrain.sources || terrain.sources.length !== expectedSources.length) {
        fail("incomplete terrain source fingerprints: " + manifestRelativePath);
    }
    for (var i = 0; i < expectedSources.length; i++) {
        if (terrain.sources[i].path !== expectedSources[i]) {
            fail("unexpected terrain source fingerprint: " + manifestRelativePath);
        }
        verifyTerrainFingerprint(terrain.sources[i]);
    }
    var names = ["height", "biome", "terrain", "water", "ice"];
    for (var j = 0; j < names.length; j++) {
        var name = names[j];
        var entry = terrain.assets[name];
        if (!entry || entry.path !== "generated/terrain/" + config.name
                + "/" + name + ".png") {
            fail("missing or misplaced processed asset: " + name);
        }
        verifyTerrainFingerprint(entry);
        imageSize(entry.path, config.width, config.height);
    }
    log("Verified processed terrain: " + manifestRelativePath);
    return terrain;
}


function resolveBuiltInLayer(name) {
    var layer =
        wp.getLayer()
            .withName(name)
            .go();

    log(
        "Resolved built-in layer: " + name
    );

    return layer;
}


function requireFile(relativePath) {
    var required =
        file(relativePath);


    if (!required.isFile()) {
        fail(
            "required input is missing: "
            + required.getAbsolutePath()
        );
    }


    return required;
}


function imageSize(
    relativePath,
    expectedWidth,
    expectedHeight
) {
    var imageFile =
        requireFile(relativePath);


    var stream =
        javax.imageio.ImageIO.createImageInputStream(
            imageFile
        );


    if (stream === null) {
        fail(
            "cannot read image header: "
            + relativePath
        );
    }


    var readers =
        javax.imageio.ImageIO.getImageReaders(
            stream
        );


    if (!readers.hasNext()) {
        stream.close();

        fail(
            "unsupported image: "
            + relativePath
        );
    }


    var reader =
        readers.next();


    reader.setInput(
        stream,
        true,
        true
    );


    var width =
        reader.getWidth(0);

    var height =
        reader.getHeight(0);


    reader.dispose();
    stream.close();


    if (
        width !== expectedWidth
        || height !== expectedHeight
    ) {
        fail(
            relativePath
            + " is "
            + width
            + " x "
            + height
            + "; expected "
            + expectedWidth
            + " x "
            + expectedHeight
        );
    }
}


function parseVersion(text) {
    var match =
        String(text).match(
            /^(\d+)\.(\d+)\.(\d+)/
        );


    if (!match) {
        fail(
            "cannot parse WorldPainter version: "
            + text
        );
    }


    return [
        Number(match[1]),
        Number(match[2]),
        Number(match[3])
    ];
}


function validateVersion(versionText) {
    var version =
        parseVersion(versionText);


    if (
        version[0] < 2
        || (
            version[0] === 2
            && version[1] < 27
        )
    ) {
        fail(
            "WorldPainter 2.27.0 is required; "
            + versionText
            + " is obsolete"
        );
    }


    if (
        !(
            version[0] === 2
            && version[1] === 27
            && version[2] === 0
        )
    ) {
        log(
            "WARNING: WorldPainter "
            + versionText
            + " is newer or otherwise untested; "
            + "2.27.0 is verified."
        );
    }
}


function requiredAssetNames(config) {
    var suffix =
        String(config.sourceScale)
        + "k.png";


    var assets = [
        "images/HeightMap" + suffix,
        "images/BiomeMap" + suffix,
        "images/WaterMap" + suffix,
        "images/Ice" + suffix
    ];


    if (config.sourceScale === 40) {
        return assets.concat([
            "images/globecover1_40k.png",
            "images/globecover2a_40k.png",
            "images/globecover2b_40k.png",
            "images/globecover3_40k.png",
            "images/globecover4_40k.png"
        ]);
    }


    return assets.concat([
        "images/globecover" + suffix
    ]);
}


function validateConfiguration(config) {
    if (!config) {
        fail(
            "unknown profile '"
            + selectedProfileName
            + "'; supported profiles: "
            + "smoke, preview, earth8000, "
            + "earth4000, earth2000, production"
        );
    }


    if (
        targetMinecraftVersion
        !== "1.7.10"
    ) {
        fail(
            "targetMinecraftVersion must be 1.7.10"
        );
    }


    if (
        config.width <= 0
        || config.height <= 0
        || config.width !== Math.floor(config.width)
        || config.height !== Math.floor(config.height)
    ) {
        fail(
            "output dimensions must be positive whole blocks"
        );
    }


    if (
        config.width % 16 !== 0
        || config.height % 16 !== 0
    ) {
        fail(
            "output dimensions must be aligned to 16-block chunks"
        );
    }


    var base =
        SOURCE_DIMENSIONS[
            config.sourceScale
        ];


    if (
        !base
        || (
            base[0]
            * config.resize
            / 100
        ) !== config.width
        || (
            base[1]
            * config.resize
            / 100
        ) !== config.height
    ) {
        fail(
            "profile dimensions do not match source scale and resize"
        );
    }


    if (
        Math.round(
            40000
            / config.sourceScale
            * 100
            / config.resize
        )
        !== config.effectiveScale
    ) {
        fail(
            "profile effective scale is inconsistent"
        );
    }


    if (
        minimumSurfaceY !== 1
        || maximumSurfaceY !== 254
        || seaLevel !== 62
    ) {
        fail(
            "surface limits must be 1..254 with sea level 62"
        );
    }


    if (
        vegetationDensity < 0
        || vegetationDensity > 15
        || maximumVegetationSlope < 0
        || maximumVegetationSlope > 90
    ) {
        fail(
            "vegetation settings are out of range"
        );
    }


    for (
        var i = 0;
        i < BIOME_MAPPINGS.length;
        i++
    ) {
        wp.checkForInterrupt();


        if (
            !ALLOWED_BIOME_IDS.hasOwnProperty(
                BIOME_MAPPINGS[i][3]
            )
        ) {
            fail(
                "unsupported biome ID "
                + BIOME_MAPPINGS[i][3]
            );
        }
    }


    var dimensions = base;

    var suffix =
        String(config.sourceScale)
        + "k.png";


    imageSize(
        "images/HeightMap" + suffix,
        dimensions[0],
        dimensions[1]
    );


    imageSize(
        "images/BiomeMap" + suffix,
        dimensions[0],
        dimensions[1]
    );


    imageSize(
        "images/WaterMap" + suffix,
        dimensions[0],
        dimensions[1]
    );


    imageSize(
        "images/Ice" + suffix,
        dimensions[0],
        dimensions[1]
    );


    if (config.sourceScale === 40) {
        imageSize(
            "images/globecover1_40k.png",
            21504,
            10752
        );

        imageSize(
            "images/globecover2a_40k.png",
            10752,
            10752
        );

        imageSize(
            "images/globecover2b_40k.png",
            10752,
            10752
        );

        imageSize(
            "images/globecover3_40k.png",
            21504,
            10752
        );

        imageSize(
            "images/globecover4_40k.png",
            21504,
            10752
        );
    } else {
        imageSize(
            "images/globecover" + suffix,
            dimensions[0],
            dimensions[1]
        );
    }


    if (generateRivers) {
        requireFile(
            "layer/Rivers.layer"
        );
    }
}


function buildApiObjects() {
    var objects = {};


    objects.mapFormat =
        wp.getMapFormat()
            .withId(
                LEGACY_ANVIL_MAP_FORMAT
            )
            .go();


    objects.biomesLayer =
        resolveBuiltInLayer(
            BUILTIN_LAYER_NAMES.biomes
        );


    objects.frostLayer =
        generateIce
            ? resolveBuiltInLayer(
                BUILTIN_LAYER_NAMES.frost
            )
            : null;


    objects.riverLayer =
        generateRivers
            ? wp.getLayer()
                .fromFile(
                    absolutePath(
                        "layer/Rivers.layer"
                    )
                )
                .go()
            : null;


    objects.vegetationLayers = {};


    if (generateVegetation) {
        objects.vegetationLayers = {
            deciduous:
                resolveBuiltInLayer(
                    BUILTIN_LAYER_NAMES.deciduous
                ),

            pine:
                resolveBuiltInLayer(
                    BUILTIN_LAYER_NAMES.pine
                ),

            jungle:
                resolveBuiltInLayer(
                    BUILTIN_LAYER_NAMES.jungle
                ),

            swamp:
                resolveBuiltInLayer(
                    BUILTIN_LAYER_NAMES.swamp
                )
        };
    }


    objects.shallowOceanFilter =
        wp.createFilter()
            .aboveLevel(
                DEEP_OCEAN_THRESHOLD
            )
            .belowLevel(
                SHALLOW_OCEAN_THRESHOLD
            )
            .onlyOnBiome(0)
            .go();


    objects.initialDeepOceanFilter =
        wp.createFilter()
            .aboveLevel(
                minimumSurfaceY
            )
            .belowLevel(
                DEEP_OCEAN_THRESHOLD
            )
            .onlyOnBiome(0)
            .go();


    objects.deepOceanFilter =
        wp.createFilter()
            .aboveLevel(
                minimumSurfaceY
            )
            .belowLevel(
                DEEP_OCEAN_THRESHOLD
            )
            .onlyOnBiome(24)
            .go();


    objects.inlandRiverFilter =
        wp.createFilter()
            .aboveLevel(
                RIVER_THRESHOLD
            )
            .belowLevel(
                maximumSurfaceY
            )
            .onlyOnLand()
            .go();


    objects.oceanRiverMaskOverlapFilter =
        wp.createFilter()
            .aboveLevel(
                minimumSurfaceY
            )
            .belowLevel(
                seaLevel
            )
            .go();


    if (
        generateVegetation
        && generateRivers
    ) {
        objects.vegetationFilter =
            wp.createFilter()
                .aboveLevel(
                    seaLevel
                )
                .belowLevel(
                    maximumSurfaceY
                )
                .belowDegrees(
                    maximumVegetationSlope
                )
                .onlyOnLand()
                .exceptOnLayer(
                    objects.riverLayer
                )
                .go();
    } else if (generateVegetation) {
        objects.vegetationFilter =
            wp.createFilter()
                .aboveLevel(
                    seaLevel
                )
                .belowLevel(
                    maximumSurfaceY
                )
                .belowDegrees(
                    maximumVegetationSlope
                )
                .onlyOnLand()
                .go();
    }


    return objects;
}


var config;
var scale;
var resize;

var SHALLOW_OCEAN_THRESHOLD;
var DEEP_OCEAN_THRESHOLD;
var RIVER_THRESHOLD;


function runXenoEarth(
    profileName,
    preflightMode
) {
    selectedProfileName =
        String(
            profileName
            || "smoke"
        );


    selectedProfileName =
        PROFILE_ALIASES[
            selectedProfileName
        ]
        || selectedProfileName;


    runPreflightOnly =
        Boolean(
            preflightMode
        );


    log(
        "[1/9] Preflight"
    );


    config =
        PROFILES[
            selectedProfileName
        ];


    validateConfiguration(
        config
    );


    scale =
        config.sourceScale;

    resize =
        config.resize;


    var minimumX =
        -config.width / 2;

    var maximumX =
        config.width / 2 - 1;

    var minimumZ =
        -config.height / 2;

    var maximumZ =
        config.height / 2 - 1;


    var horizontalScaleFactor =
        config.sourceScale
        * config.resize
        / 100.0;


    var spawnX =
        Math.round(
            110.5
            * horizontalScaleFactor
        );


    var spawnZ =
        -Math.round(
            11.4
            * horizontalScaleFactor
        );


    if (
        spawnX < minimumX
        || spawnX > maximumX
        || spawnZ < minimumZ
        || spawnZ > maximumZ
    ) {
        fail(
            "spawn point is outside generated profile bounds"
        );
    }


    var terrain = loadProcessedTerrain(config);

    SHALLOW_OCEAN_THRESHOLD = terrain.shallowOceanFloorY;
    DEEP_OCEAN_THRESHOLD = terrain.deepOceanFloorY;


    RIVER_THRESHOLD =
        seaLevel + 1;


    var wpVersion =
        String(
            wp.getVersion()
        );


    validateVersion(
        wpVersion
    );


    var api =
        buildApiObjects();


    log(
        "WorldPainter version: "
        + wpVersion
        + "\nSelected profile: "
        + config.name
        + "\nSource scale: "
        + scale
        + "k"
        + "\nResize percentage: "
        + resize
        + "%"
        + "\nEffective scale: 1:"
        + config.effectiveScale
        + "\nOutput dimensions: "
        + config.width
        + " x "
        + config.height
        + "\nExpected bounds: "
        + minimumX
        + ".."
        + maximumX
        + ", "
        + minimumZ
        + ".."
        + maximumZ
        + "\nSpawn coordinates: "
        + spawnX
        + ", "
        + spawnZ
        + "\nRequired source assets: "
        + requiredAssetNames(config).join(", ")
        + "\nMap-format ID: "
        + LEGACY_ANVIL_MAP_FORMAT
        + "\nBuild limits: "
        + LOWER_BUILD_LIMIT
        + ".."
        + (UPPER_BUILD_LIMIT - 1)
        + "\nWater level: "
        + seaLevel
        + "\nPrepared vertical range: "
        + terrain.minimumFloorY + ".." + terrain.maximumPeakY
        + "\nPrepared terrain directory: generated/terrain/" + config.name
    );


    if (runPreflightOnly) {
        log(
            "XenoEarth WorldPainter API preflight: PASS"
        );

        return;
    }


    var westShift =
        -Math.round(
            537.6
            * scale
            * (resize / 100)
        );


    var northShift =
        -Math.round(
            268.8
            * scale
            * (resize / 100)
        );


    /*
     * Terrain heightmap.
     */
    log(
        "[2/9] Importing heightmap"
    );


    var heightMap =
        wp.getHeightMap()
            .fromFile(
                processedAssetPath(terrain, "height")
            )
            .go();


    var world =
        wp.createWorld()
            .fromHeightMap(
                heightMap
            )
            .scale(
                applicationResize
            )
            .shift(
                westShift,
                northShift
            )
            .fromLevels(
                0,
                65535
            )
            .toLevels(
                minimumSurfaceY,
                maximumSurfaceY
            )
            .withMapFormat(
                api.mapFormat
            )
            .withLowerBuildLimit(
                LOWER_BUILD_LIMIT
            )
            .withUpperBuildLimit(
                UPPER_BUILD_LIMIT
            )
            .withWaterLevel(
                seaLevel
            )
            .go();


    heightMap = null;


    world.setSpawnPoint(
        new java.awt.Point(
            spawnX,
            spawnZ
        )
    );


    /*
     * Biomes.
     */
    log(
        "[3/9] Applying biomes"
    );


    var biomeMap =
        wp.getHeightMap()
            .fromFile(
                processedAssetPath(terrain, "biome")
            )
            .go();


    var biomeApplication =
        wp.applyHeightMap(
            biomeMap
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToLayer(
            api.biomesLayer
        );


    for (
        var biomeIndex = 0;
        biomeIndex < BIOME_MAPPINGS.length;
        biomeIndex++
    ) {
        wp.checkForInterrupt();


        var biomeMapping =
            BIOME_MAPPINGS[
                biomeIndex
            ];


        biomeApplication =
            biomeApplication
                .fromColour(
                    biomeMapping[0],
                    biomeMapping[1],
                    biomeMapping[2]
                )
                .toLevel(
                    biomeMapping[3]
                );
    }


    biomeApplication.go();


    /*
     * Surface terrain.
     */
    log(
        "[4/9] Applying surface terrain"
    );


    var surfaceMap = wp.getHeightMap()
        .fromFile(processedAssetPath(terrain, "terrain"))
        .go();
    var surfaceApplication = wp.applyHeightMap(surfaceMap)
        .toWorld(world)
        .scale(applicationResize)
        .shift(westShift, northShift)
        .applyToTerrain();
    var surfaceTerrainIds = [1, 5, 6, 40];
    for (var surfaceIndex = 0; surfaceIndex < surfaceTerrainIds.length; surfaceIndex++) {
        wp.checkForInterrupt();
        var surfaceId = surfaceTerrainIds[surfaceIndex];
        surfaceApplication = surfaceApplication.fromLevel(surfaceId).toTerrain(surfaceId);
    }
    surfaceApplication.go();
    surfaceMap = null;


    /*
     * Oceans.
     */
    log(
        "[5/9] Applying oceans"
    );


    wp.applyHeightMap(
        biomeMap
    )
    .toWorld(
        world
    )
    .scale(
        applicationResize
    )
    .shift(
        westShift,
        northShift
    )
    .applyToLayer(
        api.biomesLayer
    )
    .withFilter(
        api.initialDeepOceanFilter
    )
    .fromColour(
        0,
        0,
        0
    )
    .toLevel(
        24
    )
    .go();


    wp.applyHeightMap(
        biomeMap
    )
    .toWorld(
        world
    )
    .scale(
        applicationResize
    )
    .shift(
        westShift,
        northShift
    )
    .applyToTerrain()
    .withFilter(
        api.shallowOceanFilter
    )
    .fromColour(
        0,
        0,
        0
    )
    .toTerrain(
        5
    )
    .go();


    /*
     * Rivers.
     */
    log(
        "[6/9] Applying rivers"
    );


    if (generateRivers) {
        var riverMask =
            wp.getHeightMap()
                .fromFile(
                    processedAssetPath(terrain, "water")
                )
                .go();


        wp.applyHeightMap(
            riverMask
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToLayer(
            api.riverLayer
        )
        .withFilter(
            api.inlandRiverFilter
        )
        .fromLevel(
            0
        )
        .toLevel(
            0
        )
        .fromLevels(
            1,
            255
        )
        .toLevel(
            1
        )
        .go();


        wp.applyHeightMap(
            riverMask
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToLayer(
            api.biomesLayer
        )
        .withFilter(
            api.inlandRiverFilter
        )
        .fromLevels(
            1,
            255
        )
        .toLevel(
            7
        )
        .go();


        wp.applyHeightMap(
            riverMask
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToLayer(
            api.riverLayer
        )
        .withFilter(
            api.oceanRiverMaskOverlapFilter
        )
        .fromLevels(
            1,
            255
        )
        .toLevel(
            0
        )
        .go();


        wp.applyHeightMap(
            riverMask
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToTerrain()
        .withFilter(
            api.deepOceanFilter
        )
        .fromLevels(
            1,
            255
        )
        .toTerrain(
            5
        )
        .go();


        wp.applyHeightMap(
            riverMask
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToTerrain()
        .withFilter(
            api.shallowOceanFilter
        )
        .fromLevels(
            1,
            255
        )
        .toTerrain(
            5
        )
        .go();


        riverMask = null;
    }


    /*
     * Ice.
     */
    log(
        "[7/9] Applying ice"
    );


    if (generateIce) {
        var iceMask =
            wp.getHeightMap()
                .fromFile(
                    processedAssetPath(terrain, "ice")
                )
                .go();


        wp.applyHeightMap(
            iceMask
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToLayer(
            api.biomesLayer
        )
        .withFilter(
            api.oceanRiverMaskOverlapFilter
        )
        .fromLevels(
            1,
            255
        )
        .toLevel(
            10
        )
        .go();


        wp.applyHeightMap(
            iceMask
        )
        .toWorld(
            world
        )
        .scale(
            applicationResize
        )
        .shift(
            westShift,
            northShift
        )
        .applyToLayer(
            api.frostLayer
        )
        .fromLevel(
            0
        )
        .toLevel(
            0
        )
        .fromLevels(
            1,
            255
        )
        .toLevel(
            1
        )
        .go();


        iceMask = null;
    }


    /*
     * Vegetation.
     */
    log(
        "[8/9] Applying vegetation"
    );


    if (generateVegetation) {
        var vegetationRules = [
            [
                "deciduous",
                [
                    [0, 255, 255],
                    [200, 255, 80],
                    [100, 255, 80],
                    [255, 255, 0],
                    [200, 200, 0],
                    [55, 200, 255],
                    [170, 175, 255]
                ]
            ],

            [
                "pine",
                [
                    [0, 125, 125],
                    [75, 80, 180],
                    [50, 0, 135],
                    [150, 50, 150],
                    [150, 100, 150]
                ]
            ],

            [
                "jungle",
                [
                    [0, 0, 255],
                    [0, 120, 255],
                    [70, 170, 250],
                    [150, 255, 150],
                    [100, 200, 100]
                ]
            ],

            [
                "deciduous",
                [
                    [245, 165, 0],
                    [255, 0, 255]
                ]
            ],

            [
                "swamp",
                [
                    [90, 120, 220]
                ]
            ]
        ];


        for (
            var vegetationRuleIndex = 0;
            vegetationRuleIndex < vegetationRules.length;
            vegetationRuleIndex++
        ) {
            wp.checkForInterrupt();


            var vegetationRule =
                vegetationRules[
                    vegetationRuleIndex
                ];


            var vegetationLayer =
                api.vegetationLayers[
                    vegetationRule[0]
                ];


            if (
                vegetationLayer === null
                || typeof vegetationLayer
                    === "undefined"
            ) {
                fail(
                    "unknown vegetation layer key: "
                    + vegetationRule[0]
                );
            }


            var vegetationApplication =
                wp.applyHeightMap(
                    biomeMap
                )
                .toWorld(
                    world
                )
                .scale(
                    applicationResize
                )
                .shift(
                    westShift,
                    northShift
                )
                .applyToLayer(
                    vegetationLayer
                )
                .withFilter(
                    api.vegetationFilter
                );


            for (
                var colourIndex = 0;
                colourIndex < vegetationRule[1].length;
                colourIndex++
            ) {
                wp.checkForInterrupt();


                var colour =
                    vegetationRule[1][
                        colourIndex
                    ];


                vegetationApplication =
                    vegetationApplication
                        .fromColour(
                            colour[0],
                            colour[1],
                            colour[2]
                        )
                        .toLevel(
                            vegetationDensity
                        );
            }


            vegetationApplication.go();
        }
    }


    biomeMap = null;


    /*
     * Save project and profile.
     */
    log(
        "[9/9] Saving project"
    );


    var generatedDirectory =
        file(
            "generated"
        );


    if (
        !generatedDirectory.isDirectory()
        && !generatedDirectory.mkdirs()
    ) {
        fail(
            "cannot create output directory: "
            + generatedDirectory.getAbsolutePath()
        );
    }


    var outputName =
        "earth_1-"
        + config.effectiveScale
        + "_xenofactions_1.7.10_"
        + config.name
        + ".world";


    var manifest = {
        formatVersion: 1,

        profile:
            config.name,

        targetMinecraftVersion:
            targetMinecraftVersion,

        sourceScale:
            scale,

        resize:
            resize,

        effectiveScale:
            config.effectiveScale,

        scale:
            config.effectiveScale,

        width:
            config.width,

        height:
            config.height,

        minimumX:
            minimumX,

        maximumX:
            maximumX,

        minimumZ:
            minimumZ,

        maximumZ:
            maximumZ,

        minimumSurfaceY:
            minimumSurfaceY,

        maximumSurfaceY:
            maximumSurfaceY,

        seaLevel:
            seaLevel,

        terrainProcessing: {
            manifest: "generated/terrain/" + config.name + "/manifest.json",
            diagnostics: "generated/terrain/" + config.name + "/diagnostics.json",
            minimumFloorY: terrain.minimumFloorY,
            maximumPeakY: terrain.maximumPeakY,
            deepOceanFloorY: terrain.deepOceanFloorY
        },

        projection:
            "equirectangular",

        populationMode:
            "pregenerated",

        caves:
            false,

        ores:
            false,

        lava:
            false,

        structures:
            false,

        vegetation:
            true
    };


    var profileWriter =
        new java.io.FileWriter(
            file(
                "generated/xenoearth-profile-"
                + config.name
                + ".json"
            )
        );


    profileWriter.write(
        JSON.stringify(
            manifest,
            null,
            2
        )
        + "\n"
    );


    profileWriter.close();


    log(
        "*** REQUIRED MANUAL EXPORT CHECKLIST: "
        + "disable Populate, Resources, Caves, Caverns, Chasms, Ravines, "
        + "Structures, lava, and all unlisted generators; "
        + "keep bottomless world OFF. ***"
    );


    wp.saveWorld(
        world
    )
    .toFile(
        absolutePath(
            "generated/"
            + outputName
        )
    )
    .go();


    log(
        "Generation complete"
    );
}
