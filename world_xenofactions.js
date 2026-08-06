// script.name=XenoFactions Earth Map
// script.description=Generate a Minecraft 1.7.10 Earth WorldPainter project.
// script.param.profile.type=string
// script.param.profile.default=smoke
// script.param.profile.displayName=Profile
// script.param.preflightOnly.type=boolean
// script.param.preflightOnly.default=false
// script.param.preflightOnly.displayName=API preflight only
var selectedProfileName = (typeof profile === "undefined" || profile === null || String(profile).length === 0) ? "smoke" : String(profile);
var runPreflightOnly = (typeof preflightOnly === "undefined") ? false : Boolean(preflightOnly);
load(new java.io.File(scriptDir, "world_xenofactions_core.js").toURI().toURL());
runXenoEarth(selectedProfileName, runPreflightOnly);
