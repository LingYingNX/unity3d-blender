bl_info = {
    "name": "Unity3D资源包导入器",
    "author": "Local",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "文件 > 导入 > Unity3D资源包 (.unity3d)",
    "description": "选择 Unity3D AssetBundle 文件，临时转换为 FBX，打包贴图并导入当前 Blender 场景。",
    "category": "Import-Export",
}

import subprocess
import tempfile
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper


ADDON_DIR = Path(__file__).resolve().parent
CONVERTER_EXE = ADDON_DIR / "tools" / "AssetBundleToBlender" / "AssetBundleToBlender.exe"


class UNITY3D_OT_import_assetbundle(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.unity3d_assetbundle"
    bl_label = "导入 Unity3D 资源包"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".unity3d"
    filter_glob: StringProperty(
        default="*.unity3d;*.ab;*.bundle",
        options={"HIDDEN"},
    )

    output_dir: StringProperty(
        name="Output Directory",
        description="内部临时输出目录；导入后会自动清理",
        subtype="DIR_PATH",
        default="",
        options={"HIDDEN"},
    )

    clear_scene: BoolProperty(
        name="导入前清理场景",
        description="导入 FBX 前删除现有场景对象",
        default=False,
    )

    scale_factor: FloatProperty(
        name="缩放倍数",
        description="按指定值缩放导入模型",
        default=10.0,
        min=0.001,
        soft_max=1000.0,
    )

    bone_display_type: EnumProperty(
        name="骨骼显示模式",
        description="选择导入骨骼的显示方式。",
        items=(
            ("OCTAHEDRAL", "八面锥", "以八面锥显示骨骼"),
            ("STICK", "棍形", "以棍形显示骨骼"),
            ("BBONE", "柔性骨骼", "以柔性骨骼显示骨骼"),
            ("ENVELOPE", "封套", "以封套显示骨骼"),
            ("WIRE", "线框", "以线框显示骨骼"),
        ),
        default="OCTAHEDRAL",
    )

    cleanup_empty_hierarchy: BoolProperty(
        name="清理无用空对象",
        description="压平无动画、约束和自定义属性的空对象层级",
        default=True,
    )

    def execute(self, context):
        input_path = Path(self.filepath)
        if not input_path.exists():
            self.report({"ERROR"}, f"File not found: {input_path}")
            return {"CANCELLED"}

        converter = Path(CONVERTER_EXE)
        if not converter.exists():
            self.report({"ERROR"}, f"Converter not found: {converter}")
            return {"CANCELLED"}

        with tempfile.TemporaryDirectory(prefix=f"{input_path.stem}_fbx_import_") as temp_dir:
            output_dir = Path(temp_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [str(converter), str(input_path), str(output_dir)],
                cwd=str(converter.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                message = (result.stderr or result.stdout or "Converter failed").strip()
                self.report({"ERROR"}, message[-900:])
                return {"CANCELLED"}

            fbx_dir = output_dir / "fbx"
            fbx_files = sorted(fbx_dir.glob("*.fbx"))
            if not fbx_files:
                self.report({"ERROR"}, f"No FBX files found in {fbx_dir}")
                return {"CANCELLED"}

            if self.clear_scene:
                bpy.ops.object.select_all(action="SELECT")
                bpy.ops.object.delete()

            imported = 0
            imported_objects = []
            for fbx_path in fbx_files:
                before_import = set(bpy.data.objects)
                bpy.ops.import_scene.fbx(filepath=str(fbx_path))
                imported_objects.extend(obj for obj in bpy.data.objects if obj not in before_import)
                imported += 1

            character_root = bpy.data.objects.new(input_path.stem, None)
            character_root.empty_display_type = "ARROWS"
            context.collection.objects.link(character_root)
            for obj in imported_objects:
                if obj.parent is None and obj is not character_root:
                    world_matrix = obj.matrix_world.copy()
                    obj.parent = character_root
                    obj.matrix_world = world_matrix
                if obj.type == "ARMATURE":
                    obj.data.display_type = self.bone_display_type
            if self.cleanup_empty_hierarchy:
                _flatten_empty_hierarchy(character_root, imported_objects)
            character_root.scale = (self.scale_factor,) * 3

            packed = 0
            for image in bpy.data.images:
                if image.packed_file is not None or not image.filepath:
                    continue
                image_path = Path(bpy.path.abspath(image.filepath))
                if image_path.exists():
                    image.pack()
                    packed += 1

        self.report({"INFO"}, f"已导入 {imported} 个 FBX，并打包 {packed} 张贴图")
        return {"FINISHED"}


def _flatten_empty_hierarchy(root: bpy.types.Object, imported_objects: list[bpy.types.Object]) -> None:
    imported_set = set(imported_objects)
    empty_objects = [
        obj
        for obj in imported_objects
        if obj.type == "EMPTY" and (obj.parent is root or obj.parent in imported_set)
    ]
    for empty in sorted(empty_objects, key=_object_hierarchy_depth, reverse=True):
        if (
            empty.animation_data
            or empty.constraints
            or empty.instance_type != "NONE"
            or empty.parent_type != "OBJECT"
            or empty.keys()
        ):
            continue
        parent = empty.parent
        for child in list(empty.children):
            world_matrix = child.matrix_world.copy()
            child.parent = parent
            child.matrix_world = world_matrix
        bpy.data.objects.remove(empty, do_unlink=True)


def _object_hierarchy_depth(obj: bpy.types.Object) -> int:
    depth = 0
    parent = obj.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def menu_func_import(self, context):
    self.layout.operator(UNITY3D_OT_import_assetbundle.bl_idname, text="Unity3D资源包 (.unity3d)")


classes = (UNITY3D_OT_import_assetbundle,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
