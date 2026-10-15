# Runs INSIDE Blender (headless): clean scene -> user's bpy script -> export -> auto-framed preview / turntable.
#   blender -b -P blender_run.py -- <script.py> <out> [--preview p.png] [--turntable dir N] [--engine CYCLES|BLENDER_EEVEE] [--res 768]
# <out> extension picks the format: .glb .gltf .obj .fbx .stl .ply .blend
import math
import os
import runpy
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
script, out = argv[0], argv[1]
opt = {"preview": None, "turntable": None, "n": 36, "engine": "CYCLES", "res": 768}
i = 2
while i < len(argv):
    if argv[i] == "--preview": opt["preview"] = argv[i + 1]; i += 2
    elif argv[i] == "--turntable": opt["turntable"], opt["n"] = argv[i + 1], int(argv[i + 2]); i += 3
    elif argv[i] == "--engine": opt["engine"] = argv[i + 1]; i += 2
    elif argv[i] == "--res": opt["res"] = int(argv[i + 1]); i += 2
    else: i += 1

bpy.ops.wm.read_factory_settings(use_empty=True)
runpy.run_path(script, run_name="__main__")           # the script builds the model in the (empty) scene
objs = [o for o in bpy.context.scene.objects if o.type in ("MESH", "CURVE", "SURFACE", "META", "FONT")]
if not objs: sys.exit("ERROR: el script no creó ningún objeto de malla")

# --- export
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
ext = os.path.splitext(out)[1].lower()
bpy.ops.object.select_all(action="DESELECT")
for o in objs: o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
if ext in (".glb", ".gltf"): bpy.ops.export_scene.gltf(filepath=out, use_selection=True, export_format="GLB" if ext == ".glb" else "GLTF_SEPARATE")
elif ext == ".obj": bpy.ops.wm.obj_export(filepath=out, export_selected_objects=True)
elif ext == ".fbx": bpy.ops.export_scene.fbx(filepath=out, use_selection=True)
elif ext == ".stl": bpy.ops.wm.stl_export(filepath=out, export_selected_objects=True)
elif ext == ".ply": bpy.ops.wm.ply_export(filepath=out, export_selected_objects=True)
elif ext == ".blend": bpy.ops.wm.save_as_mainfile(filepath=out)
else: sys.exit(f"ERROR: formato no soportado: {ext}")

# --- bounding box of everything
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ctr, size = (lo + hi) / 2, max((hi - lo).length, 1e-3)
print(f"MODEL objects={len(objs)} dims={tuple(round(v, 3) for v in (hi - lo))} verts={sum(len(o.data.vertices) for o in objs if o.type == 'MESH')}")

if not (opt["preview"] or opt["turntable"]): sys.exit(0)

# --- studio: world light, sun, camera on an orbit
sc = bpy.context.scene
sc.render.engine = opt["engine"] if opt["engine"] in ("CYCLES", "BLENDER_EEVEE", "BLENDER_WORKBENCH") else "CYCLES"
if sc.render.engine == "CYCLES": sc.cycles.samples, sc.cycles.use_denoising = 24, False
sc.render.resolution_x = sc.render.resolution_y = opt["res"]
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.09, 0.09, 0.11, 1); bg.inputs[1].default_value = 0.8
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35)); sc.collection.objects.link(sun)
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); fill.data.energy = 300 * size; fill.data.size = size
fill.location = ctr + Vector((-size, -size, size * 0.4)); sc.collection.objects.link(fill)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50; dist = size * 1.9


def shoot(angle, path, elev=22):
    a, e = math.radians(angle), math.radians(elev)
    cam.location = ctr + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if opt["preview"]:   # 2x2 contact sheet is overkill: one 3/4 view + front view
    base, e = os.path.splitext(opt["preview"])
    shoot(35, opt["preview"]); shoot(215, f"{base}_back{e}"); shoot(90, f"{base}_side{e}", 10)
if opt["turntable"]:
    os.makedirs(opt["turntable"], exist_ok=True)
    for k in range(opt["n"]): shoot(360 * k / opt["n"], os.path.join(opt["turntable"], f"{k:04d}.png"))
