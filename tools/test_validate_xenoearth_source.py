import json
import struct
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
