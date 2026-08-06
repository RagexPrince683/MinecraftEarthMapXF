import json
import struct
import tempfile
import unittest
import re
from pathlib import Path

import validate_xenoearth_source as validator


def png_header(width, height):
    return validator.PNG_SIGNATURE + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)


class HeaderTests(unittest.TestCase):
    def test_reads_dimensions_without_pixel_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny.png"
            path.write_bytes(png_header(17, 23))
            self.assertEqual(validator.png_dimensions(path), (17, 23))

    def test_rejects_non_png(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.png"
            path.write_bytes(b"not a png")
            with self.assertRaises(ValueError): validator.png_dimensions(path)


class SourceTests(unittest.TestCase):
    def validate_mutation(self, pattern, replacement):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory)
            for name in ("README.md", "LICENSE", "world.js", "world_xenofactions.js", "xenoearth-profile.json"):
                (copy / name).write_bytes((root / name).read_bytes())
            source_path = copy / "world_xenofactions.js"
            source, count = re.subn(pattern, replacement, source_path.read_text(), count=1, flags=re.DOTALL)
            self.assertEqual(count, 1, f"test mutation did not match: {pattern}")
            source_path.write_text(source)
            (copy / "layer").mkdir(); (copy / "layer/Rivers.layer").write_bytes(b"test")
            (copy / "images").mkdir()
            for relative, dims in validator.required_images(40).items():
                target = copy / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(png_header(*dims))
            return validator.validate(copy)

    def test_repository_source_passes(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(validator.validate(root), [])

    def test_bad_profile_fails(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory)
            for name in ("README.md", "LICENSE", "world.js", "world_xenofactions.js"):
                (copy / name).write_bytes((root / name).read_bytes())
            (copy / "layer").mkdir(); (copy / "layer/Rivers.layer").write_bytes(b"test")
            (copy / "images").mkdir()
            for relative, dims in validator.required_images(40).items():
                target = copy / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(png_header(*dims))
            profile = json.loads((root / "xenoearth-profile.json").read_text())
            profile["seaLevel"] = 63
            (copy / "xenoearth-profile.json").write_text(json.dumps(profile))
            self.assertTrue(any("seaLevel" in error for error in validator.validate(copy)))

    def test_requires_legacy_anvil_and_world_creation_limits(self):
        mutations = (
            (r'var LEGACY_ANVIL_MAP_FORMAT = "org\.pepsoft\.anvil"', 'var LEGACY_ANVIL_MAP_FORMAT = "wrong"', "legacy map format"),
            (r"\.withLowerBuildLimit\(LOWER_BUILD_LIMIT\)", "", "lower build limit"),
            (r"\.withUpperBuildLimit\(UPPER_BUILD_LIMIT\)", "", "upper build limit"),
            (r"\.withWaterLevel\(seaLevel\)", "", "configured seaLevel"),
        )
        for pattern, replacement, expected in mutations:
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in error for error in self.validate_mutation(pattern, replacement)))

    def test_rejects_ocean_only_inland_rivers(self):
        errors = self.validate_mutation(r"(var inlandRiverFilter.*?maximumSurfaceY\))", r"\1.onlyOnBiome(0)")
        self.assertTrue(any("must not depend" in error for error in errors))

    def test_requires_ocean_river_layer_erasure(self):
        errors = self.validate_mutation(r"(withFilter\(oceanRiverMaskOverlapFilter\).*?)toLevel\(0\)", r"\1toLevel(1)")
        self.assertTrue(any("erased in ocean" in error for error in errors))

    def test_requires_shared_vegetation_river_and_slope_filter(self):
        mutations = (
            (r"\.belowDegrees\(maximumVegetationSlope\)", "", "enforce maximumVegetationSlope"),
            (r"\.exceptOnLayer\(riverLayer\)", ".exceptOnLayer(vegetationLayer)", "exclude Rivers.layer"),
            (r"\.withFilter\(vegetationFilter\)", "", "shared vegetation filter"),
        )
        for pattern, replacement, expected in mutations:
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in error for error in self.validate_mutation(pattern, replacement)))

    def test_requires_vegetation_slope_validation(self):
        errors = self.validate_mutation(r"if \(maximumVegetationSlope < 0.*?;\n", "")
        self.assertTrue(any("validated from 0 through 90" in error for error in errors))

    def test_requires_interrupt_checks_in_long_loops(self):
        for iterator, label in (("i", "BIOME_MAPPINGS validation"), ("b", "biome colour mapping"),
                                ("gp", "GlobCover part"), ("vr", "vegetation rule"),
                                ("c", "vegetation colour")):
            pattern = rf"(for \(var {iterator} = .*?\{{\s*)wp\.checkForInterrupt\(\);"
            with self.subTest(loop=label):
                errors = self.validate_mutation(pattern, r"\1")
                self.assertTrue(any(label in error for error in errors))

    def test_minecraft_population_remains_disabled(self):
        errors = self.validate_mutation(r"var allowMinecraftPopulation = false", "var allowMinecraftPopulation = true")
        self.assertTrue(any("allowMinecraftPopulation must be false" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
