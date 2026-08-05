#!/usr/bin/env python3
"""Validate the XenoFactions WorldPainter source without decoding full images."""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCALE_DIMENSIONS = {10: (10752, 5376), 20: (21504, 10752), 40: (43008, 21504)}
ALLOWED_1710_BIOMES = {
    0, 1, 2, 3, 4, 5, 6, 7, 10, 12, 13, 16, 17, 21, 22, 23, 24, 26, 27,
    29, 30, 32, 35, 36, 37, 129, 130, 131, 132, 134, 140, 149, 151, 160, 161,
}
DISABLED_FLAGS = (
    "generateCaves", "generateCaverns", "generateChasms", "generateRavines",
    "generateOres", "generateResources", "generateLava", "generateStructures",
    "generateCities", "generateStreets", "generateBorders", "generatePortals",
    "allowMinecraftPopulation",
)
FORBIDDEN_EXECUTABLE_REFERENCES = (
    "ore/", "portal/", "Borders.layer", "Cities.layer", "street.layer",
    "1-13", "1-14",
)


def png_dimensions(path: Path) -> tuple[int, int]:
    """Read only PNG signature and IHDR (24 bytes total)."""
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise ValueError("not a PNG with an IHDR first chunk")
    return struct.unpack(">II", header[16:24])


def value(source: str, name: str) -> str | None:
    match = re.search(rf"^var\s+{re.escape(name)}\s*=\s*([^;]+);", source, re.MULTILINE)
    return match.group(1).strip() if match else None


def required_images(scale: int) -> dict[str, tuple[int, int]]:
    dims = SCALE_DIMENSIONS[scale]
    suffix = f"{scale}k.png"
    result = {f"images/{name}{suffix}": dims for name in ("HeightMap", "BiomeMap", "WaterMap", "Ice")}
    if scale == 40:
        result.update({
            "images/globecover1_40k.png": (21504, 10752),
            "images/globecover2a_40k.png": (10752, 10752),
            "images/globecover2b_40k.png": (10752, 10752),
            "images/globecover3_40k.png": (21504, 10752),
            "images/globecover4_40k.png": (21504, 10752),
        })
    else:
        result[f"images/globecover{suffix}"] = dims
    return result


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    script_path = root / "world_xenofactions.js"
    profile_path = root / "xenoearth-profile.json"
    for relative in ("README.md", "LICENSE", "world.js", "layer/Rivers.layer", script_path.name, profile_path.name):
        if not (root / relative).is_file(): errors.append(f"missing required file: {relative}")
    if not script_path.is_file(): return errors
    source = script_path.read_text(encoding="utf-8")

    expected = {
        "targetMinecraftVersion": '"1.7.10"', "scale": "40", "minimumSurfaceY": "1",
        "maximumSurfaceY": "254", "seaLevel": "62", "allowMinecraftPopulation": "false",
    }
    for name, wanted in expected.items():
        if value(source, name) != wanted: errors.append(f"{name} must default to {wanted}")
    for flag in DISABLED_FLAGS:
        if value(source, flag) != "false": errors.append(f"{flag} must be false")

    mapping_match = re.search(r"var BIOME_MAPPINGS\s*=\s*\[(.*?)\n\];", source, re.DOTALL)
    if not mapping_match: errors.append("BIOME_MAPPINGS table is missing")
    else:
        ids = [int(item) for item in re.findall(r"\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(\d+)\s*\]", mapping_match.group(1))]
        invalid = sorted(set(ids) - ALLOWED_1710_BIOMES)
        if invalid: errors.append(f"biome IDs are not valid for 1.7.10: {invalid}")

    # Strings in comments/documentation are allowed; executable path is stripped of comments.
    executable = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)
    for forbidden in FORBIDDEN_EXECUTABLE_REFERENCES:
        if forbidden in executable: errors.append(f"forbidden executable reference: {forbidden}")

    terrain_loads = re.findall(r"getTerrain\(\)\.fromFile", executable)
    registry = re.search(r"var CUSTOM_TERRAIN_COMPATIBILITY\s*=\s*\{(.*?)\};", source, re.DOTALL)
    if terrain_loads and (not registry or not registry.group(1).strip()):
        errors.append("enabled custom terrain lacks a compatibility entry")

    checklist = "REQUIRED MANUAL EXPORT CHECKLIST"
    for label in ("Populate", "Resources", "Caves", "Caverns", "Chasms", "Structures", "lava"):
        if checklist not in source or label not in source: errors.append(f"manual export checklist does not name {label}")

    for relative, dimensions in required_images(40).items():
        path = root / relative
        if not path.is_file(): errors.append(f"missing required image: {relative}"); continue
        try:
            actual = png_dimensions(path)
        except (OSError, ValueError) as exc:
            errors.append(f"cannot inspect {relative}: {exc}"); continue
        if actual != dimensions: errors.append(f"{relative}: expected {dimensions[0]} x {dimensions[1]}, got {actual[0]} x {actual[1]}")

    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile_expected = {"targetMinecraftVersion":"1.7.10", "scale":1000, "width":43008, "height":21504,
                            "minimumSurfaceY":1, "maximumSurfaceY":254, "seaLevel":62,
                            "populationMode":"pregenerated", "caves":False, "ores":False,
                            "lava":False, "structures":False, "vegetation":True}
        for key, wanted in profile_expected.items():
            if profile.get(key) != wanted: errors.append(f"profile {key} must be {wanted!r}")
    except (OSError, json.JSONDecodeError) as exc: errors.append(f"invalid profile: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = validate(args.root.resolve())
    if errors:
        print("XenoEarth source validation: FAIL", file=sys.stderr)
        for error in errors: print(f" - {error}", file=sys.stderr)
        return 1
    print("XenoEarth source validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
