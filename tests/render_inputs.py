"""按顺序导入若干 bundle / zipmod 并渲染一张预览图，用来肉眼确认摆放对不对。

运行：
  blender -b --factory-startup --python tests/render_inputs.py -- <输出.png> <输入1> [输入2 ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_addon"))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402


def arguments() -> tuple[Path, list[Path]]:
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        raise SystemExit("用法：-- <输出.png> <输入1> [输入2 ...]")
    return Path(args[0]), [Path(item) for item in args[1:]]


def scene_bounds():
    points = []
    for object_ in bpy.data.objects:
        if object_.type != "MESH":
            continue
        matrix = object_.matrix_world
        points.extend(matrix @ Vector(corner) for corner in object_.bound_box)
    if not points:
        return Vector((0, 0, 0)), Vector((1, 1, 1))
    minimum = Vector(min(point[i] for point in points) for i in range(3))
    maximum = Vector(max(point[i] for point in points) for i in range(3))
    return (minimum + maximum) / 2.0, (maximum - minimum)


def main() -> int:
    output, inputs = arguments()
    bpy.ops.preferences.addon_enable(module="unity3d_assetbundle_importer")
    for path in inputs:
        result = bpy.ops.import_scene.zipmod(
            filepath=str(path),
            import_armatures=True,
            import_textures=True,
            pack_textures=True,
            unit_scale=1.0,
        )
        print("IMPORT", result, path.name)

    center, size = scene_bounds()
    print("BOUNDS center", tuple(round(v, 2) for v in center), "size", tuple(round(v, 2) for v in size))

    camera_data = bpy.data.cameras.new("Preview")
    camera = bpy.data.objects.new("Preview", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    distance = max(size.length, 1.0) * 1.25
    camera.location = center + Vector((distance * 0.45, -distance, size.z * 0.35))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 50
    bpy.context.scene.camera = camera

    sun_data = bpy.data.lights.new("Sun", type="SUN")
    sun_data.energy = 4.0
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (0.9, 0.2, 0.6)
    bpy.context.scene.collection.objects.link(sun)

    world = bpy.data.worlds.new("Preview")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.05, 0.06, 0.08, 1.0)
    background.inputs[1].default_value = 0.6
    bpy.context.scene.world = world

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.filepath = str(output.resolve())
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("WROTE", output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
