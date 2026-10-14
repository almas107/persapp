"""Anime face built as projected decal geometry + expression shape keys.

Every facial feature (eyes, lids, lashes, brows, mouth, teeth, tongue, blush,
...) is generated from a *state* dict with a fixed topology, so each
expression is simply the same generator evaluated with different parameters
and stored as a shape key.  The 2D layout (u = world X, v = world Z relative
to the head centre) is projected onto the head surface by ray casting, then
pushed out along the surface normal by a small per-layer offset.
"""
import copy
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .meshkit import lerp

# layer offsets (metres along surface normal)
L_WHITE, L_IRIS, L_PUPIL, L_HL = 0.0012, 0.0019, 0.0025, 0.0031
L_LID, L_LASH, L_BROW = 0.0040, 0.0046, 0.0036
L_MOUTH, L_TONGUE, L_TEETH = 0.0010, 0.0015, 0.0018
L_DECO = 0.0009

SIDE_KEYS = ["Blink", "EyeHappy", "EyeWide", "EyeSquint", "EyeAngry", "EyeSad",
             "BrowUp", "BrowDown", "BrowSad"]
MOUTH_KEYS = ["Mouth_A", "Mouth_I", "Mouth_U", "Mouth_E", "Mouth_O", "Smile", "Frown",
              "Grin", "Smirk_L", "Smirk_R", "Pout"]
OTHER_KEYS = ["PupilSmall", "Blush"]
PRESET_KEYS = ["Exp_Happy", "Exp_Angry", "Exp_Sad", "Exp_Surprised", "Exp_Smug",
               "Exp_Sleepy", "Exp_Shy"]
LOOK_KEYS = ["Look_Left", "Look_Right", "Look_Up", "Look_Down"]


def all_prop_keys():
    keys = []
    for k in SIDE_KEYS:
        keys += [k + "_L", k + "_R"]
    return keys + MOUTH_KEYS + OTHER_KEYS + PRESET_KEYS


def neutral_state(F):
    eye = dict(lid=F.get("lid", 1.0), lower=F.get("lower", 0.0), happy=0.0, scale=1.0,
               angry=0.0, sad=0.0, brow_up=0.0, brow_in=0.0)
    return dict(L=dict(eye), R=dict(eye), look=(0.0, 0.0), pupil=1.0,
                mouth=dict(open=F.get("mouth_open", 0.0), smile=F.get("mouth_smile", 0.0),
                           width=1.0, round=0.0, teeth=0.0, asym=F.get("mouth_asym", 0.0)),
                blush=F.get("blush", 0.0))


def expression_states(F):
    N = neutral_state(F)
    out = {}

    def st(**kw):
        s = copy.deepcopy(N)
        for k, v in kw.items():
            if k in ("L", "R", "mouth"):
                s[k].update(v)
            else:
                s[k] = v
        return s

    full_open = max(1.0, N["L"]["lid"])
    for side in ("L", "R"):
        out[f"Blink_{side}"] = st(**{side: dict(lid=0.0, lower=1.0)})
        out[f"EyeHappy_{side}"] = st(**{side: dict(lid=0.0, lower=1.0, happy=1.0)})
        out[f"EyeWide_{side}"] = st(**{side: dict(lid=full_open, scale=1.12, lower=0.0)})
        out[f"EyeSquint_{side}"] = st(**{side: dict(lid=N[side]["lid"] * 0.78, lower=0.42)})
        out[f"EyeAngry_{side}"] = st(**{side: dict(angry=1.0)})
        out[f"EyeSad_{side}"] = st(**{side: dict(sad=1.0)})
        out[f"BrowUp_{side}"] = st(**{side: dict(brow_up=1.0)})
        out[f"BrowDown_{side}"] = st(**{side: dict(brow_up=-0.6, brow_in=-1.0)})
        out[f"BrowSad_{side}"] = st(**{side: dict(brow_in=1.0, brow_up=0.2)})
    out["Look_Left"] = st(look=(1.0, 0.0))
    out["Look_Right"] = st(look=(-1.0, 0.0))
    out["Look_Up"] = st(look=(0.0, 1.0))
    out["Look_Down"] = st(look=(0.0, -1.0))
    out["PupilSmall"] = st(pupil=0.5)
    out["Blush"] = st(blush=min(1.6, N["blush"] + 1.0))
    M = lambda **kw: st(mouth=dict(kw))
    out["Mouth_A"] = M(open=0.95, round=0.15, width=0.95)
    out["Mouth_I"] = M(open=0.28, width=1.18, teeth=0.9, smile=0.25)
    out["Mouth_U"] = M(open=0.35, round=1.0, width=0.62)
    out["Mouth_E"] = M(open=0.55, width=1.12, teeth=0.6, smile=0.1)
    out["Mouth_O"] = M(open=0.8, round=0.75, width=0.85)
    out["Smile"] = M(smile=1.0, width=1.08)
    out["Frown"] = M(smile=-1.0, width=0.95)
    out["Grin"] = M(open=0.55, smile=0.9, width=1.25, teeth=1.0)
    out["Smirk_L"] = M(asym=1.0, smile=0.15)
    out["Smirk_R"] = M(asym=-1.0, smile=0.15)
    out["Pout"] = M(round=0.6, open=0.08, width=0.62, smile=-0.25)
    both = lambda **kw: {"L": dict(kw), "R": dict(kw)}
    out["Exp_Happy"] = st(**both(lid=0.0, lower=1.0, happy=1.0, brow_up=0.45),
                          mouth=dict(open=0.55, smile=1.0, width=1.1, teeth=0.4))
    out["Exp_Angry"] = st(**both(angry=1.0, brow_up=-0.7, brow_in=-1.0, lid=full_open * 0.92),
                          mouth=dict(open=0.25, smile=-0.8, width=1.05, teeth=1.0))
    out["Exp_Sad"] = st(**both(sad=1.0, brow_in=1.0, brow_up=0.15, lid=0.72),
                        mouth=dict(smile=-0.75, width=0.85, open=0.06), look=(0.0, -0.4))
    out["Exp_Surprised"] = st(**both(lid=full_open, scale=1.12, brow_up=1.0, lower=0.0),
                              mouth=dict(open=0.75, round=0.8, width=0.75), pupil=0.55)
    out["Exp_Smug"] = st(L=dict(lid=0.55, lower=0.25, brow_up=0.6),
                         R=dict(lid=0.5, lower=0.25, brow_up=-0.25, brow_in=-0.4),
                         mouth=dict(asym=1.0, smile=0.4, width=1.0), look=(-0.5, 0.0))
    out["Exp_Sleepy"] = st(**both(lid=0.3, lower=0.12, brow_up=-0.2),
                           mouth=dict(open=0.12, round=0.3, width=0.8))
    out["Exp_Shy"] = st(**both(brow_in=0.6, lid=0.8, lower=0.18),
                        mouth=dict(smile=0.45, width=0.8), blush=min(1.6, N["blush"] + 1.0),
                        look=(0.4, -0.8))
    return out


# --------------------------------------------------------------------------
# Geometry generation (2D: (u, v, layer))
# --------------------------------------------------------------------------
class Geo:
    def __init__(self):
        self.pts = []      # (u, v, layer)
        self.faces = []
        self.fmat = []

    def grid(self, rows, mat, layer):
        """rows: list of rows (each list of (u, v)). Quads between rows."""
        base = len(self.pts)
        w = len(rows[0])
        for r in rows:
            assert len(r) == w
            for (u, v) in r:
                self.pts.append((u, v, layer))
        for i in range(len(rows) - 1):
            for k in range(w - 1):
                a = base + i * w + k
                self.faces.append((a, a + 1, a + w + 1, a + w))
                self.fmat.append(mat if not callable(mat) else mat(i, k))

    def polar(self, center, boundary, mat, layer, rings=3):
        """Disc: center point + rings interpolated towards boundary points."""
        base = len(self.pts)
        n = len(boundary)
        self.pts.append((center[0], center[1], layer))
        for r in range(1, rings + 1):
            t = r / rings
            for (u, v) in boundary:
                self.pts.append((lerp(center[0], u, t), lerp(center[1], v, t), layer))
        for k in range(n):
            k2 = (k + 1) % n
            self.faces.append((base, base + 1 + k, base + 1 + k2))
            self.fmat.append(mat if not callable(mat) else mat(0, k))
        for r in range(rings - 1):
            for k in range(n):
                k2 = (k + 1) % n
                a = base + 1 + r * n
                b = base + 1 + (r + 1) * n
                self.faces.append((a + k, b + k, b + k2, a + k2))
                self.fmat.append(mat if not callable(mat) else mat(r + 1, k))

    def strip(self, a_pts, b_pts, mat, layer):
        self.grid([a_pts, b_pts], mat, layer)


def _ellipse(cx, cy, rx, ry, n=20, rot=0.0):
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        x, y = math.cos(a) * rx, math.sin(a) * ry
        c, s = math.cos(rot), math.sin(rot)
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out


def build_face_geo(F, S):
    g = Geo()
    ew, eh = F["eye_w"], F["eye_h"]
    tilt = math.radians(F.get("eye_tilt", 6))
    S_COL, S_SEG = 18, 28
    for side, sgn in (("L", 1), ("R", -1)):
        es = S[side]
        sc = es["scale"]
        w, h = ew * sc, eh * sc
        ex, ez = F["eye_x"], F["eye_z"]

        def to_uv(e, z):
            # e: outward from nose (local), z: up. tilt raises outer corner.
            z2 = z + e * math.tan(tilt)
            return (sgn * (ex + e), ez + z2)

        def top_b(e):
            x = max(-1.0, min(1.0, e / w))
            return h * 0.9 * math.sqrt(max(0.0, 1 - x * x)) ** 0.85

        def bot_b(e):
            x = max(-1.0, min(1.0, e / w))
            return -h * math.sqrt(max(0.0, 1 - x * x)) ** 0.9

        def closed_curve(e):
            x = max(-1.0, min(1.0, e / w))
            normal = -h * 0.28 - h * 0.18 * (1 - x * x)
            happy = -h * 0.30 + h * 0.62 * (1 - x * x)
            return lerp(normal, happy, es["happy"])

        def upper_edge(e):
            x = max(-1.0, min(1.0, e / w))
            inner = (1 - x) * 0.5          # 1 at inner corner, 0 at outer
            open_top = top_b(e)
            z = lerp(closed_curve(e), open_top, max(0.0, min(1.2, es["lid"])))
            if es["lid"] > 1.0:
                z = top_b(e) * (1 + (es["lid"] - 1.0) * 0.4)
            z -= es["angry"] * h * 0.55 * inner * min(1.0, es["lid"] + 0.2) * max(0.0, 1 - x * x) ** 0.3
            z -= es["sad"] * h * 0.45 * (1 - inner) * max(0.0, 1 - x * x) ** 0.3
            return z

        def lower_edge(e):
            return lerp(bot_b(e), min(closed_curve(e), upper_edge(e)), max(0.0, min(1.0, es["lower"])))

        # -- eye white
        bnd = []
        for k in range(S_SEG):
            a = 2 * math.pi * k / S_SEG
            e = math.cos(a) * w
            z = top_b(e) if math.sin(a) >= 0 else bot_b(e)
            bnd.append(to_uv(e, z))
        g.polar(to_uv(0, -h * 0.05), bnd, "eye_white", L_WHITE, rings=3)

        # -- iris / pupil / highlights (clipped into the eye white)
        lz = S["look"][1] * 0.20 * h
        iw, ih = w * 0.60 * F.get("iris", 1.0), h * 0.86 * F.get("iris", 1.0)

        def clip(e, z, m=0.97):
            x = e / w
            if abs(x) >= m:
                e = math.copysign(m * w, e)
                x = e / w
            lim = (top_b(e) if z >= 0 else -bot_b(e)) * m
            z = max(-lim, min(lim, z))
            return e, z

        def ring(cx, cz, rx, rz, n):
            out = []
            for k in range(n):
                a = 2 * math.pi * k / n
                out.append(clip(cx + math.cos(a) * rx, cz + math.sin(a) * rz))
            return out

        icx, icz = S["look"][0] * 0.30 * w * sgn, lz - h * 0.02   # local e coords
        ir = ring(icx, icz, iw, ih, 24)
        g.polar(to_uv(*clip(icx, icz)), [to_uv(*p) for p in ir],
                lambda r, k: "iris_dark" if (r < 2 and math.sin(2 * math.pi * k / 24) > -0.05) else "iris",
                L_IRIS, rings=3)
        pr = S["pupil"]
        pcz = icz + ih * 0.06
        pp = ring(icx, pcz, iw * 0.42 * pr, ih * 0.48 * pr, 16)
        g.polar(to_uv(*clip(icx, pcz)), [to_uv(*p) for p in pp], "pupil", L_PUPIL, rings=1)
        # highlights: same world direction for both eyes (upper viewer-left)
        for (hx, hz, hr) in ((-0.38, 0.40, 0.30), (0.38, -0.42, 0.14)):
            cx = icx + hx * iw * sgn
            hc = clip(cx, icz + hz * ih, 0.9)
            hp = ring(hc[0], hc[1], iw * hr, iw * hr, 10)
            g.polar(to_uv(*hc), [to_uv(*p) for p in hp], "highlight", L_HL, rings=1)

        # -- upper lid (skin) from lid edge up to a fixed top boundary
        cols = [lerp(-1.25 * w, 1.35 * w, i / (S_COL - 1)) for i in range(S_COL)]
        top_lim = lambda e: h * 1.25 + 0.002
        rows = []
        for r in range(4):
            t = r / 3
            rows.append([to_uv(e, lerp(min(upper_edge(e), top_lim(e) - 1e-4), top_lim(e), t)) for e in cols])
        g.grid(rows, "skin", L_LID)
        # -- lower lid (skin)
        bot_lim = lambda e: -h * 1.2 - 0.002
        rows = []
        for r in range(3):
            t = r / 2
            rows.append([to_uv(e, lerp(bot_lim(e), max(lower_edge(e), bot_lim(e) + 1e-4), t)) for e in cols])
        g.grid(rows, "skin", L_LID)

        # -- upper lash line + wing
        lcols = [lerp(-1.02 * w, 1.18 * w, i / 15) for i in range(16)]
        lt = F.get("lash", 0.0055) * sc
        a_pts, b_pts = [], []
        for e in lcols:
            x = (e / w + 1) * 0.5
            th = lt * (0.35 + 0.9 * min(1.0, x)) * (0.55 if es["lid"] < 0.3 else 1.0)
            ze = upper_edge(min(e, w))
            if e > w * 0.9:
                ze += (e - 0.9 * w) * (0.55 if es["happy"] < 0.5 else -0.25) * min(1.0, es["lid"] + 0.4)
            a_pts.append(to_uv(e, ze - th * 0.25))
            b_pts.append(to_uv(e, ze + th))
        g.strip(a_pts, b_pts, "lash", L_LASH)
        # -- small lower lash at outer corner
        lcols = [lerp(0.35 * w, 1.0 * w, i / 7) for i in range(8)]
        a_pts = [to_uv(e, lower_edge(e) - 0.0002) for e in lcols]
        b_pts = [to_uv(e, lower_edge(e) - lt * 0.32 * (1 - abs((e / w - 0.68) / 0.33) ** 2)) for e in lcols]
        g.strip(b_pts, a_pts, "lash", L_LASH)

        # -- eye bags (optional)
        if F.get("eye_bags"):
            lcols = [lerp(-0.85 * w, 0.95 * w, i / 9) for i in range(10)]
            a_pts = [to_uv(e, bot_b(e) - h * 0.18) for e in lcols]
            b_pts = [to_uv(e, bot_b(e) - h * 0.18 - h * 0.22 * (1 - (e / w - 0.05) ** 2)) for e in lcols]
            g.strip(b_pts, a_pts, "eye_bag", L_DECO)

        # -- brow
        bz = h * 1.0 + F.get("brow_gap", 0.016) + es["brow_up"] * 0.008
        bcols = [lerp(-0.95 * w, 1.1 * w, i / 11) for i in range(12)]
        bt = F.get("brow_t", 0.0042)
        a_pts, b_pts = [], []
        for e in bcols:
            x = (e / w + 0.95) / 2.05      # 0 inner -> 1 outer
            z = bz + F.get("brow_arch", 0.005) * (1 - (2 * x - 1) ** 2)
            z += es["brow_in"] * 0.009 * max(0.0, 1 - x) ** 1.5
            z -= max(0.0, es["brow_in"]) * 0.002 * x
            z += F.get("brow_tilt", 0.0) * (x - 0.5)
            th = bt * (1.0 - 0.65 * x)
            a_pts.append((sgn * (ex + e), ez + z - th * 0.5 + e * math.tan(tilt) * 0.3))
            b_pts.append((sgn * (ex + e), ez + z + th * 0.5 + e * math.tan(tilt) * 0.3))
        g.strip(a_pts, b_pts, "brow", L_BROW)

        # -- blush strokes
        bl = S["blush"]
        if F.get("blush_on", True):
            for i in range(3):
                cx = sgn * (ex + w * 0.1 + (i - 1) * 0.0085)
                cz = ez - h * 1.55
                L = 0.0075 * max(0.0, bl) + 1e-5
                ang = math.radians(65)
                d = (math.cos(ang) * L * 0.5, math.sin(ang) * L * 0.5)
                n = (-d[1] * 0.18, d[0] * 0.18)
                g.strip([(cx - d[0] - n[0], cz - d[1] - n[1]), (cx + d[0] - n[0], cz + d[1] - n[1])],
                        [(cx - d[0] + n[0], cz - d[1] + n[1]), (cx + d[0] + n[0], cz + d[1] + n[1])],
                        "blush", L_DECO)

    # ---------------- mouth
    m = S["mouth"]
    mw = F.get("mouth_w", 0.017) * m["width"] * (1 - 0.35 * m["round"])
    mz = F["mouth_z"]
    oh = 0.016 * m["open"] * (1 + 0.3 * m["round"])
    cols = 13

    def corner(u):
        lift = max(0.0, m["asym"]) * max(0.0, u) ** 2 + max(0.0, -m["asym"]) * max(0.0, -u) ** 2
        return 0.0045 * m["smile"] * u * u + 0.0055 * lift

    def upper(u):
        return mz + corner(u) + 0.12 * oh * (1 - u * u) + 0.0011 * max(0.0, 1 - u * u) ** 0.5

    def lower(u):
        k = max(0.0, 1 - u * u)
        return mz + corner(u) - oh * k ** (0.7 - 0.3 * m["round"]) - 0.0011 * k ** 0.5

    us = [lerp(-1, 1, i / (cols - 1)) for i in range(cols)]
    rows = []
    for r in range(4):
        t = r / 3
        rows.append([(u * mw, lerp(lower(u), upper(u), t)) for u in us])
    g.grid(rows, "mouth", L_MOUTH)
    # teeth: top strip inside the opening
    tw = 0.8
    trow_a = [(u * mw * tw, upper(u * tw) - 0.0006) for u in us]
    trow_b = [(u * mw * tw, upper(u * tw) - 0.0006 - min(oh * 0.45, 0.0045) * m["teeth"] * max(0.0, 1 - u * u) ** 0.3
               - 1e-5) for u in us]
    g.strip(trow_b, trow_a, "teeth", L_TEETH)
    # tongue: bottom blob
    tg = 0.62
    tr_a = [(u * mw * tg, lower(u * tg) + 0.0004) for u in us]
    tr_b = [(u * mw * tg, lower(u * tg) + 0.0004 + oh * 0.32 * max(0.0, 1 - u * u) ** 0.6 + 1e-5) for u in us]
    g.strip(tr_a, tr_b, "tongue", L_TONGUE)

    # ---------------- nose (small shadow wedge)
    nz = F["nose_z"]
    g.polar((0.0035, nz), [(0.0008, nz + 0.0045), (0.0065, nz - 0.0012), (0.0005, nz - 0.0022)],
            "nose", L_DECO, rings=1)

    # ---------------- extras
    for (fx, fz) in F.get("freckles", []):
        g.polar((fx, fz), _ellipse(fx, fz, 0.0011, 0.0011, 6), "freckle", L_DECO, rings=1)
    if F.get("bandage"):
        bx, bz, ang = F["bandage"]
        g.polar((bx, bz), _ellipse(bx, bz, 0.016, 0.0065, 16, math.radians(ang)), "bandage", L_DECO + 0.0004,
                rings=2)
    return g


# --------------------------------------------------------------------------
# Projection + Blender object
# --------------------------------------------------------------------------
def head_bvh(head_obj):
    me = head_obj.data
    verts = [head_obj.matrix_world @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    return BVHTree.FromPolygons(verts, polys)


def project(g, bvh, center):
    out = []
    nrm = []
    for (u, v, layer) in g.pts:
        o = Vector((center.x + u, center.y - 1.0, center.z + v))
        hit = bvh.ray_cast(o, Vector((0, 1, 0)), 3.0)
        if hit[0] is None:
            out.append(Vector((center.x + u, center.y - 0.1, center.z + v)))
            nrm.append(Vector((0, -1, 0)))
            continue
        p, n = hit[0], hit[1]
        out.append(p + n * layer)
        nrm.append(n)
    return out, nrm


def build_face(name, F, head_obj, head_center, materials, collection, weights_bone="head"):
    bvh = head_bvh(head_obj)
    N = neutral_state(F)
    g0 = build_face_geo(F, N)
    co0, nrm0 = project(g0, bvh, head_center)
    me = bpy.data.meshes.new(name + "_Face")
    me.from_pydata([tuple(c) for c in co0], [], g0.faces)
    # materials
    mat_order = []
    for mname in g0.fmat:
        if mname not in mat_order:
            mat_order.append(mname)
    for mname in mat_order:
        me.materials.append(materials[mname])
    for poly, mname in zip(me.polygons, g0.fmat):
        poly.material_index = mat_order.index(mname)
        poly.use_smooth = True
    # make every face point outward (towards -Y / along the head normal)
    for poly in me.polygons:
        vi = poly.vertices[0]
        if poly.normal.dot(nrm0[vi]) < 0:
            poly.flip()
    me.update()
    ob = bpy.data.objects.new(name + "_Face", me)
    collection.objects.link(ob)
    # copy head normals so the skin-coloured eyelids shade exactly like the head
    try:
        me.normals_split_custom_set_from_vertices([tuple(n) for n in nrm0])
    except Exception:
        pass
    vg = ob.vertex_groups.new(name=weights_bone)
    vg.add(list(range(len(co0))), 1.0, "REPLACE")

    ob.shape_key_add(name="Basis", from_mix=False)
    states = expression_states(F)
    for kname, S in states.items():
        g = build_face_geo(F, S)
        assert len(g.pts) == len(g0.pts), kname
        co, _ = project(g, bvh, head_center)
        kb = ob.shape_key_add(name=kname, from_mix=False)
        for i, c in enumerate(co):
            kb.data[i].co = c
    return ob, list(states.keys())
