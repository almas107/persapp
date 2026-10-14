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
- `toonchars/mhbase.py`, `stylize.py`, `mhchar.py`, `build2.py`: experimental
  builder on the CC0 MakeHuman base mesh (needs the MakeHuman `3dobjs/`,
  `targets/`, `rigs/` data in `./mh_data` or `$MH_DATA`; not committed).
- `build.py`, `cage.py`, `body.py`, `hair.py`, `assemble.py`: earlier procedural
  attempts (superseded; kept for reference).
- `retopo/`: sculpt pipeline. `split.py` splits the AI lineup sculpt (`model.glb`)
  into six characters; `retopo.py` fuses each one into a single voxel surface and
  auto-retopologizes it with Instant Meshes into ~14k quads. `pmx2blend.py` is
  a minimal MMD `.pmx` importer used to study reference models.

Generated `.blend` files and previews are git-ignored.
