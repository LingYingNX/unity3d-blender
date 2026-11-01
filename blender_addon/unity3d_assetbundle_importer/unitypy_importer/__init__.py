"""UnityPy 直读导入器：把 .zipmod / .unity3d 直接导入 Blender。

与同插件里的 AssetStudio -> FBX 路线互补：不落地 FBX，直接在 Blender 里建网格、
材质、贴图与合并骨架蒙皮。只在 `文件 > 导入` 菜单里增加一个条目，不占用 N 面板。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from . import builder, unity_loader


class UNITYPY_OT_import_zipmod(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.zipmod"
    bl_label = "导入 Zipmod / Unity3D（UnityPy 直读）"
    bl_description = "直接读取 .zipmod / .unity3d 中的网格、材质、贴图与骨骼蒙皮，不生成 FBX"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".zipmod"
    filter_glob: StringProperty(
        default="*.zipmod;*.zip;*.unity3d;*.assetbundle;*.bundle",
        options={"HIDDEN"},
    )
    filepath: StringProperty(subtype="FILE_PATH")

    import_armatures: BoolProperty(
        name="导入骨骼蒙皮",
        description="把 SkinnedMeshRenderer 的骨骼合并成一套骨架并写入顶点权重",
        default=True,
    )
    import_textures: BoolProperty(
        name="导入贴图",
        description="解码 _MainTex / _BumpMap 并接到材质节点",
        default=True,
    )
    pack_textures: BoolProperty(
        name="贴图打包进 .blend",
        description="导入后立即 pack 贴图，避免保存 .blend 时丢失外部图片",
        default=True,
    )
    texture_dir: StringProperty(
        name="贴图输出目录",
        description="解码后的贴图写到哪里；留空使用系统临时目录",
        subtype="DIR_PATH",
        default="",
    )
    unit_scale: FloatProperty(
        name="导入缩放",
        description="整套模型整体缩放。HS2 几何约 10 单位每米，填 0.1 即换算成米",
        default=1.0,
        min=0.0001,
        soft_max=100.0,
    )

    def execute(self, context):
        source = Path(self.filepath)
        if not source.exists():
            self.report({"ERROR"}, "路径不存在：{0}".format(source))
            return {"CANCELLED"}

        options = builder.ImportOptions(
            import_armatures=self.import_armatures,
            import_textures=self.import_textures,
            pack_textures=self.pack_textures,
            texture_dir=(
                Path(self.texture_dir)
                if self.texture_dir
                else Path(tempfile.gettempdir()) / "zipmod_import_textures"
            ),
            unit_scale=self.unit_scale,
        )

        collection = bpy.data.collections.new(source.stem or "Zipmod")
        context.scene.collection.children.link(collection)
        root = bpy.data.objects.new(collection.name, None)
        collection.objects.link(root)
        root.scale = (options.unit_scale,) * 3
        name_pools = {"object": {root.name}}

        reports = []
        importers = []
        try:
            with unity_loader.collect_bundles(source) as bundle_set:
                if not bundle_set.bundles:
                    for warning in bundle_set.warnings:
                        self.report({"WARNING"}, warning)
                    self.report({"ERROR"}, "{0} 里没有找到 AssetBundle".format(source.name))
                    return self._rollback(collection, root, importers)
                unitypy = unity_loader.import_unitypy()
                for reference in bundle_set.bundles:
                    importer = builder.BundleImporter(
                        unitypy, reference, options, collection, root, name_pools
                    )
                    importers.append(importer)
                    reports.append(importer.run())
                for warning in bundle_set.warnings:
                    self.report({"WARNING"}, warning)
        except unity_loader.UnityPyMissing as exc:
            self.report({"ERROR"}, str(exc).splitlines()[0])
            return self._rollback(collection, root, importers)
        except Exception as exc:  # noqa: BLE001 - 任何异常都不能让 Blender 崩
            self.report({"ERROR"}, "{0}: {1}".format(type(exc).__name__, exc))
            return self._rollback(collection, root, importers)

        imported = [report for report in reports if report.objects]
        if not imported:
            for report in reports:
                for warning in report.warnings:
                    self.report({"WARNING"}, warning)
                for error in report.errors:
                    self.report({"ERROR"}, error)
            self.report({"WARNING"}, "{0} 没有导入任何网格".format(source.name))
            return self._rollback(collection, root, importers)

        self._select(imported)
        total_objects = sum(report.objects for report in imported)
        total_vertices = sum(report.vertices for report in imported)
        total_triangles = sum(report.triangles for report in imported)
        total_images = sum(report.images for report in imported)
        for report in reports:
            self.report({"INFO"}, report.summary())
            for error in report.errors:
                self.report({"WARNING"}, error)
        self.report(
            {"INFO"},
            "已导入 {0} 个网格、{1} 个顶点、{2} 个三角面、{3} 张贴图".format(
                total_objects, total_vertices, total_triangles, total_images
            ),
        )
        return {"FINISHED"}

    def _rollback(self, collection, root, importers):
        """失败时清掉本次新建的集合、物体和数据块，不留半成品。"""
        objects = [root] + [item for importer in importers for item in importer.created_objects]
        for object_ in objects:
            if object_.name in bpy.data.objects:
                bpy.data.objects.remove(object_, do_unlink=True)
        for importer in importers:
            for mesh in importer.created_meshes:
                if mesh.users == 0 and mesh.name in bpy.data.meshes:
                    bpy.data.meshes.remove(mesh)
            for armature in importer.created_armatures:
                if armature.users == 0 and armature.name in bpy.data.armatures:
                    bpy.data.armatures.remove(armature)
            for material in importer.created_materials:
                if material.users == 0 and not material.use_fake_user and material.name in bpy.data.materials:
                    bpy.data.materials.remove(material)
            for image in importer.created_images:
                if image.users == 0 and not image.use_fake_user and image.name in bpy.data.images:
                    bpy.data.images.remove(image)
        bpy.data.collections.remove(collection)
        return {"CANCELLED"}

    def _select(self, reports):
        for object_ in bpy.context.selected_objects:
            object_.select_set(False)
        for report in reports:
            for name in report.object_names:
                object_ = bpy.data.objects.get(name)
                if object_ is not None:
                    object_.select_set(True)
                    bpy.context.view_layer.objects.active = object_


def menu_func_import(self, context):
    self.layout.operator(
        UNITYPY_OT_import_zipmod.bl_idname,
        text="Zipmod / Unity3D（UnityPy 直读）",
    )


classes = (UNITYPY_OT_import_zipmod,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
