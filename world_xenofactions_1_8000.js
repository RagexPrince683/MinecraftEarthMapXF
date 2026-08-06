// script.name=XenoFactions Earth 1:8000
// script.description=Generate the clean Minecraft 1.7.10 Earth map at 1:8000.
// script.param.preflightOnly.type=boolean
// script.param.preflightOnly.default=false
// script.param.preflightOnly.displayName=API preflight only
var selectedPreflightMode = (typeof preflightOnly === "undefined") ? false : Boolean(preflightOnly);
load(new java.io.File(scriptDir, "world_xenofactions_core.js").toURI().toURL());
runXenoEarth("earth8000", selectedPreflightMode);
