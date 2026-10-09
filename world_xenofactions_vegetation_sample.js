// script.name=XenoFactions vegetation sample
// script.param.builtinReference.type=boolean
// script.param.builtinReference.default=false
// Small owner-reproducible export using the production vegetation implementation.
load(new java.io.File(scriptDir, "world_xenofactions_core.js").toURI().toURL());
var sampleConfiguration = XenoVegetation.configuration();
var sampleLayers = XenoVegetation.build(sampleConfiguration);
// Optional diagnostic export of the previous built-in forest path at strength 3.
var sampleReference = typeof builtinReference !== "undefined" ? Boolean(builtinReference)
    : (typeof params !== "undefined" && String(params.get("builtinReference")) === "true");
var samplePlatform = wp.getMapFormat().withId(LEGACY_ANVIL_MAP_FORMAT).go();
var sampleHeight = wp.getHeightMap().fromFile(absolutePath("generated/vegetation-sample/height.png")).go();
var sampleWorld = XenoVegetation.importWorld(sampleHeight, samplePlatform, 0, 0, sampleConfiguration);
sampleWorld.setName(sampleReference ? "XenoEarthVegetationReference" : "XenoEarthVegetationSample");
XenoVegetation.configureExport(sampleWorld);
var sampleBiome = wp.getHeightMap().fromFile(absolutePath("generated/vegetation-sample/biome.png")).go();
var sampleBiomesLayer = resolveBuiltInLayer(BUILTIN_LAYER_NAMES.biomes);
var sampleBiomeMapping = wp.applyHeightMap(sampleBiome).toWorld(sampleWorld).applyToLayer(sampleBiomesLayer);
sampleConfiguration.profiles.forEach(function (profile) {
    sampleBiomeMapping = sampleBiomeMapping.fromLevel(profile.biomes[0]).toLevel(profile.biomes[0]);
});
sampleBiomeMapping.go();
var sampleTerrain = wp.getHeightMap().fromFile(absolutePath("generated/vegetation-sample/terrain.png")).go();
wp.applyHeightMap(sampleTerrain).toWorld(sampleWorld).applyToTerrain()
    .fromLevel(1).toTerrain(1).fromLevel(5).toTerrain(5).go();
if (sampleReference) {
    sampleConfiguration.profiles.forEach(function (profile, index) {
        if (!Object.keys(profile.trees).length) { return; }
        var name = profile.name === "taiga" || profile.name === "alpine" ? "Pine"
            : (profile.name === "jungle" ? "Jungle" : "Deciduous");
        var layer = wp.getLayer().withName(name).go();
        wp.applyHeightMap(sampleBiome).toWorld(sampleWorld).applyToLayer(layer)
            .fromLevel(profile.biomes[0]).toLevel(3).go();
    });
    sampleLayers.trees = [];
}
XenoVegetation.apply(sampleWorld, sampleConfiguration, sampleLayers,
    absolutePath("generated/vegetation-sample/trees.png"),
    absolutePath("generated/vegetation-sample/plants.png"), 0, 0);
wp.saveWorld(sampleWorld).toFile(absolutePath("generated/vegetation-sample/"
    + (sampleReference ? "reference.world" : "vegetation.world"))).go();
var sampleExportDirectory = file("generated/vegetation-sample/export");
sampleExportDirectory.mkdirs();
wp.exportWorld(sampleWorld).toDirectory(sampleExportDirectory.getAbsolutePath()).go();
log("Vegetation sample exported; inspect with tools/export-validation/vegetation_scan.py");
