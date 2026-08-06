// script.name=XenoFactions Earth Map
// script.description=Generate a Minecraft 1.7.10 Earth WorldPainter project.
// script.param.profile.type=string
// script.param.profile.default=smoke
// script.param.profile.displayName=Profile
// script.param.preflightOnly.type=boolean
// script.param.preflightOnly.default=false
// script.param.preflightOnly.displayName=API preflight only
/*
 * XenoFactions Earth pipeline for WorldPainter 2.27.0.
 * Minecraft 1.7.10 only. world.js remains the unmodified upstream reference.
 */
var sourceRoot = new java.io.File(scriptDir);
function file(relativePath) { return new java.io.File(sourceRoot, relativePath); }
function absolutePath(relativePath) { return file(relativePath).getAbsolutePath(); }

var targetMinecraftVersion = "1.7.10";
var PROFILES = {
    smoke: {name:"smoke", sourceScale:10, resize:25, effectiveScale:16000, width:2688, height:1344},
    preview: {name:"preview", sourceScale:10, resize:100, effectiveScale:4000, width:10752, height:5376},
    production: {name:"production", sourceScale:40, resize:100, effectiveScale:1000, width:43008, height:21504}
};
var selectedProfileName = (typeof profile === "undefined" || profile === null || String(profile).length === 0) ? "smoke" : String(profile);
var runPreflightOnly = (typeof preflightOnly === "undefined") ? false : Boolean(preflightOnly);
var groundMaterialMode = "globecover";
var minimumSurfaceY = 1, maximumSurfaceY = 254, seaLevel = 62;
var generateVegetation = true, generateRivers = true, generateIce = true;
var generateCaves=false, generateCaverns=false, generateChasms=false, generateRavines=false;
var generateOres=false, generateResources=false, generateLava=false, generateStructures=false;
var generateCities=false, generateStreets=false, generateBorders=false, generatePortals=false;
var allowMinecraftPopulation=false;
var vegetationSeed=68317010, vegetationDensity=3, maximumVegetationSlope=35;
var LEGACY_ANVIL_MAP_FORMAT="org.pepsoft.anvil", LOWER_BUILD_LIMIT=0, UPPER_BUILD_LIMIT=256;
var BUILTIN_LAYER_NAMES = {
    biomes: "Biomes", frost: "Frost", deciduous: "Deciduous",
    pine: "Pine", jungle: "Jungle", swamp: "Swamp"
};
var CUSTOM_TERRAIN_COMPATIBILITY = {};
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


function fail(message) { throw new Error("XenoFactions configuration error: " + message); }
function resolveBuiltInLayer(name) {
    var layer=wp.getLayer().withName(name).go();
    java.lang.System.out.println("Resolved built-in layer: "+name);
    return layer;
}
function requireFile(relativePath) { var f=file(relativePath); if (!f.isFile()) fail("required input is missing: "+f.getAbsolutePath()); return f; }
function imageSize(relativePath, expectedWidth, expectedHeight) {
    var f=requireFile(relativePath), stream=javax.imageio.ImageIO.createImageInputStream(f);
    if (stream === null) fail("cannot read image header: "+relativePath);
    var readers=javax.imageio.ImageIO.getImageReaders(stream);
    if (!readers.hasNext()) { stream.close(); fail("unsupported image: "+relativePath); }
    var reader=readers.next(); reader.setInput(stream,true,true);
    var width=reader.getWidth(0), height=reader.getHeight(0); reader.dispose(); stream.close();
    if (width !== expectedWidth || height !== expectedHeight) fail(relativePath+" is "+width+" x "+height+"; expected "+expectedWidth+" x "+expectedHeight);
}
function parseVersion(text) {
    var match=String(text).match(/^(\d+)\.(\d+)\.(\d+)/);
    if (!match) fail("cannot parse WorldPainter version: "+text);
    return [Number(match[1]),Number(match[2]),Number(match[3])];
}
function validateVersion(versionText) {
    var v=parseVersion(versionText);
    if (v[0] < 2 || (v[0] === 2 && v[1] < 27)) fail("WorldPainter 2.27.0 is required; "+versionText+" is obsolete");
    if (!(v[0] === 2 && v[1] === 27 && v[2] === 0)) java.lang.System.out.println("WARNING: WorldPainter "+versionText+" is newer or otherwise untested; 2.27.0 is verified.");
}
function validateConfiguration(config) {
    if (!config) fail("unknown profile '"+selectedProfileName+"'; supported profiles: smoke, preview, production");
    if (targetMinecraftVersion !== "1.7.10") fail("targetMinecraftVersion must be 1.7.10");
    if (config.width <= 0 || config.height <= 0 || config.width !== Math.floor(config.width) || config.height !== Math.floor(config.height)) fail("output dimensions must be positive whole blocks");
    if (config.width % 16 !== 0 || config.height % 16 !== 0) fail("output dimensions must be aligned to 16-block chunks");
    var base={10:[10752,5376],40:[43008,21504]}[config.sourceScale];
    if (!base || base[0]*config.resize/100 !== config.width || base[1]*config.resize/100 !== config.height) fail("profile dimensions do not match source scale and resize");
    if (Math.round(40000/config.sourceScale*100/config.resize) !== config.effectiveScale) fail("profile effective scale is inconsistent");
    if (minimumSurfaceY !== 1 || maximumSurfaceY !== 254 || seaLevel !== 62) fail("surface limits must be 1..254 with sea level 62");
    if (vegetationDensity < 0 || vegetationDensity > 15 || maximumVegetationSlope < 0 || maximumVegetationSlope > 90) fail("vegetation settings are out of range");
    for (var i=0;i<BIOME_MAPPINGS.length;i++) { wp.checkForInterrupt(); if (!ALLOWED_BIOME_IDS.hasOwnProperty(BIOME_MAPPINGS[i][3])) fail("unsupported biome ID "+BIOME_MAPPINGS[i][3]); }
    var dims=base, suffix=String(config.sourceScale)+"k.png";
    imageSize("images/HeightMap"+suffix,dims[0],dims[1]); imageSize("images/BiomeMap"+suffix,dims[0],dims[1]);
    imageSize("images/WaterMap"+suffix,dims[0],dims[1]); imageSize("images/Ice"+suffix,dims[0],dims[1]);
    if (config.sourceScale === 40) {
        imageSize("images/globecover1_40k.png",21504,10752); imageSize("images/globecover2a_40k.png",10752,10752);
        imageSize("images/globecover2b_40k.png",10752,10752); imageSize("images/globecover3_40k.png",21504,10752); imageSize("images/globecover4_40k.png",21504,10752);
    } else imageSize("images/globecover"+suffix,dims[0],dims[1]);
    if (generateRivers) requireFile("layer/Rivers.layer");
}
function buildApiObjects() {
    var objects={};
    objects.mapFormat=wp.getMapFormat().withId(LEGACY_ANVIL_MAP_FORMAT).go();
    objects.biomesLayer=resolveBuiltInLayer(BUILTIN_LAYER_NAMES.biomes);
    objects.frostLayer=generateIce ? resolveBuiltInLayer(BUILTIN_LAYER_NAMES.frost) : null;
    objects.riverLayer=generateRivers ? wp.getLayer().fromFile(absolutePath("layer/Rivers.layer")).go() : null;
    objects.vegetationLayers={};
    if (generateVegetation) {
        objects.vegetationLayers={
            deciduous:resolveBuiltInLayer(BUILTIN_LAYER_NAMES.deciduous),
            pine:resolveBuiltInLayer(BUILTIN_LAYER_NAMES.pine),
            jungle:resolveBuiltInLayer(BUILTIN_LAYER_NAMES.jungle),
            swamp:resolveBuiltInLayer(BUILTIN_LAYER_NAMES.swamp)
        };
    }
    objects.shallowOceanFilter=wp.createFilter().aboveLevel(DEEP_OCEAN_THRESHOLD).belowLevel(SHALLOW_OCEAN_THRESHOLD).onlyOnBiome(0).go();
    objects.initialDeepOceanFilter=wp.createFilter().aboveLevel(minimumSurfaceY).belowLevel(DEEP_OCEAN_THRESHOLD).onlyOnBiome(0).go();
    objects.deepOceanFilter=wp.createFilter().aboveLevel(minimumSurfaceY).belowLevel(DEEP_OCEAN_THRESHOLD).onlyOnBiome(24).go();
    objects.inlandRiverFilter=wp.createFilter().aboveLevel(RIVER_THRESHOLD).belowLevel(maximumSurfaceY).onlyOnLand().go();
    objects.oceanRiverMaskOverlapFilter=wp.createFilter().aboveLevel(minimumSurfaceY).belowLevel(seaLevel).go();
    if (generateVegetation && generateRivers) objects.vegetationFilter=wp.createFilter().aboveLevel(seaLevel).belowLevel(maximumSurfaceY).belowDegrees(maximumVegetationSlope).onlyOnLand().exceptOnLayer(objects.riverLayer).go();
    else if (generateVegetation) objects.vegetationFilter=wp.createFilter().aboveLevel(seaLevel).belowLevel(maximumSurfaceY).belowDegrees(maximumVegetationSlope).onlyOnLand().go();
    return objects;
}
var config, scale, resize, SHALLOW_OCEAN_THRESHOLD, DEEP_OCEAN_THRESHOLD, RIVER_THRESHOLD;
function main() {
    java.lang.System.out.println("[1/9] Preflight");
    config=PROFILES[selectedProfileName]; validateConfiguration(config); scale=config.sourceScale; resize=config.resize;
    SHALLOW_OCEAN_THRESHOLD=seaLevel-Math.round(scale*0.30); DEEP_OCEAN_THRESHOLD=seaLevel-Math.round(scale*0.65); RIVER_THRESHOLD=seaLevel+1;
    var wpVersion=String(wp.getVersion()); validateVersion(wpVersion); var api=buildApiObjects();
    java.lang.System.out.println("WorldPainter version: "+wpVersion+"\nProfile: "+config.name+"\nSource scale: "+scale+"\nResize: "+resize+"%\nEffective scale: 1:"+config.effectiveScale+"\nOutput dimensions: "+config.width+" x "+config.height+"\nMap-format ID: "+LEGACY_ANVIL_MAP_FORMAT+"\nBuild limits: "+LOWER_BUILD_LIMIT+".."+(UPPER_BUILD_LIMIT-1)+"\nWater level: "+seaLevel);
    if (runPreflightOnly) { java.lang.System.out.println("XenoEarth WorldPainter API preflight: PASS"); return; }
    var suffix=String(scale)+"k.png", westShift=-Math.round(537.6*scale*(resize/100)), northShift=-Math.round(268.8*scale*(resize/100));
    java.lang.System.out.println("[2/9] Importing heightmap");
    var heightMap=wp.getHeightMap().fromFile(absolutePath("images/HeightMap"+suffix)).go();
    var world=wp.createWorld().fromHeightMap(heightMap).scale(resize).shift(westShift,northShift).fromLevels(0,65535).toLevels(minimumSurfaceY,maximumSurfaceY).withMapFormat(api.mapFormat).withLowerBuildLimit(LOWER_BUILD_LIMIT).withUpperBuildLimit(UPPER_BUILD_LIMIT).withWaterLevel(seaLevel).go();
    heightMap=null; world.setSpawnPoint(new java.awt.Point(Math.round(110.5*scale),-Math.round(11.4*scale)));
    java.lang.System.out.println("[3/9] Applying biomes");
    var biomeMap=wp.getHeightMap().fromFile(absolutePath("images/BiomeMap"+suffix)).go();
    var biomeApplication=wp.applyHeightMap(biomeMap).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(api.biomesLayer);
    for (var b=0;b<BIOME_MAPPINGS.length;b++) { wp.checkForInterrupt(); var m=BIOME_MAPPINGS[b]; biomeApplication=biomeApplication.fromColour(m[0],m[1],m[2]).toLevel(m[3]); } biomeApplication.go();
    java.lang.System.out.println("[4/9] Applying surface terrain");
    function applyGlobCover(map,x,z) { wp.applyHeightMap(map).toWorld(world).scale(resize).shift(x,z).applyToTerrain().fromColour(0,255,0).toTerrain(1).fromColour(255,255,0).toTerrain(5).fromColour(255,255,255).toTerrain(40).fromColour(127,0,0).toTerrain(1).fromColour(255,0,0).toTerrain(6).fromColour(150,150,150).toTerrain(1).fromColour(255,127,0).toTerrain(5).fromColour(0,127,127).toTerrain(1).fromColour(0,148,255).toTerrain(5).go(); }
    if (scale===40) { var parts=[["globecover1_40k.png",westShift,northShift],["globecover2a_40k.png",0,northShift],["globecover2b_40k.png",-westShift/2,northShift],["globecover3_40k.png",westShift,0],["globecover4_40k.png",0,0]]; for(var gp=0;gp<parts.length;gp++){wp.checkForInterrupt();applyGlobCover(wp.getHeightMap().fromFile(absolutePath("images/"+parts[gp][0])).go(),parts[gp][1],parts[gp][2]);} } else applyGlobCover(wp.getHeightMap().fromFile(absolutePath("images/globecover"+suffix)).go(),westShift,northShift);
    java.lang.System.out.println("[5/9] Applying oceans");
    wp.applyHeightMap(biomeMap).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(api.biomesLayer).withFilter(api.initialDeepOceanFilter).fromColour(0,0,0).toLevel(24).go();
    wp.applyHeightMap(biomeMap).toWorld(world).scale(resize).shift(westShift,northShift).applyToTerrain().withFilter(api.shallowOceanFilter).fromColour(0,0,0).toTerrain(5).go();
    java.lang.System.out.println("[6/9] Applying rivers");
    if(generateRivers){var riverMask=wp.getHeightMap().fromFile(absolutePath("images/WaterMap"+suffix)).go(); wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(api.riverLayer).withFilter(api.inlandRiverFilter).fromLevel(0).toLevel(0).fromLevels(1,255).toLevel(1).go(); wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(api.biomesLayer).withFilter(api.inlandRiverFilter).fromLevels(1,255).toLevel(7).go(); wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(api.riverLayer).withFilter(api.oceanRiverMaskOverlapFilter).fromLevels(1,255).toLevel(0).go(); wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift).applyToTerrain().withFilter(api.deepOceanFilter).fromLevels(1,255).toTerrain(5).go(); wp.applyHeightMap(riverMask).toWorld(world).scale(resize).shift(westShift,northShift).applyToTerrain().withFilter(api.shallowOceanFilter).fromLevels(1,255).toTerrain(5).go();}
    java.lang.System.out.println("[7/9] Applying ice");
    if(generateIce){var iceMask=wp.getHeightMap().fromFile(absolutePath("images/Ice"+suffix)).go(); wp.applyHeightMap(iceMask).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(api.biomesLayer).fromLevels(1,255).toLevel(10).go(); wp.applyHeightMap(iceMask).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(api.frostLayer).fromLevel(0).toLevel(0).fromLevels(1,255).toLevel(1).go();}
    java.lang.System.out.println("[8/9] Applying vegetation");
    if(generateVegetation){var rules=[["deciduous",[[0,255,255],[200,255,80],[100,255,80],[255,255,0],[200,200,0],[55,200,255],[170,175,255]]],["pine",[[0,125,125],[75,80,180],[50,0,135],[150,50,150],[150,100,150]]],["jungle",[[0,0,255],[0,120,255],[70,170,250],[150,255,150],[100,200,100]]],["deciduous",[[245,165,0],[255,0,255]]],["swamp",[[90,120,220]]]];for(var vr=0;vr<rules.length;vr++){wp.checkForInterrupt();var vegetationLayer=api.vegetationLayers[rules[vr][0]];if(vegetationLayer === null || typeof vegetationLayer === "undefined") fail("unknown vegetation layer key: "+rules[vr][0]);var veg=wp.applyHeightMap(biomeMap).toWorld(world).scale(resize).shift(westShift,northShift).applyToLayer(vegetationLayer).withFilter(api.vegetationFilter);for(var c=0;c<rules[vr][1].length;c++){wp.checkForInterrupt();var colour=rules[vr][1][c];veg=veg.fromColour(colour[0],colour[1],colour[2]).toLevel(vegetationDensity);}veg.go();}}
    java.lang.System.out.println("[9/9] Saving project");
    var generated=file("generated"); if(!generated.isDirectory() && !generated.mkdirs()) fail("cannot create output directory: "+generated.getAbsolutePath());
    var outputName="earth_1-"+config.effectiveScale+"_xenofactions_1.7.10_"+config.name+".world";
    var manifest={formatVersion:1,profile:config.name,targetMinecraftVersion:targetMinecraftVersion,sourceScale:scale,resize:resize,effectiveScale:config.effectiveScale,scale:config.effectiveScale,width:config.width,height:config.height,minimumX:-config.width/2,maximumX:config.width/2-1,minimumZ:-config.height/2,maximumZ:config.height/2-1,minimumSurfaceY:minimumSurfaceY,maximumSurfaceY:maximumSurfaceY,seaLevel:seaLevel,projection:"equirectangular",populationMode:"pregenerated",caves:false,ores:false,lava:false,structures:false,vegetation:true};
    var writer=new java.io.FileWriter(file("generated/xenoearth-profile-"+config.name+".json")); writer.write(JSON.stringify(manifest,null,2)+"\n"); writer.close();
    java.lang.System.out.println("*** REQUIRED MANUAL EXPORT CHECKLIST: disable Populate, Resources, Caves, Caverns, Chasms, Ravines, Structures, lava, and all unlisted generators; keep bottomless world OFF. ***");
    wp.saveWorld(world).toFile(absolutePath("generated/"+outputName)).go();
}
main();
