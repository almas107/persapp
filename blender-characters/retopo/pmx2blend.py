"""Minimal PMX 2.0/2.1 reader -> .blend (mesh + vertex-morph shape keys + bones as vertex groups)."""
import sys, struct, bpy
from mathutils import Vector

class R:
    def __init__(s, b): s.b, s.o = b, 0
    def u(s, f):
        v = struct.unpack_from("<" + f, s.b, s.o); s.o += struct.calcsize("<" + f); return v
    def i(s): return s.u("i")[0]
    def f(s): return s.u("f")[0]
    def B(s): return s.u("B")[0]
    def t(s):
        n = s.i(); raw = s.b[s.o:s.o + n]; s.o += n
        return raw.decode("utf-16-le" if s.enc == 0 else "utf-8", "replace")
    def idx(s, size, unsigned=False):
        fmt = {1: "B" if unsigned else "b", 2: "H" if unsigned else "h", 4: "i"}[size]
        return s.u(fmt)[0]

def read(path):
    r = R(open(path, "rb").read())
    assert r.b[:4] == b"PMX ", r.b[:4]
    r.o = 4; ver = r.f(); n = r.B(); g = r.u("B" * n)
    r.enc, addu, vis, tis, mis, bis, mos, ris = g[:8]
    name, name_en, com, com_en = r.t(), r.t(), r.t(), r.t()
    nv = r.i(); V = []; W = []
    for _ in range(nv):
        p = r.u("3f"); nrm = r.u("3f"); uv = r.u("2f")
        for _a in range(addu): r.u("4f")
        dt = r.B()
        if dt == 0: w = [(r.idx(bis), 1.0)]
        elif dt == 1:
            a, b = r.idx(bis), r.idx(bis); x = r.f(); w = [(a, x), (b, 1 - x)]
        elif dt in (2, 4):
            ids = [r.idx(bis) for _ in range(4)]; ws = r.u("4f"); w = list(zip(ids, ws))
        elif dt == 3:
            a, b = r.idx(bis), r.idx(bis); x = r.f(); r.u("9f"); w = [(a, x), (b, 1 - x)]
        r.f()
        V.append((p, uv)); W.append(w)
    nf = r.i(); F = [r.idx(vis, True) for _ in range(nf)]
    nt = r.i(); T = [r.t() for _ in range(nt)]
    nm = r.i(); M = []
    for _ in range(nm):
        mn = r.t(); r.t(); diff = r.u("4f"); r.u("3f"); r.f(); r.u("3f"); flag = r.B(); r.u("4f"); r.f()
        tex = r.idx(tis); r.idx(tis); r.B(); tf = r.B()
        if tf == 0: r.idx(tis)
        else: r.B()
        r.t(); cnt = r.i()
        M.append(dict(name=mn, diffuse=diff, tex=T[tex] if 0 <= tex < len(T) else None, count=cnt))
    nb = r.i(); BN = []
    for _ in range(nb):
        bn = r.t(); r.t(); pos = r.u("3f"); par = r.idx(bis); r.i(); fl = r.u("H")[0]
        if fl & 1: r.idx(bis)
        else: r.u("3f")
        if fl & 0x300: r.idx(bis); r.f()
        if fl & 0x400: r.u("3f")
        if fl & 0x800: r.u("6f")
        if fl & 0x2000: r.i()
        if fl & 0x20:
            r.idx(bis); r.i(); r.f(); nl = r.i()
            for _l in range(nl):
                r.idx(bis)
                if r.B(): r.u("6f")
        BN.append((bn, pos, par))
    nmo = r.i(); MO = []
    for _ in range(nmo):
        mn = r.t(); r.t(); panel = r.B(); typ = r.B(); cnt = r.i(); offs = []
        for _o in range(cnt):
            if typ in (0, 9): r.idx(mos); r.f()
            elif typ == 1: offs.append((r.idx(vis, True), r.u("3f")))
            elif typ == 2: r.idx(bis); r.u("7f")
            elif typ in (3, 4, 5, 6, 7): r.idx(vis, True); r.u("4f")
            elif typ == 8: r.idx(mis); r.B(); r.u("28f")
            elif typ == 10: r.idx(ris); r.B(); r.u("6f")
            elif typ == 11: r.idx(mos); r.f()
        MO.append(dict(name=mn, panel=panel, type=typ, offs=offs, count=cnt))
    return dict(name=name, V=V, W=W, F=F, M=M, B=BN, MO=MO)

def conv(p, k=0.08):
    return (p[0] * k, p[2] * k, p[1] * k)

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    d = read(src)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new(d["name"] or "pmx")
    verts = [conv(p) for p, uv in d["V"]]
    tris = [(d["F"][i], d["F"][i + 2], d["F"][i + 1]) for i in range(0, len(d["F"]), 3)]
    me.from_pydata(verts, [], tris)
    uvl = me.uv_layers.new(name="UV")
    for loop in me.loops:
        u, v = d["V"][loop.vertex_index][1]
        uvl.data[loop.index].uv = (u, 1 - v)
    # material index per face
    fi = 0
    for mi, m in enumerate(d["M"]):
        mat = bpy.data.materials.new(m["name"]); mat.diffuse_color = m["diffuse"]; me.materials.append(mat)
        for _ in range(m["count"] // 3):
            me.polygons[fi].material_index = mi; fi += 1
    ob = bpy.data.objects.new(d["name"] or "pmx", me); bpy.context.scene.collection.objects.link(ob)
    groups = {}
    for vi, w in enumerate(d["W"]):
        for b, x in w:
            if x > 0 and 0 <= b < len(d["B"]):
                groups.setdefault(b, []).append((vi, x))
    for b, lst in groups.items():
        vg = ob.vertex_groups.new(name=d["B"][b][0])
        for vi, x in lst: vg.add([vi], x, "REPLACE")
    vm = [m for m in d["MO"] if m["type"] == 1]
    if vm:
        ob.shape_key_add(name="Basis")
        for m in vm:
            kb = ob.shape_key_add(name=m["name"] or "morph", from_mix=False)
            for vi, off in m["offs"]:
                kb.data[vi].co = Vector(verts[vi]) + Vector(conv(off))
    import json
    json.dump(dict(name=d["name"], verts=len(verts), tris=len(tris),
                   materials=[(m["name"], m["count"] // 3, m["tex"]) for m in d["M"]],
                   bones=[b[0] for b in d["B"]],
                   morphs=[(m["name"], m["panel"], m["type"], m["count"]) for m in d["MO"]]),
              open(dst + ".json", "w"), ensure_ascii=False, indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=dst)
    print("ok", len(verts), len(tris), len(vm))
