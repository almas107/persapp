"""Anime stylisation of the MakeHuman body: target recipe + face clean-up.

The anatomical topology is kept; we only move vertices:
  * targets: bigger rounder cranium, smaller nose/mouth/jaw, slimmer neck, longer legs
  * the eye openings are filled flush and the face front relaxed, so the
    anime eye/brow/mouth pieces can sit on a clean surface (like Mitsuru's
    face, where eyes, lashes and brows are separate meshes over the skin).
"""
import math
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree

ANIME_FEMALE = {
    "head/head-scale-horiz-incr": 0.22, "head/head-scale-depth-incr": 0.18, "head/head-scale-vert-decr": 0.05,
    "head/head-round": 0.8, "head/head-invertedtriangular": 0.3,
    "forehead/forehead-scale-vert-incr": 0.2, "head/head-back-scale-depth-incr": 0.5,
    "chin/chin-width-decr": 0.7, "chin/chin-prominent-decr": 0.4, "chin/chin-height-decr": 0.3,
    "chin/chin-jaw-drop-decr": 0.3,
    "nose/nose-scale-horiz-decr": 1.0, "nose/nose-scale-vert-decr": 0.8, "nose/nose-scale-depth-decr": 0.8,
    "nose/nose-point-width-decr": 0.8,
    "mouth/mouth-scale-horiz-decr": 0.7, "mouth/mouth-scale-vert-decr": 0.6, "mouth/mouth-scale-depth-decr": 0.6,
    "eyes/l-eye-scale-incr": 1.0, "eyes/r-eye-scale-incr": 1.0,
    "neck/neck-scale-horiz-decr": 0.5, "neck/neck-scale-depth-decr": 0.4,
    "armslegs/upperlegs-height-incr": 0.5, "armslegs/lowerlegs-height-incr": 0.4,
    "cheek/l-cheek-bones-decr": 0.6, "cheek/r-cheek-bones-decr": 0.6,
}
ANIME_MALE = dict(ANIME_FEMALE)
ANIME_MALE.update({"head/head-scale-horiz-incr": 0.15,
                   "chin/chin-width-decr": 0.5, "neck/neck-scale-horiz-decr": 0.25,
                   "head/head-invertedtriangular": 0.25})


def apply_recipe(mh, recipe):
    for rel, w in recipe.items():
        mh.apply_target(rel, w)


def lerp(a, b, t):
    return a + (b - a) * t


def clean_face(me, joints, relax=30):
    """Fill the eye openings flush and relax the front of the face."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    head = joints["head"]
    eyes = [joints["l-eye"], joints["r-eye"]]
    eye_r = (eyes[0] - eyes[1]).length * 0.36
    # 1) eye region: delete faces around the eye opening, then fill and relax the patch
    for e in eyes:
        region = [f for f in bm.faces if (f.calc_center_median() - e).length < eye_r]
        bmesh.ops.delete(bm, geom=region, context="FACES_ONLY")
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        edges = [ed for ed in bm.edges if ed.is_boundary and (ed.verts[0].co - e).length < eye_r * 1.6]
        res = bmesh.ops.holes_fill(bm, edges=edges, sides=0)
        new_faces = res["faces"]
        tri = bmesh.ops.triangulate(bm, faces=new_faces)
        inner = set(v for f in tri["faces"] for v in f.verts)
        bmesh.ops.subdivide_edges(bm, edges=list({ed for f in tri["faces"] for ed in f.edges}), cuts=1,
                                  use_grid_fill=True)
    bm.verts.ensure_lookup_table()
    # 2) relax: eye areas strongly, nostrils / lips (anime faces have almost no nose or lip volume)
    mid = (eyes[0] + eyes[1]) * 0.5
    jaw = joints["jaw"]
    near = [v for v in bm.verts if abs(v.co.x) < 0.012 and v.co.y < head.y and jaw.z < v.co.z < mid.z]
    nose_tip = min((v for v in near if v.co.z > lerp(jaw.z, mid.z, 0.45)), key=lambda v: v.co.y).co.copy()
    lips = min((v for v in near if v.co.z < lerp(jaw.z, mid.z, 0.45) and v.co.z > lerp(jaw.z, mid.z, 0.1)),
               key=lambda v: v.co.y).co.copy()
    zones = [(e, eye_r * 2.2, eye_r, 1.0) for e in eyes]
    zones += [(nose_tip + Vector((0, 0.006, -0.006)), 0.03, 0.014, 1.0),
              (lips + Vector((0, 0.006, 0)), 0.034, 0.02, 1.0)]
    front = []
    for v in bm.verts:
        if v.co.y > head.y + 0.02:
            continue
        w = 0.0
        for c, rmax, rfull, k in zones:
            d = (v.co - c).length
            if d < rmax:
                w = max(w, k * (1.0 if d < rfull else 1.0 - (d - rfull) / (rmax - rfull)))
        if w > 0:
            front.append((v, w))
    for _ in range(relax):
        new = {}
        for v, w in front:
            nb = [e.other_vert(v).co for e in v.link_edges]
            if not nb:
                continue
            avg = sum(nb, Vector()) / len(nb)
            new[v] = v.co.lerp(avg, 0.6 * max(0.0, min(1.0, w)))
        for v, c in new.items():
            v.co = c
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
