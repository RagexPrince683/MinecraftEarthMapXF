#!/usr/bin/env python3
"""Static contract checks for the WorldPainter 2.27.0 XenoEarth script."""
from __future__ import annotations
import argparse, json, re, struct, sys
from pathlib import Path
PNG_SIGNATURE=b"\x89PNG\r\n\x1a\n"
SCALE_DIMENSIONS={10:(10752,5376),20:(21504,10752),40:(43008,21504)}
PROFILES={"smoke":(10,25,16000,2688,1344),"earth8000":(10,50,8000,5376,2688),"earth4000":(10,100,4000,10752,5376),"earth2000":(20,100,2000,21504,10752),"production":(40,100,1000,43008,21504)}
PROFILE_ALIASES={"preview":"earth4000"}
LAUNCHERS={"world_xenofactions_1_8000.js":"earth8000","world_xenofactions_1_4000.js":"earth4000","world_xenofactions_1_2000.js":"earth2000"}
ALLOWED_1710_BIOMES={0,1,2,3,4,5,6,7,10,12,13,16,17,21,22,23,24,26,27,29,30,32,35,36,37,129,130,131,132,134,140,149,151,160,161}
DISABLED_FLAGS=("generateCaves","generateCaverns","generateChasms","generateRavines","generateOres","generateResources","generateLava","generateStructures","generateCities","generateStreets","generateBorders","generatePortals","allowMinecraftPopulation")
BUILTIN_LAYERS={"biomes":"Biomes","frost":"Frost","deciduous":"Deciduous","pine":"Pine","jungle":"Jungle","swamp":"Swamp"}
FORBIDDEN_LAYER_NAMES={"Deciduous Forest","Pine Forest","Swamp Land","DeciduousForest","PineForest","SwampLand"}

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

def validate_with_name_arguments(source:str)->list[str]:
    """Reject known description aliases and Java class names in executable lookups."""
    errors=[]
    for name in re.findall(r'\.withName\s*\(\s*["\']([^"\']+)["\']\s*\)',strip_comments(source)):
        if name in FORBIDDEN_LAYER_NAMES:
            errors.append(f"forbidden WorldPainter layer name passed to withName(): {name}")
    return errors

def validate_builtin_layers(source:str)->list[str]:
    errors=[]; executable=strip_comments(source)
    errors.extend(validate_with_name_arguments(executable))
    registry=re.search(r"var\s+BUILTIN_LAYER_NAMES\s*=\s*\{(.*?)\}\s*;",executable,re.S)
    if not registry:
        return errors+["central BUILTIN_LAYER_NAMES registry is required"]
    entries=dict(re.findall(r'([A-Za-z]\w*)\s*:\s*["\']([^"\']+)["\']',registry.group(1)))
    for key,name in BUILTIN_LAYERS.items():
        if entries.get(key)!=name: errors.append(f"BUILTIN_LAYER_NAMES.{key} must be {name!r}")
        if not re.search(rf"resolveBuiltInLayer\s*\(\s*BUILTIN_LAYER_NAMES\.{key}\s*\)",executable):
            errors.append(f"enabled built-in layer {name!r} is not resolved during API preflight")
    if not re.search(r'log\s*\(\s*["\']Resolved built-in layer: ["\']\s*\+\s*name\s*\)',executable):
        errors.append("successful built-in layer lookups must be printed")
    # Executable lookup sites must use the registry rather than duplicate literals.
    if re.search(r'\.withName\s*\(\s*["\']',executable): errors.append("withName() built-in lookups must use BUILTIN_LAYER_NAMES")
    veg_objects=re.findall(r"objects\.vegetationLayers\s*=\s*\{(.*?)\}\s*;",executable,re.S)
    vegetation_keys=set(re.findall(r"\b(deciduous|pine|jungle|swamp)\s*:",veg_objects[-1])) if veg_objects else set()
    if vegetation_keys!=set(BUILTIN_LAYERS)-{"biomes","frost"}: errors.append("vegetationLayers must define all semantic vegetation keys")
    rules=re.search(r"var\s+rules\s*=\s*\[(.*?)\]\s*;",executable,re.S)
    rule_keys=re.findall(r'\[\s*["\']([^"\']+)["\']\s*,\s*\[',rules.group(1)) if rules else []
    if not rule_keys: errors.append("semantic vegetation rules are required")
    for key in rule_keys:
        if key not in vegetation_keys: errors.append(f"unknown vegetation layer key in rule: {key}")
    if re.search(r"vegetationLayers\s*\[\s*\d+\s*\]",executable) or re.search(r"var\s+rules\s*=\s*\[\s*\[\s*\d",executable):
        errors.append("positional vegetation layer indexes are forbidden")
    if "unknown vegetation layer key:" not in executable: errors.append("unknown vegetation rule keys must fail clearly")
    build=executable.find("var api=buildApiObjects()")
    passed=executable.find("XenoEarth WorldPainter API preflight: PASS")
    if build<0 or passed<0 or passed<build: errors.append("preflight PASS must occur after all layer lookups")
    return errors

def validate(root:Path)->list[str]:
    errors=[]; launcher=root/"world_xenofactions.js"; script=root/"world_xenofactions_core.js"; contract=root/"xenoearth-profile.json"
    for rel in ("README.md","LICENSE","world.js","layer/Rivers.layer",launcher.name,script.name,contract.name,*LAUNCHERS):
        if not (root/rel).is_file(): errors.append(f"missing required file: {rel}")
    if not script.is_file() or not launcher.is_file(): return errors
    source=script.read_text(encoding="utf-8"); executable=strip_comments(source)
    launcher_source=launcher.read_text(encoding="utf-8")
    if "script.param.profile.default=smoke" not in launcher_source: errors.append("default GUI profile must be smoke")
    if not re.search(r'load\(new java\.io\.File\(scriptDir,\s*["\']world_xenofactions_core\.js["\']\)\.toURI\(\)\.toURL\(\)\);', strip_comments(launcher_source)): errors.append("general launcher must load shared core relative to scriptDir")
    if "runXenoEarth(selectedProfileName, runPreflightOnly);" not in launcher_source: errors.append("general launcher must invoke selected profile")
    errors.extend(validate_filter_chains(source))
    errors.extend(validate_builtin_layers(source))
    if re.search(r"(?:[A-Za-z]:[\\/]|var\s+path\s*=|/Users/|/home/)",executable): errors.append("script contains a machine-specific absolute path")
    if "new java.io.File(scriptDir)" not in executable: errors.append("core must derive sourceRoot from scriptDir")
    if "script.param.preflightOnly.type=boolean" not in launcher_source or "if (runPreflightOnly)" not in executable or "API preflight: PASS" not in source: errors.append("preflight-only execution path is required")
    if not re.search(r"wp\.getMapFormat\(\)\s*\.withId\(LEGACY_ANVIL_MAP_FORMAT\)\s*\.go\(\)",executable): errors.append("legacy Anvil Platform must be resolved with getMapFormat().withId().go()")
    if re.search(r"\.withMapFormat\s*\(\s*LEGACY_ANVIL_MAP_FORMAT\s*\)",executable): errors.append("withMapFormat must not receive the legacy format string")
    platform=re.search(r"(\w+)\s*=\s*wp\.getMapFormat\(\)\s*\.withId\(LEGACY_ANVIL_MAP_FORMAT\)\s*\.go\(\)",executable)
    if not platform or not re.search(rf"\.withMapFormat\s*\(\s*(?:\w+\.)?{re.escape(platform.group(1))}\s*\)",executable): errors.append("resolved Platform variable must be passed to withMapFormat")
    inland=re.search(r"inlandRiverFilter\s*=\s*(wp\.createFilter\(\).*?\.go\(\))",executable,re.S)
    if not inland or ".onlyOnLand()" not in inland.group(1) or "exceptOnBiome" in inland.group(1): errors.append("inland rivers must use one legal onlyOnLand filter")
    veg=re.search(r"vegetationFilter\s*=\s*(wp\.createFilter\(\).*?\.go\(\))",executable,re.S)
    if not veg or ".onlyOnLand()" not in veg.group(1) or ".exceptOnLayer(" not in veg.group(1): errors.append("vegetation must use legal land-plus-river-layer filter")
    if re.search(r"exceptOnBiome\s*\(\s*(?:0|24|10)\s*\)",executable): errors.append("old repeated ocean-biome exclusions are forbidden")
    for alias,canonical in PROFILE_ALIASES.items():
        if not re.search(rf'var\s+PROFILE_ALIASES\s*=\s*\{{[^}}]*{alias}\s*:\s*["\']{canonical}["\']', executable): errors.append(f"profile alias {alias} must resolve to {canonical}")
        if re.search(rf'\b{alias}\s*:\s*\{{', re.search(r"var\s+PROFILES\s*=\s*\{(.*?)\};", executable, re.S).group(1)): errors.append(f"profile alias {alias} must not have an independent profile object")
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
    if not re.search(r"horizontalScaleFactor\s*=\s*config\.sourceScale\s*\*\s*config\.resize\s*/\s*100\.0", executable): errors.append("spawn calculation must include resize")
    if not re.search(r"minimumX:minimumX,maximumX:maximumX,minimumZ:minimumZ,maximumZ:maximumZ", executable): errors.append("manifest must use validated integer bounds")
    if "function log(message)" not in source or not all(f'log("[{i}/9]' in source for i in range(1,10)): errors.append("all progress stages must use central log()")
    without_log=re.sub(r"function\s+log\s*\(message\)\s*\{.*?\n\}", "", executable, count=1, flags=re.S)
    if "java.lang.System.out.println" in without_log: errors.append("System.out.println must not be used for normal progress")
    if not re.search(r"catch\s*\(error\)\s*\{\s*java\.lang\.System\.out\.println\(text\);\s*\}", executable): errors.append("log() must have a guarded System.out fallback")
    if not re.search(r"if\s*\(config\.sourceScale\s*===\s*40\)", executable): errors.append("split GlobCover must be restricted to source scale 40")
    for filename,profile_name in LAUNCHERS.items():
        path=root/filename
        if not path.is_file(): continue
        text=path.read_text(encoding="utf-8"); code=strip_comments(text)
        if not re.search(r'new java\.io\.File\(scriptDir,\s*["\']world_xenofactions_core\.js["\']\)', code): errors.append(f"{filename} must load shared core relative to scriptDir")
        calls=re.findall(r'runXenoEarth\(\s*["\']([^"\']+)["\']', code)
        if calls != [profile_name]: errors.append(f"{filename} must select exactly {profile_name}")
        if re.search(r'(?:[A-Za-z]:[\\/]|/Users/|/home/)', code): errors.append(f"{filename} uses an absolute path")
        if any(token in code for token in ("wp.createWorld", "wp.applyHeightMap", "BIOME_MAPPINGS", "function validateConfiguration")): errors.append(f"{filename} copies generation implementation")
    for scale in SCALE_DIMENSIONS:
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
