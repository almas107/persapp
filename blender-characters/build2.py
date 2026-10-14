"""Build the six characters on the anatomical MakeHuman base (v2).

blender -b -P build2.py -- [--only Racer,...] [--renders]
Needs the MakeHuman CC0 data folder (3dobjs/base.obj, targets/, rigs/) in ./mh_data
or the MH_DATA environment variable.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from toonchars import scene as sc, mhchar, mhbase, poses  # noqa: E402
from toonchars.characters import CHARACTERS  # noqa: E402

OUT = os.path.join(HERE, "output")
PREV = os.path.join(HERE, "previews")


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    only = a[a.index("--only") + 1].split(",") if "--only" in a else None
    return only, "--renders" in a, "--no-lineup" in a, "--no-single" in a


def render(path, res):
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = res
    s.render.filepath = path
    bpy.ops.render.render(write_still=True)


def build_single(spec, renders):
    sc.reset()
    coll = sc.collection(spec["name"])
    lights = sc.collection("Lights")
    sc.add_sun(lights)
    group, empties = sc.add_fake_lights(spec["name"], 0.0, lights, spec["P"]["height"])
    ch = mhchar.build(spec, coll, group, mhbase.ROOT)
    H = spec["P"]["height"]
    sc.add_camera(lights, (0.0, -3.2, H * 0.55), (0, 0, H * 0.5), lens=50)
    poses.demo_animation(spec, ch, empties)
    bpy.context.scene.frame_set(1)
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"{spec['name']}.blend"), compress=True)
    if renders:
        os.makedirs(PREV, exist_ok=True)
        render(os.path.join(PREV, f"{spec['name']}_front.png"), (700, 1100))
    return ch


def build_lineup(specs, renders):
    sc.reset()
    lights = sc.collection("Lights")
    sc.add_sun(lights)
    n = len(specs)
    for i, spec in enumerate(specs):
        x = (i - (n - 1) / 2) * 0.75
        coll = sc.collection(spec["name"])
        group, _ = sc.add_fake_lights(spec["name"], x, lights, spec["P"]["height"])
        ch = mhchar.build(spec, coll, group, mhbase.ROOT)
        ch["rig"].location.x = x
        poses.lineup_pose(spec, ch)
    sc.add_camera(lights, (0.0, -8.5, 0.95), (0, 0, 0.88), lens=50)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "Lineup.blend"), compress=True)
    if renders:
        render(os.path.join(PREV, "Lineup.png"), (2000, 1100))


def main():
    only, renders, no_lineup, no_single = args()
    specs = [c for c in CHARACTERS if not only or c["name"] in only]
    if not no_single:
        for s in specs:
            build_single(s, renders)
    if not no_lineup:
        build_lineup(specs, renders)


if __name__ == "__main__":
    main()
