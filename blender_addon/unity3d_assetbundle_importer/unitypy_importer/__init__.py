"""UnityPy 直读导入器：把 .zipmod / .unity3d 直接导入 Blender。

与同插件里的 AssetStudio -> FBX 路线互补：不落地 FBX，直接在 Blender 里建网格、
材质、贴图与合并骨架蒙皮。只在 `文件 > 导入` 菜单里增加一个条目，不占用 N 面板。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    StringProperty,
)
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
    # 文件浏览器里多选时，Blender 把选中的文件名放进 files，目录放进 directory。
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})

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
        description="对齐后沿世界轴再加的偏移，用来微调（单位是世界坐标，不受导入缩放影响）",
        size=3,
        subtype="TRANSLATION",
        default=(0.0, 0.0, 0.0),
    )

    def execute(self, context):
        sources = self._sources()
        missing = [path for path in sources if not path.exists()]
        sources = [path for path in sources if path.exists()]
        for path in missing:
            self.report({"WARNING"}, "跳过不存在的路径：{0}".format(path))
        if not sources:
            self.report({"ERROR"}, "没有选中任何文件")
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
        entries: dict[str, dict] = {}
        name_pools: dict[str, set[str]] = {}
        # 一个总根：整套 mod（主体 + 花、蝴蝶结这类配件）都挂在它下面，一起移动、一起缩放。
        batch_name = sources[0].stem or "Zipmod"
        root = bpy.data.objects.new(
            builder.unique_name(name_pools, "object", batch_name, "root"), None
        )
        context.scene.collection.objects.link(root)
        root.scale = (options.unit_scale,) * 3
        for source in sources:
            try:
                part = self._import_source(context, source, options, root, name_pools)
            except unity_loader.UnityPyMissing as exc:
                self.report({"ERROR"}, str(exc).splitlines()[0])
                return self._rollback(bundles, importers, root)
            except Exception as exc:  # noqa: BLE001 - 单个文件失败不该拖垮整批
                self.report({"WARNING"}, "{0} 导入失败：{1}: {2}".format(source.name, type(exc).__name__, exc))
                continue
            part_reports, part_importers, part_bundles, part_entries = part
            reports.extend(part_reports)
            importers.extend(part_importers)
            bundles.extend(part_bundles)
            entries.update(part_entries)

        imported = [report for report in reports if report.objects]
        if not imported:
            for report in reports:
                for warning in report.warnings:
                    self.report({"WARNING"}, warning)
                for error in report.errors:
                    self.report({"ERROR"}, error)
            self.report({"WARNING"}, "{0} 没有导入任何网格".format(batch_name))
            return self._rollback(bundles, importers, root)

        self._select(imported)
        self._attach_to_character_bone(context, bundles, importers, entries)
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
            "已导入 {0} 个来源、{1} 个网格、{2} 个顶点、{3} 个三角面、{4} 张贴图".format(
                len(sources), total_objects, total_vertices, total_triangles, total_images
            ),
        )
        return {"FINISHED"}

    def _sources(self) -> list[Path]:
        """多选走 files + directory，单选走 filepath。"""
        if self.files:
            directory = Path(self.directory) if self.directory else None
            names = [item.name for item in self.files if item.name]
            if directory is not None and names:
                return [directory / name for name in names]
            return [Path(name) for name in names]
        return [Path(self.filepath)] if self.filepath else []

    def _import_source(self, context, source, options, root, name_pools):
        """把一个来源里的所有 AssetBundle 导到 root 下面，返回 (reports, importers, bundles, entries)。"""
        reports = []
        importers = []
        bundles = []
        entries: dict[str, dict] = {}
        with unity_loader.collect_bundles(source) as bundle_set:
            if not bundle_set.bundles:
                for warning in bundle_set.warnings:
                    self.report({"WARNING"}, warning)
                raise ValueError("{0} 里没有找到 AssetBundle".format(source.name))
            unitypy = unity_loader.import_unitypy()
            entries = unity_loader.read_characustom(bundle_set.characustom)
            for reference in bundle_set.bundles:
                bundle_name = Path(reference.display).stem or "bundle"
                bundle_collection = bpy.data.collections.new(bundle_name)
                context.scene.collection.children.link(bundle_collection)
                bundle_root = bpy.data.objects.new(
                    builder.unique_name(name_pools, "object", bundle_name, "bundle"), None
                )
                bundle_collection.objects.link(bundle_root)
                bundle_root.parent = root
                bundles.append((bundle_collection, bundle_root))
                importer = builder.BundleImporter(
                    unitypy, reference, options, bundle_collection, bundle_root, name_pools
                )
                importers.append(importer)
                reports.append(importer.run())
            for warning in bundle_set.warnings:
                self.report({"WARNING"}, warning)
        return reports, importers, bundles, entries

    def _attach_to_character_bone(self, context, bundles, importers, entries):
        """按登记表把局部坐标的 bundle 挂到角色的骨骼或挂点节点上。

        zipmod 里的 `abdata/list/characustom/*.csv` 才是真正的登记表：头发一行带 SetHair，
        挂头骨；饰品一行带 Parent，挂它声明的那根节点（可能是骨骼，也可能是 HS2 的 N_*
        挂点空物体）；衣服靠角色骨架自己定位，不挂。声明的节点找不到时按头骨粗略放置并
        提示，不会默默丢在原点。
        """
        if self.attach_mode == "NONE":
            return
        wanted_names = [self.target_bone, "cf_J_Head", "cf_J_Head_s"]

        def head_bone_name(armature):
            names = {bone.name for bone in armature.data.bones}
            for name in wanted_names:
                if name and name in names:
                    return name
            return next((name for name in sorted(names) if name.startswith("cf_J_Head")), None)

        def match_rank(item):
            names = {bone.name for bone in item.data.bones}
            for index, name in enumerate(wanted_names):
                if name and name in names:
                    return index
            return len(wanted_names)

        def is_character_rig(object_):
            return object_.type == "ARMATURE" and any(
                bone.name.startswith("cf_J_") for bone in object_.data.bones
            )

        def pick_rig(own):
            candidates = [
                object_
                for object_ in bpy.data.objects
                if is_character_rig(object_) and object_.name not in own
            ]
            if self.target_armature:
                candidates = [item for item in candidates if item.name == self.target_armature]
            if not candidates:
                return None
            candidates.sort(key=match_rank)
            return candidates[0]

        def find_declared_node(declared, own):
            """声明的父节点：先当骨名找骨架，再当对象名找 N_* 挂点空物体。"""
            if not declared or declared in own:
                return None
            for object_ in bpy.data.objects:
                if object_.type != "ARMATURE":
                    continue
                if declared in {bone.name for bone in object_.data.bones}:
                    return object_, declared
            node = bpy.data.objects.get(declared)
            # 身体包里的 N_* 是占位点（实测 N_Earring_L 在 z=0.203 贴着地面），真正的节点位置
            # 由游戏/角色卡给。判定阈值跟角色骨架高度挂钩，不写死 1.0 这种魔法数。
            rig = pick_rig(own)
            height = max((bone.head_local.z for bone in rig.data.bones), default=0.0) if rig else 0.0
            threshold = max(1.0, height * 0.15)
            if (
                node is not None
                and node.type == "EMPTY"
                and node.matrix_world.translation.length > threshold
            ):
                return node, None
            return None

        skipped = []
        for (bundle_collection, bundle_root), importer in zip(bundles, importers):
            if not importer.report.objects:
                continue
            entry = entries.get(unity_loader.bundle_key(importer.ref.display))
            role = unity_loader.bundle_role(entry)
            if role == "clothing":
                continue  # 衣服本来就长在角色骨架上，不用挂
            own = {object_.name for object_ in bundle_collection.all_objects}
            if role == "unknown":
                if any(
                    object_.type == "ARMATURE"
                    and any(bone.name.startswith("cf_J_") for bone in object_.data.bones)
                    for object_ in bundle_collection.objects
                ):
                    continue
                role = "hair"  # 没有登记信息、也不是角色骨架：按局部坐标处理

            note = ""
            target = None
            if role == "accessory":
                declared = (entry or {}).get("parent")
                target = find_declared_node(declared, own)
                if target is None:
                    # 饰品和主体往往是一套（例如 polySurface977 属于 polySurface154 那套衣服，
                    # 坐标本来就落在主体上）。挂点不可用时不能乱挪，留在它自己的坐标里。
                    self.report(
                        {"INFO"},
                        "{0}（accessory）不挂：声明的父节点 {1} 不可用，保持 bundle 自身坐标".format(
                            bundle_root.name, declared or "未声明"
                        ),
                    )
                    continue
            if target is None:
                rig = pick_rig(own)
                if rig is None:
                    skipped.append("{0}（没有可挂的角色骨架）".format(bundle_root.name))
                    continue
                bone_name = head_bone_name(rig)
                if bone_name is None:
                    skipped.append("{0}（{1} 里没有头骨）".format(bundle_root.name, rig.name))
                    continue
                target = (rig, bone_name)

            try:
                position = builder.attach_object_to_target(
                    bundle_root, target[0], target[1], tuple(self.attach_offset)
                )
            except Exception as exc:  # noqa: BLE001 - 挂载失败不能丢掉已经导入的模型
                skipped.append(
                    "{0}（挂载失败 {1}: {2}）".format(
                        bundle_root.name, type(exc).__name__, exc
                    )
                )
                continue
            self.report(
                {"INFO"},
                "{0}（{1}）已挂到 {2}{3}{4}，世界原点 {5}".format(
                    bundle_root.name,
                    role,
                    target[0].name,
                    "/" + target[1] if target[1] else "",
                    note,
                    tuple(round(v, 3) for v in position),
                ),
            )
        if skipped:
            self.report(
                {"WARNING"},
                "{0}；需要的话用面板里的「目标骨骼 / 挂点偏移」手动指定".format("、".join(skipped)),
            )
    def _rollback(self, bundles, importers, root=None):
        """失败时清掉本次新建的集合、物体和数据块，不留半成品。"""
        if root is not None and root.name in bpy.data.objects:
            bpy.data.objects.remove(root, do_unlink=True)
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
