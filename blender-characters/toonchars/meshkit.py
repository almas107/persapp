"""Procedural geometry helpers: lofted tubes, strands, primitives, skin weights.

Everything here produces plain python data (verts / faces / per-vertex weight
dicts) that is accumulated in a ``Part`` and turned into a Blender object at the
end.  Generating weights analytically (instead of Blender's heat weighting)
keeps skinning deterministic even with overlapping clothing layers.
"""
import math
from mathutils import Vector, Matrix


def V(*a):
    return Vector(a[0]) if len(a) == 1 else Vector(a)


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    if e0 == e1:
        return 0.0 if x < e0 else 1.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------
# Part: geometry accumulator for one Blender object
# --------------------------------------------------------------------------
class Part:
    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []
        self.face_mats = []
        self.weights = []          # one dict {bone: w} per vertex
        self.mat_names = []
        self.flat_faces = set()

    def mat(self, name):
        if name not in self.mat_names:
            self.mat_names.append(name)
        return self.mat_names.index(name)

    def add(self, verts, faces, mat, weights, flat=False):
        base = len(self.verts)
        mi = self.mat(mat)
        self.verts.extend(Vector(v) for v in verts)
        if isinstance(weights, dict):
            self.weights.extend(dict(weights) for _ in verts)
        else:
            assert len(weights) == len(verts), (len(weights), len(verts))
            self.weights.extend(weights)
        for f in faces:
            self.faces.append(tuple(i + base for i in f))
            self.face_mats.append(mi)
            if flat:
                self.flat_faces.add(len(self.faces) - 1)
        return base


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
def catmull(points, samples_per_seg=6):
    """Smooth path through control points (Catmull-Rom)."""
    pts = [Vector(p) for p in points]
    if len(pts) < 3:
        out = []
        n = samples_per_seg * (len(pts) - 1)
        for i in range(n + 1):
            out.append(pts[0].lerp(pts[-1], i / n))
        return out
    ext = [pts[0] * 2 - pts[1]] + pts + [pts[-1] * 2 - pts[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(samples_per_seg):
            t = s / samples_per_seg
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t +
                              (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1].copy())
    return out


def resample(points, n):
    """Resample polyline to n points evenly by arc length."""
    pts = [Vector(p) for p in points]
    d = [0.0]
    for a, b in zip(pts, pts[1:]):
        d.append(d[-1] + (b - a).length)
    L = d[-1] or 1e-9
    out = []
    j = 0
    for i in range(n):
        s = L * i / (n - 1)
        while j < len(d) - 2 and d[j + 1] < s:
            j += 1
        seg = (d[j + 1] - d[j]) or 1e-9
        out.append(pts[j].lerp(pts[j + 1], (s - d[j]) / seg))
    return out


def _frames(path, side0):
    """Parallel-transport frames along a path. Returns (tangent, side, up)."""
    n = len(path)
    tans = []
    for i in range(n):
        if i == 0:
            t = path[1] - path[0]
        elif i == n - 1:
            t = path[-1] - path[-2]
        else:
            t = path[i + 1] - path[i - 1]
        tans.append(t.normalized())
    side = Vector(side0)
    side = (side - tans[0] * side.dot(tans[0]))
    if side.length < 1e-6:
        side = tans[0].orthogonal()
    side.normalize()
    out = []
    for i in range(n):
        if i > 0:
            # rotate previous side by rotation between tangents
            rot = tans[i - 1].rotation_difference(tans[i])
            side = rot @ side
            side = (side - tans[i] * side.dot(tans[i])).normalized()
        up = tans[i].cross(side).normalized()
        out.append((tans[i], side.copy(), up))
    return out


def loft(part, path, rx, ry=None, mat="skin", weights=None, segs=12, side=(1, 0, 0),
         cap0="round", cap1="round", shape=None, arc=None, flat=False,
         cap_rings=3, weight_fn=None):
    """Tube along ``path`` with elliptical cross-section.

    rx/ry: float, list (per path point) or callable(t) -> radius.
    shape: optional callable(angle, t) -> radius multiplier (or (mx, my)).
    arc:   (a0, a1) in radians for an open shell (no caps).
    weights: dict (rigid) or callable(center_point, t) -> {bone: w}.
    The local ring frame: angle 0 points along ``side``; angle +90deg along
    tangent x side.  For a path going up +Z with side +X, +90deg is +Y (back).
    """
    n = len(path)
    ry = rx if ry is None else ry

    def val(r, i, t):
        if callable(r):
            return r(t)
        if isinstance(r, (list, tuple)):
            return r[i]
        return r

    frames = _frames(path, side)
    closed = arc is None
    if closed:
        angles = [2 * math.pi * k / segs for k in range(segs)]
    else:
        angles = [lerp(arc[0], arc[1], k / segs) for k in range(segs + 1)]
    na = len(angles)

    rings = []      # list of (center, [points], t)
    for i, (p, (tan, sd, up)) in enumerate(zip(path, frames)):
        t = i / (n - 1)
        a_rx, a_ry = val(rx, i, t), val(ry, i, t)
        ring = []
        for a in angles:
            mx = my = 1.0
            if shape:
                m = shape(a, t)
                mx, my = (m, m) if not isinstance(m, tuple) else m
            ring.append(p + sd * (math.cos(a) * a_rx * mx) + up * (math.sin(a) * a_ry * my))
        rings.append((p, ring, t, tan, a_rx, a_ry))

    # round caps: extra shrinking rings
    def cap_rings_for(idx, direction, kind):
        if kind != "round" or not closed:
            return []
        p, ring, t, tan, a_rx, a_ry = rings[idx]
        extra = []
        rad = (a_rx + a_ry) * 0.5
        for k in range(1, cap_rings + 1):
            ang = (math.pi / 2) * k / (cap_rings + 1)
            s, c = math.sin(ang), math.cos(ang)
            off = tan * direction * s * rad
            extra.append((p + off, [p + off + (q - p) * c for q in ring], t, tan, a_rx * c, a_ry * c))
        return extra

    pre = list(reversed(cap_rings_for(0, -1, cap0)))
    post = cap_rings_for(n - 1, 1, cap1)
    all_rings = pre + rings + post

    verts, faces, wts = [], [], []
    for (p, ring, t, *_r) in all_rings:
        if weight_fn:
            for q in ring:
                wts.append(weight_fn(q, p, t))
        else:
            w = weights(p, t) if callable(weights) else (weights or {})
            wts.extend(dict(w) for _ in ring)
        verts.extend(ring)
    nr = len(all_rings)
    for r in range(nr - 1):
        for k in range(na if closed else na - 1):
            k2 = (k + 1) % na
            a, b = r * na + k, r * na + k2
            c, d = (r + 1) * na + k2, (r + 1) * na + k
            faces.append((a, b, c, d))
    if closed:
        # end fans
        for idx, kind, flip in ((0, cap0, True), (nr - 1, cap1, False)):
            if kind is None:
                continue
            p, ring, t, tan, *_r = all_rings[idx]
            ci = len(verts)
            if kind == "round":
                rad = (_r[0] + _r[1]) * 0.5
                cp = p + tan * (-1 if flip else 1) * rad * 0.35
            else:
                cp = p
            verts.append(cp)
            if weight_fn:
                wts.append(weight_fn(cp, p, t))
            else:
                w = weights(p, t) if callable(weights) else (weights or {})
                wts.append(dict(w))
            base = idx * na
            for k in range(na):
                k2 = (k + 1) % na
                f = (base + k, base + k2, ci)
                faces.append(tuple(reversed(f)) if flip else f)
    part.add(verts, faces, mat, wts, flat=flat)
    return all_rings


def ellipsoid(part, center, radii, mat, weights, segs=16, rings=10, deform=None, rot=None):
    """UV ellipsoid. deform(local_unit_vec) -> local vec (before scaling)."""
    verts, faces = [], []
    c = Vector(center)
    R = rot or Matrix.Identity(3)
    verts.append(None)
    for r in range(1, rings):
        th = math.pi * r / rings
        for s in range(segs):
            ph = 2 * math.pi * s / segs
            verts.append(Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th))))
    verts[0] = Vector((0, 0, 1))
    verts.append(Vector((0, 0, -1)))
    out = []
    for v in verts:
        if deform:
            v = deform(v)
        out.append(c + R @ Vector((v.x * radii[0], v.y * radii[1], v.z * radii[2])))
    top, bot = 0, len(out) - 1
    for s in range(segs):
        faces.append((top, 1 + s, 1 + (s + 1) % segs))
    for r in range(rings - 2):
        for s in range(segs):
            a = 1 + r * segs + s
            b = 1 + r * segs + (s + 1) % segs
            faces.append((a, a + segs, b + segs, b))
    lb = 1 + (rings - 2) * segs
    for s in range(segs):
        faces.append((lb + s, bot, lb + (s + 1) % segs))
    # orient faces outward: flip all (computed winding is inward for quads/top)
    faces = [tuple(reversed(f)) for f in faces]
    if callable(weights):
        w = [weights(v) for v in out]
    else:
        w = weights
    part.add(out, faces, mat, w)
    return out


def box(part, center, size, mat, weights, rot=None, bevel=0.0):
    c = Vector(center)
    R = rot or Matrix.Identity(3)
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    vs = [Vector((x, y, z)) for x in (-hx, hx) for y in (-hy, hy) for z in (-hz, hz)]
    vs = [c + R @ v for v in vs]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    part.add(vs, faces, mat, weights, flat=True)


def cylinder(part, p0, p1, r, mat, weights, segs=16, side=(1, 0, 0), flat=False):
    loft(part, [Vector(p0), Vector(p1)], r, r, mat=mat, weights=weights, segs=segs,
         side=side, cap0="flat", cap1="flat", flat=flat)


def torus(part, center, R, r, mat, weights, normal=(0, 0, 1), segs=24, tube=8, arc=None):
    n = Vector(normal).normalized()
    a = n.orthogonal().normalized()
    b = n.cross(a)
    c = Vector(center)
    a0, a1 = (0, 2 * math.pi) if arc is None else arc
    closed = arc is None
    cnt = segs if closed else segs + 1
    path = [c + (a * math.cos(lerp(a0, a1, i / segs)) + b * math.sin(lerp(a0, a1, i / segs))) * R
            for i in range(cnt)]
    verts, faces = [], []
    for i, p in enumerate(path):
        radial = (p - c).normalized()
        for k in range(tube):
            ang = 2 * math.pi * k / tube
            verts.append(p + radial * math.cos(ang) * r + n * math.sin(ang) * r)
    for i in range(cnt if closed else cnt - 1):
        i2 = (i + 1) % cnt
        for k in range(tube):
            k2 = (k + 1) % tube
            faces.append((i * tube + k, i2 * tube + k, i2 * tube + k2, i * tube + k2))
    part.add(verts, faces, mat, weights)


# --------------------------------------------------------------------------
# Skin weights
# --------------------------------------------------------------------------
def seg_param(p, a, b):
    ab = b - a
    L2 = ab.length_squared or 1e-12
    s = (p - a).dot(ab) / L2
    return s, (p - (a + ab * max(0, min(1, s)))).length


def chain_weights(p, chain, blend=0.18):
    """Blend weights along a bone chain [(name, head, tail), ...].

    The point is assigned to the closest bone segment; near a joint the weight
    cross-fades into the neighbouring bone so the joint bends smoothly.
    """
    best = None
    for i, (name, h, t) in enumerate(chain):
        s, d = seg_param(p, h, t)
        if best is None or d < best[2] - 1e-9:
            best = (i, s, d)
    i, s, _ = best
    name = chain[i][0]
    w = {name: 1.0}
    if s < blend and i > 0:
        k = 0.5 * (1 - max(s, -blend) / blend) if s > -blend else 1.0
        k = min(k, 1.0)
        w = {chain[i - 1][0]: k, name: 1 - k} if k < 1 else {chain[i - 1][0]: 1.0}
    elif s > 1 - blend and i < len(chain) - 1:
        k = 0.5 * (1 - (1 - s) / blend)
        k = max(0.0, min(k, 1.0))
        w = {chain[i + 1][0]: k, name: 1 - k}
    return {k: v for k, v in w.items() if v > 1e-4}


def mix_weights(a, b, t):
    out = {}
    for k, v in a.items():
        out[k] = out.get(k, 0) + v * (1 - t)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v * t
    return {k: v for k, v in out.items() if v > 1e-4}
