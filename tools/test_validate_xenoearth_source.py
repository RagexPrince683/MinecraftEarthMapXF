import json, re, struct, tempfile, unittest
from pathlib import Path
import validate_xenoearth_source as validator

def png_header(width,height): return validator.PNG_SIGNATURE+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",width,height)

class HeaderTests(unittest.TestCase):
    def test_reads_dimensions_without_pixels(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.png"; p.write_bytes(png_header(17,23)); self.assertEqual(validator.png_dimensions(p),(17,23))
    def test_rejects_non_png(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.png"; p.write_bytes(b"bad")
            with self.assertRaises(ValueError): validator.png_dimensions(p)

class FilterParserTests(unittest.TestCase):
    def errors(self,chain): return validator.validate_filter_chains(chain)
    def test_rejects_two_except_biomes(self):
        self.assertTrue(self.errors("wp.createFilter().exceptOnBiome(0).exceptOnBiome(24).go();"))
    def test_rejects_two_only_conditions(self):
        self.assertTrue(self.errors("wp.createFilter().onlyOnBiome(0).onlyOnLand().go();"))
    def test_rejects_biome_and_layer_exceptions(self):
        self.assertTrue(self.errors("wp.createFilter().exceptOnBiome(0).exceptOnLayer(riverLayer).go();"))
    def test_accepts_one_only_and_one_except(self):
        chain="""wp.createFilter()
            .aboveLevel(seaLevel)
            .belowDegrees(maximumVegetationSlope)
            .onlyOnLand()
            .exceptOnLayer(riverLayer)
            .go();"""
        self.assertEqual(self.errors(chain),[])

class SourceTests(unittest.TestCase):
    def fixture(self,mutate=None):
        root=Path(__file__).resolve().parents[1]; temp=tempfile.TemporaryDirectory(); copy=Path(temp.name)
        for name in ("README.md","LICENSE","world.js","world_xenofactions.js","world_xenofactions_core.js","world_xenofactions_1_8000.js","world_xenofactions_1_4000.js","world_xenofactions_1_2000.js","xenoearth-profile.json"):
            (copy/name).write_bytes((root/name).read_bytes())
        (copy/"layer").mkdir(); (copy/"layer/Rivers.layer").write_bytes(b"test")
        for scale in validator.SCALE_DIMENSIONS:
            for rel,dims in validator.required_images(scale).items():
                target=copy/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(png_header(*dims))
        if mutate:
            path=copy/"world_xenofactions_core.js"; source=path.read_text(); source,count=re.subn(mutate[0],mutate[1],source,count=1,flags=re.S); self.assertEqual(count,1); path.write_text(source)
        return temp,copy
    def mutation_errors(self,pattern,replacement):
        temp,copy=self.fixture((pattern,replacement))
        try: return validator.validate(copy)
        finally: temp.cleanup()
    def test_repository_passes(self): self.assertEqual(validator.validate(Path(__file__).resolve().parents[1]),[])
    def test_rejects_string_map_format(self):
        errors=self.mutation_errors(r"\.withMapFormat\(api\.mapFormat\)",".withMapFormat(LEGACY_ANVIL_MAP_FORMAT)")
        self.assertTrue(any("must not receive" in e for e in errors))
    def test_rejects_windows_path(self):
        errors=self.mutation_errors(r"var sourceRoot = new java\.io\.File\(scriptDir\);",'var sourceRoot = new java.io.File("C:/Users/example/Downloads/map");')
        self.assertTrue(any("absolute path" in e for e in errors))
    def test_profiles_have_expected_values(self):
        source=(Path(__file__).resolve().parents[1]/"world_xenofactions_core.js").read_text()
        for name,(_,_,effective,width,height) in validator.PROFILES.items():
            with self.subTest(profile=name):
                self.assertIn(f'{name}: {{name:"{name}"',source); self.assertIn(f'effectiveScale:{effective}',source); self.assertIn(f'width:{width}, height:{height}',source)
    def test_effective_scale_output_naming(self):
        source=(Path(__file__).resolve().parents[1]/"world_xenofactions_core.js").read_text()
        self.assertIn('"earth_1-"+config.effectiveScale',source); self.assertIn('effectiveScale:config.effectiveScale',source)
    def test_default_profile_is_smoke(self):
        temp,copy=self.fixture()
        try:
            path=copy/"world_xenofactions.js"; path.write_text(path.read_text().replace("script.param.profile.default=smoke","script.param.profile.default=production"))
            self.assertTrue(any("default GUI profile" in e for e in validator.validate(copy)))
        finally: temp.cleanup()
    def test_rejects_region_boundary_regression(self):
        source=(Path(__file__).resolve().parents[1]/"world_xenofactions_core.js").read_text(); self.assertNotIn("% 512",source); self.assertIn("% 16",source)
    def test_bad_contract_fails(self):
        temp,copy=self.fixture()
        try:
            profile=json.loads((copy/"xenoearth-profile.json").read_text()); profile["seaLevel"]=63; (copy/"xenoearth-profile.json").write_text(json.dumps(profile))
            self.assertTrue(any("seaLevel" in e for e in validator.validate(copy)))
        finally: temp.cleanup()
    def test_rejects_noncanonical_layer_aliases(self):
        for alias in ("Deciduous Forest","Pine Forest","Swamp Land"):
            with self.subTest(alias=alias):
                errors=validator.validate_with_name_arguments(f'wp.getLayer().withName("{alias}").go();')
                self.assertTrue(any("forbidden" in error for error in errors))
    def test_rejects_java_class_names_in_layer_lookup(self):
        for class_name in ("DeciduousForest","PineForest","SwampLand"):
            with self.subTest(class_name=class_name):
                self.assertTrue(validator.validate_with_name_arguments(f'wp.getLayer().withName("{class_name}").go();'))
    def test_accepts_canonical_layer_lookup_names(self):
        for name in ("Deciduous","Pine","Jungle","Swamp","Frost"):
            with self.subTest(name=name):
                self.assertEqual(validator.validate_with_name_arguments(f'wp.getLayer().withName("{name}").go();'),[])
    def test_unknown_vegetation_rule_key_fails(self):
        errors=self.mutation_errors(r'\["swamp",\[\[90,120,220\]\]\]', '["bog",[[90,120,220]]]')
        self.assertTrue(any("unknown vegetation layer key in rule: bog" in error for error in errors))
    def test_rejects_positional_vegetation_regression(self):
        errors=self.mutation_errors(r'\["deciduous",\[\[0,255,255\]', '[0,[[0,255,255]')
        self.assertTrue(any("positional vegetation" in error or "semantic vegetation" in error for error in errors))

    def test_preview_aliases_canonical_earth4000(self):
        source=(Path(__file__).resolve().parents[1]/"world_xenofactions_core.js").read_text()
        self.assertRegex(source, r'PROFILE_ALIASES\s*=\s*\{preview:"earth4000"\}')
        profiles=re.search(r"var PROFILES = \{(.*?)\};",source,re.S).group(1)
        self.assertNotRegex(profiles,r"\bpreview\s*:\s*\{")

    def test_rejects_earth8000_wrong_resize(self):
        errors=self.mutation_errors(r'earth8000: \{name:"earth8000", sourceScale:10, resize:50', 'earth8000: {name:"earth8000", sourceScale:10, resize:100')
        self.assertTrue(any("profile earth8000 definition is invalid" in e for e in errors))

    def test_rejects_earth2000_wrong_source(self):
        errors=self.mutation_errors(r'earth2000: \{name:"earth2000", sourceScale:20', 'earth2000: {name:"earth2000", sourceScale:10')
        self.assertTrue(any("profile earth2000 definition is invalid" in e for e in errors))

    def test_rejects_spawn_without_resize(self):
        errors=self.mutation_errors(r'var horizontalScaleFactor = config\.sourceScale \* config\.resize / 100\.0;', 'var horizontalScaleFactor = config.sourceScale;')
        self.assertTrue(any("spawn calculation must include resize" in e for e in errors))

    def test_earth2000_requires_every_20k_asset(self):
        for rel in validator.required_images(20):
            with self.subTest(asset=rel):
                temp,copy=self.fixture()
                try:
                    (copy/rel).unlink()
                    self.assertTrue(any(rel in e for e in validator.validate(copy)))
                finally: temp.cleanup()

    def test_dedicated_launchers_select_exact_profiles(self):
        root=Path(__file__).resolve().parents[1]
        for filename,profile in validator.LAUNCHERS.items():
            with self.subTest(launcher=filename):
                source=(root/filename).read_text()
                self.assertEqual(re.findall(r'runXenoEarth\(\s*"([^"]+)"',source),[profile])

if __name__=="__main__": unittest.main()
