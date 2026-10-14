"""Turns a character spec into a rigged, skinned, face-keyed Blender character."""
import math
import bmesh
import bpy
from mathutils import Vector, Matrix

from . import shading, rig as rigmod, face as facemod
from .meshkit import (Part, V, lerp, loft, ellipsoid, box, cylinder, torus, catmull, resample,
                      chain_weights, mix_weights, smoothstep)
from .body import Torso, Limbs, front_gap, build_head, build_neck, build_shoe, head_frame
from .hair import HairKit, build_hair
from .characters import srgb


def shade_of(c, k=(0.62, 0.56, 0.78)):
    return tuple(max(0.0, a * b) for a, b in zip(c, k))


class Mats:
    """Lazy material registry for one character."""

    def __init__(self, prefix, fake_group):
        self.prefix, self.fg = prefix, fake_group
        self.toon = {}
        self.flat = {}
        self.defs = {}

    def define(self, name, base, shadow=None, rim=0.35):
        self.defs[name] = (base, shadow or shade_of(base), rim)

    def get(self, name):
        if name in self.toon:
            return self.toon[name]
        if name in self.flat:
            return self.flat[name]
        base, shadow, rim = self.defs[name]
        m = shading.toon_material(f"{self.prefix}_{name}", base, shadow, self.fg, rim=rim)
        self.toon[name] = m
        return m

    def flat_def(self, name, color, lit=True):
        self.flat[name] = shading.flat_material(f"{self.prefix}_{name}", color, self.fg if lit else None)


def make_object(part, mats, coll, recalc=True):
    me = bpy.data.meshes.new(part.name)
    me.from_pydata([tuple(v) for v in part.verts], [], part.faces)
    for n in part.mat_names:
        me.materials.append(mats.get(n))
    for i, p in enumerate(me.polygons):
        p.material_index = part.face_mats[i]
        p.use_smooth = i not in part.flat_faces
    me.validate(clean_customdata=False)
    if recalc:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    ob = bpy.data.objects.new(part.name, me)
    coll.objects.link(ob)
    groups = {}
    for i, w in enumerate(part.weights):
        for b, val in w.items():
            groups.setdefault(b, {}).setdefault(val, []).append(i)
    for b, byval in groups.items():
        vg = ob.vertex_groups.new(name=b)
        for val, idx in byval.items():
            vg.add(idx, val, "REPLACE")
    return ob


def bind(ob, rig_ob):
    ob.parent = rig_ob
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig_ob
    return mod


# ==========================================================================
def build_character(spec, coll, fake_group, s_lights=None):
    name = spec["name"]
    P, B, F = spec["P"], dict(spec["B"]), dict(spec["F"])
    P = dict(P)
    sk = rigmod.Skeleton(P)
    s = sk.s
    torso = Torso(sk, B)
    limbs = Limbs(sk, B)
    O = spec["outfit"]

    mats = Mats(name, fake_group)
    mats.define("skin", spec["skin"], spec["skin_shadow"], rim=0.25)
    hs = spec["hair"]
    mats.define("hair", hs["color"], hs["shadow"], rim=0.45)
    mats.define("hair_tie", hs.get("tie", hs["shadow"]))
    for g in O.get("torso", []) + O.get("sleeves", []):
        mats.define(g["name"], g["color"], g.get("shadow"))
    for key in ("pants", "skirt"):
        if key in O:
            mats.define(O[key].get("name", key), O[key]["color"], O[key].get("shadow"))
    mats.define("shoe", O["shoes"]["color"])
    mats.define("sole", O["shoes"]["sole"])
    mats.define("metal", srgb("#c9ccd6"), srgb("#6e6a86"), rim=0.8)
    mats.define("gold", srgb("#d9b25a"), srgb("#8e5f3a"), rim=0.8)
    mats.define("black", srgb("#1b1b1f"), srgb("#0c0c10"))
    mats.define("white", srgb("#f4f4f0"), srgb("#b8b8c8"))
    mats.define("red", srgb("#d22c34"), srgb("#7a1a30"))
    mats.define("yellow", srgb("#f1c232"), srgb("#b07a2a"))
    mats.define("leaf", srgb("#5aa85a"), srgb("#2e6a4a"))
    eye = spec["eye"]
    for n, c in (("eye_white", srgb("#fbfbff")), ("iris", eye), ("iris_dark", spec["eye_dark"]),
                 ("pupil", srgb("#141016")), ("highlight", (1, 1, 1)), ("lash", srgb("#1d1519")),
                 ("brow", spec["brow"]), ("mouth", srgb("#5c1f27")), ("teeth", srgb("#fffaf4")),
                 ("tongue", srgb("#d76f74")), ("blush", srgb("#ec7e86")), ("nose", spec["skin_shadow"]),
                 ("freckle", shade_of(spec["skin_shadow"], (0.9, 0.8, 0.8))), ("eye_bag", srgb("#b39aae")),
                 ("bandage", srgb("#f1d6b0"))):
        mats.flat_def(n, c, lit=n not in ("eye_white", "pupil", "highlight", "lash", "mouth", "teeth"))
    outline_col = shade_of(spec["skin_shadow"], (0.3, 0.25, 0.3))
    outline_mat = shading.outline_material(f"{name}_outline", srgb("#2a1d22"))

    # ------------------------------------------------------------------ head
    head = Part(f"{name}_Head")
    hc = build_head(head, sk, P, "skin")
    head_ob = make_object(head, mats, coll)
    head_c, head_R = head_frame(sk, P)

    # ------------------------------------------------------------------ body
    body = Part(f"{name}_Body")
    build_neck(body, sk, "skin", B.get("neck_r", 0.034))
    for (z0, z1) in O.get("skin_torso", []):
        torso.shell(body, z0, z1, "skin", inflate=0.0, bust=B.get("bust", 0.0))
    for side in ("L", "R"):
        if O.get("skin_arms") is not None:
            limbs.arm(body, side, "skin", t0=O["skin_arms"], t1=1.0)
        limbs.hand(body, side, "skin")
        if O.get("skin_legs"):
            t0, t1 = O["skin_legs"]
            limbs.leg(body, side, "skin", t0=t0, t1=t1)

    # tops
    for g in O.get("torso", []):
        arc = front_gap(g["gap"]) if g.get("gap") else None
        torso.shell(body, g["z0"], g["z1"], g["name"], inflate=g["inflate"], arc=arc,
                    cap0=g.get("cap0", None), bust=g.get("bust", 0.0) * 0.9, flare=g.get("flare", 0.0) * s)
        neck_r = B.get("neck_r", 0.034) * s
        L = torso.levels
        if g.get("hem"):
            mats.define(g["name"] + "_hem", g["hem"])
            torso.shell(body, g["z0"], (torso.z(g["z0"]) + 0.03 * s), g["name"] + "_hem",
                        inflate=g["inflate"] + 0.004, arc=arc, flare=g.get("flare", 0.0) * s)
        if g.get("yoke"):
            mats.define(g["name"] + "_yoke", g["yoke"])
            torso.shell(body, ("under", -0.035), ("neck", -0.008), g["name"] + "_yoke",
                        inflate=g["inflate"] + 0.003, arc=arc)
        if g.get("collar"):
            gap = arc or front_gap(40)
            path = [V(0, 0.012 * s, L["neck"] - 0.012 * s), V(0, 0.018 * s, L["neck"] + 0.035 * s)]
            loft(body, path, [neck_r + 0.03 * s, neck_r + 0.034 * s], [neck_r + 0.028 * s, neck_r + 0.036 * s],
                 mat=g["name"], segs=20, side=(1, 0, 0), arc=gap, cap0=None, cap1=None,
                 weights=lambda p, t: chain_weights(p, sk.chain("chest", "neck"), blend=0.4))
        if g.get("high_collar"):
            path = [V(0, 0.01 * s, L["neck"] - 0.015 * s), V(0, 0.008 * s, L["neck"] + 0.045 * s)]
            loft(body, path, [neck_r + 0.02 * s, neck_r + 0.012 * s], [neck_r + 0.018 * s, neck_r + 0.012 * s],
                 mat=g["name"], segs=20, side=(1, 0, 0), cap0=None, cap1=None,
                 weights=lambda p, t: chain_weights(p, sk.chain("chest", "neck"), blend=0.4))
        if g.get("crew"):
            path = [V(0, 0.01 * s, L["neck"] - 0.012 * s), V(0, 0.009 * s, L["neck"] + 0.006 * s)]
            loft(body, path, neck_r + 0.012 * s, neck_r + 0.012 * s, mat=g["name"], segs=18, side=(1, 0, 0),
                 cap0=None, cap1=None, weights=lambda p, t: chain_weights(p, sk.chain("chest", "neck"), blend=0.4))
        if g.get("hood"):
            ellipsoid(body, V(0, 0.085 * s, L["neck"] - 0.02 * s), (0.10 * s, 0.045 * s, 0.06 * s), g["name"],
                      {"chest": 0.7, "neck": 0.3}, segs=16, rings=10)
        if g.get("buttons"):
            mats.define("button", g["buttons"])
            for i in range(5):
                z = lerp(L["neck"] - 0.03 * s, torso.z(g["z0"]) + 0.05 * s, i / 4)
                rx_, ry_, yo = torso.at(z)
                p = V(0, yo - ry_ - g["inflate"] * s - 0.004 * s, z)
                if i == 1:
                    p.y -= B.get("bust", 0) * 0.02 * s
                ellipsoid(body, p, (0.0065 * s, 0.003 * s, 0.0065 * s), "button",
                          chain_weights(p, sk.chain("spine", "chest")), segs=10, rings=6)
            # placket line
        if g.get("vneck"):
            # white shirt "V" + collar points (the shirt under the sweater)
            mats.define("shirt_v", O.get("shirt_collar", srgb("#f5f5f2")))
            zt, zb = L["neck"] + 0.004 * s, L["chest"] - 0.0 * s
            vs, fs = [], []
            for i in range(6):
                z = lerp(zt, zb, i / 5)
                rx_, ry_, yo = torso.at(z)
                half = (1 - i / 5) * 0.042 * s + 0.001 * s
                yf = yo - ry_ - g["inflate"] * s - 0.0025 * s - B.get("bust", 0) * 0.02 * s
                vs += [V(-half, yf + 0.002 * s, z), V(0, yf - 0.001 * s, z), V(half, yf + 0.002 * s, z)]
            for i in range(5):
                o = i * 3
                fs += [(o, o + 1, o + 4, o + 3), (o + 1, o + 2, o + 5, o + 4)]
            body.add(vs, fs, "shirt_v", [chain_weights(v, sk.chain("chest", "neck")) for v in vs])
            for sg in (1, -1):
                rx_, ry_, yo = torso.at(L["neck"] - 0.02 * s)
                yf = yo - ry_ - g["inflate"] * s - 0.006 * s
                p1 = V(sg * 0.012 * s, yf - 0.004 * s, L["neck"] + 0.012 * s)
                p2 = V(sg * 0.055 * s, yf + 0.012 * s, L["neck"] - 0.002 * s)
                p3 = V(sg * 0.03 * s, yf - 0.002 * s, L["neck"] - 0.04 * s)
                body.add([p1, p2, p3], [(0, 1, 2) if sg > 0 else (0, 2, 1)], "shirt_v",
                         [chain_weights(p, sk.chain("chest", "neck")) for p in (p1, p2, p3)])
        if g.get("letter"):
            add_letter(body, g["letter"], sk, torso, g, mats)
    if O.get("patches"):
        add_patches(body, sk, torso, O, mats)

    # sleeves
    for g in O.get("sleeves", []):
        for side in ("L", "R"):
            limbs.arm(body, side, g["name"], t0=0.0, t1=g["t1"], inflate=g["inflate"], cap0="round",
                      cap1=None, flare=g.get("flare", 0.0) * s)
            if g.get("cuff"):
                mats.define(g["name"] + "_cuff", g["cuff"])
                limbs.arm(body, side, g["name"] + "_cuff", t0=g["t1"] - 0.05, t1=g["t1"],
                          inflate=g["inflate"] + 0.004 + g.get("flare", 0.0), cap0=None, cap1=None)

    # pants / shorts
    if "pants" in O:
        pg = O["pants"]
        top = pg.get("top", ("waist", -0.01))
        torso.shell(body, ("crotch", -0.012), top, pg["name"], inflate=pg["inflate"] + 0.004, cap0="round")
        for side in ("L", "R"):
            t1 = pg["t1"]
            limbs.leg(body, side, pg["name"], t0=0.0, t1=t1, inflate=pg["inflate"], flare=pg.get("flare", 0) * s,
                      cap0="round", cap1=None if t1 < 0.99 else "flat")
            if pg.get("stripe"):
                mats.define("stripe", pg["stripe"])
                outer = 0.0 if side == "L" else math.pi
                limbs.leg(body, side, "stripe", t0=0.02, t1=t1, inflate=pg["inflate"] + 0.0025,
                          arc=(outer - 0.28, outer + 0.28), cap0=None, cap1=None, segs=4)
        if pg.get("belt"):
            mats.define("belt", pg["belt"])
            zt = torso.z(top)
            torso.shell(body, zt - 0.03 * s, zt - 0.005 * s, "belt", inflate=pg["inflate"] + 0.009)
    if "skirt" in O:
        add_skirt(body, sk, torso, O["skirt"])
    if "socks" in O:
        mats.define("socks", O["socks"]["color"])
        for side in ("L", "R"):
            limbs.leg(body, side, "socks", t0=O["socks"]["t0"], t1=1.0, inflate=0.003, cap0=None, cap1="round")
            limbs.leg(body, side, "socks", t0=O["socks"]["t0"], t1=O["socks"]["t0"] + 0.03, inflate=0.006,
                      cap0=None, cap1=None)
    sh = O["shoes"]
    if sh.get("laces"):
        mats.define("lace", sh["laces"])
    for side in ("L", "R"):
        build_shoe(body, sk, side, "shoe", "sole", height=sh.get("height", 0.05), lace_mat="lace" if sh.get("laces") else None)

    # ------------------------------------------------------------------ hair
    hair = Part(f"{name}_Hair")
    bvh = facemod.head_bvh(head_ob)
    kit = HairKit(hair, sk, head_c, head_R, bvh, "hair", torso)
    hs = dict(hs)
    hs["tie_mat"] = "hair_tie"
    build_hair(hs["style"], kit, hs, F)

    # ------------------------------------------------------------------ accessories
    acc = Part(f"{name}_Accessories")
    for a in spec.get("acc", []):
        ACCESSORIES[a](acc, sk, torso, head_c, head_R, F, bvh)

    # ------------------------------------------------------------------ objects
    body_ob = make_object(body, mats, coll)
    hair_ob = make_object(hair, mats, coll)
    acc_ob = make_object(acc, mats, coll) if acc.verts else None
    face_ob, key_names = facemod.build_face(name, F, head_ob, head_c, _FaceMats(mats), coll)

    rig_ob = rigmod.build_armature(name, sk, coll)
    for ob in (body_ob, head_ob, hair_ob, acc_ob, face_ob):
        if ob is None:
            continue
        bind(ob, rig_ob)
        if ob is not face_ob:
            shading.add_mask_attributes(ob)
    shading.add_mask_attributes(face_ob)

    for ob, sub, th in ((body_ob, 1, 0.0035), (hair_ob, 1, 0.003), (head_ob, 0, 0.0028), (acc_ob, 0, 0.0015)):
        if ob is None:
            continue
        if sub:
            m = ob.modifiers.new("Subdivision", "SUBSURF")
            m.levels = 1
            m.render_levels = 1
            m.quality = 2
        shading.add_outline(ob, outline_mat, th * s)

    # face controls
    props = facemod.all_prop_keys()
    rigmod.add_face_props(rig_ob, props)
    look = 1.0 * 0.06 * s
    rigmod.drive_shape_keys(rig_ob, face_ob, props, look)
    rig_ob["character"] = spec["title"]

    # props held in hands
    held = {}
    for pr in spec.get("props", []):
        held[pr] = PROPS[pr](name, sk, coll, mats, rig_ob)

    return dict(rig=rig_ob, body=body_ob, head=head_ob, hair=hair_ob, face=face_ob, acc=acc_ob, sk=sk,
                torso=torso, head_c=head_c, head_R=head_R, props=held, mats=mats, keys=key_names)


class _FaceMats:
    def __init__(self, mats):
        self.m = mats

    def __getitem__(self, k):
        return self.m.get(k)


# ==========================================================================
# Clothing extras
# ==========================================================================
def add_skirt(part, sk, torso, g):
    s = sk.s
    z0 = torso.z(g["top"])
    z1 = z0 - g["length"] * s
    n = 16
    path = [V(0, 0.01 * s, lerp(z0, z1, i / (n - 1))) for i in range(n)]
    r0x, r0y, _ = torso.at(z0)
    rx = lambda t: r0x + 0.016 * s + t ** 0.9 * 0.17 * s
    ry = lambda t: r0y + 0.016 * s + t ** 0.9 * 0.13 * s

    def shape(a, t):
        return 1.0 + 0.045 * t * math.cos(a * 14)

    def wfn(q, p, t):
        side = smoothstep(-0.06 * s, 0.06 * s, q.x)
        k = smoothstep(0.05, 0.9, t) * 0.75
        w = {"hips": 1 - k}
        if k > 0:
            w["thigh.L"] = k * side
            w["thigh.R"] = k * (1 - side)
        return {a: b for a, b in w.items() if b > 1e-4}
    loft(part, path, rx, ry, mat="skirt", segs=56, side=(1, 0, 0), shape=shape, cap0=None, cap1=None,
         weight_fn=wfn)
    # waistband
    torso.shell(part, z0 - 0.025 * s, z0 + 0.005 * s, "skirt", inflate=0.02)


def add_letter(part, letter, sk, torso, g, mats):
    s = sk.s
    cu = bpy.data.curves.new("tmp_letter", "FONT")
    cu.body = letter
    cu.size = 0.07 * s
    cu.extrude = 0.002 * s
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new("tmp_letter", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    z = torso.levels["chest"] - 0.01 * s
    x = 0.072 * s
    rx_, ry_, yo = torso.at(z)
    y = yo - ry_ - g["inflate"] * s - 0.012 * s
    R = Matrix.Rotation(math.radians(90), 3, "X") @ Matrix.Rotation(0, 3, "Z")
    rot_y = Matrix.Rotation(math.radians(-28), 3, "Z")
    verts = [rot_y @ (R @ v.co) + V(x, y + 0.012 * s, z) for v in me.vertices]
    faces = [tuple(p.vertices) for p in me.polygons]
    mats.define("letter", srgb("#8e1f22"))
    part.add(verts, faces, "letter", [chain_weights(v, sk.chain("spine", "chest")) for v in verts], flat=True)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)


def add_patches(part, sk, torso, O, mats):
    s = sk.s
    z = torso.levels["chest"] + 0.012 * s
    rx_, ry_, yo = torso.at(z)
    yf = yo - ry_ - 0.022 * s - 0.004 * s
    ch = sk.chain("spine", "chest")
    for (x, dz, w, h, m) in ((0.085, 0.0, 0.03, 0.016, "red"), (0.085, -0.025, 0.026, 0.01, "yellow"),
                             (-0.085, 0.004, 0.032, 0.014, "white"), (-0.09, -0.022, 0.022, 0.012, "red")):
        p = V(x * s, yf + abs(x) * 0.25 * s, z + dz * s)
        rot = Matrix.Rotation(math.radians(-25 if x > 0 else 25), 3, "Z")
        box(part, p, (w * s, 0.003 * s, h * s), m, chain_weights(p, ch), rot=rot)
    # chequered flag patch
    for i in range(4):
        for j in range(3):
            p = V(0.07 * s + i * 0.006 * s, yf + 0.026 * s, z - 0.05 * s + j * 0.006 * s)
            rot = Matrix.Rotation(math.radians(-28), 3, "Z")
            box(part, p, (0.006 * s, 0.003 * s, 0.006 * s), "black" if (i + j) % 2 else "white",
                chain_weights(p, ch), rot=rot)
    # sleeve stripes
    for side, sg in (("L", 1), ("R", -1)):
        a = sk.j("shoulder", side)
        e = sk.j("elbow", side)
        p = lerp(a, e, 0.45)
        d = (e - a).normalized()
        box(part, p + V(0, -0.038 * s, 0), (0.014 * s, 0.003 * s, 0.03 * s), "red",
            {f"upper_arm.{side}": 1.0}, rot=Matrix.Rotation(math.atan2(d.z, d.x) * -1 - math.pi / 2, 3, "Y"))


# ==========================================================================
# Accessories (weighted into the Accessories mesh)
# ==========================================================================
def _necklace_path(sk, torso, drop, s):
    L = torso.levels
    pts = []
    zt = L["neck"] - 0.005 * s
    for i in range(13):
        a = math.pi * 2 * i / 12
        x = math.sin(a) * 0.05 * s
        y = 0.01 * s - math.cos(a) * 0.04 * s
        z = zt
        if math.cos(a) > 0:
            k = math.cos(a) ** 3
            z = zt - drop * k
            rx_, ry_, yo = torso.at(z)
            y = min(y, yo - ry_ - 0.03 * s) if k > 0.3 else y
        pts.append(V(x, y, z))
    return pts


def acc_cross(part, sk, torso, hc, hR, F, bvh, drop=0.12):
    s = sk.s
    pts = _necklace_path(sk, torso, drop * s, s)
    ch = sk.chain("chest", "neck")
    loft(part, catmull(pts, 4), 0.0022 * s, mat="metal", segs=5, side=(0, 0, 1), cap0=None, cap1=None,
         weights=lambda p, t: chain_weights(p, ch, blend=0.4))
    bottom = min(pts, key=lambda p: p.z)
    c = bottom + V(0, -0.004 * s, -0.03 * s)
    box(part, c, (0.008 * s, 0.006 * s, 0.05 * s), "metal", {"chest": 1.0})
    box(part, c + V(0, 0, 0.01 * s), (0.03 * s, 0.006 * s, 0.008 * s), "metal", {"chest": 1.0})
    # second shorter chain
    pts2 = _necklace_path(sk, torso, drop * 0.55 * s, s)
    loft(part, catmull(pts2, 4), 0.0018 * s, mat="metal", segs=5, side=(0, 0, 1), cap0=None, cap1=None,
         weights=lambda p, t: chain_weights(p, ch, blend=0.4))


def acc_lock_key(part, sk, torso, hc, hR, F, bvh):
    s = sk.s
    ch = sk.chain("chest", "neck")
    for drop, item in ((0.09, "lock"), (0.15, "key")):
        pts = _necklace_path(sk, torso, drop * s, s)
        loft(part, catmull(pts, 4), 0.0015 * s, mat="metal", segs=5, side=(0, 0, 1), cap0=None, cap1=None,
             weights=lambda p, t: chain_weights(p, ch, blend=0.4))
        b = min(pts, key=lambda p: p.z) + V(0, -0.004 * s, 0)
        if item == "lock":
            box(part, b + V(0, 0, -0.02 * s), (0.022 * s, 0.008 * s, 0.018 * s), "metal", {"chest": 1.0})
            torus(part, b + V(0, 0, -0.008 * s), 0.0075 * s, 0.0017 * s, "metal", {"chest": 1.0}, normal=(0, 1, 0),
                  arc=(0, math.pi), segs=10)
        else:
            torus(part, b + V(0, 0, -0.01 * s), 0.0065 * s, 0.0018 * s, "metal", {"chest": 1.0}, normal=(0, 1, 0))
            cylinder(part, b + V(0, 0, -0.016 * s), b + V(0, 0, -0.05 * s), 0.0022 * s, "metal", {"chest": 1.0},
                     segs=6)
            box(part, b + V(0.004 * s, 0, -0.045 * s), (0.007 * s, 0.003 * s, 0.006 * s), "metal", {"chest": 1.0})


def acc_wallet_chain(part, sk, torso, hc, hR, F, bvh):
    s = sk.s
    z = torso.levels["waist"] - 0.03 * s
    rx_, ry_, yo = torso.at(z)
    pts = [V(0.06 * s, yo - ry_ - 0.02 * s, z), V(0.12 * s, yo - ry_ * 0.4, z - 0.14 * s),
           V(0.16 * s, yo, z - 0.22 * s), V(0.15 * s, yo + ry_ * 0.6, z - 0.12 * s),
           V(0.10 * s, yo + ry_ + 0.02 * s, z - 0.03 * s)]
    ch = [("hips", V(0, 0, sk.hips_z + 0.02 * s), V(0, 0, sk.hips_z - 0.10 * s))] + sk.chain("thigh.L")
    loft(part, catmull(pts, 6), 0.0028 * s, mat="metal", segs=6, side=(0, 0, 1), cap0="round", cap1="round",
         weights=lambda p, t: mix_weights({"hips": 1.0}, {"thigh.L": 1.0}, math.sin(math.pi * t) * 0.6))


def acc_glasses(part, sk, torso, hc, hR, F, bvh):
    s = sk.s
    for sg in (1, -1):
        x = sg * F["eye_x"]
        z = hc.z + F["eye_z"]
        hit = bvh.ray_cast(V(x, hc.y - 1, z), V(0, 1, 0), 3.0)
        y = hit[0].y - 0.016 * s if hit[0] else hc.y - hR[1]
        torus(part, V(x, y, z), F["eye_w"] * 1.55, 0.0016 * s, "black", {"head": 1.0}, normal=(0, 1, 0),
              segs=28, tube=6)
        # temple arm back to the ear
        cylinder(part, V(sg * (F["eye_x"] + F["eye_w"] * 1.5), y + 0.004 * s, z + 0.004 * s),
                 V(sg * hR[0] * 1.02, hc.y + 0.02 * s, z + 0.0), 0.0014 * s, "black", {"head": 1.0}, segs=6)
    hit = bvh.ray_cast(V(0, hc.y - 1, hc.z + F["eye_z"]), V(0, 1, 0), 3.0)
    y = hit[0].y - 0.016 * s
    loft(part, [V(F["eye_x"] - F["eye_w"] * 1.55, y, hc.z + F["eye_z"] + 0.004 * s),
                V(0, y - 0.004 * s, hc.z + F["eye_z"] + 0.010 * s),
                V(-F["eye_x"] + F["eye_w"] * 1.55, y, hc.z + F["eye_z"] + 0.004 * s)],
         0.0015 * s, mat="black", segs=6, side=(0, 0, 1), cap0=None, cap1=None, weights={"head": 1.0})


def acc_earrings(part, sk, torso, hc, hR, F, bvh):
    s = sk.s
    for sg in (1, -1):
        p = V(sg * hR[0] * 0.98, hc.y + 0.008 * s, hc.z - (hR[2] + hR[3]) * 0.5 * 0.42)
        ellipsoid(part, p, (0.0045 * s,) * 3, "gold", {"head": 1.0}, segs=10, rings=6)


def acc_leaves(part, sk, torso, hc, hR, F, bvh):
    s = sk.s
    # leaf hair clip + two small leaves tucked behind the ear
    for (az, el, rot, sc) in ((60, 30, 30, 1.0), (75, 18, -10, 0.8), (-70, 25, 200, 0.7)):
        a, e = math.radians(az), math.radians(el)
        p = hc + V(math.sin(a) * math.cos(e) * hR[0] * 1.13, -math.cos(a) * math.cos(e) * hR[1] * 1.13,
                   math.sin(e) * hR[2] * 1.1)
        R = Matrix.Rotation(math.radians(rot), 3, "Y") @ Matrix.Rotation(-a, 3, "Z")
        ellipsoid(part, p, (0.022 * s * sc, 0.003 * s, 0.011 * s * sc), "leaf", {"head": 1.0}, segs=12, rings=6,
                  rot=R)


ACCESSORIES = dict(cross_necklace=acc_cross, lock_key_necklace=acc_lock_key, wallet_chain=acc_wallet_chain,
                   glasses=acc_glasses, earrings=acc_earrings, leaves=acc_leaves)


# ==========================================================================
# Props (separate objects parented to a hand bone)
# ==========================================================================
def _prop_object(part, mats, coll, rig_ob, bone, name):
    ob = make_object(part, mats, coll)
    ob.name = name
    ob.parent = rig_ob
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    # keep the rest-pose world position (bone-parented objects attach at the bone tail)
    bpy.context.view_layer.update()
    pbone = rig_ob.pose.bones[bone]
    attach = rig_ob.matrix_world @ pbone.matrix @ Matrix.Translation(V(0, pbone.bone.length, 0))
    ob.matrix_parent_inverse = attach.inverted()
    shading.add_mask_attributes(ob)
    return ob


def prop_console(name, sk, coll, mats, rig_ob):
    s = sk.s
    part = Part(f"{name}_Console")
    mats.define("console", srgb("#c7ccd6"), srgb("#7b7f9a"))
    mats.define("screen", srgb("#4fa3d9"), srgb("#2f6a9a"))
    c = sk.j("knuckle", "R") + V(0, -0.02 * s, -0.02 * s)
    # lower half (lying in the palms) + upper half (screen) opened ~110 deg
    box(part, c, (0.12 * s, 0.07 * s, 0.012 * s), "console", {})
    box(part, c + V(0, -0.02 * s, -0.0065 * s), (0.04 * s, 0.03 * s, 0.002 * s), "black", {})
    R = Matrix.Rotation(math.radians(-70), 3, "X")
    top = c + V(0, 0.035 * s, 0.006 * s) + R @ V(0, 0.035 * s, 0)
    box(part, top, (0.12 * s, 0.07 * s, 0.01 * s), "console", {}, rot=R)
    box(part, top + R @ V(0, 0, -0.0055 * s), (0.085 * s, 0.05 * s, 0.002 * s), "screen", {}, rot=R)
    return _prop_object(part, mats, coll, rig_ob, "hand.R", f"{name}_Console")


def prop_camera(name, sk, coll, mats, rig_ob):
    s = sk.s
    part = Part(f"{name}_Camera")
    mats.define("cam_body", srgb("#2a2a2e"), srgb("#121216"))
    c = sk.j("knuckle", "R") + V(0, -0.03 * s, 0)
    box(part, c, (0.13 * s, 0.05 * s, 0.08 * s), "cam_body", {})
    cylinder(part, c + V(0.015 * s, -0.024 * s, 0), c + V(0.015 * s, -0.06 * s, 0), 0.028 * s, "black", {}, segs=20)
    cylinder(part, c + V(0.015 * s, -0.06 * s, 0), c + V(0.015 * s, -0.062 * s, 0), 0.02 * s, "screen_glass", {},
             segs=20)
    mats.define("screen_glass", srgb("#5b6f8a"), srgb("#2e3b52"), rim=1.0)
    cylinder(part, c + V(-0.045 * s, 0, 0.04 * s), c + V(-0.045 * s, 0, 0.05 * s), 0.01 * s, "metal", {}, segs=12)
    box(part, c + V(0.04 * s, -0.026 * s, 0.025 * s), (0.016 * s, 0.003 * s, 0.01 * s), "white", {})
    return _prop_object(part, mats, coll, rig_ob, "hand.R", f"{name}_Camera")


PROPS = dict(console=prop_console, camera=prop_camera)
