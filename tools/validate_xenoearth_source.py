#!/usr/bin/env python3
"""Static contract checks for the WorldPainter 2.27.0 XenoEarth script."""
from __future__ import annotations
import argparse, json, re, struct, sys
from pathlib import Path
PNG_SIGNATURE=b"\x89PNG\r\n\x1a\n"
SCALE_DIMENSIONS={10:(10752,5376),40:(43008,21504)}
PROFILES={"smoke":(10,25,16000,2688,1344),"preview":(10,100,4000,10752,5376),"production":(40,100,1000,43008,21504)}
ALLOWED_1710_BIOMES={0,1,2,3,4,5,6,7,10,12,13,16,17,21,22,23,24,26,27,29,30,32,35,36,37,129,130,131,132,134,140,149,151,160,161}
DISABLED_FLAGS=("generateCaves","generateCaverns","generateChasms","generateRavines","generateOres","generateResources","generateLava","generateStructures","generateCities","generateStreets","generateBorders","generatePortals","allowMinecraftPopulation")

def png_dimensions(path:Path)->tuple[int,int]:
    with path.open("rb") as stream: header=stream.read(24)
    if len(header)!=24 or header[:8]!=PNG_SIGNATURE or header[12:16]!=b"IHDR": raise ValueError("not a PNG with an IHDR first chunk")
    return struct.unpack(">II",header[16:24])

def value(source:str,name:str)->str|None:
    m=re.search(rf"^var\s+{re.escape(name)}\s*=\s*([^;]+);",source,re.M); return m.group(1).strip() if m else None

def required_images(scale:int)->dict[str,tuple[int,int]]:
    dims=SCALE_DIMENSIONS[scale]; suffix=f"{scale}k.png"; out={f"images/{n}{suffix}":dims for n in ("HeightMap","BiomeMap","WaterMap","Ice")}
    if scale==40: out.update({"images/globecover1_40k.png":(21504,10752),"images/globecover2a_40k.png":(10752,10752),"images/globecover2b_40k.png":(10752,10752),"images/globecover3_40k.png":(21504,10752),"images/globecover4_40k.png":(21504,10752)})
    else: out[f"images/globecover{suffix}"]=dims
    return out

def strip_comments(source:str)->str: return re.sub(r"/\*.*?\*/|//[^\n]*","",source,flags=re.S)

def filter_chains(source:str)->list[str]:
    """Extract complete createFilter fluent expressions through their terminal go()."""
    chains=[]; start=0
    while True:
        pos=source.find("wp.createFilter",start)
        if pos<0: return chains
        i=pos; depth=0; quote=None; escape=False
        while i<len(source):
            ch=source[i]
            if quote:
                if escape: escape=False
                elif ch=="\\": escape=True
                elif ch==quote: quote=None
            elif ch in "'\"": quote=ch
            elif ch=="(": depth+=1
            elif ch==")":
                depth-=1
                if depth==0 and re.match(r"\s*;",source[i+1:]): chains.append(source[pos:i+1]); i+=1; break
            i+=1
        else: chains.append(source[pos:]); return chains
        start=i

def validate_filter_chains(source:str)->list[str]:
    errors=[]; chains=filter_chains(strip_comments(source))
    if not chains: return ["no wp.createFilter() chains found"]
    for number,chain in enumerate(chains,1):
        only=re.findall(r"\.\s*(onlyOn[A-Za-z]+)\s*\(",chain); exc=re.findall(r"\.\s*(exceptOn[A-Za-z]+)\s*\(",chain)
        if len(only)>1: errors.append(f"filter {number} has more than one onlyOn condition: {', '.join(only)}")
        if len(exc)>1: errors.append(f"filter {number} has more than one exceptOn condition: {', '.join(exc)}")
        if not re.search(r"\.go\s*\(\s*\)\s*$",chain): errors.append(f"filter {number} does not terminate with go()")
    return errors

def validate(root:Path)->list[str]:
    errors=[]; script=root/"world_xenofactions.js"; contract=root/"xenoearth-profile.json"
    for rel in ("README.md","LICENSE","world.js","layer/Rivers.layer",script.name,contract.name):
        if not (root/rel).is_file(): errors.append(f"missing required file: {rel}")
    if not script.is_file(): return errors
    source=script.read_text(encoding="utf-8"); executable=strip_comments(source)
    errors.extend(validate_filter_chains(source))
    if re.search(r"(?:[A-Za-z]:[\\/]|var\s+path\s*=|/Users/|/home/)",executable): errors.append("script contains a machine-specific absolute path")
    if "new java.io.File(scriptDir)" not in executable: errors.append("script must derive sourceRoot from scriptDir")
    if "script.param.profile.default=smoke" not in source: errors.append("default GUI profile must be smoke")
    if "script.param.preflightOnly.type=boolean" not in source or "if (runPreflightOnly)" not in executable or "API preflight: PASS" not in source: errors.append("preflight-only execution path is required")
    if not re.search(r"wp\.getMapFormat\(\)\s*\.withId\(LEGACY_ANVIL_MAP_FORMAT\)\s*\.go\(\)",executable): errors.append("legacy Anvil Platform must be resolved with getMapFormat().withId().go()")
    if re.search(r"\.withMapFormat\s*\(\s*LEGACY_ANVIL_MAP_FORMAT\s*\)",executable): errors.append("withMapFormat must not receive the legacy format string")
    platform=re.search(r"(\w+)\s*=\s*wp\.getMapFormat\(\)\s*\.withId\(LEGACY_ANVIL_MAP_FORMAT\)\s*\.go\(\)",executable)
    if not platform or not re.search(rf"\.withMapFormat\s*\(\s*(?:\w+\.)?{re.escape(platform.group(1))}\s*\)",executable): errors.append("resolved Platform variable must be passed to withMapFormat")
    inland=re.search(r"inlandRiverFilter\s*=\s*(wp\.createFilter\(\).*?\.go\(\))",executable,re.S)
    if not inland or ".onlyOnLand()" not in inland.group(1) or "exceptOnBiome" in inland.group(1): errors.append("inland rivers must use one legal onlyOnLand filter")
    veg=re.search(r"vegetationFilter\s*=\s*(wp\.createFilter\(\).*?\.go\(\))",executable,re.S)
    if not veg or ".onlyOnLand()" not in veg.group(1) or ".exceptOnLayer(" not in veg.group(1): errors.append("vegetation must use legal land-plus-river-layer filter")
    if re.search(r"exceptOnBiome\s*\(\s*(?:0|24|10)\s*\)",executable): errors.append("old repeated ocean-biome exclusions are forbidden")
    for name,(scale,resize,effective,width,height) in PROFILES.items():
        pattern=rf'{name}:\s*\{{name:"{name}",\s*sourceScale:{scale},\s*resize:{resize},\s*effectiveScale:{effective},\s*width:{width},\s*height:{height}\}}'
        if not re.search(pattern,executable): errors.append(f"profile {name} definition is invalid")
        if width<=0 or height<=0 or width%16 or height%16: errors.append(f"profile {name} dimensions must be positive and chunk-aligned")
        if round(40000/scale*100/resize)!=effective: errors.append(f"profile {name} effective scale is invalid")
    if '"earth_1-"+config.effectiveScale' not in executable or '"generated/xenoearth-profile-"+config.name+".json"' not in executable: errors.append("output names must include effective scale and selected profile")
    if not re.search(r'absolutePath\("generated/"\+outputName\)',executable) or not re.search(r'file\("generated/xenoearth-profile-',executable): errors.append("generated projects and manifests must be written under generated/")
    for flag in DISABLED_FLAGS:
        if not re.search(rf"var\s+[^;]*\b{flag}\s*=\s*false",source): errors.append(f"{flag} must be false")
    mapping=re.search(r"var BIOME_MAPPINGS\s*=\s*\[(.*?)\n\];",source,re.S)
    if mapping:
        ids={int(x) for x in re.findall(r"\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(\d+)\s*\]",mapping.group(1))}; bad=sorted(ids-ALLOWED_1710_BIOMES)
        if bad: errors.append(f"biome IDs are not valid for 1.7.10: {bad}")
    else: errors.append("BIOME_MAPPINGS table is missing")
    for scale in (10,40):
        for rel,dims in required_images(scale).items():
            path=root/rel
            if not path.is_file(): errors.append(f"missing required image: {rel}"); continue
            try: actual=png_dimensions(path)
            except (OSError,ValueError) as exc: errors.append(f"cannot inspect {rel}: {exc}"); continue
            if actual!=dims: errors.append(f"{rel}: expected {dims[0]} x {dims[1]}, got {actual[0]} x {actual[1]}")
    try:
        profile=json.loads(contract.read_text()); expected={"targetMinecraftVersion":"1.7.10","scale":1000,"width":43008,"height":21504,"seaLevel":62}
        for key,wanted in expected.items():
            if profile.get(key)!=wanted: errors.append(f"profile {key} must be {wanted!r}")
    except (OSError,json.JSONDecodeError) as exc: errors.append(f"invalid profile: {exc}")
    return errors

def main(argv=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("root",nargs="?",type=Path,default=Path(__file__).resolve().parents[1]); args=parser.parse_args(argv)
    errors=validate(args.root.resolve())
    if errors:
        print("XenoEarth source validation: FAIL",file=sys.stderr)
        for error in errors: print(f" - {error}",file=sys.stderr)
        return 1
    print("XenoEarth source validation: PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
