"""Makoto-style head retopology fitted onto a sculpt.

The MakeHuman (CC0) head already has game-character face topology: concentric
loops around the eye sockets and mouth, nose loops, ear loops, and separate
eyeballs sitting in real sockets.  We align it to the sculpt's head from a few
landmarks, then project the face surface onto the sculpt while keeping the eye
sockets carved in (the sculpt faces are blank).
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toonchars import mhbase  # noqa: E402

FACE_RECIPE = {
    "nose/nose-scale-horiz-decr": 1.0, "nose/nose-scale-vert-decr": 0.8, "nose/nose-scale-depth-decr": 1.0,
    "nose/nose-point-width-decr": 1.0, "nose/nose-compression-compress": 0.5,
    "mouth/mouth-scale-horiz-decr": 0.8, "mouth/mouth-scale-vert-decr": 0.8, "mouth/mouth-scale-depth-decr": 1.0,
    "eyes/l-eye-scale-incr": 1.0, "eyes/r-eye-scale-incr": 1.0,
    "chin/chin-width-decr": 0.5, "head/head-round": 0.5,
}


def mh_head(root, gender, races):
    mh = mhbase.MHBase(root)
    mh.macro(gender=gender, races=races, proportions=1.0, muscle=0.5, weight=0.4)
    for rel, w in FACE_RECIPE.items():
        mh.apply_target(rel, w)
    j = mh.joints()
    neck_z = j["neck"].z
    verts, faces, uvs, groups, remap = mh.submesh(["body", "helper-l-eye", "helper-r-eye"])
    # keep head + upper neck faces, and the eyeballs
    keep = []
    for f, g in zip(faces, groups):
        if g.startswith("helper-"):
            keep.append((f, g))
        elif min(verts[i].z for i in f) > neck_z - 0.02 and all(abs(verts[i].x) < 0.13 for i in f):
            keep.append((f, g))
    used = sorted({i for f, _ in keep for i in f})
    m = {o: n for n, o in enumerate(used)}
    V = [verts[i].copy() for i in used]
    F = [[m[i] for i in f] for f, _ in keep]
    G = [g for _, g in keep]
    return V, F, G, j


def landmarks_mh(V, G, F, j):
    skin = {i for f, g in zip(F, G) if g == "body" for i in f}
    pts = [V[i] for i in skin]
    eye = (j["l-eye"] + j["r-eye"]) * 0.5
    crown = max(p.z for p in pts)
    front = [p for p in pts if abs(p.x) < 0.006 and p.y < eye.y + 0.02]
    chin = min((p for p in front if p.z < eye.z - 0.05), key=lambda p: p.z + (p.y - eye.y) * 0.0)
    # chin = lowest front-centre point above the neck turn: use the most forward low point
    lows = [p for p in front if eye.z - 0.15 < p.z < eye.z - 0.07]
    chin = min(lows, key=lambda p: p.z) if lows else chin
    w = max(abs(p.x) for p in pts if abs(p.z - eye.z) < 0.01) * 2
    face_y = min(p.y for p in pts if abs(p.z - eye.z) < 0.01 and abs(p.x) < 0.01)
    return dict(crown=crown, chin=chin, eye=eye, width=w, face_y=face_y)


def fit(V, F, G, j, L, sculpt_bvh):
    """L: sculpt landmarks dict(chin=(x,y,z), eye_z, crown_z (skull), width, face_y, tilt_deg, yaw_deg)."""
    M = landmarks_mh(V, G, F, j)
    G_body = [False] * len(V)
    for f, g in zip(F, G):
        if g == "body":
            for i in f:
                G_body[i] = True
    # vertical scale from chin->eye, horizontal from cheek width
    sz = (L["eye_z"] - L["chin"][2]) / (M["eye"].z - M["chin"].z)
    sx = L["width"] / M["width"]
    sy = (sx + sz) * 0.5
    pivot = M["chin"]
    rot = Matrix.Rotation(math.radians(L.get("tilt", 0.0)), 3, "Y") @ \
        Matrix.Rotation(math.radians(L.get("yaw", 0.0)), 3, "Z") @ \
        Matrix.Rotation(math.radians(L.get("pitch", 0.0)), 3, "X")
    tgt = Vector(L["chin"])

    def xf(p):
        q = p - pivot
        q = Vector((q.x * sx, q.y * sy, q.z * sz))
        return tgt + rot @ q
    W = [xf(p) for p in V]
    fwd0 = rot @ Vector((0, -1, 0))
    # depth / height refinement: median signed gap between MH face points and the sculpt along the face axis
    tg = Vector(L["chin"])
    for _ in range(3):
        gaps = []
        for i, p in enumerate(W):
            if G_body[i] and (p - tg).length < 0.16 and (p.z > tg.z + 0.02) and (p - tg).dot(fwd0) > -0.02:
                h = sculpt_bvh.ray_cast(p + fwd0 * 0.15, -fwd0, 0.4)
                if h[0] is not None:
                    gaps.append((h[0] - p).dot(fwd0))
        if not gaps:
            break
        gaps.sort()
        g = gaps[len(gaps) // 2]
        W = [p + fwd0 * g for p in W]
        print("depth shift", round(g, 4), "samples", len(gaps))
    eyes_c = [xf(j["l-eye"]) + (W[0] - xf(V[0])), xf(j["r-eye"]) + (W[0] - xf(V[0]))]
    eye_r = (eyes_c[0] - eyes_c[1]).length * 0.42
    fwd = rot @ Vector((0, -1, 0))
    # vertex normals
    nrm = [Vector() for _ in W]
    for f in F:
        n = (W[f[1]] - W[f[0]]).cross(W[f[2]] - W[f[0]])
        for i in f:
            nrm[i] += n
    nrm = [n.normalized() if n.length else Vector((0, 0, 1)) for n in nrm]
    skin = [False] * len(W)
    for f, g in zip(F, G):
        if g == "body":
            for i in f:
                skin[i] = True
    eyez = L["eye_z"]
    ipd = (j["l-eye"] - j["r-eye"]).length
    emid = (j["l-eye"] + j["r-eye"]) * 0.5
    front_c = [p for p, b in zip(V, G_body) if b and abs(p.x) < 0.004 and emid.z - 1.4 * ipd < p.z < emid.z - 0.3 * ipd]
    nose_tip = min((p for p in front_c if p.z > emid.z - 0.85 * ipd), key=lambda p: p.y)
    lip = min((p for p in front_c if p.z < nose_tip.z - 0.25 * ipd), key=lambda p: p.y)
    keep_zone = [G_body[i] and ((V[i] - nose_tip).length < 0.42 * ipd or
                                (Vector((V[i].x * 0.8, V[i].y, V[i].z)) - lip).length < 0.5 * ipd) for i in range(len(V))]
    disp = [None] * len(W)
    for i, p in enumerate(W):
        if not skin[i]:
            continue
        rel = p - tgt
        front = nrm[i].dot(fwd) > 0.25
        in_face_band = (L["chin"][2] - 0.01) < p.z < eyez + 0.012
        near_eye = min((p - e).length for e in eyes_c) < eye_r or keep_zone[i]
        if not (front and in_face_band) or near_eye:
            continue
        best = None
        for d in (nrm[i], -nrm[i]):
            h = sculpt_bvh.ray_cast(p, d, 0.035)
            if h[0] is not None and (best is None or (h[0] - p).length < best.length):
                best = h[0] - p
        if best is not None:
            disp[i] = best
    # diffuse displacement into the sockets and blend at the borders (keeps eye sockets carved)
    nb = [set() for _ in W]
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            nb[a].add(b)
            nb[b].add(a)
    D = [d.copy() if d is not None else Vector() for d in disp]
    fixed = [d is not None for d in disp]
    for _ in range(60):
        nd = list(D)
        for i in range(len(W)):
            if fixed[i] or not skin[i]:
                continue
            ns = [D[k] for k in nb[i]]
            if ns:
                nd[i] = sum(ns, Vector()) / len(ns) * 0.97
        D = nd
    out = [p + D[i] if skin[i] else p for i, p in enumerate(W)]
    # relax + re-project: removes the folds of realistic nose/lip geometry flattened onto an anime face,
    # keeps every edge loop (only vertex positions slide along the surface)
    sock = [min((W[i] - e).length for e in eyes_c) < eye_r * 1.05 or keep_zone[i] for i in range(len(W))]
    movable = [fixed[i] and not sock[i] for i in range(len(W))]
    for it in range(25):
        nxt = list(out)
        for i in range(len(W)):
            if not movable[i]:
                continue
            ns = [out[k] for k in nb[i]]
            if not ns:
                continue
            avg = sum(ns, Vector()) / len(ns)
            q = out[i].lerp(avg, 0.55)
            loc, n_, idx, dist = sculpt_bvh.find_nearest(q, 0.05)
            nxt[i] = loc if loc is not None else q
        out = nxt
    # tuck the skull inside the sculpted hair wherever it pokes out (scalp / back of head only)
    hc = Vector((L["chin"][0], L["chin"][1] + 0.07, L["eye_z"] + 0.01))
    for i in range(len(W)):
        if not skin[i] or fixed[i] or keep_zone[i]:
            continue
        p = out[i]
        if not (p.z > L["eye_z"] + 0.025 or p.y > L["chin"][1] + 0.06):
            continue
        d = (p - hc)
        if d.length < 1e-6:
            continue
        h = sculpt_bvh.ray_cast(hc + d.normalized() * 0.4, -d.normalized(), 0.4)
        if h[0] is None:
            continue
        rs = (h[0] - hc).length
        if d.length > rs - 0.012:
            out[i] = hc + d.normalized() * (rs - 0.012)
    # eyeballs follow the mean displacement of their socket rim
    for side, e in enumerate(eyes_c):
        rim = [D[i] for i in range(len(W)) if skin[i] and (W[i] - e).length < eye_r * 1.3]
        md = sum(rim, Vector()) / max(1, len(rim))
        tag = "helper-l-eye" if side == 0 else "helper-r-eye"
        ids = {i for f, g in zip(F, G) if g == tag for i in f}
        for i in ids:
            out[i] = W[i] + md
    return out, eyes_c
