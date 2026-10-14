"""Character builder v2: anatomical MakeHuman body + body-derived clothing.

Pipeline per character
  1. MakeHuman hm08 base (CC0) morphed with targets (gender / ethnicity / build
     + an anime head recipe), scaled to the character's height.
  2. MakeHuman's artist-made skin weights (163 bones) merged down to an
     animation rig (FK/IK arms & legs, fingers, hair chains, face controls).
  3. Clothing = body faces duplicated and pushed out along the normals
     (exactly how game/MMD characters are built: clothes follow the anatomy and
     share its weights).  Skin under opaque clothing is removed.
  4. Anime face pieces (eyes, lids, lashes, brows, mouth...) projected on the
     head with expression blend shapes; hair = thick tapered clumps.
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

from . import mhbase, stylize, shading, rig as rigmod, face as facemod
from .meshkit import Part, V, lerp, smoothstep, loft, chain_weights, catmull, resample
from .assemble import Mats, make_object, bind, add_skirt, ACCESSORIES, PROPS, add_letter
from .hair import HairKit, build_hair
from .characters import srgb

# ---------------------------------------------------------------------------
# MakeHuman bone -> rig bone
MERGE = {
    "root": "hips", "pelvis.L": "hips", "pelvis.R": "hips",
    "spine05": "spine", "spine04": "spine",
    "spine03": "chest", "spine02": "chest", "spine01": "chest", "breast.L": "chest", "breast.R": "chest",
    "neck01": "neck", "neck02": "neck", "neck03": "neck", "head": "head",
}
for S_ in ("L", "R"):
    MERGE.update({
        f"clavicle.{S_}": f"shoulder.{S_}", f"shoulder01.{S_}": f"shoulder.{S_}",
        f"upperarm01.{S_}": f"upper_arm.{S_}", f"upperarm02.{S_}": f"upper_arm.{S_}",
        f"lowerarm01.{S_}": f"forearm.{S_}", f"lowerarm02.{S_}": f"forearm.{S_}",
        f"wrist.{S_}": f"hand.{S_}",
        f"upperleg01.{S_}": f"thigh.{S_}", f"upperleg02.{S_}": f"thigh.{S_}",
        f"lowerleg01.{S_}": f"shin.{S_}", f"lowerleg02.{S_}": f"shin.{S_}",
        f"foot.{S_}": f"foot.{S_}",
    })
    for i in range(1, 5):
        MERGE[f"metacarpal{i}.{S_}"] = f"hand.{S_}"
    for fi, fn in enumerate(("thumb", "index", "middle", "ring", "pinky"), start=1):
        for k in (1, 2, 3):
            MERGE[f"finger{fi}-{k}.{S_}"] = f"{fn}_{k}.{S_}"
    for t in range(1, 6):
        for k in (1, 2, 3):
            MERGE[f"toe{t}-{k}.{S_}"] = f"toe.{S_}"

LABEL = {"hips": "torso", "spine": "torso", "chest": "torso", "neck": "neck", "head": "head"}
for S_ in ("L", "R"):
    LABEL.update({f"shoulder.{S_}": "torso", f"upper_arm.{S_}": "arm", f"forearm.{S_}": "arm",
                  f"hand.{S_}": "hand", f"thigh.{S_}": "leg", f"shin.{S_}": "leg",
                  f"foot.{S_}": "foot", f"toe.{S_}": "foot"})
    for fn in ("thumb", "index", "middle", "ring", "pinky"):
        for k in (1, 2, 3):
            LABEL[f"{fn}_{k}.{S_}"] = "hand"


class MHSkeleton:
    """Duck-types rig.Skeleton so the existing armature / IK / face-control code is reused."""

    def __init__(self, mh, skel, scale, ground):
        self.P = {}
        self.s = 1.0
        self.mhs = skel

        def jp(n):
            idx = skel["joints"][n]
            c = Vector()
            for i in idx:
                c += mhbase.conv(*mh.v[i])
            return (c / len(idx) - Vector((0, 0, ground))) * scale
        self._jp = jp
        B = skel["bones"]
        h = lambda b: jp(B[b]["head"])
        t = lambda b: jp(B[b]["tail"])
        self.bones = {}

        def add(name, head, tail, parent, roll=(0, -1, 0), deform=True, coll="Body"):
            self.bones[name] = dict(head=Vector(head), tail=Vector(tail), parent=parent, roll=Vector(roll),
                                    deform=deform, coll=coll)
        hip_c = h("spine05")
        self.hips_z = hip_c.z
        add("root", (0, 0, 0), (0, 0.3, 0), None, roll=(0, 0, 1), deform=False, coll="Root")
        add("torso", hip_c, hip_c + Vector((0, 0.2, 0)), "root", roll=(0, 0, 1), deform=False, coll="Root")
        add("hips", hip_c + Vector((0, 0, 0.02)), hip_c - Vector((0, 0, 0.1)), "torso")
        add("spine", hip_c + Vector((0, 0, 0.02)), t("spine04"), "torso")
        add("chest", t("spine04"), t("spine01"), "spine")
        add("neck", h("neck01"), t("neck03"), "chest")
        add("head", h("head"), t("head"), "neck")
        self.spine_z = t("spine04").z
        self.chest_z = (h("spine02").z + t("spine02").z) / 2
        self.neck_z = h("neck01").z
        self.joints = {}
        for S_, sg in (("L", 1), ("R", -1)):
            add(f"shoulder.{S_}", h(f"clavicle.{S_}"), t(f"shoulder01.{S_}"), "chest", roll=(0, 0, 1))
            sh, el, wr = h(f"upperarm01.{S_}"), h(f"lowerarm01.{S_}"), h(f"wrist.{S_}")
            up = (el - sh).cross(wr - el).normalized()
            if up.z < 0:
                up = -up
            add(f"upper_arm.{S_}", sh, el, f"shoulder.{S_}", roll=up)
            add(f"forearm.{S_}", el, wr, f"upper_arm.{S_}", roll=up)
            knuck = h(f"finger3-1.{S_}")
            add(f"hand.{S_}", wr, knuck, f"forearm.{S_}", roll=up)
            for fi, fn in enumerate(("thumb", "index", "middle", "ring", "pinky"), start=1):
                for k in (1, 2, 3):
                    b = f"finger{fi}-{k}.{S_}"
                    add(f"{fn}_{k}.{S_}", h(b), t(b), f"hand.{S_}" if k == 1 else f"{fn}_{k - 1}.{S_}",
                        roll=up, coll="Fingers")
            hp, kn, an = h(f"upperleg01.{S_}"), h(f"lowerleg01.{S_}"), h(f"foot.{S_}")
            ball = h(f"toe3-1.{S_}")
            ball = Vector((ball.x, ball.y, max(ball.z, 0.015)))
            toe = ball + Vector((0, -0.05, 0)) * scale * 10 * 0.1
            add(f"thigh.{S_}", hp, kn, "hips")
            add(f"shin.{S_}", kn, an, f"thigh.{S_}")
            add(f"foot.{S_}", an, ball, f"shin.{S_}", roll=(0, 0, 1))
            add(f"toe.{S_}", ball, toe, f"foot.{S_}", roll=(0, 0, 1))
            add(f"foot_ik.{S_}", an, an + Vector((0, -0.12, 0)), "root", roll=(0, 0, 1), deform=False, coll="IK")
            add(f"knee_pole.{S_}", kn + Vector((0, -0.4, 0)), kn + Vector((0, -0.47, 0)), "root", roll=(0, 0, 1),
                deform=False, coll="IK")
            add(f"hand_ik.{S_}", wr, wr + (wr - el).normalized() * 0.09, "root", roll=up, deform=False, coll="IK")
            add(f"elbow_pole.{S_}", el + Vector((0, 0.35, 0)), el + Vector((0, 0.42, 0)), "root", roll=(0, 0, 1),
                deform=False, coll="IK")
            if S_ == "L":
                self.joints.update(shoulder=sh, elbow=el, wrist=wr, knuckle=knuck, hip=hp, knee=kn, ankle=an,
                                   ball=ball, toe=toe)
                self.arm_dir = (wr - el).normalized()
                self.hand_up = up
        self.eye = jp("l-eye____head") if "l-eye____head" in skel["joints"] else None
        top = t("head")
        self.crown = top.z
        self.fingers = {}

    def finish(self, head_c, crown, chin):
        self.crown, self.chin = crown, chin
        H = crown
        self.bones["eye_target"] = dict(head=Vector((0, -0.45, head_c.z)), tail=Vector((0, -0.45, head_c.z + 0.05)),
                                        parent="head", roll=Vector((0, -1, 0)), deform=False, coll="Face")
        self.bones["face_ctrl"] = dict(head=Vector((0, 0, H + 0.1)), tail=Vector((0, 0, H + 0.16)), parent="head",
                                       roll=Vector((0, -1, 0)), deform=False, coll="Face")

    # helpers used by hair / accessories
    def add_chain(self, prefix, points, parent, coll="Hair"):
        return rigmod.Skeleton.add_chain(self, prefix, points, parent, coll)

    def seg(self, name):
        b = self.bones[name]
        return (name, b["head"], b["tail"])

    def chain(self, *names):
        return [self.seg(n) for n in names]

    def j(self, name, side="L"):
        p = self.joints[name]
        return p if side == "L" else Vector((-p.x, p.y, p.z))


class TorsoProxy:
    """Cross-section lookups on the real body (used by hair, skirt, accessories)."""

    def __init__(self, verts, labels, sk):
        self.sk = sk
        self.pts = [(v, l) for v, l in zip(verts, labels) if l == "torso"]
        self.levels = dict(hips=sk.hips_z, waist=sk.spine_z, chest=sk.chest_z, neck=sk.neck_z,
                           under=sk.neck_z - 0.07, shoulder=sk.neck_z - 0.03, crotch=sk.joints["hip"].z - 0.05)
        self._cache = {}

    def z(self, key):
        if isinstance(key, (int, float)):
            return key
        if isinstance(key, tuple):
            return self.levels[key[0]] + key[1]
        return self.levels[key]

    def at(self, z):
        k = round(z, 3)
        if k in self._cache:
            return self._cache[k]
        sl = [v for v, _ in self.pts if abs(v.z - z) < 0.015 and abs(v.x) < 0.2]
        if not sl:
            zz = min(max(z, self.levels["crotch"]), self.levels["neck"])
            sl = [v for v, _ in self.pts if abs(v.z - zz) < 0.02 and abs(v.x) < 0.2] or [Vector((0.1, 0.08, z))]
        rx = max(abs(v.x) for v in sl)
        y0, y1 = min(v.y for v in sl), max(v.y for v in sl)
        out = (rx, (y1 - y0) / 2, (y0 + y1) / 2)
        self._cache[k] = out
        return out


# ---------------------------------------------------------------------------
def load_skel(root):
    with open(os.path.join(root, "rigs", "default.mhskel")) as fh:
        skel = json.load(fh)
    with open(os.path.join(root, "rigs", "default_weights.mhw")) as fh:
        w = json.load(fh)["weights"]
    return skel, w


def rig_bone_for(mhbone, skel):
    b = mhbone
    while b is not None:
        if b in MERGE:
            return MERGE[b]
        b = skel["bones"].get(b, {}).get("parent")
    return "head"


def build_body_mesh(spec, root):
    M = spec["mh"]
    mh = mhbase.MHBase(root)
    mh.macro(gender=M["gender"], races=M["races"], proportions=1.0, muscle=M.get("muscle", 0.5),
             weight=M.get("weight", 0.5), height=M.get("mh_height", 0.0))
    recipe = dict(stylize.ANIME_MALE if M["gender"] > 0.5 else stylize.ANIME_FEMALE)
    recipe.update(M.get("recipe", {}))
    stylize.apply_recipe(mh, recipe)
    skel, wts = load_skel(root)
    verts, faces, uvs, fg, remap = mh.submesh(["body"])
    ground = mh.joints()["ground"].z
    zs = [p.z - ground for p in verts]
    scale = spec["P"]["height"] / max(zs)
    verts = [(p - Vector((0, 0, ground))) * scale for p in verts]
    sk = MHSkeleton(mh, skel, scale, ground)
    # weights (merged)
    vw = [dict() for _ in verts]
    for b, lst in wts.items():
        rb = rig_bone_for(b, skel)
        for i, w in lst:
            if i in remap:
                d = vw[remap[i]]
                d[rb] = d.get(rb, 0.0) + w
    for d in vw:
        s = sum(d.values()) or 1.0
        for k in d:
            d[k] /= s
    joints = {k: (p - Vector((0, 0, ground))) * scale for k, p in mh.joints().items()}
    verts, faces, vw = _clean(verts, faces, vw, joints)
    return verts, faces, vw, sk, joints, scale


def _clean(verts, faces, vw, joints):
    """Anime face clean-up on the real topology (eye openings filled, nose/lips relaxed)."""
    me = bpy.data.meshes.new("_tmp")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    a = me.attributes.new("orig", "INT", "POINT")
    for i in range(len(verts)):
        a.data[i].value = i + 1
    stylize.clean_face(me, joints)
    orig = [d.value - 1 for d in me.attributes["orig"].data]
    nv = [v.co.copy() for v in me.vertices]
    nf = [list(p.vertices) for p in me.polygons]
    nw = [dict(vw[o]) if 0 <= o < len(vw) else {"head": 1.0} for o in orig]
    bpy.data.meshes.remove(me)
    return nv, nf, nw


# ---------------------------------------------------------------------------
class BodyData:
    def __init__(self, verts, faces, vw, sk):
        self.verts, self.faces, self.vw, self.sk = verts, faces, vw, sk
        self.dom = [max(d, key=d.get) if d else "head" for d in vw]
        self.label = [LABEL.get(b, "torso") for b in self.dom]
        # vertex normals
        nrm = [Vector() for _ in verts]
        for f in faces:
            a, b, c = verts[f[0]], verts[f[1]], verts[f[2]]
            n = (b - a).cross(c - a)
            for i in f:
                nrm[i] += n
        self.nrm = [n.normalized() if n.length else Vector((0, 0, 1)) for n in nrm]
        # limb params: arm a in [0,2] (shoulder->wrist), leg l in [0,2] (hip->ankle)
        self.arm = [None] * len(verts)
        self.leg = [None] * len(verts)
        for i, (p, b) in enumerate(zip(verts, self.dom)):
            side = b[-1] if b.endswith((".L", ".R")) else ("L" if p.x > 0 else "R")
            if b.startswith(("upper_arm", "forearm", "hand", "thumb", "index", "middle", "ring", "pinky")):
                self.arm[i] = self._param(p, [f"upper_arm.{side}", f"forearm.{side}"])
            if b.startswith(("thigh", "shin", "foot", "toe")):
                self.leg[i] = self._param(p, [f"thigh.{side}", f"shin.{side}"])

    def _param(self, p, names):
        best = None
        for k, n in enumerate(names):
            b = self.sk.bones[n]
            ab = b["tail"] - b["head"]
            t = (p - b["head"]).dot(ab) / ab.length_squared
            tc = max(0.0, min(1.0, t))
            d = (p - (b["head"] + ab * tc)).length
            val = k + (max(0.0, t) if k == len(names) - 1 else tc)
            if best is None or d < best[0]:
                best = (d, val)
        return best[1]


def garment(body, name, pred, offset, flare=None, gap=None, closed_hem=True):
    """Duplicate body faces whose verts all satisfy pred(i), push out along normals."""
    sel = [f for f in body.faces if all(pred(i) for i in f)]
    if gap:
        x_gap, z_low = gap
        sel = [f for f in sel if not all(abs(body.verts[i].x) < x_gap and body.nrm[i].y < -0.25 and
                                         body.verts[i].z > z_low for i in f)]
    remap = {}
    verts, faces, wts = [], [], []
    for f in sel:
        nf = []
        for i in f:
            if i not in remap:
                remap[i] = len(verts)
                p = body.verts[i] + body.nrm[i] * offset
                if flare:
                    p = flare(i, p)
                verts.append(p)
                wts.append(dict(body.vw[i]))
            nf.append(remap[i])
        faces.append(nf)
    _smooth_boundary(verts, faces)
    return verts, faces, wts, set(remap)


def _smooth_boundary(verts, faces, iters=6):
    from collections import Counter, defaultdict
    ec = Counter()
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1]):
            ec[(min(a, b), max(a, b))] += 1
    nb = defaultdict(list)
    for (a, b), c in ec.items():
        if c == 1:
            nb[a].append(b)
            nb[b].append(a)
    for _ in range(iters):
        new = {}
        for v, ns in nb.items():
            if len(ns) == 2:
                new[v] = verts[v] * 0.5 + (verts[ns[0]] + verts[ns[1]]) * 0.25
        for v, p in new.items():
            verts[v] = p


# ---------------------------------------------------------------------------
def build(spec, coll, fake_group, root):
    name = spec["name"]
    verts, faces, vw, sk, joints, scale = build_body_mesh(spec, root)
    body = BodyData(verts, faces, vw, sk)
    lab, arm, leg = body.label, body.arm, body.leg
    O = spec["outfit2"]

    # ---------------- head frame + face layout
    head_pts = [verts[i] for i in range(len(verts)) if lab[i] == "head"]
    crown = max(p.z for p in head_pts)
    eye_l = joints["l-eye"]
    chin = min(p.z for p in head_pts if abs(p.x) < 0.01 and p.y < eye_l.y + 0.03)
    crania = [p for p in head_pts if p.z > eye_l.z]
    hc = Vector((0.0, (min(p.y for p in crania) + max(p.y for p in crania)) / 2, eye_l.z + 0.012))
    rx = max(abs(p.x) for p in crania if abs(p.z - hc.z - 0.03) < 0.02)
    ry = (max(p.y for p in crania) - min(p.y for p in crania)) / 2
    head_R = (rx, ry, crown - hc.z, hc.z - chin)
    sk.finish(hc, crown, chin)
    hh = crown - chin

    # ---------------- materials
    mats = Mats(name, fake_group)
    mats.define("skin", spec["skin"], spec["skin_shadow"], rim=0.25)
    hs = spec["hair"]
    mats.define("hair", hs["color"], hs["shadow"], rim=0.45)
    mats.define("hair_tie", hs.get("tie", hs["shadow"]))
    for n, c in (("metal", "#c9ccd6"), ("gold", "#d9b25a"), ("black", "#1b1b1f"), ("white", "#f4f4f0"),
                 ("red", "#d22c34"), ("yellow", "#f1c232"), ("leaf", "#5aa85a")):
        mats.define(n, srgb(c))
    for n, c in (("eye_white", srgb("#fbfbff")), ("iris", spec["eye"]), ("iris_dark", spec["eye_dark"]),
                 ("pupil", srgb("#141016")), ("highlight", (1, 1, 1)), ("lash", srgb("#1d1519")),
                 ("brow", spec["brow"]), ("mouth", srgb("#5c1f27")), ("teeth", srgb("#fffaf4")),
                 ("tongue", srgb("#d76f74")), ("blush", srgb("#ec7e86")), ("nose", spec["skin_shadow"]),
                 ("freckle", spec["skin_shadow"]), ("eye_bag", srgb("#b39aae")), ("bandage", srgb("#f1d6b0"))):
        mats.flat_def(n, c, lit=n not in ("eye_white", "pupil", "highlight", "lash", "mouth", "teeth"))
    outline_mat = shading.outline_material(f"{name}_outline", srgb("#2a1d22"))

    # ---------------- clothing (body-derived shells)
    covered = set()
    shells = []
    for g in O["garments"]:
        mats.define(g["name"], g["color"], g.get("shadow"))
        if g["kind"] == "shoes":
            continue
        pred = make_pred(g, body, sk)
        flare = make_flare(g, body, sk)
        gv, gf, gw, used = garment(body, g["name"], pred, g.get("offset", 0.006),
                                   flare=flare, gap=(g["gap"], g.get("gap_z", 0)) if g.get("gap") else None)
        shells.append((g, gv, gf, gw))
        if g.get("hides", True):
            covered |= {i for i in used if all_inside(i, pred, body)}
    # ---------------- body (skin) without covered faces
    bodyp = Part(f"{name}_Body")
    if any(g["kind"] == "shoes" for g in O["garments"]):
        covered |= {i for i in range(len(verts)) if lab[i] == "foot" or (leg[i] is not None and leg[i] > 1.93)}
    keep = [f for f in faces if not all(i in covered for i in f)]
    bodyp.add(verts, keep, "skin", vw)
    clothp = Part(f"{name}_Clothes")
    for g, gv, gf, gw in shells:
        clothp.add(gv, gf, g["name"], gw)
    for g in O["garments"]:
        if g["kind"] == "shoes":
            mats.define("sole", g.get("sole", srgb("#2a2420")))
            for side in ("L", "R"):
                _shoe(clothp, sk, side, g["name"], "sole", body)

    # skirt / extras via the older generators (they use the TorsoProxy)
    torso = TorsoProxy(verts, lab, sk)
    if O.get("skirt"):
        mats.define("skirt", O["skirt"]["color"], O["skirt"].get("shadow"))
        add_skirt(clothp, sk, torso, O["skirt"])

    # ---------------- objects
    body_ob = make_object(bodyp, mats, coll)
    _remove_loose(body_ob)
    cloth_ob = make_object(clothp, mats, coll, recalc=False)
    # face / hair need the head surface
    bvh = BVHTree.FromPolygons([tuple(v) for v in verts], [tuple(f) for f in faces])

    F = face_layout(spec, joints, hc, hh)
    face_ob, keys = facemod.build_face(name, F, body_ob, hc, _FM(mats), coll)

    hair = Part(f"{name}_Hair")
    kit = HairKit(hair, sk, hc, head_R, bvh, "hair", torso)
    _patch_kit(kit, body, hc)
    H = dict(hs)
    H["tie_mat"] = "hair_tie"
    build_hair(hs["style"], kit, H, F)
    hair_ob = make_object(hair, mats, coll)

    acc = Part(f"{name}_Accessories")
    for a in spec.get("acc", []):
        ACCESSORIES[a](acc, sk, torso, hc, head_R, F, bvh)
    acc_ob = make_object(acc, mats, coll) if acc.verts else None

    rig_ob = rigmod.build_armature(name, sk, coll)
    for ob in (body_ob, cloth_ob, hair_ob, acc_ob, face_ob):
        if ob is None:
            continue
        bind(ob, rig_ob)
        shading.add_mask_attributes(ob)
    for ob, sub, th, solid in ((body_ob, 1, 0.0025, 0), (cloth_ob, 1, 0.003, 0.004), (hair_ob, 1, 0.0025, 0),
                               (acc_ob, 0, 0.0015, 0)):
        if ob is None:
            continue
        if solid:
            m = ob.modifiers.new("Thickness", "SOLIDIFY")
            m.thickness = solid
            m.offset = -1
            m.use_even_offset = True
        if sub:
            m = ob.modifiers.new("Subdivision", "SUBSURF")
            m.levels = 1
            m.render_levels = 1
        shading.add_outline(ob, outline_mat, th)
    _face_light_mask(body_ob, face_ob, hc)
    props = facemod.all_prop_keys()
    rigmod.add_face_props(rig_ob, props)
    rigmod.drive_shape_keys(rig_ob, face_ob, props, 0.06)
    rig_ob["character"] = spec["title"]
    held = {}
    for pr in spec.get("props", []):
        held[pr] = PROPS[pr](name, sk, coll, mats, rig_ob)
    return dict(rig=rig_ob, body=body_ob, clothes=cloth_ob, hair=hair_ob, face=face_ob, acc=acc_ob, sk=sk,
                torso=torso, head_c=hc, head_R=head_R, props=held, mats=mats, keys=keys)


class _FM:
    def __init__(self, m):
        self.m = m

    def __getitem__(self, k):
        return self.m.get(k)


def _remove_loose(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()


def all_inside(i, pred, body):
    return pred(i)


def face_layout(spec, joints, hc, hh):
    e = joints["l-eye"]
    Fs = spec.get("face", {})
    ew = Fs.get("eye_w", 0.0155)
    eh = Fs.get("eye_h", 0.0175)
    F = dict(eye_x=abs(e.x) * 1.08 + 0.002, eye_z=e.z - hc.z - 0.004, eye_w=ew, eye_h=eh, eye_tilt=6, iris=1.0,
             lash=0.0055, brow_gap=0.011, brow_t=0.0034, brow_arch=0.003,
             mouth_z=(joints["mouth"].z - hc.z) - 0.004, mouth_w=0.0125, nose_z=(e.z - hc.z) - hh * 0.2,
             blush=0.0, blush_on=True)
    F.update(Fs)
    return F


def _patch_kit(kit, body, hc):
    """Hair kit on the real skull: scalp points are projected on the head surface."""
    bvh = kit.bvh
    ell = kit.scalp

    def scalp(az, el, lift=1.0):
        p = ell(az, el, 1.0)
        d = (p - hc)
        hit = bvh.ray_cast(hc + d * 3.0, -d.normalized(), 10.0)
        surf = hit[0] if hit[0] is not None else p
        return hc + (surf - hc) * (1.0 + (lift - 1.0) * 1.25) + (surf - hc).normalized() * 0.004
    kit.scalp = scalp

    head_faces = [f for f in body.faces if all(body.label[i] in ("head",) for i in f)]

    def cap(hairline, lift=1.04, mat=None, rows=None, cols=None, part_line=False):
        """Scalp cap = head faces above the hairline pushed out (follows the real skull)."""
        sel = []
        for f in head_faces:
            ok = True
            for i in f:
                p = body.verts[i] - hc
                az = math.degrees(math.atan2(p.x, -p.y))
                el = math.degrees(math.atan2(p.z, math.hypot(p.x, p.y) + 1e-9))
                if el < hairline(az) - 2:
                    ok = False
                    break
            if ok:
                sel.append(f)
        remap, vs, fs = {}, [], []
        thick = 0.006 + (lift - 1.0) * 0.12
        for f in sel:
            nf = []
            for i in f:
                if i not in remap:
                    remap[i] = len(vs)
                    p = body.verts[i]
                    up = max(0.0, (p.z - hc.z) / 0.12)
                    vs.append(p + body.nrm[i] * (thick + 0.006 * up))
                nf.append(remap[i])
            fs.append(nf)
        kit.part.add(vs, fs, mat or kit.mat, {"head": 1.0})
    kit.cap = cap


# ---------------------------------------------------------------------------
# Garment region predicates
def make_pred(g, body, sk):
    lab, arm, leg, P = body.label, body.arm, body.leg, body.verts
    kind = g["kind"]
    z0 = g.get("z0")
    z1 = g.get("z1")
    zr = lambda key: _z(sk, key)

    if kind == "top":
        zb, zt = zr(g.get("bottom", "hips")), zr(g.get("top", "neck"))
        sl = g.get("sleeve", 0.0)          # 0 none, 1 elbow, 2 wrist

        def pred(i):
            L = lab[i]
            if L == "torso":
                return zb <= P[i].z <= zt + 0.01
            if L == "neck":
                return g.get("collar_up", False) and P[i].z < zt + 0.035
            if L == "arm":
                return arm[i] is not None and arm[i] <= sl
            return False
        return pred
    if kind == "bottom":
        zt = zr(g.get("top", "waist"))
        ln = g.get("length", 2.0)          # leg param: 1 = knee, 2 = ankle

        def pred(i):
            L = lab[i]
            if L == "torso":
                return P[i].z <= zt
            if L == "leg":
                return leg[i] is not None and leg[i] <= ln
            if L == "foot":
                return ln >= 2.0 and P[i].z > 0.07
            return False
        return pred
    if kind == "socks":
        a, b = g.get("from", 1.3), 2.0

        def pred(i):
            if lab[i] == "leg":
                return leg[i] is not None and leg[i] >= a
            return lab[i] == "foot"
        return pred
    if kind == "shoes":
        def pred(i):
            if lab[i] == "foot":
                return True
            return lab[i] == "leg" and leg[i] is not None and leg[i] >= g.get("from", 1.88)
        return pred
    if kind == "gloves":
        return lambda i: lab[i] == "hand"
    raise ValueError(kind)


def make_flare(g, body, sk):
    fl = g.get("flare", 0.0)
    if not fl:
        return None
    kind = g["kind"]
    lab, leg, P = body.label, body.leg, body.verts

    def flare(i, p):
        if kind == "bottom" and lab[i] == "leg" and leg[i] is not None:
            side = "L" if P[i].x > 0 else "R"
            k = max(0.0, leg[i] - 0.4) / 1.6
            b = sk.bones[f"shin.{side}"] if leg[i] > 1 else sk.bones[f"thigh.{side}"]
            ab = b["tail"] - b["head"]
            t = max(0, min(1, (p - b["head"]).dot(ab) / ab.length_squared))
            axis = b["head"] + ab * t
            out = (p - axis)
            out.z = 0
            return p + out.normalized() * fl * k if out.length > 1e-6 else p
        if kind == "top" and lab[i] == "torso":
            k = max(0.0, (sk.chest_z - p.z) / 0.25)
            out = Vector((p.x, p.y - 0.0, 0))
            return p + out.normalized() * fl * k
        return p
    return flare


def _z(sk, key):
    lv = dict(hips=sk.hips_z, waist=sk.spine_z, chest=sk.chest_z, neck=sk.neck_z, under=sk.chest_z + 0.05,
              crotch=sk.joints["hip"].z - 0.06)
    if isinstance(key, (int, float)):
        return key
    if isinstance(key, tuple):
        return lv[key[0]] + key[1]
    return lv[key]


def _face_light_mask(body_ob, face_ob, hc):
    """Paint the LightMask so the face stays lit (only fix what needs fixing - video 2)."""
    me = body_ob.data
    attr = me.color_attributes[shading.MASK_LIGHT]
    for v in me.vertices:
        p = v.co
        if p.z > hc.z - 0.13 and (p - hc).length < 0.16 and p.y < hc.y + 0.02:
            front = max(0.0, min(1.0, (hc.y + 0.02 - p.y) / 0.05))
            k = front * max(0.0, min(1.0, (p.z - (hc.z - 0.13)) / 0.03))
            attr.data[v.index].color = (k, k, k, 1.0)
    fa = face_ob.data.color_attributes[shading.MASK_LIGHT]
    for d in fa.data:
        d.color = (1.0, 1.0, 1.0, 1.0)


def _shoe(part, sk, side, mat, sole_mat, body):
    an = sk.j("ankle", side)
    ball = sk.j("ball", side)
    pts = [body.verts[i] for i in range(len(body.verts))
           if body.label[i] == "foot" and (body.verts[i].x > 0) == (side == "L")]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    x = (min(xs) + max(xs)) / 2
    w = (max(xs) - min(xs)) / 2 + 0.008
    heel_y, toe_y = max(ys) + 0.008, min(ys) - 0.01
    ch = sk.chain(f"shin.{side}", f"foot.{side}", f"toe.{side}")
    path = [Vector((x, heel_y - 0.02, 0.045)), Vector((x, an.y, 0.05)), Vector((x, lerp(an.y, toe_y, 0.55), 0.042)),
            Vector((x, toe_y + 0.03, 0.032))]
    path = resample(catmull(path, 5), 14)

    def shape(a, t):
        return (1.0, 0.8 if math.sin(a) < 0 else 1.0 + 0.25 * (1 - t))
    rx = lambda t: w * (0.78 + 0.25 * math.sin(math.pi * min(1.0, t * 1.15)))
    ry = lambda t: 0.05 * (1.0 - 0.42 * t)
    loft(part, path, rx, ry, mat=mat, segs=16, side=(1, 0, 0), shape=shape, cap0="round", cap1="round",
         weights=lambda p, t: chain_weights(p, ch, blend=0.3))
    cpath = [Vector((x, an.y + 0.008, 0.035)), Vector((x, an.y + 0.006, 0.10))]
    loft(part, cpath, 0.042, 0.046, mat=mat, segs=16, side=(1, 0, 0), cap0="flat", cap1=None,
         weights=lambda p, t: chain_weights(p, ch, blend=0.3))
    sp = [Vector((p.x, p.y, 0.011)) for p in path]
    loft(part, sp, lambda t: rx(t) * 1.03, 0.0095, mat=sole_mat, segs=16, side=(1, 0, 0), cap0="round",
         cap1="round", cap_rings=2, weights=lambda p, t: chain_weights(p, ch, blend=0.3))
