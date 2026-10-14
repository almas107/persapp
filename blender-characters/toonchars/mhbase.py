"""MakeHuman hm08 base mesh (CC0) loader + target morphing.

The base mesh gives us real anatomical topology (face loops, deltoids,
3-loop knees/elbows, proper hands and feet) and named joint helpers that
mark where every bone goes.  Targets (also CC0) reshape it per character.
"""
import os
from mathutils import Vector

ROOT = os.environ.get("MH_DATA", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mh_data"))


def conv(x, y, z):
    """MakeHuman (Y up, decimetres, faces +Z) -> Blender (Z up, metres, faces -Y)."""
    return Vector((x * 0.1, -z * 0.1, y * 0.1))


class MHBase:
    def __init__(self, root=ROOT):
        self.root = root
        self.v = []          # raw MH coords
        self.vt = []
        self.faces = []      # (group, [vi...], [vti...])
        group = None
        with open(os.path.join(root, "3dobjs", "base.obj")) as fh:
            for line in fh:
                if line.startswith("v "):
                    self.v.append([float(a) for a in line.split()[1:4]])
                elif line.startswith("vt "):
                    self.vt.append([float(a) for a in line.split()[1:3]])
                elif line.startswith("g "):
                    group = line.split()[1]
                elif line.startswith("f "):
                    vi, ti = [], []
                    for tok in line.split()[1:]:
                        parts = tok.split("/")
                        vi.append(int(parts[0]) - 1)
                        ti.append(int(parts[1]) - 1 if len(parts) > 1 and parts[1] else -1)
                    self.faces.append((group, vi, ti))
        self.base = [list(p) for p in self.v]

    def apply_target(self, rel, weight):
        if weight == 0:
            return
        path = os.path.join(self.root, "targets", rel)
        if not path.endswith(".target"):
            path += ".target"
        with open(path) as fh:
            for line in fh:
                if not line.strip() or line.startswith("#"):
                    continue
                a = line.split()
                i = int(a[0])
                self.v[i][0] += float(a[1]) * weight
                self.v[i][1] += float(a[2]) * weight
                self.v[i][2] += float(a[3]) * weight

    def macro(self, gender=0.0, races=None, proportions=1.0, height=0.0, muscle=0.5, weight=0.5):
        """gender 0=female 1=male; races {'african':w,'asian':w,'caucasian':w}; height -1..1."""
        races = races or {"caucasian": 1.0}
        gw = {"female": 1 - gender, "male": gender}

        def mw(v):   # 0..1 -> {min, average, max} weights
            if v < 0.5:
                return {"min": 1 - v * 2, "average": v * 2, "max": 0.0}
            return {"min": 0.0, "average": 1 - (v - 0.5) * 2, "max": (v - 0.5) * 2}
        mus, wei = mw(muscle), mw(weight)
        for g, w in gw.items():
            if w <= 0:
                continue
            for mk, m in mus.items():
                for wk, ww in wei.items():
                    k = w * m * ww
                    if k <= 0:
                        continue
                    self.apply_target(f"macrodetails/universal-{g}-young-{mk}muscle-{wk}weight", k)
                    if proportions:
                        self.apply_target(f"macrodetails/proportions/{g}-young-{mk}muscle-{wk}weight-idealproportions",
                                          k * proportions)
                    if height > 0:
                        self.apply_target(f"macrodetails/height/{g}-young-{mk}muscle-{wk}weight-maxheight", k * height)
                    elif height < 0:
                        self.apply_target(f"macrodetails/height/{g}-young-{mk}muscle-{wk}weight-minheight", -k * height)
            for race, rw in races.items():
                self.apply_target(f"macrodetails/{race}-{g}-young", w * rw)

    def mods(self, targets):
        for rel, w in targets.items():
            if w > 0:
                self.apply_target(rel + "-incr" if not rel.endswith(("-incr", "-decr", "-in", "-out", "-up", "-down")) else rel, w)
            elif w < 0:
                self.apply_target(rel + "-decr", -w)

    # ---------------------------------------------------------------
    def group_faces(self, prefix):
        return [f for f in self.faces if f[0] == prefix or (prefix.endswith("*") and f[0].startswith(prefix[:-1]))]

    def joints(self):
        out = {}
        acc = {}
        for g, vi, _ in self.faces:
            if g.startswith("joint-"):
                acc.setdefault(g[6:], set()).update(vi)
        for name, idx in acc.items():
            c = Vector((0, 0, 0))
            for i in idx:
                c += conv(*self.v[i])
            out[name] = c / len(idx)
        return out

    def submesh(self, groups):
        """Return (verts, faces, uvs-per-face-corner, group-per-face) for the given face groups (compact indices)."""
        sel = [f for f in self.faces if any(f[0] == g or (g.endswith("*") and f[0].startswith(g[:-1])) for g in groups)]
        remap = {}
        verts = []
        faces, uvs, fgroups = [], [], []
        for g, vi, ti in sel:
            face = []
            for i in vi:
                if i not in remap:
                    remap[i] = len(verts)
                    verts.append(conv(*self.v[i]))
                face.append(remap[i])
            faces.append(face)
            uvs.append([tuple(self.vt[t]) if t >= 0 else (0, 0) for t in ti])
            fgroups.append(g)
        return verts, faces, uvs, fgroups, remap
