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

## Retopology of the sculpt (current)
`retopo/characters/` holds the six retopologised characters from the lineup sculpt
(`<Name>_retopo.blend`, plus `Lineup_retopo.blend`; preview in `preview_all.png`).
Each character has four objects:
- **Head** (~4.4k verts): MakeHuman CC0 head topology (Makoto-style concentric eye-socket
  loops, nose loops, mouth ring, jaw/cheek flow) fitted to the sculpt's face
  (`makoto_head.py`: landmark alignment, depth fit, projection, eye sockets and
  nose/mouth kept as clean loop zones, skull tucked under the hair).
- **Eyes**: separate eyeballs sitting in the sockets.
- **Hair** (~3.3k quads): sculpted hair re-meshed on its own with Instant Meshes.
- **Body** (~11k quads): body + clothes, Instant Meshes auto-retopo snapped to the sculpt.

Pipeline: `split.py` → `retopo.py <Name> 3600 0.004` (use `REMESH_MODE=SMOOTH` for sculpts whose
normals break the voxel remesher, e.g. Collector / NatureSpirit) → `assemble_retopo.py <Name>`.
Head landmarks per character are in `assemble_retopo.py` (read off orthographic grid renders).

Not done yet (hand-retopo work): Makoto-style hair clumps as separate cone strips,
clothing as separate thick shells with seam-aligned loops, cone-shaped sleeve/trouser
openings, separate 8-sided finger cones, T-pose and rig.
