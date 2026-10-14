"""Stylised hair: a scalp cap plus tapered ribbon strands.

Styles: ponytail_rebel, twintails, buzz, long_parted, ponytail_neat, messy.
Long hair gets its own bone chains (ponytail / twintails / back hair) that
are added to the skeleton so the animator can pose or simulate them.
"""
import math
import random
from mathutils import Vector

from .meshkit import V, lerp, loft, catmull, resample, chain_weights, torus, smoothstep, ellipsoid


class HairKit:
    def __init__(self, part, sk, head_c, head_R, bvh, mat, torso):
        self.part, self.sk, self.c, self.R, self.bvh, self.mat, self.torso = part, sk, head_c, head_R, bvh, mat, torso
        self.s = sk.s
        self.rng = random.Random(7)

    # point on the cranium ellipsoid; az 0 = front (-Y), +90 = character left (+X)
    def scalp(self, az, el, lift=1.0):
        rx, ry, rzu, rzl = self.R
        a, e = math.radians(az), math.radians(el)
        rz = rzu if el >= 0 else rzl
        x = math.sin(a) * math.cos(e) * rx
        y = -math.cos(a) * math.cos(e) * ry
        z = math.sin(e) * rz
        if el < 0:
            k = (-math.sin(e)) ** 1.5
            x *= 1 - 0.35 * k
            y *= 1 - 0.3 * k
        return self.c + V(x, y, z) * lift

    def front(self, x, z, off):
        hit = self.bvh.ray_cast(V(self.c.x + x, self.c.y - 1, z), V(0, 1, 0), 3.0)
        if hit[0] is None:
            return V(self.c.x + x, self.c.y - self.R[1], z)
        return hit[0] + hit[1] * off

    def back_y(self, z, clearance=0.03):
        rx, ry, y = self.torso.at(z)
        return y + ry + clearance * self.s

    def strand(self, pts, width, thick=None, chain=None, samples=None, bulge=0.2, root_w=1.0, tip=0.0,
               mat=None, outward=None, twist_side=None):
        path = catmull(pts, 6)
        n = samples or max(6, min(26, int(sum((b - a).length for a, b in zip(path, path[1:])) / (0.012 * self.s)) + 4))
        path = resample(path, n)
        thick = thick or width * 0.38
        hseg = self.sk.seg("head")
        ch = [hseg] + [self.sk.seg(b) for b in (chain or [])]
        out = outward or (path[0] - self.c)
        tan = (path[1] - path[0]).normalized()
        side = twist_side or tan.cross(out).normalized()
        rx = lambda t: max(width * (root_w * (1 - t) + tip * t) * (1 - t ** 1.6) * (1 + bulge * math.sin(math.pi * t)),
                           0.0004)
        ry = lambda t: max(thick * (1 - t) ** 0.8 * (1 + bulge * 0.5 * math.sin(math.pi * t)), 0.0003)

        if chain:
            wfn = lambda p, t: chain_weights(p, ch, blend=0.25)
        else:
            wfn = {"head": 1.0}
        loft(self.part, path, rx, ry, mat=mat or self.mat, segs=8, side=side, cap0="round", cap1="flat",
             cap_rings=1, weights=wfn)
        return path

    def cap(self, hairline, lift=1.045, mat=None, rows=14, cols=48, part_line=False):
        """Scalp cap from hairline(az)->top. hairline returns elevation in degrees."""
        verts, faces = [], []
        for r in range(rows + 1):
            for k in range(cols):
                az = 360.0 * k / cols
                el0 = hairline(az)
                el = lerp(el0, 89.0, (r / rows) ** 0.9)
                p = self.scalp(az, el, lift)
                if part_line and r == rows:
                    pass
                verts.append(p)
        top = len(verts)
        verts.append(self.c + V(0, 0, self.R[2] * lift))
        for r in range(rows):
            for k in range(cols):
                k2 = (k + 1) % cols
                a, b = r * cols + k, r * cols + k2
                faces.append((a, b, b + cols, a + cols))
        for k in range(cols):
            faces.append((rows * cols + k, rows * cols + (k + 1) % cols, top))
        self.part.add(verts, faces, mat or self.mat, {"head": 1.0})

    def tie(self, center, normal, r, mat):
        torus(self.part, center, r, r * 0.35, mat, {"head": 1.0}, normal=normal, segs=18, tube=8)


def hairline_default(front=38, side=-6, back=-38, temple=8):
    def f(az):
        a = math.radians(az)
        c = math.cos(a)       # 1 front, -1 back
        if c >= 0:
            return lerp(side, front, c ** 1.4) + temple * math.sin(math.pi * c) * 0.0
        return lerp(side, back, (-c) ** 1.2)
    return f


# --------------------------------------------------------------------------
def build_hair(style, kit, H, F):
    """H: hair params dict. F: face params (for brow/eye heights)."""
    sk, s, c = kit.sk, kit.s, kit.c
    rx, ry, rzu, rzl = kit.R
    rng = kit.rng
    brow_z = c.z + F["eye_z"] + F["eye_h"] + 0.018
    chains = {}

    def bangs(n, az0, az1, tip_z, length_jitter=0.01, width=0.022, sweep=0.0, root_el=62, off=0.012, curl=0.0):
        for i in range(n):
            t = i / max(1, n - 1)
            az = lerp(az0, az1, t)
            root = kit.scalp(az * 0.6, root_el, 1.03)
            mid = kit.scalp(az * 0.95, 30, 1.11)
            x_tip = math.sin(math.radians(az)) * rx * 0.95 + sweep * s
            zt = tip_z + rng.uniform(-length_jitter, length_jitter) - abs(math.sin(math.radians(az))) * 0.012
            tipp = kit.front(x_tip, zt, off + 0.004)
            mid2 = kit.front(lerp(mid.x, x_tip, 0.6) + curl * 0.01, lerp(mid.z, zt, 0.55), off + 0.008)
            kit.strand([root, mid, mid2, tipp], width * rng.uniform(0.85, 1.15) * s, bulge=0.25)

    def side_locks(sign, z_end, n=3, width=0.022, forward=0.0, chain=None, az=78, spread=10, out=0.0):
        for i in range(n):
            a = sign * (az + (i - (n - 1) / 2) * spread)
            root = kit.scalp(a * 0.85, 45, 1.04)
            p1 = kit.scalp(a, 8, 1.12)
            p2 = kit.scalp(a * 0.95, -25, 1.15) + V(sign * out * 0.5, -forward * 0.5, 0)
            end = V(sign * (rx * 0.95 + out + i * 0.006), c.y - ry * 0.35 - forward + i * 0.012, z_end + i * 0.012)
            kit.strand([root, p1, p2, end], width * s * rng.uniform(0.9, 1.1), chain=chain, bulge=0.3)

    def back_hair(z_end, n=9, width=0.03, az_span=(110, 250), chain_for=None, el_root=70, wave=0.0,
                  lift=1.12):
        for i in range(n):
            t = i / max(1, n - 1)
            az = lerp(az_span[0], az_span[1], t)
            root = kit.scalp(az, el_root, 1.03)
            p1 = kit.scalp(az, 15, lift)
            p2 = kit.scalp(az, -30, lift + 0.08)
            x = math.sin(math.radians(az))
            pts = [root, p1, p2]
            zz = p2.z
            k = 0
            while zz - 0.09 * s > z_end:
                zz -= 0.09 * s
                k += 1
                xx = x * (kit.torso.at(zz)[0] * 0.75 + 0.02 * s) + wave * math.sin(k * 1.7 + i) * 0.012 * s
                pts.append(V(xx, kit.back_y(zz, 0.035), zz))
            pts.append(V(x * kit.torso.at(z_end)[0] * 0.8, kit.back_y(z_end, 0.04), z_end + rng.uniform(-0.015, 0.015)))
            ch = chain_for(x) if chain_for else None
            kit.strand(pts, width * s * rng.uniform(0.85, 1.15), chain=ch, bulge=0.15)

    def ponytail(tie_az, tie_el, length, prefix="ponytail", n=9, width=0.03, flare=1.0, side=0.0):
        T = kit.scalp(tie_az, tie_el, 1.06)
        outd = (T - c).normalized()
        down = V(0, 0, -1)
        # centre curve
        p0 = T
        p1 = T + outd * 0.06 * s + V(side * 0.02, 0, 0.02 * s)
        p2 = p1 + outd * 0.04 * s + down * 0.08 * s + V(side * 0.03, 0, 0)
        zz = p2.z - length * 0.35
        p3 = V(p2.x + side * 0.04, max(kit.back_y(zz, 0.05), p2.y - 0.01), zz)
        zz2 = p2.z - length * 0.75
        p4 = V(p3.x + side * 0.02, kit.back_y(zz2, 0.04), zz2)
        zz3 = p2.z - length
        p5 = V(p4.x - side * 0.01, kit.back_y(zz3, 0.03), zz3)
        center = resample(catmull([p0, p1, p2, p3, p4, p5], 8), 5)
        names = sk.add_chain(prefix, center, "head")
        chains[prefix] = names
        kit.tie(T + outd * 0.008 * s, outd, 0.016 * s, H.get("tie_mat", kit.mat))
        cpath = [p0, p1, p2, p3, p4, p5]
        for i in range(n):
            ang = 2 * math.pi * i / n
            r = 0.012 * s * flare
            off = V(math.cos(ang), math.sin(ang) * 0.6, 0) * r
            pts = [cpath[0] + off * 0.3]
            for j, p in enumerate(cpath[1:]):
                f = [1.4, 1.8, 2.2, 1.6, 0.6][j]
                pts.append(p + off * f * (1 + rng.uniform(-0.2, 0.2)))
            cut = rng.uniform(0.0, 0.08)
            pts[-1] = pts[-1] + (pts[-2] - pts[-1]) * cut
            kit.strand(pts, width * s * rng.uniform(0.8, 1.1), chain=names, bulge=0.45, twist_side=V(1, 0, 0))
        return names

    def twintail(sign, z_end, prefix, n=10, width=0.034):
        T = kit.scalp(sign * 98, 38, 1.06)
        outd = V(sign, 0.15, 0.25).normalized()
        p0 = T
        p1 = T + outd * 0.05 * s + V(0, 0, 0.025 * s)
        p2 = p1 + V(sign * 0.06 * s, 0.01 * s, -0.04 * s)
        p3 = V(p2.x + sign * 0.035 * s, p2.y + 0.02 * s, lerp(p2.z, z_end, 0.4))
        p4 = V(p3.x - sign * 0.005 * s, p3.y + 0.01 * s, lerp(p2.z, z_end, 0.78))
        p5 = V(p4.x - sign * 0.03 * s, p4.y, z_end)
        cp = [p0, p1, p2, p3, p4, p5]
        center = resample(catmull(cp, 8), 5)
        names = sk.add_chain(prefix, center, "head")
        chains[prefix] = names
        kit.tie(T + outd * 0.01 * s, outd, 0.015 * s, H.get("tie_mat", kit.mat))
        for i in range(n):
            ang = 2 * math.pi * i / n
            off = V(math.cos(ang) * 0.4, math.sin(ang), 0.0) * 0.014 * s
            off = V(off.x + 0, off.y, math.cos(ang) * 0.006 * s)
            pts = [cp[0] + off * 0.3]
            for j, p in enumerate(cp[1:]):
                f = [1.3, 2.2, 2.6, 2.0, 0.8][j]
                pts.append(p + off * f * rng.uniform(0.85, 1.15))
            pts[-1] = pts[-1] + V(0, 0, rng.uniform(0, 0.05) * s)
            kit.strand(pts, width * s * rng.uniform(0.8, 1.15), chain=names, bulge=0.5, twist_side=V(0, 1, 0))
        return names

    # ------------------------------------------------------------------
    if style == "buzz":
        kit.cap(hairline_default(front=40, side=2, back=-30), lift=1.022)
        # slight crisp hairline at the temples
        return chains

    if style == "ponytail_rebel":
        kit.cap(hairline_default(front=30, side=-5, back=-35), lift=1.04)
        bangs(10, -58, 45, brow_z - 0.004, width=0.032, sweep=-0.012, off=0.012)
        # long strand over one eye
        root = kit.scalp(15, 60, 1.03)
        kit.strand([root, kit.scalp(25, 30, 1.12), kit.front(0.045, c.z + F["eye_z"] + 0.01, 0.022),
                    kit.front(0.06, c.z + F["eye_z"] - 0.035, 0.02)], 0.024 * s, bulge=0.3)
        cl = sk.add_chain("hair_side.L", [V(rx * 1.05, c.y - 0.02, c.z - 0.06), V(rx * 1.1, c.y - 0.03, sk.chin - 0.04),
                                          V(rx * 1.15, c.y - 0.04, sk.neck_z - 0.08)], "head")
        cr = sk.add_chain("hair_side.R", [V(-rx * 1.05, c.y - 0.02, c.z - 0.06), V(-rx * 1.1, c.y - 0.03, sk.chin - 0.04),
                                          V(-rx * 1.15, c.y - 0.04, sk.neck_z - 0.08)], "head")
        side_locks(1, sk.neck_z - 0.09, n=3, width=0.026, forward=0.02, chain=cl)
        side_locks(-1, sk.neck_z - 0.08, n=3, width=0.026, forward=0.02, chain=cr)
        back_hair(sk.chin - 0.02, n=8, width=0.032, az_span=(115, 245), el_root=40, lift=1.09)
        ponytail(180, 52, H.get("length", 0.42) * s, n=11, width=0.034, flare=1.3)
        return chains

    if style == "twintails":
        kit.cap(hairline_default(front=30, side=-4, back=-32), lift=1.04)
        bangs(13, -62, 62, brow_z - 0.002, width=0.03, off=0.011)
        side_locks(1, sk.chin + 0.01, n=2, width=0.02, forward=0.015)
        side_locks(-1, sk.chin + 0.01, n=2, width=0.02, forward=0.015)
        back_hair(sk.chin - 0.03, n=9, width=0.03, az_span=(110, 250), el_root=40, lift=1.08)
        twintail(1, H.get("tail_end", sk.chest_z - 0.02), "twintail.L")
        twintail(-1, H.get("tail_end", sk.chest_z - 0.02), "twintail.R")
        return chains

    if style == "long_parted":
        def hl(az):
            return hairline_default(front=46, side=-4, back=-40)(az)
        kit.cap(hl, lift=1.04)
        z_end = H.get("z_end", sk.hips_z + 0.08)
        bc = {}
        for side, sg in (("L", 1), ("R", -1)):
            zs = sk.chin
            bc[side] = sk.add_chain(f"hair_back.{side}", [V(sg * 0.07 * s, 0.08 * s, zs), V(sg * 0.10 * s, 0.10 * s, lerp(zs, z_end, 0.35)),
                                               V(sg * 0.11 * s, 0.11 * s, lerp(zs, z_end, 0.7)),
                                               V(sg * 0.11 * s, 0.11 * s, z_end)], "head")
        bc["C"] = sk.add_chain("hair_back.C", [V(0, 0.11 * s, sk.chin), V(0, 0.12 * s, lerp(sk.chin, z_end, 0.35)),
                                     V(0, 0.12 * s, lerp(sk.chin, z_end, 0.7)), V(0, 0.12 * s, z_end)], "head")
        chains["hair_back"] = True
        # centre-parted curtain strands framing the face
        for sign in (1, -1):
            for i in range(5):
                a = sign * (40 + i * 13)
                root = kit.scalp(sign * 3, 84, 1.03)
                p1 = kit.scalp(a, 40, 1.08)
                p2 = kit.scalp(a * 1.05 + sign * 10, -5, 1.14)
                p3 = kit.scalp(a * 1.0 + sign * 25, -40, 1.24)
                zs = sk.neck_z - 0.02
                p4 = V(sign * (kit.torso.at(zs)[0] * 0.75 + 0.02 * i), kit.back_y(zs, 0.0) - 0.06 + i * 0.012, zs)
                zz = lerp(zs, z_end, 0.5)
                p5 = V(sign * (kit.torso.at(zz)[0] * 0.95 + 0.004 * i), kit.back_y(zz, 0.02) - 0.07 + i * 0.012, zz)
                p6 = V(sign * (kit.torso.at(z_end)[0] * 0.9), kit.back_y(z_end, 0.03) - 0.06 + i * 0.012,
                       z_end + rng.uniform(0, 0.05))
                chain = bc["L"] if sign > 0 else bc["R"]
                kit.strand([root, p1, p2, p3, p4, p5, p6], 0.034 * s, chain=chain, bulge=0.25)

        def chain_for(x):
            if x > 0.35:
                return bc["L"]
            if x < -0.35:
                return bc["R"]
            return bc["C"]
        back_hair(z_end, n=14, width=0.036, az_span=(95, 265), chain_for=chain_for, el_root=78, wave=1.0,
                  lift=1.1)
        return chains

    if style == "ponytail_neat":
        kit.cap(hairline_default(front=32, side=-4, back=-30), lift=1.04)
        bangs(9, -52, 38, brow_z + 0.004, width=0.032, sweep=-0.015, off=0.011)
        side_locks(1, sk.chin + 0.005, n=2, width=0.022, forward=0.018)
        side_locks(-1, sk.chin + 0.005, n=2, width=0.022, forward=0.018)
        back_hair(sk.chin + 0.01, n=7, width=0.03, az_span=(120, 240), el_root=45, lift=1.07)
        ponytail(178, 30, H.get("length", 0.30) * s, n=10, width=0.03, flare=1.1)
        return chains

    if style == "messy":
        kit.cap(hairline_default(front=46, side=-2, back=-28), lift=1.05)
        # spiky strands around the whole head
        for i in range(70):
            az = rng.uniform(0, 360)
            el = rng.uniform(5, 80)
            if math.cos(math.radians(az)) > 0.55 and el < 50:
                continue   # leave the face open, bangs handled below
            root = kit.scalp(az, el, 1.02)
            outd = (root - c).normalized()
            down = V(0, 0, -1)
            L = rng.uniform(0.05, 0.095) * s
            outd = (outd + V(0, 0, -0.9)).normalized() if outd.z > -0.2 else outd
            p1 = root + outd * L * 0.5 + down * L * 0.25
            p2 = p1 + (outd * 0.5 + down * 0.8 + V(rng.uniform(-.3, .3), rng.uniform(-.3, .3), 0)).normalized() * L * 0.6
            kit.strand([root, p1, p2], rng.uniform(0.02, 0.03) * s, bulge=0.35)
        bangs(12, -62, 62, c.z + F["eye_z"] + F["eye_h"] * 0.6, length_jitter=0.018, width=0.03, off=0.013)
        # ahoge
        r = kit.scalp(0, 88, 1.0)
        kit.strand([r, r + V(0.01, -0.01, 0.04) * s, r + V(0.035, -0.02, 0.05) * s, r + V(0.05, -0.02, 0.035) * s],
                   0.012 * s, bulge=0.2)
        return chains

    raise ValueError(style)
