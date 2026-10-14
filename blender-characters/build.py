"""Build the rigged toon characters.

Run with Blender:   blender -b -P build.py -- [--only Rebel,Racer] [--renders]
or with the bpy module:   python build.py [--only ...] [--renders]

Outputs (next to this script):
  output/<Name>.blend   one character + lights + camera (+ demo animation)
  output/Lineup.blend   all six characters posed like the reference sheet
  previews/*.png        quick renders (with --renders)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402

from toonchars import scene as sc  # noqa: E402
from toonchars.characters import CHARACTERS  # noqa: E402
from toonchars.assemble import build_character  # noqa: E402
from toonchars import poses  # noqa: E402

OUT = os.path.join(HERE, "output")
PREV = os.path.join(HERE, "previews")


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    only = None
    renders = "--renders" in a
    skip_lineup = "--no-lineup" in a
    skip_single = "--no-single" in a
    if "--only" in a:
        only = a[a.index("--only") + 1].split(",")
    return only, renders, skip_lineup, skip_single


def render(path, res=(900, 1200)):
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.filepath = path
    bpy.ops.render.render(write_still=True)


def build_single(spec, renders):
    sc.reset()
    coll = sc.collection(spec["name"])
    lights = sc.collection("Lights")
    sc.add_sun(lights)
    group, empties = sc.add_fake_lights(spec["name"], 0.0, lights, spec["P"]["height"])
    ch = build_character(spec, coll, group)
    H = spec["P"]["height"]
    cam = sc.add_camera(lights, (0.0, -3.0, H * 0.56), (0, 0, H * 0.5), lens=50)
    poses.demo_animation(spec, ch, empties)
    bpy.context.scene.frame_set(1)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{spec['name']}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("saved", path)
    if renders:
        os.makedirs(PREV, exist_ok=True)
        render(os.path.join(PREV, f"{spec['name']}_front.png"), (700, 1100))
        poses.expression_sheet(spec, ch, os.path.join(PREV, f"{spec['name']}_expressions.png"), render)
    return ch


def build_lineup(specs, renders):
    sc.reset()
    lights = sc.collection("Lights")
    sc.add_sun(lights)
    gap = 0.72
    n = len(specs)
    for i, spec in enumerate(specs):
        x = (i - (n - 1) / 2) * gap
        coll = sc.collection(spec["name"])
        group, empties = sc.add_fake_lights(spec["name"], x, lights, spec["P"]["height"])
        ch = build_character(spec, coll, group)
        ch["rig"].location.x = x
        poses.lineup_pose(spec, ch)
    sc.add_camera(lights, (0.0, -9.0, 1.0), (0, 0, 0.9), lens=50)
    path = os.path.join(OUT, "Lineup.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("saved", path)
    if renders:
        render(os.path.join(PREV, "Lineup.png"), (1800, 1000))


def main():
    only, renders, skip_lineup, skip_single = args()
    specs = [c for c in CHARACTERS if not only or c["name"] in only]
    if not skip_single:
        for spec in specs:
            build_single(spec, renders)
    if not skip_lineup:
        build_lineup(specs, renders)


if __name__ == "__main__":
    main()
