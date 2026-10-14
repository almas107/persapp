# Blender toon characters (work in progress)

Python/bpy tooling for the six-character lineup (Rebel, Racer, Collector,
Nature Spirit, Scholar, Trickster). Runs with Blender 5.x (`blender -b -P ...`)
or the `bpy` pip module.

## Status
- `toonchars/shading.py`: toon shader with paintable **Light/Shadow mask** color
  attributes, plus Empty-driven **fake light spheres**
  (Texture Coordinate → Length → Less Than → Mix), the two lighting techniques
  from the reference videos.
- `toonchars/rig.py`, `face.py`: FK/IK rig, face controls, expression shape keys.
- `build.py`, `cage.py`, `body.py`, `hair.py`, `assemble.py`: earlier procedural
  attempts (superseded; kept for reference).
- `retopo/`: sculpt pipeline. `split.py` splits the AI lineup sculpt (`model.glb`)
  into six characters; `retopo.py` fuses each one into a single voxel surface and
  auto-retopologizes it with Instant Meshes into ~14k quads. `pmx2blend.py` is
  a minimal MMD `.pmx` importer used to study reference models.

Generated `.blend` files and previews are git-ignored.

## Retopology of the sculpt
`retopo/characters/` holds the six characters from the lineup sculpt
(`<Name>_retopo.blend`, plus `Lineup_retopo.blend`): **Hair** and **Body** quad meshes
re-meshed with Instant Meshes and snapped to the sculpt.
Pipeline: `split.py` -> `retopo.py <Name> 3600 0.004` (use `REMESH_MODE=SMOOTH` for sculpts whose
normals break the voxel remesher, e.g. Collector / NatureSpirit).
