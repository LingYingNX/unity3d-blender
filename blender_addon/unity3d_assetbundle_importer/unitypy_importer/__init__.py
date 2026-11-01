"""UnityPy 直读导入器：把 .zipmod / .unity3d 直接导入 Blender。

与同插件里的 AssetStudio -> FBX 路线互补：不落地 FBX，直接在 Blender 里建网格、
材质、贴图与合并骨架蒙皮。只在 `文件 > 导入` 菜单里增加一个条目，不占用 N 面板。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from . import builder, unity_loader


def _unique_name(pools: dict[str, set[str]], base: str, fallback: str = "object") -> str:
    """在共享的名字池里取一个不重名的 Blender 物体名。"""
    name = builder.sanitize(base, fallback)
    used = pools.setdefault("object", set())
    candidate = name
    index = 1
    while candidate in used:
        index += 1
        candidate = "{0}.{1:03d}".format(name, index)
    used.add(candidate)
    return candidate


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
    attach_mode: EnumProperty(
        name="挂到角色骨骼",
        description="局部坐标的模型（HS2 头发、饰品只带相对坐标）需要挂到角色骨上才会到位",
        items=(
            ("AUTO", "自动", "场景里有带 cf_J_ 骨骼的角色骨架就挂到头骨，没有就保持 bundle 原点"),
            ("NONE", "不挂", "始终按 bundle 自己的原点摆放"),
        ),
        default="AUTO",
    )
    target_armature: StringProperty(
        name="目标骨架",
        description="留空则自动挑场景里带 cf_J_ 骨骼的骨架",
        default="",
    )
    target_bone: StringProperty(
        name="目标骨骼",
        description="默认 cf_J_Head；找不到时按 cf_J_Head_s、cf_J_Head* 依次尝试",
        default="cf_J_Head",
    )
    attach_offset: FloatVectorProperty(
        name="挂点偏移",
        description="对齐后沿世界轴再加的偏移，用来微调",
        size=3,
        subtype="TRANSLATION",
        default=(0.0, 0.0, 0.0),
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

        reports = []
        importers = []
        bundles = []  # 每个 bundle 一个顶层集合 + 一个根空物体
        name_pools: dict[str, set[str]] = {}
        try:
            with unity_loader.collect_bundles(source) as bundle_set:
                if not bundle_set.bundles:
                    for warning in bundle_set.warnings:
                        self.report({"WARNING"}, warning)
                    self.report({"ERROR"}, "{0} 里没有找到 AssetBundle".format(source.name))
                    return self._rollback(bundles, importers)
                unitypy = unity_loader.import_unitypy()
                for reference in bundle_set.bundles:
                    bundle_name = Path(reference.display).stem or "bundle"
                    bundle_collection = bpy.data.collections.new(
                        bundle_name
                    )
                    context.scene.collection.children.link(bundle_collection)
                    bundle_root = bpy.data.objects.new(_unique_name(name_pools, bundle_name, "bundle"), None)
                    bundle_collection.objects.link(bundle_root)
                    bundle_root.scale = (options.unit_scale,) * 3
                    bundles.append((bundle_collection, bundle_root))
                    importer = builder.BundleImporter(
                        unitypy, reference, options, bundle_collection, bundle_root, name_pools
                    )
                    importers.append(importer)
                    reports.append(importer.run())
                for warning in bundle_set.warnings:
                    self.report({"WARNING"}, warning)
        except unity_loader.UnityPyMissing as exc:
            self.report({"ERROR"}, str(exc).splitlines()[0])
            return self._rollback(bundles, importers)
        except Exception as exc:  # noqa: BLE001 - 任何异常都不能让 Blender 崩
            self.report({"ERROR"}, "{0}: {1}".format(type(exc).__name__, exc))
            return self._rollback(bundles, importers)

        imported = [report for report in reports if report.objects]
        if not imported:
            for report in reports:
                for warning in report.warnings:
                    self.report({"WARNING"}, warning)
                for error in report.errors:
                    self.report({"ERROR"}, error)
            self.report({"WARNING"}, "{0} 没有导入任何网格".format(source.name))
            return self._rollback(bundles, importers)

        self._select(imported)
        self._attach_to_character_bone(context, bundles, importers)
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

    def _attach_to_character_bone(self, context, bundles, importers):
        """把「自带局部坐标」的 bundle 挂到角色骨上。

        判断依据：bundle 自己的骨架里有没有 cf_J_ 角色骨。衣服/身体这类 bundle 直接用
        角色骨架，本身就在角色坐标里，不能动；头发、饰品这类 bundle 用的是自带的通用
        关节（joint1、joint2……），只有局部坐标，游戏里靠挂到角色骨上才到位。
        """
        if self.attach_mode == "NONE":
            return
        created = {object_.name for importer in importers for object_ in importer.created_objects}
        local_bundles = [
            (bundle_collection, bundle_root, importer)
            for (bundle_collection, bundle_root), importer in zip(bundles, importers)
            if importer.report.objects
            and not any(
                object_.type == "ARMATURE"
                and any(bone.name.startswith("cf_J_") for bone in object_.data.bones)
                for object_ in bundle_collection.objects
            )
        ]
        if not local_bundles:
            return

        armatures = [
            object_
            for object_ in bpy.data.objects
            if object_.type == "ARMATURE" and object_.name not in created
        ]
        if self.target_armature:
            armatures = [item for item in armatures if item.name == self.target_armature]
        candidates = [
            item
            for item in armatures
            if any(bone.name.startswith("cf_J_") for bone in item.data.bones)
        ]
        if not candidates:
            self.report(
                {"WARNING"},
                "{0} 个局部坐标 bundle（{1}）没找到可挂的角色骨架，已按 bundle 原点导入；"
                "可以先导入角色/衣服，或填「目标骨架 / 目标骨骼」手动指定".format(
                    len(local_bundles),
                    "、".join(bundle_root.name for _, bundle_root, _ in local_bundles[:4]),
                ),
            )
            return

        wanted_names = [self.target_bone, "cf_J_Head", "cf_J_Head_s"]

        def match_rank(item):
            names = {bone.name for bone in item.data.bones}
            for index, name in enumerate(wanted_names):
                if name and name in names:
                    return index
            return len(wanted_names)

        candidates.sort(key=match_rank)
        armature = candidates[0]
        names = {bone.name for bone in armature.data.bones}
        bone_name = next((name for name in wanted_names if name and name in names), None)
        if bone_name is None:
            bone_name = next(
                (name for name in sorted(names) if name.startswith("cf_J_Head")), None
            )
        if bone_name is None:
            self.report({"WARNING"}, "{0} 里没有可用的头骨，保持原样".format(armature.name))
            return

        for _bundle_collection, bundle_root, _importer in local_bundles:
            try:
                target = builder.attach_object_to_bone(
                    bundle_root, armature, bone_name, tuple(self.attach_offset)
                )
            except Exception as exc:  # noqa: BLE001 - 挂载失败不能丢掉已经导入的模型
                self.report(
                    {"WARNING"},
                    "{0} 挂到骨骼失败：{1}: {2}".format(
                        bundle_root.name, type(exc).__name__, exc
                    ),
                )
                continue
            self.report(
                {"INFO"},
                "{0} 已挂到角色骨骼 {1}/{2}，世界原点 {3}".format(
                    bundle_root.name,
                    armature.name,
                    bone_name,
                    tuple(round(v, 3) for v in target),
                ),
            )

    def _rollback(self, bundles, importers):
        """失败时清掉本次新建的集合、物体和数据块，不留半成品。"""
        for bundle_collection, bundle_root in bundles:
            if bundle_root.name in bpy.data.objects:
                bpy.data.objects.remove(bundle_root, do_unlink=True)
            for object_ in list(bundle_collection.all_objects):
                if object_.name in bpy.data.objects:
                    bpy.data.objects.remove(object_, do_unlink=True)
            bpy.data.collections.remove(bundle_collection)
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
