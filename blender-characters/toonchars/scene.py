"""Scene setup: render settings, sun, fake-light empties, cameras."""
import math
import bpy
from mathutils import Vector, Euler

from . import shading
from .characters import srgb


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 120
    try:
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs[0].default_value = (*srgb("#f6efe1"), 1)
    bg.inputs[1].default_value = 1.0
    # background is only seen by the camera; it must not light the toon shading
    dark = nt.nodes.new("ShaderNodeBackground")
    dark.inputs[0].default_value = (0.02, 0.02, 0.025, 1)
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.get("World Output")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(dark.outputs[0], mix.inputs[1])
    nt.links.new(bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return scene


def collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def add_sun(coll, name="Toon_Key_Sun", rot=(48, 0, -52), energy=3.0):
    """The sun only drives the toon light/shadow split (Shader to RGB)."""
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = energy
    ld.angle = math.radians(2)
    ld.use_shadow = False   # toon split from N.L only; use the painted masks / fake lights for shadows
    ob = bpy.data.objects.new(name, ld)
    ob.rotation_euler = Euler([math.radians(a) for a in rot])
    coll.objects.link(ob)
    return ob


def add_fake_lights(name, x, coll, height=1.6):
    """Two 'manual' lights per character: a warm key blob and a cool shadow blob."""
    s = height / 1.6
    key = shading.fake_light_empty(f"FL_{name}_Key", (x - 0.16 * s, -0.25 * s, 1.5 * s), (0.5 * s,) * 3,
                                   srgb("#ffc890"), 0.35, 0.0, "LIGHT", coll)
    shadow = shading.fake_light_empty(f"FL_{name}_Shadow", (x, 0.0, -0.05 * s), (0.6 * s, 0.6 * s, 0.6 * s),
                                      srgb("#9a8fd0"), 0.4, 0.7, "SHADOW", coll)
    group = shading.fake_lights_group(f"FAKE_LIGHTS_{name}", [key, shadow])
    return group, [key, shadow]


def add_camera(coll, loc, look_at, lens=50, name="Camera", ortho=None):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    ob = bpy.data.objects.new(name, cd)
    ob.location = loc
    d = Vector(look_at) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(ob)
    bpy.context.scene.camera = ob
    return ob
