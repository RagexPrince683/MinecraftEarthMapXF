/* WorldPainter 2.27 native export layers. No population or live-world mutation. */
var XenoVegetation = (function () {
    var Dimension = Java.type("org.pepsoft.worldpainter.Dimension");
    var Terrain = Java.type("org.pepsoft.worldpainter.Terrain");
    var Bo2Object = Java.type("org.pepsoft.worldpainter.layers.bo2.Bo2Object");
    var Bo2Layer = Java.type("org.pepsoft.worldpainter.layers.Bo2Layer");
    var WPObject = Java.type("org.pepsoft.worldpainter.objects.WPObject");
    var PlantLayer = Java.type("org.pepsoft.worldpainter.layers.plants.PlantLayer");
    var PlantSettings = Java.type("org.pepsoft.worldpainter.layers.plants.PlantLayer$PlantSettings");
    var Plants = Java.type("org.pepsoft.worldpainter.layers.plants.Plants");
    var species = {
        oak: [17, 18, 0], birch: [17, 18, 2], spruce: [17, 18, 1],
        jungle: [17, 18, 3], acacia: [162, 161, 0], darkOak: [162, 161, 1],
        swamp: [17, 18, 0], shrub: [17, 18, 3]
    };
    var neighbours = [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];

    function readConfiguration() {
        var text = new java.lang.String(java.nio.file.Files.readAllBytes(
            requireFile("vegetation.json").toPath()), java.nio.charset.StandardCharsets.UTF_8);
        var cfg = JSON.parse(String(text));
        if (cfg.formatVersion !== 1 || typeof cfg.enabled !== "boolean"
                || cfg.seed !== Math.floor(cfg.seed) || Math.abs(cfg.seed) > 2147483648) {
            fail("invalid vegetation configuration; rerun preprocessing");
        }
        return cfg;
    }

    function key(x, y, z) { return x + "," + y + "," + z; }

    function tree(kind, height) {
        var s = species[kind];
        if (!s) { fail("unknown vegetation tree: " + kind); }
        var blocks = {};
        function logAt(x, y, z, axis) {
            blocks[key(x,y,z)] = [s[0], s[2] | (axis || 0)];
        }
        function leafAt(x, y, z) {
            var k = key(x,y,z);
            if (!blocks[k]) {
                // 1.7.10: species in bits 0..1; persistent bit 4 OFF;
                // check-decay bit 8 ON, so intact geometry is checked by the game.
                blocks[k] = [s[1], s[2] | 8];
            }
        }
        var wide = kind === "darkOak" ? 2 : 1;
        for (var z = 0; z < height; z++) {
            for (var x = 0; x < wide; x++) {
                for (var y = 0; y < wide; y++) { logAt(x,y,z,0); }
            }
        }
        if (kind === "acacia") {
            logAt(1,0,height-1,4);
            logAt(2,0,height-1,4);
        }
        if (kind === "spruce") {
            for (var level = 2; level <= height + 2; level++) {
                var radius = level > height ? 0 : (level % 2 ? 1 : 2);
                for (var dx = -radius; dx <= radius; dx++) {
                    for (var dy = -radius; dy <= radius; dy++) {
                        if (Math.abs(dx) + Math.abs(dy) <= radius) { leafAt(dx,dy,level); }
                    }
                }
            }
        } else {
            var centre = kind === "acacia" ? 1 : 0;
            for (var dz = -2; dz <= 1; dz++) {
                if (height + dz < 0) { continue; }
                var r = kind === "shrub" ? 1 : (dz <= 0 ? 2 : 1);
                if (kind === "acacia" && dz <= 0) { r = 3; }
                for (var a = -r; a <= r + wide - 1; a++) {
                    for (var b = -r; b <= r + wide - 1; b++) {
                        var distance = Math.max(0, -a, a-wide+1) + Math.max(0, -b, b-wide+1);
                        if (distance <= r) { leafAt(a+centre,b,height+dz); }
                    }
                }
            }
        }
        // The legacy game floods through six face neighbours for FOUR steps.
        // Check the actual object, not straight-line distance or modern distance=7.
        var queue = [], supported = {}, leaves = 0;
        Object.keys(blocks).forEach(function (k) {
            var block = blocks[k];
            if (block[0] === 17 || block[0] === 162) {
                queue.push([k.split(",").map(Number), 0]); supported[k] = true;
            } else { leaves++; }
        });
        for (var i = 0; i < queue.length; i++) {
            var entry = queue[i];
            if (entry[1] === 4) { continue; }
            neighbours.forEach(function (d) {
                var p = [entry[0][0]+d[0], entry[0][1]+d[1], entry[0][2]+d[2]];
                var k = key(p[0],p[1],p[2]);
                if (blocks[k] && !supported[k]) {
                    supported[k] = true; queue.push([p, entry[1]+1]);
                }
            });
        }
        if (!leaves || Object.keys(blocks).some(function (k) { return !supported[k]; })) {
            fail("unsupported 1.7.10 foliage in " + kind + " height " + height);
        }
        var lines = ["[META]", "needsFoundation=true", "spawnWater=false", "spawnLava=false", "[DATA]"];
        Object.keys(blocks).sort().forEach(function (k) {
            lines.push(k + ":" + blocks[k][0] + "." + blocks[k][1]);
        });
        var object = Bo2Object.load("XF " + kind + " " + height,
            new java.io.ByteArrayInputStream(new java.lang.String(lines.join("\n")).getBytes("US-ASCII")));
        object.setAttribute(WPObject.ATTRIBUTE_LEAF_DECAY_MODE, new java.lang.Integer(WPObject.LEAF_DECAY_NO_CHANGE));
        // Solid collisions reject the whole tree; never overwrite a structure/log.
        object.setAttribute(WPObject.ATTRIBUTE_COLLISION_MODE, new java.lang.Integer(WPObject.COLLISION_MODE_SOLID));
        return object;
    }

    function treeLayer(kind, height) {
        // A singleton Bo2Object is itself a provider whose setSeed is a no-op.
        // Species/height are selected in the mask, not in shared mutable state.
        var layer = new Bo2Layer(tree(kind,height),
            "Natural 1.7.10 trees with verified four-step leaf support", new java.awt.Color(0x286828));
        // Masks already select one anchor per cell; strength 15 always passes.
        layer.setDensity(1);
        return layer;
    }

    function plantLayer(profile) {
        var keys = Object.keys(profile.plants).sort();
        if (!keys.length) { return null; }
        var layer = new PlantLayer("XF plants " + profile.name, "Biome-native ground vegetation", new java.awt.Color(0x62a840));
        layer.setGenerateFarmland(false);
        layer.setOnlyOnValidBlocks(true);
        // WP 2.27 exposes setSettings but no setters on its PlantSettings record.
        // Confine the required field access to construction; no exporter patching.
        var occurrence = PlantSettings.class.getDeclaredField("occurrence");
        var growthFrom = PlantSettings.class.getDeclaredField("growthFrom");
        var growthTo = PlantSettings.class.getDeclaredField("growthTo");
        occurrence.setAccessible(true); growthFrom.setAccessible(true); growthTo.setAccessible(true);
        keys.forEach(function (name) {
            var plant = Plants[name], index = -1;
            for (var i = 0; i < Plants.ALL_PLANTS.length; i++) {
                if (Plants.ALL_PLANTS[i].equals(plant)) { index = i; break; }
            }
            if (index < 0) { fail("unknown 1.7.10 plant: " + name); }
            var settings = new PlantSettings();
            occurrence.setShort(settings, profile.plants[name]);
            growthFrom.setInt(settings, 1);
            growthTo.setInt(settings, name === "CACTUS" ? 3 : 1);
            layer.setSettings(index, settings);
        });
        return layer;
    }

    function build(cfg) {
        var layers = {trees:[], plants:[]};
        cfg.treeVariants.forEach(function (entry) {
            entry.heights.forEach(function (height) {
                wp.checkForInterrupt();
                layers.trees.push(treeLayer(entry.kind,height));
            });
        });
        cfg.profiles.forEach(function (profile) {
            wp.checkForInterrupt();
            layers.plants.push(plantLayer(profile));
        });
        log("Resolved vegetation profiles: " + cfg.profiles.length
            + "; verified natural tree variants: " + layers.trees.length);
        return layers;
    }

    function importWorld(heightMap, platform, shiftX, shiftZ, cfg) {
        // ImportHeightMapOp uses a new random seed on every call and has no seed setter.
        // Use its native importer, with the SAME transform and level mapping.
        var Importer = Java.type("org.pepsoft.worldpainter.importing.HeightMapImporter");
        var Transform = Java.type("org.pepsoft.worldpainter.heightMaps.TransformingHeightMap");
        var Factory = Java.type("org.pepsoft.worldpainter.TileFactoryFactory");
        var importer = new Importer();
        importer.setHeightMap(new Transform("XenoEarth", heightMap, 1, 1, shiftX, shiftZ, 0));
        importer.setImageFile(heightMap.getImageFile());
        importer.setName("XenoEarth");
        importer.setPlatform(platform);
        importer.setMinHeight(0); importer.setMaxHeight(256);
        importer.setImageLowLevel(0); importer.setImageHighLevel(65535);
        importer.setWorldLowLevel(1); importer.setWorldHighLevel(254);
        importer.setWorldWaterLevel(62);
        importer.setMinecraftSeed(cfg.seed);
        importer.setTileFactory(Factory.createNoiseTileFactory(cfg.seed, Terrain.GRASS, 0, 256, 58, 62, false, true, 20, 1));
        return importer.importToNewWorld(Dimension.Anchor.NORMAL_DETAIL, null);
    }

    function configureExport(world) {
        var dimension = world.getDimension(Dimension.Anchor.NORMAL_DETAIL);
        var ExportSettings = Java.type("org.pepsoft.worldpainter.platforms.JavaExportSettings");
        var ResourcesSettings = Java.type("org.pepsoft.worldpainter.layers.exporters.ResourcesExporter$ResourcesExporterSettings");
        var Resources = Java.type("org.pepsoft.worldpainter.layers.Resources");
        var resources = ResourcesSettings.defaultSettings(world.getPlatform(), Dimension.Anchor.NORMAL_DETAIL, 0, 256);
        resources.setMinimumLevel(0);
        dimension.setLayerSettings(Resources.INSTANCE, resources);
        dimension.setPopulate(false);
        dimension.setBottomless(false);
        world.setMapFeatures(false);
        world.setCreateGoodiesChest(false);
        // The legacy postprocessor must never globally mark foliage permanent.
        dimension.setExportSettings(new ExportSettings().withMakeAllLeavesPersistent(false));
        var disabled = ["Populate","Resources","Caves","Caverns","Chasms"];
        disabled.forEach(function (name) {
            dimension.clearLayerData(wp.getLayer().withName(name).go());
        });
        ["Caves","Caverns","Chasms"].forEach(function (name) {
            var Settings = Java.type("org.pepsoft.worldpainter.layers.exporters."
                + name + "Exporter$" + name + "Settings");
            var settings = new Settings();
            settings["set" + name + "EverywhereLevel"](0);
            settings.setFloodWithLava(false);
            dimension.setLayerSettings(wp.getLayer().withName(name).go(), settings);
        });
        // Imported themes/preferences must not reintroduce the superseded forests.
        var TreeSettings = Java.type("org.pepsoft.worldpainter.layers.exporters.TreesExporter$TreeLayerSettings");
        ["Deciduous","Pine","Jungle","Swamp"].forEach(function (name) {
            var layer = wp.getLayer().withName(name).go();
            dimension.clearLayerData(layer);
            var settings = new TreeSettings(layer);
            settings.setMinimumLevel(0);
            dimension.setLayerSettings(layer, settings);
        });
    }

    function apply(world, cfg, layers, treePath, plantPath, shiftX, shiftZ) {
        if (!cfg.enabled) { return; }
        var trees = wp.getHeightMap().fromFile(treePath).go();
        var plants = wp.getHeightMap().fromFile(plantPath).go();
        for (var i = 0; i < layers.trees.length; i++) {
            wp.checkForInterrupt();
            wp.applyHeightMap(trees).toWorld(world).shift(shiftX,shiftZ)
                .applyToLayer(layers.trees[i]).fromLevel(i+1).toLevel(15).go();
        }
        for (var j = 0; j < layers.plants.length; j++) {
            wp.checkForInterrupt();
            if (layers.plants[j]) {
                wp.applyHeightMap(plants).toWorld(world).shift(shiftX,shiftZ)
                    .applyToLayer(layers.plants[j]).fromLevel(j+1).toLevel(1).go();
            }
        }
    }

    return {configuration:readConfiguration, build:build, importWorld:importWorld,
            configureExport:configureExport, apply:apply};
}());
