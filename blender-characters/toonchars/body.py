"""Body, head and clothing geometry driven by a character spec."""
import math
from mathutils import Vector, Matrix

from .meshkit import (Part, V, lerp, smoothstep, loft, ellipsoid, box, cylinder, torus,
                      catmull, resample, chain_weights, mix_weights)


# --------------------------------------------------------------------------
# Torso profile
# --------------------------------------------------------------------------
class Torso:
    def __init__(self, sk, B):
        s = sk.s
        self.sk = sk
        self.B = B
        sh = B.get("shoulders", 1.0)
        wa = B.get("waist", 1.0)
        hp = B.get("hips", 1.0)
        g = B.get("girth", 1.0)
        neck_r = B.get("neck_r", 0.034) * s
        self.levels = dict(
            crotch=sk.joints["hip"].z - 0.055 * s,
            hips=sk.hips_z,
            waist=sk.spine_z + 0.01 * s,
            chest=sk.chest_z + 0.035 * s,
            under=sk.neck_z - 0.075 * s,
            shoulder=sk.neck_z - 0.032 * s,
            neck=sk.neck_z + 0.0 * s,
        )
        L = self.levels
        # (z, rx, ry, y offset)
        self.rings = [
            (L["crotch"] - 0.01 * s, 0.07 * s * hp * g, 0.065 * s * g, 0.004 * s),
            (L["crotch"] + 0.03 * s, 0.135 * s * hp * g, 0.092 * s * g, 0.006 * s),
            (L["hips"], 0.145 * s * hp * g, 0.098 * s * g, 0.008 * s),
            (lerp(L["hips"], L["waist"], 0.5), 0.13 * s * lerp(hp, wa, 0.5) * g, 0.088 * s * g, 0.006 * s),
            (L["waist"], 0.112 * s * wa * g, 0.08 * s * g, 0.004 * s),
            (L["chest"] - 0.04 * s, 0.122 * s * lerp(wa, sh, 0.4) * g, 0.085 * s * g, 0.002 * s),
            (L["chest"], 0.132 * s * lerp(wa, sh, 0.7) * g, 0.09 * s * g, 0.002 * s),
            (L["under"], 0.142 * s * sh * g, 0.083 * s * g, 0.006 * s),
            (L["shoulder"], 0.135 * s * sh * g, 0.07 * s * g, 0.009 * s),
            (L["neck"] - 0.01 * s, 0.07 * s * sh, 0.052 * s, 0.009 * s),
            (L["neck"] + 0.012 * s, neck_r * 1.15, neck_r * 1.1, 0.008 * s),
        ]

    def z(self, key):
        if isinstance(key, (int, float)):
            return key
        if isinstance(key, tuple):
            return self.levels[key[0]] + key[1] * self.sk.s
        return self.levels[key]

    def at(self, z):
        R = self.rings
        if z <= R[0][0]:
            return R[0][1:]
        for a, b in zip(R, R[1:]):
            if a[0] <= z <= b[0]:
                t = (z - a[0]) / (b[0] - a[0])
                t = t * t * (3 - 2 * t) * 0.5 + t * 0.5
                return tuple(lerp(a[i], b[i], t) for i in (1, 2, 3))
        return R[-1][1:]

    def bust_shape(self, z0, z1, amount):
        cz = self.levels["chest"]
        s = self.sk.s

        def shape(a, t):
            z = lerp(z0, z1, t)
            k = math.exp(-((z - cz) / (0.045 * s)) ** 2)
            front = max(0.0, -math.sin(a)) ** 2.2
            side = 1.0 + amount * 0.10 * k * (1 - abs(math.cos(a)))
            flatback = 1.0 - 0.1 * max(0.0, math.sin(a)) ** 3 * (1 - k)
            return (1.0, (1.0 + amount * 0.32 * k * front) * flatback * side)
        return shape

    def weights(self):
        sk = self.sk
        s = sk.s
        hips = ("hips", V(0, 0, sk.hips_z - 0.10 * s), V(0, 0, sk.hips_z + 0.02 * s))
        ch = [hips, sk.seg("spine"), sk.seg("chest"), sk.seg("neck")]
        crotch = self.levels["crotch"]

        def fn(q, p, t):
            w = chain_weights(p, ch, blend=0.3)
            # pelvis sides follow the thighs a little
            if q.z < sk.hips_z:
                k = smoothstep(sk.hips_z, crotch, q.z) * 0.6
                side = smoothstep(0.02 * s, 0.10 * s, abs(q.x))
                kk = k * max(side, smoothstep(sk.hips_z - 0.02 * s, crotch, q.z))
                if kk > 0:
                    thigh = "thigh.L" if q.x > 0 else "thigh.R"
                    w = mix_weights(w, {thigh: 1.0}, kk)
            # top of the shoulders follow the shoulder bones a little
            if q.z > self.levels["under"] - 0.02 * s and abs(q.x) > 0.06 * s:
                k = smoothstep(0.06 * s, 0.13 * s, abs(q.x)) * 0.55
                w = mix_weights(w, {"shoulder.L" if q.x > 0 else "shoulder.R": 1.0}, k)
            return w
        return fn

    def shell(self, part, z0, z1, mat, inflate=0.0, arc=None, cap0=None, cap1=None, bust=0.0,
              n=None, segs=20, flare=0.0):
        z0, z1 = self.z(z0), self.z(z1)
        n = n or max(4, int(abs(z1 - z0) / (0.018 * self.sk.s)) + 2)
        path, rx, ry = [], [], []
        for i in range(n):
            z = lerp(z0, z1, i / (n - 1))
            a, b, y = self.at(z)
            fl = flare * (1 - i / (n - 1))
            path.append(V(0, y, z))
            rx.append(a + inflate * self.sk.s + fl)
            ry.append(b + inflate * self.sk.s + fl * 0.8)
        return loft(part, path, rx, ry, mat=mat, segs=segs, side=(1, 0, 0), cap0=cap0, cap1=cap1,
                    arc=arc, shape=self.bust_shape(z0, z1, bust) if bust else None,
                    weight_fn=self.weights())


def front_gap(deg):
    g = math.radians(deg) / 2
    return (-math.pi / 2 + g, 3 * math.pi / 2 - g)


# --------------------------------------------------------------------------
# Limbs
# --------------------------------------------------------------------------
class Limbs:
    def __init__(self, sk, B):
        self.sk = sk
        self.B = B
        s = sk.s
        ag = B.get("arm_girth", 1.0)
        lg = B.get("leg_girth", 1.0)
        # control radii along normalised length
        self.arm_r = [(0.0, 0.040 * s * ag), (0.12, 0.041 * s * ag), (0.5, 0.032 * s * ag),
                      (0.55, 0.029 * s * ag), (0.75, 0.029 * s * ag), (1.0, 0.0215 * s * ag)]
        self.leg_r = [(0.0, 0.088 * s * lg), (0.12, 0.080 * s * lg), (0.5, 0.050 * s * lg),
                      (0.56, 0.047 * s * lg), (0.68, 0.052 * s * lg), (0.93, 0.031 * s * lg),
                      (1.0, 0.028 * s * lg)]

    @staticmethod
    def _interp(table, t):
        for (a, ra), (b, rb) in zip(table, table[1:]):
            if a <= t <= b:
                u = (t - a) / (b - a)
                u = u * u * (3 - 2 * u)
                return lerp(ra, rb, u)
        return table[-1][1]

    def arm_path(self, side):
        sk = self.sk
        d = sk.arm_dir if side == "L" else V(-sk.arm_dir.x, 0, sk.arm_dir.z)
        sh, el, wr = sk.j("shoulder", side), sk.j("elbow", side), sk.j("wrist", side)
        start = sh - d * 0.035 * sk.s + V(0, 0, 0.004 * sk.s)
        return resample(catmull([start, sh, el, wr], 8), 26)

    def leg_path(self, side):
        sk = self.sk
        hip, kn, an = sk.j("hip", side), sk.j("knee", side), sk.j("ankle", side)
        start = hip + V(-0.01 * sk.s * (1 if side == "L" else -1), 0, 0.075 * sk.s)
        return resample(catmull([start, hip, kn, an], 8), 30)

    def arm_chain(self, side):
        return self.sk.chain(f"shoulder.{side}", f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}")

    def leg_chain(self, side):
        sk = self.sk
        hips = ("hips", V(0, 0, sk.hips_z + 0.02 * sk.s), V(0, 0, sk.hips_z - 0.10 * sk.s))
        return [hips] + sk.chain(f"thigh.{side}", f"shin.{side}", f"foot.{side}")

    def _sub(self, path, t0, t1):
        n = len(path)
        i0, i1 = int(round(t0 * (n - 1))), int(round(t1 * (n - 1)))
        return path[i0:i1 + 1], [i / (n - 1) for i in range(i0, i1 + 1)]

    def arm(self, part, side, mat, t0=0.0, t1=1.0, inflate=0.0, cap0="round", cap1="round", flare=0.0,
            segs=12):
        path = self.arm_path(side)
        sub, ts = self._sub(path, t0, t1)
        ch = self.arm_chain(side)
        r = [self._interp(self.arm_r, t) + inflate * self.sk.s + flare * smoothstep(t0, t1, t) for t in ts]
        side_v = (0, -1, 0)
        return loft(part, sub, r, [x * 0.92 for x in r], mat=mat, segs=segs, side=side_v, cap0=cap0, cap1=cap1,
                    weights=lambda p, t: chain_weights(p, ch, blend=0.22))

    def leg(self, part, side, mat, t0=0.0, t1=1.0, inflate=0.0, cap0="round", cap1="round", flare=0.0,
            segs=14, arc=None, extra=0.0):
        path = self.leg_path(side)
        sub, ts = self._sub(path, t0, t1)
        ch = self.leg_chain(side)
        r = [self._interp(self.leg_r, t) + inflate * self.sk.s + flare * smoothstep(t0, 1.0, t) + extra
             for t in ts]
        return loft(part, sub, r, [x * 0.95 for x in r], mat=mat, segs=segs, side=(1, 0, 0), cap0=cap0,
                    cap1=cap1, arc=arc, weights=lambda p, t: chain_weights(p, ch, blend=0.22))

    def hand(self, part, side, mat):
        sk = self.sk
        s = sk.s * sk.P.get("hand_scale", 1.0)
        sg = 1 if side == "L" else -1
        d = V(sk.arm_dir.x * sg, 0, sk.arm_dir.z)
        n = V(sk.hand_up.x * sg, 0, sk.hand_up.z)
        wr, kn = sk.j("wrist", side), sk.j("knuckle", side)
        ch = sk.chain(f"forearm.{side}", f"hand.{side}")
        path = [wr - d * 0.012 * s, wr + d * 0.018 * s, lerp(wr, kn, 0.65), kn + d * 0.004 * s]
        loft(part, path, [0.019 * s, 0.026 * s, 0.031 * s, 0.029 * s], [0.012 * s, 0.013 * s, 0.012 * s, 0.010 * s],
             mat=mat, segs=12, side=(0, -1, 0), cap0="round", cap1="round", cap_rings=2,
             weights=lambda p, t: chain_weights(p, ch, blend=0.35))
        for f in ("thumb", "index", "middle", "ring", "pinky"):
            pts = sk.finger_pts(f, side)
            fch = [sk.seg(f"hand.{side}")] + [sk.seg(f"{f}_{i}.{side}") for i in (1, 2, 3)]
            start = pts[0] - (pts[1] - pts[0]).normalized() * 0.012 * s
            path = resample(catmull([start] + pts, 4), 12)
            r0 = (0.0105 if f == "thumb" else 0.0085) * s
            if f == "pinky":
                r0 *= 0.85
            loft(part, path, lambda t, r0=r0: r0 * (1 - 0.22 * t), mat=mat, segs=8, side=n, cap0="round",
                 cap1="round", cap_rings=2, weights=lambda p, t, fch=fch: chain_weights(p, fch, blend=0.3))


# --------------------------------------------------------------------------
# Head
# --------------------------------------------------------------------------
def head_frame(sk, P):
    hh = P["head_h"]
    c = V(0, 0.004 * sk.s, sk.chin + hh * 0.55)
    R = (hh * P.get("head_wide", 0.40), hh * 0.43, hh * 0.45, hh * 0.55)   # rx, ry, rz_up, rz_low
    return c, R


def build_head(part, sk, P, mat_skin):
    c, (rx, ry, rzu, rzl) = head_frame(sk, P)
    jaw = P.get("jaw", 0.5)
    chin_fw = P.get("chin_forward", 0.03)

    def deform(v):
        x, y, z = v.x, v.y, v.z
        if z < 0:
            f = -z
            x *= (1 - jaw * f ** 1.7) * (1 + 0.05 * math.sin(math.pi * f))
            if y < 0:
                y *= (1 - 0.32 * f ** 1.4)
                y -= chin_fw * f ** 2
            else:
                y *= (1 - 0.55 * f ** 1.1)
            z *= rzl / rzu
        else:
            # flatter forehead front, rounder back
            if y < 0:
                y *= 1 - 0.06 * z
        if y < -0.2:
            y = -0.2 + (y + 0.2) * 0.85      # flatter face plane
        return V(x, y, z)

    w = {"head": 1.0}
    verts = ellipsoid(part, c, (rx, ry, rzu), mat_skin, w, segs=48, rings=36, deform=deform)
    # ears
    ez = c.z - (rzu + rzl) * 0.5 * 0.18
    for sg in (1, -1):
        rot = Matrix.Rotation(math.radians(-12 * sg), 3, "Z") @ Matrix.Rotation(math.radians(8), 3, "Y")
        ellipsoid(part, V(sg * rx * 0.94, c.y + 0.012 * sk.s, ez), (0.011, 0.02, 0.03), mat_skin, w,
                  segs=12, rings=8, rot=rot)
    return c


def build_neck(part, sk, mat, r=0.034):
    s = sk.s
    ch = sk.chain("chest", "neck", "head")
    path = [V(0, 0.01 * s, sk.neck_z - 0.04 * s), V(0, 0.008 * s, sk.neck_z + 0.03 * s),
            V(0, 0.004 * s, sk.chin + 0.04 * s)]
    path = resample(catmull(path, 4), 8)
    loft(part, path, r * s, r * s * 1.05, mat=mat, segs=14, side=(1, 0, 0), cap0="round", cap1="round",
         weights=lambda p, t: chain_weights(p, ch, blend=0.4))


# --------------------------------------------------------------------------
# Shoes
# --------------------------------------------------------------------------
def build_shoe(part, sk, side, mat, sole_mat=None, height=0.05, width=0.045, boot=False, lace_mat=None):
    s = sk.s
    an = sk.j("ankle", side)
    toe = sk.j("toe", side)
    ch = sk.chain(f"shin.{side}", f"foot.{side}", f"toe.{side}")
    x = an.x
    heel = V(x, an.y + 0.04 * s, 0.05 * s)
    path = [heel, V(x, an.y + 0.0, 0.055 * s), V(x, an.y - 0.06 * s, 0.045 * s), V(x, toe.y - 0.012 * s, 0.038 * s)]
    path = resample(catmull(path, 5), 14)

    def shape(a, t):
        sn = math.sin(a)
        return (1.0, 0.75 if sn < 0 else (1.0 + 0.2 * (1 - t)))
    rx = lambda t: width * s * (0.82 + 0.22 * math.sin(math.pi * min(1, t * 1.2)))
    ry = lambda t: height * s * (1.15 - 0.4 * t)
    loft(part, path, rx, ry, mat=mat, segs=14, side=(1, 0, 0), shape=shape, cap0="round", cap1="round",
         weights=lambda p, t: chain_weights(p, ch, blend=0.3))
    # ankle collar
    top = boot and 0.16 or 0.085
    cpath = [V(x, an.y + 0.01 * s, 0.03 * s), V(x, an.y + 0.008 * s, top * s)]
    loft(part, cpath, 0.038 * s, 0.04 * s, mat=mat, segs=14, side=(1, 0, 0), cap0="flat", cap1=None,
         weights=lambda p, t: chain_weights(p, ch, blend=0.3))
    if sole_mat:
        spath = [V(x, p.y, 0.011 * s) for p in path]
        spath[0].y -= 0.008 * s
        spath[-1].y += 0.006 * s
        loft(part, spath, lambda t: rx(t) * 1.04, 0.009 * s, mat=sole_mat, segs=14, side=(1, 0, 0),
             cap0="round", cap1="round", cap_rings=2, weights=lambda p, t: chain_weights(p, ch, blend=0.3))
    if lace_mat:
        for i in range(3):
            t = 0.38 + i * 0.1
            p = path[int(t * (len(path) - 1))]
            cylinder(part, p + V(-0.022 * s, 0, 0.048 * s * (1 - 0.3 * t)), p + V(0.022 * s, 0, 0.048 * s * (1 - 0.3 * t)),
                     0.003 * s, lace_mat, chain_weights(p, ch), segs=6)
