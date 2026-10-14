"""Box-modelled subdivision cage for an anime body (one connected mesh).

Torso = stack of 8-vertex loops. Arms and legs are 6-vertex loops bridged
into holes in the torso, exactly like extruding limbs out of a box model.
A Subdivision Surface modifier turns the cage into a smooth body.
"""
import math
import bmesh
import bpy
from mathutils import Vector, Matrix

def V(*a):
    return Vector(a[0]) if len(a) == 1 else Vector(a)

# Torso loops for a 1.6 m female, (z, F_y, FL(x,y), L(x,y), BL(x,y), B_y)
TORSO_F = [
    (0.80, -0.058, (0.088, -0.054), (0.130, 0.006), (0.100, 0.078), 0.088),
    (0.875, -0.068, (0.100, -0.064), (0.140, 0.008), (0.108, 0.084), 0.096),
    (0.95, -0.068, (0.090, -0.060), (0.125, 0.006), (0.090, 0.068), 0.074),
    (1.01, -0.062, (0.072, -0.056), (0.100, 0.004), (0.072, 0.056), 0.060),
    (1.08, -0.070, (0.080, -0.066), (0.110, 0.002), (0.080, 0.058), 0.062),
    (1.14, -0.080, (0.072, -0.100), (0.118, 0.000), (0.086, 0.062), 0.066),
    (1.205, -0.070, (0.080, -0.072), (0.124, 0.002), (0.088, 0.064), 0.066),
    (1.255, -0.050, (0.075, -0.048), (0.135, 0.006), (0.075, 0.052), 0.056),
    (1.29, -0.032, (0.034, -0.026), (0.042, 0.004), (0.032, 0.034), 0.036),
]
TORSO_M = [
    (0.80, -0.060, (0.082, -0.055), (0.122, 0.005), (0.090, 0.064), 0.070),
    (0.875, -0.070, (0.094, -0.064), (0.132, 0.006), (0.098, 0.074), 0.082),
    (0.95, -0.068, (0.090, -0.062), (0.122, 0.006), (0.090, 0.066), 0.070),
    (1.01, -0.066, (0.084, -0.060), (0.116, 0.004), (0.084, 0.062), 0.066),
    (1.08, -0.072, (0.090, -0.068), (0.124, 0.002), (0.090, 0.064), 0.068),
    (1.14, -0.080, (0.094, -0.078), (0.134, 0.000), (0.096, 0.068), 0.072),
    (1.205, -0.074, (0.098, -0.070), (0.142, 0.002), (0.100, 0.070), 0.072),
    (1.255, -0.052, (0.084, -0.050), (0.150, 0.006), (0.084, 0.056), 0.060),
    (1.29, -0.035, (0.037, -0.028), (0.046, 0.004), (0.035, 0.036), 0.040),
]


def torso_loop(row, sx=1.0, sy=1.0):
    z, fy, fl, l, bl, by = row
    pts = [(0, fy), fl, l, bl, (0, by), (-bl[0], bl[1]), (-l[0], l[1]), (-fl[0], fl[1])]
    return [V((x * sx, y * sy, z)) for x, y in pts]


def ring6(center, axis, side, r_side, r_up, twist=0.0):
    """6-vertex loop around ``axis``. side = direction of vertex 0."""
    axis = axis.normalized()
    side = (side - axis * side.dot(axis)).normalized()
    up = axis.cross(side).normalized()
    out = []
    for k in range(6):
        a = 2 * math.pi * k / 6 + twist
        out.append(center + side * math.cos(a) * r_side + up * math.sin(a) * r_up)
    return out


class BodyCage:
    def __init__(self, sk, female=True, build=None):
        self.sk = sk
        self.female = female
        self.b = build or {}

    # ---------------------------------------------------------------
    def build(self, name):
        sk, b = self.sk, self.b
        s = sk.s
        rows = TORSO_F if self.female else TORSO_M
        sx = b.get("width", 1.0)
        bust = b.get("bust", 0.5 if self.female else 0.0)
        bm = bmesh.new()
        loops = []
        for row in rows:
            row = list(row)
            if self.female and abs(row[0] - 1.14) < 1e-3:
                fl = row[2]
                row[2] = (fl[0], -0.066 - (fl[1] + 0.066) * -1 * (bust / 0.5) if False else -0.07 - 0.05 * bust / 0.5)
            pts = torso_loop(row, sx * s * 1.1, s * 1.22)
            for p in pts:
                p.z = row[0] * s
            loops.append([bm.verts.new(p) for p in pts])
        # torso faces
        faces = {}
        for i in range(len(loops) - 1):
            for k in range(8):
                k2 = (k + 1) % 8
                f = bm.faces.new((loops[i][k], loops[i][k2], loops[i + 1][k2], loops[i + 1][k]))
                faces[(i, k)] = f
        # crotch
        L0 = loops[0]
        crotch = bm.verts.new(V((0, 0.008 * s, L0[0].co.z - 0.03 * s)))

        def tube(rings, close_end=True):
            vs = [[bm.verts.new(p) for p in r] for r in rings]
            n = len(rings[0])
            for i in range(len(vs) - 1):
                for k in range(n):
                    k2 = (k + 1) % n
                    bm.faces.new((vs[i][k], vs[i][k2], vs[i + 1][k2], vs[i + 1][k]))
            if close_end:
                bm.faces.new(list(reversed(vs[-1])))
            return vs

        def bridge(loop_a, loop_b):
            # loop_a, loop_b: ordered vertex lists with matching start/direction
            n = len(loop_a)
            for k in range(n):
                k2 = (k + 1) % n
                bm.faces.new((loop_a[k], loop_a[k2], loop_b[k2], loop_b[k]))

        # ---------------- legs: holes = (F, FL, L, BL, B, crotch) and mirror
        for side, sg in (("L", 1), ("R", -1)):
            if sg > 0:
                hole = [L0[0], L0[1], L0[2], L0[3], L0[4], crotch]
            else:
                hole = [L0[0], L0[7], L0[6], L0[5], L0[4], crotch]
            hip, knee, ankle = sk.j("hip", side), sk.j("knee", side), sk.j("ankle", side)
            rings = []
            lg = b.get("legs", 1.0) * (1.0 if self.female else 0.95)
            spec = [  # (point, radius_side, radius_front)
                (lerp(hip, knee, 0.30) + V(0.004 * s * (1 if side == 'L' else -1), 0.006 * s, 0), 0.074, 0.072),
                (lerp(hip, knee, 0.55), 0.064, 0.062),
                (lerp(hip, knee, 0.82), 0.052, 0.052),
                (knee + V(0, -0.004 * s, 0), 0.046, 0.048),
                (lerp(knee, ankle, 0.22) + V(0, 0.006 * s, 0), 0.047, 0.052),
                (lerp(knee, ankle, 0.5), 0.040, 0.043),
                (lerp(knee, ankle, 0.85), 0.027, 0.029),
                (ankle + V(0, 0, -0.01 * s), 0.025, 0.028),
            ]
            for p, rs, rf in spec:
                axis = V((0, 0, -1))
                # vertex 0 points front (-Y) to match hole order F, FL(side) ...
                rings.append(ring6(p, axis, V((0, -1, 0)), rf * s * lg * 1.32, rs * s * lg * 1.32))
            vs = tube(rings, close_end=True)
            bridge(hole, _align(hole, vs[0]))
        # bottom closing faces between legs are the crotch triangles (none needed: holes share F/B/crotch)

        # ---------------- arms: hole between loops 6 and 7 around L (index 2)
        for side, sg in (("L", 1), ("R", -1)):
            ks = (1, 2, 3) if sg > 0 else (7, 6, 5)
            a, b_ = 6, 7
            # remove the two side faces
            for kk in ((1, 2) if sg > 0 else (5, 6)):
                f = faces.get((a, kk))
                if f is not None and f.is_valid:
                    bm.faces.remove(f)
            hole = [loops[a][ks[0]], loops[a][ks[1]], loops[a][ks[2]],
                    loops[b_][ks[2]], loops[b_][ks[1]], loops[b_][ks[0]]]
            sh, el, wr = sk.j("shoulder", side), sk.j("elbow", side), sk.j("wrist", side)
            d1 = (el - sh).normalized()
            d2 = (wr - el).normalized()
            ag = b.get("arms", 1.0) * (0.9 if self.female else 1.0)
            spec = [
                (sh + d1 * 0.01 * s, d1, 0.040, 0.044),
                (lerp(sh, el, 0.4), d1, 0.036, 0.036),
                (lerp(sh, el, 0.85), d1, 0.030, 0.030),
                (el, (d1 + d2).normalized(), 0.028, 0.030),
                (lerp(el, wr, 0.3), d2, 0.030, 0.029),
                (lerp(el, wr, 0.75), d2, 0.024, 0.022),
                (wr + d2 * 0.012 * s, d2, 0.020, 0.016),
            ]
            rings = []
            for p, ax, r1, r2 in spec:
                # vertex 0 toward front (-Y); order must follow the hole orientation
                r = ring6(p, ax, V((0, -1, 0)), r1 * s * ag * 1.3, r2 * s * ag * 1.3, twist=0.0)
                rings.append(r)
            # match: hole[0] = loop a front-side vertex. Find best rotation/direction.
            vs = tube(rings, close_end=True)
            first = _align(hole, vs[0])
            bridge(hole, first)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        return me


def _align(hole, ring):
    """Rotate/reverse ``ring`` so ring[i] is nearest to hole[i] (min total twist)."""
    best = None
    n = len(ring)
    for rev in (False, True):
        r = list(reversed(ring)) if rev else list(ring)
        for off in range(n):
            rr = r[off:] + r[:off]
            d = sum((a.co - b.co).length for a, b in zip(hole, rr))
            if best is None or d < best[0]:
                best = (d, rr)
    return best[1]


def lerp(a, b, t):
    return a + (b - a) * t
