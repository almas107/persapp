import bpy, bmesh, sys, subprocess, os, time
name, faces = sys.argv[1], int(sys.argv[2])
voxel = float(sys.argv[3]) if len(sys.argv) > 3 else 0.004
S = os.environ.get("RETOPO_DIR", "retopo_work")
IM = os.environ.get("INSTANT_MESHES", "Instant Meshes")
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(f"{S}/{name}_sculpt.blend") as (src, dst):
    dst.objects = src.objects
hi = dst.objects[0]; bpy.context.scene.collection.objects.link(hi)
v = hi.copy(); v.data = hi.data.copy(); bpy.context.scene.collection.objects.link(v)
m = v.modifiers.new("v", "REMESH")
if os.environ.get("REMESH_MODE", "VOXEL") == "VOXEL":
    m.mode = "VOXEL"; m.voxel_size = voxel
else:
    m.mode = "SMOOTH"; m.octree_depth = int(os.environ.get("OCTREE", "9")); m.scale = 0.99
    m.use_remove_disconnected = True; m.threshold = 0.5
bpy.context.view_layer.objects.active = v
bpy.ops.object.modifier_apply(modifier="v")
bm = bmesh.new(); bm.from_mesh(v.data); bm.verts.ensure_lookup_table()
seen, comps = set(), []
for a in bm.verts:
    if a.index in seen: continue
    st = [a]; seen.add(a.index); comp = []
    while st:
        x = st.pop(); comp.append(x)
        for e in x.link_edges:
            y = e.other_vert(x)
            if y.index not in seen: seen.add(y.index); st.append(y)
    comps.append(comp)
comps.sort(key=len, reverse=True)
print("components", [len(c) for c in comps[:5]], len(comps))
bmesh.ops.delete(bm, geom=[x for c in comps[1:] for x in c], context="VERTS")
obj_in, obj_out = f"{S}/{name}_vox.obj", f"{S}/{name}_quad.obj"
with open(obj_in, "w") as fh:
    for x in bm.verts: fh.write("v %f %f %f\n" % tuple(x.co))
    bm.verts.index_update()
    for f in bm.faces: fh.write("f " + " ".join(str(x.index + 1) for x in f.verts) + "\n")
bm.free()
t = time.time()
r = subprocess.run([IM, obj_in, "-o", obj_out, "-f", str(faces), "-r", "4", "-p", "4", "-S", "4", "-c", sys.argv[4] if len(sys.argv) > 4 else "35", "-d", "-t", "4"],
                   capture_output=True, text=True, cwd=None)
print("instant meshes", r.returncode, time.time() - t, r.stdout[-300:], r.stderr[-300:])
verts, fcs = [], []
for line in open(obj_out):
    if line.startswith("v "): verts.append(tuple(float(a) for a in line.split()[1:4]))
    elif line.startswith("f "): fcs.append([int(a.split("/")[0]) - 1 for a in line.split()[1:]])
me = bpy.data.meshes.new(name + "_retopo"); me.from_pydata(verts, [], fcs); me.validate()
lo = bpy.data.objects.new(name + "_retopo", me); bpy.context.scene.collection.objects.link(lo)
sw = lo.modifiers.new("snap", "SHRINKWRAP"); sw.target = hi; sw.wrap_method = "NEAREST_SURFACEPOINT"
bpy.context.view_layer.objects.active = lo
bpy.ops.object.modifier_apply(modifier="snap")
for p in me.polygons: p.use_smooth = True
import collections
print(name, "retopo verts", len(me.vertices), "faces", len(me.polygons), collections.Counter(len(p.vertices) for p in me.polygons))
bpy.data.objects.remove(v)
bpy.data.libraries.write(f"{S}/{name}_retopo.blend", {lo, hi}, compress=True)
