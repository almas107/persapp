"""Skeleton layout + armature construction (FK/IK, face controls, widgets)."""
import math
import bpy
from mathutils import Vector, Matrix

from .meshkit import V


# --------------------------------------------------------------------------
# Joint layout
# --------------------------------------------------------------------------
class Skeleton:
    """Computes joint positions from body proportions (rest pose = A-pose).

    Character faces -Y, +Z up, left side of the character is +X.
    """

    def __init__(self, P):
        self.P = P
        H = P["height"]
        s = H / 1.6
        self.s = s
        hh = P["head_h"]
        self.crown = H
        self.chin = H - hh
        self.hips_z = 0.55 * H
        self.spine_z = 0.62 * H
        self.chest_z = 0.70 * H
        self.neck_z = self.chin - 0.05 * s
        sw = P.get("shoulder_x", 0.155) * s
        hw = P.get("hip_x", 0.085) * s
        self.bones = {}      # name -> dict(head, tail, parent, roll, deform, coll)

        def add(name, head, tail, parent, roll=(0, -1, 0), deform=True, coll="Body"):
            self.bones[name] = dict(head=V(head), tail=V(tail), parent=parent,
                                    roll=V(roll), deform=deform, coll=coll)

        add("root", (0, 0, 0), (0, 0.35 * s, 0), None, roll=(0, 0, 1), deform=False, coll="Root")
        add("torso", (0, 0, self.hips_z), (0, 0.22 * s, self.hips_z), "root", roll=(0, 0, 1),
            deform=False, coll="Root")
        add("hips", (0, 0, self.hips_z + 0.02 * s), (0, 0, self.hips_z - 0.10 * s), "torso")
        add("spine", (0, 0, self.hips_z + 0.02 * s), (0, 0.004 * s, self.spine_z + 0.05 * s), "torso")
        add("chest", self.bones["spine"]["tail"], (0, 0.004 * s, self.neck_z), "spine")
        add("neck", (0, 0.004 * s, self.neck_z), (0, 0.0, self.chin + 0.03 * s), "chest")
        add("head", (0, 0.0, self.chin + 0.03 * s), (0, 0, H + 0.02 * s), "neck")

        # ---------------- arms (built for the left side, mirrored later)
        a = math.radians(P.get("arm_angle", 42))
        d = V(math.cos(a), 0, -math.sin(a))
        n = V(math.sin(a), 0, math.cos(a))          # back of hand / outward-up
        T = V(0, -1, 0)                             # thumb direction
        self.arm_dir, self.hand_up = d, n
        sh_z = self.neck_z - 0.03 * s
        shoulder = V(sw, 0.012 * s, sh_z)
        up_len, fo_len = 0.168 * H, 0.148 * H
        elbow = shoulder + d * up_len + V(0, 0.018 * s, 0)
        wrist = elbow + d * fo_len + V(0, -0.012 * s, 0)
        palm = 0.058 * H
        knuckle = wrist + d * palm
        self.joints = dict(shoulder=shoulder, elbow=elbow, wrist=wrist, knuckle=knuckle)
        add("shoulder.L", (0.025 * s, 0.006 * s, sh_z + 0.012 * s), shoulder, "chest", roll=(0, 0, 1))
        add("upper_arm.L", shoulder, elbow, "shoulder.L", roll=n)
        add("forearm.L", elbow, wrist, "upper_arm.L", roll=n)
        add("hand.L", wrist, knuckle, "forearm.L", roll=n)

        hs = s * P.get("hand_scale", 1.0)
        self.fingers = {}
        spec = {
            "index": (0.026, 0.004, [0.034, 0.021, 0.017], -6),
            "middle": (0.009, 0.0, [0.037, 0.023, 0.018], 0),
            "ring": (-0.009, -0.003, [0.034, 0.021, 0.017], 5),
            "pinky": (-0.025, -0.010, [0.026, 0.016, 0.014], 11),
        }
        for fname, (off, along, lens, spread) in spec.items():
            base = knuckle + T * off * hs + d * along * hs
            fd = Matrix.Rotation(math.radians(-spread), 3, n) @ d
            pts = [base]
            dirv = fd.copy()
            for L in lens:
                dirv = (Matrix.Rotation(math.radians(9), 3, fd.cross(n)) @ dirv).normalized()
                pts.append(pts[-1] + dirv * L * hs)
            self.fingers[fname] = pts
            for i in range(3):
                add(f"{fname}_{i + 1}.L", pts[i], pts[i + 1],
                    "hand.L" if i == 0 else f"{fname}_{i}.L", roll=n, coll="Fingers")
        tb = wrist + d * 0.02 * hs + T * 0.018 * hs - n * 0.012 * hs
        td = (d * 0.55 + T * 0.75 - n * 0.35).normalized()
        pts = [tb]
        for L in (0.030, 0.024, 0.019):
            pts.append(pts[-1] + td * L * hs)
            td = (td + d * 0.25 - T * 0.05).normalized()
        self.fingers["thumb"] = pts
        for i in range(3):
            add(f"thumb_{i + 1}.L", pts[i], pts[i + 1], "hand.L" if i == 0 else f"thumb_{i}.L",
                roll=n, coll="Fingers")

        # ---------------- legs
        hip_j = V(hw, 0.0, 0.535 * H)
        knee = V(hw * 0.96, -0.014 * s, 0.29 * H)
        ankle = V(hw * 0.92, 0.012 * s, 0.05 * H)
        ball = V(hw * 0.92, -0.085 * s, 0.012 * H)
        toe = V(hw * 0.92, -0.15 * s, 0.012 * H)
        self.joints.update(hip=hip_j, knee=knee, ankle=ankle, ball=ball, toe=toe)
        add("thigh.L", hip_j, knee, "hips")
        add("shin.L", knee, ankle, "thigh.L")
        add("foot.L", ankle, ball, "shin.L", roll=(0, 0, 1))
        add("toe.L", ball, toe, "foot.L", roll=(0, 0, 1))

        # ---------------- IK controls
        add("foot_ik.L", ankle, ankle + V(0, -0.12 * s, 0), "root", roll=(0, 0, 1), deform=False, coll="IK")
        add("knee_pole.L", knee + V(0, -0.35 * s, 0), knee + V(0, -0.42 * s, 0), "root", roll=(0, 0, 1),
            deform=False, coll="IK")
        add("hand_ik.L", wrist, wrist + d * 0.09 * s, "root", roll=n, deform=False, coll="IK")
        add("elbow_pole.L", elbow + V(0, 0.32 * s, 0), elbow + V(0, 0.39 * s, 0), "root", roll=(0, 0, 1),
            deform=False, coll="IK")

        # ---------------- face controls
        self.eye_z = P.get("eye_z", None)
        add("eye_target", (0, -0.45 * s, H - hh * 0.55), (0, -0.45 * s, H - hh * 0.55 + 0.05 * s),
            "head", roll=(0, -1, 0), deform=False, coll="Face")
        add("face_ctrl", (0.0, 0.0, H + 0.10 * s), (0.0, 0, H + 0.16 * s), "head", roll=(0, -1, 0),
            deform=False, coll="Face")

        self.mirror()

    def mirror(self):
        for name in list(self.bones):
            if name.endswith(".L"):
                b = self.bones[name]
                m = lambda v: V(-v.x, v.y, v.z)
                par = b["parent"]
                if par and par.endswith(".L"):
                    par = par[:-2] + ".R"
                self.bones[name[:-2] + ".R"] = dict(head=m(b["head"]), tail=m(b["tail"]), parent=par,
                                                    roll=m(b["roll"]), deform=b["deform"], coll=b["coll"])

    def add_chain(self, prefix, points, parent, coll="Hair"):
        names = []
        base, suffix = (prefix[:-2], prefix[-2:]) if prefix.endswith((".L", ".R")) else (prefix, "")
        for i in range(len(points) - 1):
            nm = f"{base}_{i + 1}{suffix}"
            self.bones[nm] = dict(head=V(points[i]), tail=V(points[i + 1]),
                                  parent=parent if i == 0 else names[-1],
                                  roll=V(0, -1, 0), deform=True, coll=coll)
            names.append(nm)
        return names

    def seg(self, name):
        b = self.bones[name]
        return (name, b["head"], b["tail"])

    def chain(self, *names):
        return [self.seg(n) for n in names]

    def j(self, name, side="L"):
        p = self.joints[name]
        return p if side == "L" else V(-p.x, p.y, p.z)

    def finger_pts(self, fname, side="L"):
        pts = self.fingers[fname]
        return pts if side == "L" else [V(-p.x, p.y, p.z) for p in pts]


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------
def _widget(name, verts, edges):
    if name in bpy.data.objects:
        return bpy.data.objects[name]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    coll = bpy.data.collections.get("WGTS")
    if coll is None:
        coll = bpy.data.collections.new("WGTS")
        bpy.context.scene.collection.children.link(coll)
        coll.hide_render = True
        coll.hide_viewport = True
    coll.objects.link(ob)
    return ob


def widget_circle(name="WGT_circle", r=1.0, n=32, axis="Y"):
    vs = []
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s = math.cos(a) * r, math.sin(a) * r
        vs.append((c, 0, s) if axis == "Y" else (c, s, 0))
    return _widget(name, vs, [(i, (i + 1) % n) for i in range(n)])


def widget_sphere(name="WGT_sphere"):
    vs, es = [], []
    for ax in range(3):
        base = len(vs)
        for i in range(24):
            a = 2 * math.pi * i / 24
            c, s = math.cos(a), math.sin(a)
            vs.append([(c, s, 0), (c, 0, s), (0, c, s)][ax])
            es.append((base + i, base + (i + 1) % 24))
    return _widget(name, vs, es)


def widget_square(name="WGT_square"):
    vs = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
    return _widget(name, vs, [(0, 1), (1, 2), (2, 3), (3, 0)])


def widget_foot(name="WGT_foot"):
    vs = [(-0.5, 0, 0), (0.5, 0, 0), (0.5, 1.2, 0), (-0.5, 1.2, 0)]
    return _widget(name, vs, [(0, 1), (1, 2), (2, 3), (3, 0)])


# --------------------------------------------------------------------------
# Armature
# --------------------------------------------------------------------------
FACE_PROPS = []   # filled by face module (list of shape key names exposed on face_ctrl)


def build_armature(name, sk, collection):
    arm = bpy.data.armatures.new(name + "_Armature")
    arm.display_type = "OCTAHEDRAL"
    rig = bpy.data.objects.new(name + "_Rig", arm)
    collection.objects.link(rig)
    rig.show_in_front = True
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    for bn, b in sk.bones.items():
        e = eb.new(bn)
        e.head, e.tail = b["head"], b["tail"]
        e.use_deform = b["deform"]
    for bn, b in sk.bones.items():
        e = eb[bn]
        if b["parent"]:
            e.parent = eb[b["parent"]]
            if (e.head - e.parent.tail).length < 1e-5 and b["coll"] in ("Body", "Fingers", "Hair") \
                    and not bn.startswith(("thigh", "shoulder", "spine", "hips")):
                e.use_connect = True
        e.align_roll(b["roll"])
    bpy.ops.object.mode_set(mode="POSE")

    # bone collections
    colls = {}
    for cn in ("Root", "Body", "IK", "Fingers", "Face", "Hair"):
        colls[cn] = arm.collections.new(cn)
    for bn, b in sk.bones.items():
        colls[b["coll"]].assign(arm.bones[bn])

    pb = rig.pose.bones
    circ = widget_circle()
    sq = widget_square()
    sph = widget_sphere()
    foot = widget_foot()
    for p in pb:
        p.rotation_mode = "QUATERNION" if p.name not in ("eye_target", "face_ctrl") else "XYZ"
        c = sk.bones[p.name]["coll"]
        if p.name.endswith(".R"):
            p.color.palette = "THEME01"
        elif p.name.endswith(".L"):
            p.color.palette = "THEME03"
        elif c == "Hair":
            p.color.palette = "THEME06"
        else:
            p.color.palette = "THEME09"
        if p.name == "root":
            p.custom_shape = circ
            p.custom_shape_scale_xyz = (2.2, 2.2, 2.2)
            p.custom_shape_rotation_euler = (math.pi / 2, 0, 0)
        elif p.name == "torso":
            p.custom_shape = circ
            p.custom_shape_scale_xyz = (1.3, 1.3, 1.3)
        elif p.name.startswith("foot_ik"):
            p.custom_shape = foot
            p.custom_shape_rotation_euler = (0, 0, math.pi)
            p.custom_shape_translation = (0, 0, -sk.joints["ankle"].z)
        elif p.name.startswith(("knee_pole", "elbow_pole", "hand_ik")):
            p.custom_shape = sph
            p.custom_shape_scale_xyz = (0.35, 0.35, 0.35)
        elif p.name == "eye_target":
            p.custom_shape = circ
            p.custom_shape_scale_xyz = (0.8, 0.8, 0.8)
            p.custom_shape_rotation_euler = (math.pi / 2, 0, 0)
            p.lock_rotation = (True, True, True)
            p.lock_location[1] = True
        elif p.name == "face_ctrl":
            p.custom_shape = sq
            p.custom_shape_scale_xyz = (0.6, 0.6, 0.6)
            p.lock_location = (True, True, True)
            p.lock_rotation = (True, True, True)
            p.lock_scale = (True, True, True)
        elif c in ("Body", "Fingers", "Hair") and p.name not in ("hips",):
            p.custom_shape = circ
            p.custom_shape_scale_xyz = (0.25, 0.25, 0.25) if c != "Body" else (0.35, 0.35, 0.35)
            p.custom_shape_translation = (0, (p.bone.length * 0.5), 0)
            p.use_custom_shape_bone_size = True
        elif p.name == "hips":
            p.custom_shape = circ
            p.custom_shape_scale_xyz = (1.6, 1.6, 1.6)
            p.custom_shape_translation = (0, p.bone.length, 0)

    # ---------- IK legs (on by default) and arms (off by default = FK)
    def ik_prop(prop, default):
        pb["torso"][prop] = default
        pb["torso"].id_properties_ui(prop).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0,
                                                  description="0 = FK, 1 = IK")
        pb["torso"].property_overridable_library_set(f'["{prop}"]', True)

    def drive(con, prop):
        fc = con.driver_add("influence")
        drv = fc.driver
        drv.type = "AVERAGE"
        v = drv.variables.new()
        v.name = "ik"
        v.targets[0].id = rig
        v.targets[0].data_path = f'pose.bones["torso"]["{prop}"]'

    for side in ("L", "R"):
        ik_prop(f"leg_ik.{side}", 1.0)
        ik_prop(f"arm_ik.{side}", 0.0)
        for (mid, tip, tgt, pole, prop) in (
                (f"shin.{side}", f"foot.{side}", f"foot_ik.{side}", f"knee_pole.{side}", f"leg_ik.{side}"),
                (f"forearm.{side}", f"hand.{side}", f"hand_ik.{side}", f"elbow_pole.{side}", f"arm_ik.{side}")):
            ik = pb[mid].constraints.new("IK")
            ik.target = rig
            ik.subtarget = tgt
            ik.pole_target = rig
            ik.pole_subtarget = pole
            ik.chain_count = 2
            drive(ik, prop)
            cr = pb[tip].constraints.new("COPY_ROTATION")
            cr.target = rig
            cr.subtarget = tgt
            drive(cr, prop)
        pb[f"shin.{side}"].ik_min_x = 0
        pb[f"shin.{side}"].lock_ik_y = pb[f"shin.{side}"].lock_ik_z = True
    _solve_pole_angles(rig)
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def _solve_pole_angles(rig):
    """Pick the IK pole angle that keeps the rest pose unchanged."""
    pb = rig.pose.bones
    for side in ("L", "R"):
        for prop, mid, upper in ((f"leg_ik.{side}", f"shin.{side}", f"thigh.{side}"),
                                 (f"arm_ik.{side}", f"forearm.{side}", f"upper_arm.{side}")):
            ik = [c for c in pb[mid].constraints if c.type == "IK"][0]
            old = pb["torso"][prop]
            pb["torso"][prop] = 1.0
            best = None
            for deg in range(-180, 180, 5):
                ik.pole_angle = math.radians(deg)
                bpy.context.view_layer.update()
                err = 0.0
                for bn in (mid, upper):
                    m = pb[bn].matrix
                    r = rig.data.bones[bn].matrix_local
                    err += (m.col[0].xyz - r.col[0].xyz).length + (m.col[2].xyz - r.col[2].xyz).length
                if best is None or err < best[0]:
                    best = (err, deg)
            ik.pole_angle = math.radians(best[1])
            pb["torso"][prop] = old
    bpy.context.view_layer.update()


def add_face_props(rig, names, defaults=None):
    pb = rig.pose.bones["face_ctrl"]
    for n in names:
        pb[n] = float((defaults or {}).get(n, 0.0))
        pb.id_properties_ui(n).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0)
        pb.property_overridable_library_set(f'["{n}"]', True)


def drive_shape_keys(rig, face_obj, names, look_range):
    """Shape key value <- face_ctrl custom property (and eye_target for Look_*)."""
    keys = face_obj.data.shape_keys.key_blocks
    for n in names:
        fc = keys[n].driver_add("value")
        d = fc.driver
        d.type = "SCRIPTED"
        v = d.variables.new()
        v.name = "p"
        v.targets[0].id = rig
        v.targets[0].data_path = f'pose.bones["face_ctrl"]["{n}"]'
        d.expression = "p"
    for n, axis, sign in (("Look_Left", "LOC_X", 1), ("Look_Right", "LOC_X", -1),
                          ("Look_Up", "LOC_Z", 1), ("Look_Down", "LOC_Z", -1)):
        fc = keys[n].driver_add("value")
        d = fc.driver
        d.type = "SCRIPTED"
        v = d.variables.new()
        v.name = "t"
        v.type = "TRANSFORMS"
        v.targets[0].id = rig
        v.targets[0].bone_target = "eye_target"
        v.targets[0].transform_type = axis
        v.targets[0].transform_space = "LOCAL_SPACE"
        # bone local axes: eye_target points +Z (world) so its local Y = world Z,
        # local X = world X.  LOC_Z in local space is world -Y (unused).
        if axis == "LOC_Z":
            v.targets[0].transform_type = "LOC_Y"
        d.expression = f"min(1, max(0, {sign}*t/{look_range:.4f}))"
