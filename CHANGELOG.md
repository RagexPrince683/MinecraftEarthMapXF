# Phase 1 XenoFactions Earth map pipeline

## PR: Add dedicated clean Earth scale launchers

* Refactored WorldPainter generation into one shared core with general and
  dedicated 1:8000, 1:4000, and 1:2000 launchers.
* Added canonical scale profiles, the backward-compatible `preview` alias, 20k
  source validation, resize-aware spawn coordinates, integer bounds, and unique
  output manifests/projects.
* Routed progress through the Run Script output, expanded static and mutation
  tests, and documented profile inputs, scale relationships, and runtime checks.

## PR: Fix WorldPainter 2.27.0 vegetation layer lookup

* Replaced description-style vegetation layer aliases with WorldPainter's exact
  built-in layer names and a central registry.
* Converted vegetation application from positional indexes to checked semantic
  keys and made preflight report every resolved built-in layer.
* Extended source validation and mutation coverage for canonical layer names,
  preflight ordering, and vegetation key integrity.

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

## PR: Repair XenoFactions WorldPainter 2.27.0 pipeline

* Replaced machine-specific source configuration with `scriptDir`-relative file
  resolution and isolated all generated projects/manifests under `generated/`.
* Added smoke, preview, and production profiles with resize-aware dimensions,
  effective-scale manifests, GUI parameters, numeric version checks, and API-only
  preflight execution.
* Corrected legacy Anvil `Platform` resolution, river and vegetation filters, all
  stage reporting, and chunk-aligned partial-region validation.
* Reworked static validation around parsed filter chains and added mutation tests
  for invalid map-format, filter, path, profile, and output behavior.
* Expanded the XenoFactions guide with WorldPainter 2.27.0 commands, known failure
  causes, output expectations, and the required visual/export checklist.
