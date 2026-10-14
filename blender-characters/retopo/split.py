"""Split the lineup sculpt into 6 characters (by island centroid x), scale to metres, save each."""
import bpy, bmesh, sys
from mathutils import Vector
src, outdir = sys.argv[1], sys.argv[2]
NAMES = ["Rebel", "Racer", "Collector", "NatureSpirit", "Scholar", "Trickster"]
CUTS = [-0.62, -0.30, 0.015, 0.30, 0.60]
SCALE = 1.5
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ob = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
me = ob.data
me.transform(ob.matrix_world)
bm = bmesh.new(); bm.from_mesh(me)
bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
zmin = min(v.co.z for v in bm.verts)
# islands
label = [-1] * len(bm.verts)
isl = 0; info = []
for v in bm.verts:
    if label[v.index] >= 0: continue
    stack = [v]; label[v.index] = isl; members = []
    while stack:
        a = stack.pop(); members.append(a.index)
        for e in a.link_edges:
            b = e.other_vert(a)
            if label[b.index] < 0: label[b.index] = isl; stack.append(b)
    cx = sum(bm.verts[i].co.x for i in members) / len(members)
    info.append(sum(1 for c in CUTS if cx > c))
    isl += 1
print("islands", isl)
for ci, name in enumerate(NAMES):
    nb = bmesh.new()
    vmap = {}
    for f in bm.faces:
        if info[label[f.verts[0].index]] != ci: continue
        vs = []
        for v in f.verts:
            if v.index not in vmap:
                vmap[v.index] = nb.verts.new((v.co - Vector((0, 0, zmin))) * SCALE)
            vs.append(vmap[v.index])
        try: nb.faces.new(vs)
        except ValueError: pass
    xs = [v.co.x for v in nb.verts]; cx = (min(xs) + max(xs)) / 2
    for v in nb.verts: v.co.x -= cx
    m2 = bpy.data.meshes.new(name); nb.to_mesh(m2); nb.free()
    o2 = bpy.data.objects.new(name, m2)
    print(name, len(m2.vertices), "height", max(v.co.z for v in m2.vertices))
    sc = bpy.data.scenes.new(name); sc.collection.objects.link(o2)
    bpy.data.libraries.write(f"{outdir}/{name}_sculpt.blend", {o2}, compress=True)
