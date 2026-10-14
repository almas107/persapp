"""Assemble a retopologised character: Makoto-style head (face loops, eye sockets,
eyeballs) fitted to the sculpt + quad retopo of hair / body / clothes.

python assemble_retopo.py <Name>      (RETOPO_DIR, MH_DATA env vars)
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import makoto_head as mkh  # noqa: E402

RD = os.environ.get("RETOPO_DIR", "retopo_work")
MH = os.environ.get("MH_DATA", os.path.join(os.path.dirname(HERE), "mh_data"))

# landmarks read off orthographic grid renders of each sculpt (metres)
LANDMARKS = {
    "Rebel": dict(chin=(-0.015, -0.075, 1.315), eye_z=1.47, width=0.19, tilt=-10, gender=0.2,
                  races={"asian": 0.5, "caucasian": 0.5}),
    "Racer": dict(chin=(0.0, -0.045, 1.26), eye_z=1.385, width=0.21, tilt=0, gender=0.0,
                  races={"asian": 0.6, "caucasian": 0.4}),
    "Collector": dict(chin=(-0.01, -0.07, 1.152), eye_z=1.29, width=0.25, tilt=-6, gender=1.0,
                      races={"african": 1.0}),
    "NatureSpirit": dict(chin=(0.0, -0.068, 1.266), eye_z=1.405, width=0.205, tilt=0, gender=0.0,
                         races={"african": 0.6, "asian": 0.2, "caucasian": 0.2}),
    "Scholar": dict(chin=(-0.045, -0.06, 1.168), eye_z=1.285, width=0.2, tilt=-9, gender=0.0,
                    races={"asian": 0.8, "caucasian": 0.2}),
    "Trickster": dict(chin=(0.01, -0.07, 1.272), eye_z=1.395, width=0.215, tilt=0, gender=1.0,
                      races={"asian": 0.5, "caucasian": 0.5}),
}


IM = os.environ.get("INSTANT_MESHES", "Instant Meshes")


def _hair_region(L, hb, face_y):
    chin = Vector(L["chin"])
    hx, hy = chin.x, chin.y + 0.07

    def inside(c, n=None):
        if c.z < chin.z - 0.005:
            return False
        if (Vector((c.x - hx, c.y - hy, 0))).length > 0.3:
            return False
        if c.z < L["eye_z"] - 0.02 and c.y < face_y - 0.012:
            return False          # hands / props in front of the face
        if c.z > L["eye_z"] + 0.02 or c.y > chin.y + 0.07:
            return True
        loc, nrm, idx, dist = hb.find_nearest(c)
        return loc is None or dist > 0.004
    return inside


def hair_retopo(name, L, hb, body, W, coll):
    """Hair = sculpt surface around the head that is not face skin; retopologised on its own,
    finer and crease-aligned so quads follow the locks (Makoto's hair is a separate mesh)."""
    import subprocess
    face_y = min(p.y for p in W if abs(p.z - L["eye_z"]) < 0.02 and abs(p.x - L["chin"][0]) < 0.02)
    inside = _hair_region(L, hb, face_y)
    vox = f"{RD}/{name}_vox.obj"
    vs, fs = [], []
    for line in open(vox):
        if line.startswith("v "):
            vs.append(Vector([float(a) for a in line.split()[1:4]]))
        elif line.startswith("f "):
            fs.append([int(a) - 1 for a in line.split()[1:]])
    sel = [f for f in fs if inside(sum((vs[i] for i in f), Vector()) / len(f))]
    used = sorted({i for f in sel for i in f})
    m = {o: k for k, o in enumerate(used)}
    hin, hout = f"{RD}/{name}_hair_in.obj", f"{RD}/{name}_hair_q.obj"
    with open(hin, "w") as fh:
        for i in used:
            fh.write("v %f %f %f\n" % tuple(vs[i]))
        for f in sel:
            fh.write("f " + " ".join(str(m[i] + 1) for i in f) + "\n")
    r = subprocess.run([IM, hin, "-o", hout, "-f", os.environ.get("HAIR_FACES", "800"), "-r", "4", "-p", "4",
                        "-S", "4", "-c", "25", "-b", "-d", "-t", "4"], capture_output=True, text=True)
    hv, hf = [], []
    for line in open(hout):
        if line.startswith("v "):
            hv.append(tuple(float(a) for a in line.split()[1:4]))
        elif line.startswith("f "):
            hf.append([int(a.split("/")[0]) - 1 for a in line.split()[1:]])
    # snap the hair quads back onto the sculpted hair surface
    sb = BVHTree.FromPolygons([tuple(v) for v in vs], fs)
    hv = [tuple(sb.find_nearest(Vector(p))[0] or Vector(p)) for p in hv]
    me = bpy.data.meshes.new(f"{name}_Hair")
    me.from_pydata(hv, [], hf)
    me.validate()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(f"{name}_Hair", me)
    coll.objects.link(ob)
    # remove the hair area from the body retopo
    bm = bmesh.new()
    bm.from_mesh(body.data)
    hbvh = BVHTree.FromPolygons(hv, hf)
    kill = []
    for f in bm.faces:
        c = f.calc_center_median()
        if inside(c):
            loc, n_, i_, d = hbvh.find_nearest(c)
            if loc is not None and d < 0.008:
                kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    # body faces left inside the hair region fill holes of the hair retopo: move them into the hair object
    rest = [f for f in bm.faces if inside(f.calc_center_median())]
    hb2 = bmesh.new()
    hb2.from_mesh(me)
    vmap = {}
    for f in rest:
        vs2 = []
        for v in f.verts:
            if v not in vmap:
                vmap[v] = hb2.verts.new(v.co)
            vs2.append(vmap[v])
        try:
            hb2.faces.new(vs2)
        except ValueError:
            pass
    hb2.to_mesh(me)
    hb2.free()
    bmesh.ops.delete(bm, geom=rest, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(body.data)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    print("hair quads", len(me.polygons), "removed from body", len(kill))
    return ob


def main(name):
    L = LANDMARKS[name]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(f"{RD}/{name}_retopo.blend") as (src, dst):
        dst.objects = src.objects
    body = [o for o in dst.objects if o.name.endswith("_retopo")][0]
    sculpt = [o for o in dst.objects if o is not body][0]
    sc = bpy.context.scene
    ref = bpy.data.collections.new("Reference_Sculpt")
    sc.collection.children.link(ref)
    ref.objects.link(sculpt)
    ref.hide_viewport = True
    ref.hide_render = True
    retopo = bpy.data.collections.new(f"{name}_Retopo")
    sc.collection.children.link(retopo)
    retopo.objects.link(body)
    body.name = f"{name}_Body"

    sbvh = BVHTree.FromPolygons([v.co[:] for v in sculpt.data.vertices], [p.vertices[:] for p in sculpt.data.polygons])
    V, F, G, j = mkh.mh_head(MH, L["gender"], L["races"])
    W, eyes = mkh.fit(V, F, G, j, L, sbvh)

    # head skin and eyes as separate objects (like Makoto: face/head mesh + eye meshes)
    def make(nm, faces):
        used = sorted({i for f in faces for i in f})
        m = {o: k for k, o in enumerate(used)}
        me = bpy.data.meshes.new(nm)
        me.from_pydata([tuple(W[i]) for i in used], [], [[m[i] for i in f] for f in faces])
        me.validate()
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new(nm, me)
        retopo.objects.link(ob)
        return ob
    head_f = [f for f, g in zip(F, G) if g == "body"]
    eye_f = [f for f, g in zip(F, G) if g.startswith("helper-")]
    head = make(f"{name}_Head", head_f)
    eyes_ob = make(f"{name}_Eyes", eye_f)
    # Makoto-level density: dissolve every other edge loop (keeps the face loop structure)
    unsub = int(os.environ.get("HEAD_UNSUB", "0"))
    if unsub:
        bm = bmesh.new()
        bm.from_mesh(head.data)
        bmesh.ops.unsubdivide(bm, verts=bm.verts, iterations=unsub)
        bm.to_mesh(head.data)
        bm.free()

    # cut the auto-retopo where the fitted face skin now sits (keep hair and everything else)
    hb = BVHTree.FromPolygons([tuple(W[i]) for i in range(len(W))], head_f)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    kill = []
    chin_z = L["chin"][2]
    for f in bm.faces:
        c = f.calc_center_median()
        if c.z < chin_z - 0.03 or c.z > L["eye_z"] + 0.03 or c.y > L["chin"][1] + 0.07:
            continue
        loc, nrm, idx, dist = hb.find_nearest(c)
        if loc is not None and dist < 0.012:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # drop small floating islands left behind by the cut
    bm.faces.ensure_lookup_table()
    seen, small = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        st, comp = [f], []
        seen.add(f.index)
        while st:
            a = st.pop()
            comp.append(a)
            for e in a.edges:
                for b in e.link_faces:
                    if b.index not in seen:
                        seen.add(b.index)
                        st.append(b)
        if len(comp) < 60:
            small += comp
    bmesh.ops.delete(bm, geom=small, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(body.data)
    bm.free()
    hair = hair_retopo(name, L, hb, body, W, retopo)
    print(name, "head verts", len(head.data.vertices), "eyes", len(eyes_ob.data.vertices),
          "body verts", len(body.data.vertices), "removed", len(kill))
    bpy.ops.wm.save_as_mainfile(filepath=f"{RD}/{name}_final.blend", compress=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else sys.argv[1])
