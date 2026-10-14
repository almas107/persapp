"""Toon shading + "fake light" rig (the two lighting techniques).

1. TOON_Shader (node group) - hard-edged anime shading:
     Diffuse -> Shader to RGB -> threshold = lit / shadow
   plus two *painted masks* (color attributes on every mesh):
     ShadowMask  (paint white = force shadow)
     LightMask   (paint white = force light)
   so you only fix the parts that need it instead of re-lighting the shot,
   and a rim light.

2. FAKE_LIGHTS_<char> (node group) - Blender "manual lights":
     Texture Coordinate (Object = Empty) -> Vector Length -> < 1.0
   Every Empty is a sphere volume that tints whatever is inside it.  Move,
   scale (non-uniform works) and keyframe the Empty like a light; set its
   colour / strength / softness / mode in the Empty's custom properties.
"""
import bpy

MASK_SHADOW = "ShadowMask"
MASK_LIGHT = "LightMask"


def _sock(node, name, out=False, kind=None):
    socks = node.outputs if out else node.inputs
    for s in socks:
        if s.name == name and getattr(s, "enabled", True) and not getattr(s, "is_unavailable", False):
            if kind is None or s.type == kind:
                return s
    for s in socks:
        if s.name == name and (kind is None or s.type == kind):
            return s
    raise KeyError(f"{node.bl_idname}:{name}")


def _mix(nodes, blend="MIX"):
    m = nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    m.clamp_result = True
    return m


def mix_in(m, which):
    """'F' / 'A' / 'B' input socket of an RGBA ShaderNodeMix."""
    if which == "F":
        return _sock(m, "Factor", kind="VALUE")
    return _sock(m, which, kind="RGBA")


def mix_out(m):
    return _sock(m, "Result", out=True, kind="RGBA")


def _iface(ng, name, io, stype, default=None, lo=None, hi=None):
    s = ng.interface.new_socket(name=name, in_out=io, socket_type=stype)
    if default is not None:
        s.default_value = default
    if lo is not None:
        s.min_value = lo
    if hi is not None:
        s.max_value = hi
    return s


# --------------------------------------------------------------------------
def toon_group():
    if "TOON_Shader" in bpy.data.node_groups:
        return bpy.data.node_groups["TOON_Shader"]
    ng = bpy.data.node_groups.new("TOON_Shader", "ShaderNodeTree")
    _iface(ng, "Base Color", "INPUT", "NodeSocketColor", (0.8, 0.8, 0.8, 1))
    _iface(ng, "Shadow Color", "INPUT", "NodeSocketColor", (0.5, 0.45, 0.6, 1))
    _iface(ng, "Shadow Mask", "INPUT", "NodeSocketFloat", 0.0, 0.0, 1.0)
    _iface(ng, "Light Mask", "INPUT", "NodeSocketFloat", 0.0, 0.0, 1.0)
    _iface(ng, "Threshold", "INPUT", "NodeSocketFloat", 0.42, 0.0, 1.0)
    _iface(ng, "Softness", "INPUT", "NodeSocketFloat", 0.015, 0.0, 0.5)
    _iface(ng, "Rim Strength", "INPUT", "NodeSocketFloat", 0.35, 0.0, 2.0)
    _iface(ng, "Rim Color", "INPUT", "NodeSocketColor", (1.0, 0.95, 0.85, 1))
    _iface(ng, "Rim Width", "INPUT", "NodeSocketFloat", 0.22, 0.0, 1.0)
    _iface(ng, "Color", "OUTPUT", "NodeSocketColor")
    _iface(ng, "Lit", "OUTPUT", "NodeSocketFloat")
    N, Lk = ng.nodes, ng.links
    gi = N.new("NodeGroupInput"); gi.location = (-900, 0)
    go = N.new("NodeGroupOutput"); go.location = (700, 0)

    diff = N.new("ShaderNodeBsdfDiffuse"); diff.location = (-700, 250)
    s2r = N.new("ShaderNodeShaderToRGB"); s2r.location = (-500, 250)
    bw = N.new("ShaderNodeRGBToBW"); bw.location = (-320, 250)
    Lk.new(diff.outputs[0], s2r.inputs[0])
    Lk.new(_sock(s2r, "Color", out=True), bw.inputs[0])

    lo = N.new("ShaderNodeMath"); lo.operation = "SUBTRACT"; lo.location = (-500, 0)
    hi = N.new("ShaderNodeMath"); hi.operation = "ADD"; hi.location = (-500, -150)
    for m in (lo, hi):
        Lk.new(gi.outputs["Threshold"], m.inputs[0])
        Lk.new(gi.outputs["Softness"], m.inputs[1])
    mr = N.new("ShaderNodeMapRange"); mr.location = (-150, 200)
    mr.interpolation_type = "SMOOTHSTEP"
    mr.clamp = True
    Lk.new(bw.outputs[0], mr.inputs["Value"])
    Lk.new(lo.outputs[0], mr.inputs["From Min"])
    Lk.new(hi.outputs[0], mr.inputs["From Max"])

    # painted masks: lit = max(toon * (1 - shadowMask), lightMask)
    inv = N.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.location = (-150, -50)
    inv.inputs[0].default_value = 1.0
    Lk.new(gi.outputs["Shadow Mask"], inv.inputs[1])
    mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.location = (40, 120)
    Lk.new(_sock(mr, "Result", out=True), mul.inputs[0])
    Lk.new(inv.outputs[0], mul.inputs[1])
    mx = N.new("ShaderNodeMath"); mx.operation = "MAXIMUM"; mx.location = (200, 120)
    Lk.new(mul.outputs[0], mx.inputs[0])
    Lk.new(gi.outputs["Light Mask"], mx.inputs[1])

    col = _mix(N); col.location = (380, 120)
    Lk.new(mx.outputs[0], mix_in(col, "F"))
    Lk.new(gi.outputs["Shadow Color"], mix_in(col, "A"))
    Lk.new(gi.outputs["Base Color"], mix_in(col, "B"))

    # rim light (only on the lit side)
    lw = N.new("ShaderNodeLayerWeight"); lw.location = (-150, -250)
    Lk.new(gi.outputs["Rim Width"], lw.inputs["Blend"])
    rmr = N.new("ShaderNodeMapRange"); rmr.location = (40, -250)
    rmr.inputs["From Min"].default_value = 0.55
    rmr.inputs["From Max"].default_value = 0.6
    Lk.new(_sock(lw, "Facing", out=True), rmr.inputs["Value"])
    r1 = N.new("ShaderNodeMath"); r1.operation = "MULTIPLY"; r1.location = (200, -200)
    Lk.new(_sock(rmr, "Result", out=True), r1.inputs[0])
    Lk.new(mx.outputs[0], r1.inputs[1])
    r2 = N.new("ShaderNodeMath"); r2.operation = "MULTIPLY"; r2.location = (380, -200)
    Lk.new(r1.outputs[0], r2.inputs[0])
    Lk.new(gi.outputs["Rim Strength"], r2.inputs[1])
    rim = _mix(N, "SCREEN"); rim.location = (550, 0)
    Lk.new(r2.outputs[0], mix_in(rim, "F"))
    Lk.new(mix_out(col), mix_in(rim, "A"))
    Lk.new(gi.outputs["Rim Color"], mix_in(rim, "B"))
    Lk.new(mix_out(rim), go.inputs["Color"])
    Lk.new(mx.outputs[0], go.inputs["Lit"])
    return ng


# --------------------------------------------------------------------------
def fake_light_empty(name, location, scale, color, strength, softness, mode, collection):
    """mode: 'LIGHT' (screen-add colour) or 'SHADOW' (multiply colour)."""
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "SPHERE"
    e.empty_display_size = 1.0
    e.location = location
    e.scale = scale
    e["fl_color"] = list(color)
    e.id_properties_ui("fl_color").update(subtype="COLOR", min=0.0, max=1.0)
    e["fl_strength"] = strength
    e.id_properties_ui("fl_strength").update(min=0.0, max=1.0)
    e["fl_softness"] = softness
    e.id_properties_ui("fl_softness").update(min=0.0, max=1.0,
                                             description="0 = hard edge (Less Than 1.0), 1 = soft falloff")
    e["fl_mode"] = mode
    collection.objects.link(e)
    return e


def fake_lights_group(gname, empties):
    """Build the per-character FAKE_LIGHTS group: Color in -> Color out."""
    ng = bpy.data.node_groups.new(gname, "ShaderNodeTree")
    _iface(ng, "Color", "INPUT", "NodeSocketColor", (1, 1, 1, 1))
    _iface(ng, "Color", "OUTPUT", "NodeSocketColor")
    N, Lk = ng.nodes, ng.links
    gi = N.new("NodeGroupInput"); gi.location = (-900, 0)
    go = N.new("NodeGroupOutput")
    cur = gi.outputs["Color"]
    x = -600
    for i, e in enumerate(empties):
        y = -i * 420
        tc = N.new("ShaderNodeTexCoord"); tc.object = e; tc.location = (x, y)
        tc.label = f"{e.name} (Object coords)"
        ln = N.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; ln.location = (x + 200, y)
        Lk.new(_sock(tc, "Object", out=True), ln.inputs[0])
        # inside the unit sphere -> 1 ; softness widens the edge inward
        soft = N.new("ShaderNodeValue"); soft.name = soft.label = f"{e.name} softness"
        soft.location = (x + 200, y - 160)
        one_minus = N.new("ShaderNodeMath"); one_minus.operation = "SUBTRACT"
        one_minus.inputs[0].default_value = 1.0; one_minus.location = (x + 380, y - 160)
        Lk.new(soft.outputs[0], one_minus.inputs[1])
        mr = N.new("ShaderNodeMapRange"); mr.location = (x + 560, y)
        mr.interpolation_type = "SMOOTHSTEP"; mr.clamp = True
        mr.inputs["From Min"].default_value = 1.0     # length 1 -> 0
        mr.inputs["To Min"].default_value = 0.0
        mr.inputs["To Max"].default_value = 1.0
        Lk.new(_sock(ln, "Value", out=True), mr.inputs["Value"])
        Lk.new(one_minus.outputs[0], mr.inputs["From Max"])  # length (1-soft) -> 1
        # hard version (exactly the video's "Less Than 1.0") when softness == 0
        lt = N.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.location = (x + 560, y - 220)
        lt.inputs[1].default_value = 1.0
        Lk.new(_sock(ln, "Value", out=True), lt.inputs[0])
        is_hard = N.new("ShaderNodeMath"); is_hard.operation = "LESS_THAN"; is_hard.location = (x + 380, y - 300)
        is_hard.inputs[1].default_value = 0.001
        Lk.new(soft.outputs[0], is_hard.inputs[0])
        pick = N.new("ShaderNodeMix"); pick.data_type = "FLOAT"; pick.location = (x + 760, y - 100)
        Lk.new(is_hard.outputs[0], _sock(pick, "Factor", kind="VALUE"))
        Lk.new(_sock(mr, "Result", out=True), _sock(pick, "A", kind="VALUE"))
        Lk.new(lt.outputs[0], _sock(pick, "B", kind="VALUE"))
        strength = N.new("ShaderNodeValue"); strength.name = strength.label = f"{e.name} strength"
        strength.location = (x + 760, y - 300)
        fac = N.new("ShaderNodeMath"); fac.operation = "MULTIPLY"; fac.location = (x + 940, y - 100)
        Lk.new(_sock(pick, "Result", out=True, kind="VALUE"), fac.inputs[0])
        Lk.new(strength.outputs[0], fac.inputs[1])
        rgb = N.new("ShaderNodeRGB"); rgb.name = rgb.label = f"{e.name} color"; rgb.location = (x + 940, y - 260)
        # LIGHT: colour * (light colour * 2)  -> warm brightening that keeps darks dark
        # SHADOW: colour * shadow colour
        tint = _mix(N, "MULTIPLY")
        tint.location = (x + 1000, y - 420)
        tint.clamp_result = False
        mix_in(tint, "F").default_value = 1.0
        Lk.new(cur, mix_in(tint, "A"))
        if e["fl_mode"] == "LIGHT":
            dbl = N.new("ShaderNodeVectorMath"); dbl.operation = "SCALE"; dbl.location = (x + 1000, y - 560)
            dbl.inputs["Scale"].default_value = 2.0
            Lk.new(rgb.outputs[0], dbl.inputs[0])
            Lk.new(dbl.outputs[0], mix_in(tint, "B"))
        else:
            Lk.new(rgb.outputs[0], mix_in(tint, "B"))
        mix = _mix(N, "MIX")
        mix.clamp_result = False
        mix.location = (x + 1140, y)
        mix.label = f"{e.name} ({e['fl_mode'].lower()})"
        Lk.new(fac.outputs[0], mix_in(mix, "F"))
        Lk.new(cur, mix_in(mix, "A"))
        Lk.new(mix_out(tint), mix_in(mix, "B"))
        cur = mix_out(mix)
        # drive node values from the Empty's custom properties
        for path, prop, idx in ((f'nodes["{soft.name}"].outputs[0].default_value', "fl_softness", None),
                                (f'nodes["{strength.name}"].outputs[0].default_value', "fl_strength", None),
                                (f'nodes["{rgb.name}"].outputs[0].default_value', "fl_color", 0),
                                (f'nodes["{rgb.name}"].outputs[0].default_value', "fl_color", 1),
                                (f'nodes["{rgb.name}"].outputs[0].default_value', "fl_color", 2)):
            fc = ng.driver_add(path, idx) if idx is not None else ng.driver_add(path)
            d = fc.driver
            d.type = "SCRIPTED"
            v = d.variables.new()
            v.name = "v"
            v.targets[0].id = e
            v.targets[0].data_path = f'["{prop}"]' + (f"[{idx}]" if idx is not None else "")
            d.expression = "v"
        rgb.outputs[0].default_value = (*e["fl_color"], 1.0)
        strength.outputs[0].default_value = e["fl_strength"]
        soft.outputs[0].default_value = e["fl_softness"]
        x += 0
    go.location = (900, 0)
    Lk.new(cur, go.inputs["Color"])
    return ng


# --------------------------------------------------------------------------
def toon_material(name, base, shadow, fake_group, rim=0.35, threshold=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    tg = N.new("ShaderNodeGroup"); tg.node_tree = toon_group(); tg.location = (0, 0)
    tg.inputs["Base Color"].default_value = (*base, 1)
    tg.inputs["Shadow Color"].default_value = (*shadow, 1)
    tg.inputs["Rim Strength"].default_value = rim
    if threshold is not None:
        tg.inputs["Threshold"].default_value = threshold
    for i, (attr, sock) in enumerate(((MASK_SHADOW, "Shadow Mask"), (MASK_LIGHT, "Light Mask"))):
        ca = N.new("ShaderNodeVertexColor"); ca.layer_name = attr; ca.location = (-300, -120 - i * 140)
        ca.label = f"{attr} (paint in Vertex Paint)"
        Lk.new(_sock(ca, "Color", out=True), tg.inputs[sock])
    fl = N.new("ShaderNodeGroup"); fl.node_tree = fake_group; fl.location = (300, 0)
    Lk.new(tg.outputs["Color"], fl.inputs["Color"])
    em = N.new("ShaderNodeEmission"); em.location = (600, 0)
    Lk.new(fl.outputs["Color"], em.inputs["Color"])
    Lk.new(em.outputs[0], out.inputs["Surface"])
    mat.diffuse_color = (*base, 1)
    return mat


def flat_material(name, color, fake_group=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    rgb = N.new("ShaderNodeRGB"); rgb.outputs[0].default_value = (*color, 1); rgb.location = (-200, 0)
    em = N.new("ShaderNodeEmission"); em.location = (350, 0)
    src = rgb.outputs[0]
    if fake_group is not None:
        fl = N.new("ShaderNodeGroup"); fl.node_tree = fake_group; fl.location = (80, 0)
        Lk.new(src, fl.inputs["Color"])
        src = fl.outputs["Color"]
    Lk.new(src, em.inputs["Color"])
    Lk.new(em.outputs[0], out.inputs["Surface"])
    mat.diffuse_color = (*color, 1)
    return mat


def outline_material(name, color):
    mat = flat_material(name, color)
    mat.use_backface_culling = True
    return mat


def add_mask_attributes(obj):
    me = obj.data
    for n in (MASK_SHADOW, MASK_LIGHT):
        if n not in me.color_attributes:
            me.color_attributes.new(name=n, type="BYTE_COLOR", domain="POINT")
            attr = me.color_attributes[n]
            for d in attr.data:
                d.color = (0.0, 0.0, 0.0, 1.0)


def add_outline(obj, outline_mat, thickness):
    obj.data.materials.append(outline_mat)
    mod = obj.modifiers.new("Outline", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = 1.0
    mod.use_flip_normals = True
    mod.use_rim = False
    mod.material_offset = len(obj.data.materials) - 1
    mod.use_quality_normals = True
    return mod
