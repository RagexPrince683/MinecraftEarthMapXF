# Phase 1 XenoFactions Earth map pipeline

## Unreleased

* Fixed the XenoFactions WorldPainter pipeline to select legacy Anvil explicitly,
  enforce build/water limits, correctly distinguish inland rivers from ocean mask
  overlap, and restore ocean floors.
* Added a shared river-, ocean-, water-, and slope-aware vegetation filter plus
  cooperative interruption checks for long mapping loops.
* Expanded source validation and unit coverage for format, limits, river behavior,
  vegetation safety, cancellation, and disabled Minecraft population.
* Updated the XenoFactions guide to distinguish automatic project configuration
  from settings which still require manual export control.
* Added the Minecraft 1.7.10-only WorldPainter source script and default profile.
* Added header-only source validation with automated tests.
* Documented legacy export controls, inspected layer/terrain compatibility, source
  attribution, offline vegetation limitations, and Phase 2 Anvil scan requirements.
* Ignored generated WorldPainter projects, exports, and validation reports.
