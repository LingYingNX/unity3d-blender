"""UnityPy 直读路线的端到端无头测试（网格 / 材质 / 贴图 / 骨架 / 异常路径 / 缩放）。

固件从游戏目录里的真实 zipmod 现取现解，不需要提前准备。

运行：
  blender -b --factory-startup --python tests/test_zipmod_import_headless.py
"""

from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_addon"))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

GAME_MODS = Path(r"F:\HY\HS22\HoneySelect2_ArcticFox\mods")
ARCHIVE = GAME_MODS / "[YYG]-孙尚香 自由礼赞.zipmod"
LOCAL = ROOT / "_local"
FIXTURE_DIR = LOCAL / "YYG"

RESULTS: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> bool:
    RESULTS.append((bool(condition), message))
    print("{0} {1}".format("PASS" if condition else "FAIL", message))
    return bool(condition)


def operator_exists(idname: str) -> bool:
    """bpy.ops 的属性访问永远成功，只有 get_rna_type() 才能证明操作符真的注册了。"""
    module, name = idname.split(".", 1)
    try:
        getattr(getattr(bpy.ops, module), name).get_rna_type()
    except Exception:  # noqa: BLE001 - 缺操作符时 Blender 抛 KeyError
        return False
    return True


def ensure_fixtures() -> Path | None:
    """Extract the chara bundles out of the zipmod once, reuse afterwards."""
    single = FIXTURE_DIR / "abdata" / "chara" / "YYG" / "[YYG]ZYLZ.unity3d"
    if single.exists():
        return single
    if not ARCHIVE.exists():
        return None
    with zipfile.ZipFile(ARCHIVE) as handle:
        for member in handle.infolist():
            name = member.filename.replace("\\", "/")
            wanted = name.endswith(".unity3d") and name.startswith("abdata/chara/YYG/")
            wanted = wanted or (name.endswith(".csv") and "/characustom/" in name)
            if not wanted:
                continue
            output = FIXTURE_DIR.joinpath(*name.split("/"))
            output.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(member) as source, open(output, "wb") as destination:
                destination.write(source.read())
    return single if single.exists() else None


def reset_scene() -> None:
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for object_ in list(bpy.data.objects):
        bpy.data.objects.remove(object_, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for armature in list(bpy.data.armatures):
        bpy.data.armatures.remove(armature)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        if image.users == 0 and image.name != "Render Result":
            bpy.data.images.remove(image)


def scene_stats() -> dict:
    meshes = [object_ for object_ in bpy.data.objects if object_.type == "MESH"]
    armatures = [object_ for object_ in bpy.data.objects if object_.type == "ARMATURE"]
    # 只看从文件加载的贴图，排除 Blender 自带的 Render Result / Viewer Node。
    images = [image for image in bpy.data.images if image.source == "FILE"]
    return {
        "mesh_objects": len(meshes),
        "armatures": len(armatures),
        "vertices": sum(len(object_.data.vertices) for object_ in meshes),
        "polygons": sum(len(object_.data.polygons) for object_ in meshes),
        "uv_layers": sum(len(object_.data.uv_layers) for object_ in meshes),
        "materials": len(bpy.data.materials),
        "images": len(images),
        "packed_images": len([image for image in images if image.packed_file is not None]),
        "vertex_groups": sum(len(object_.vertex_groups) for object_ in meshes),
        "modifiers": sum(len(object_.modifiers) for object_ in meshes),
        "empties": len([object_ for object_ in bpy.data.objects if object_.type == "EMPTY"]),
        "collections": sorted(collection.name for collection in bpy.data.collections),
    }


def winding_agreement() -> float:
    from mathutils import Vector

    agree = 0
    total = 0
    for object_ in bpy.data.objects:
        if object_.type != "MESH" or not object_.data.vertices:
            continue
        mesh = object_.data
        for polygon in mesh.polygons:
            if polygon.normal.length < 1e-9:
                continue
            accumulated = Vector((0.0, 0.0, 0.0))
            for index in polygon.vertices:
                accumulated += mesh.vertices[index].normal
            if accumulated.length < 1e-9:
                continue
            total += 1
            if polygon.normal.dot(accumulated.normalized()) > 0.0:
                agree += 1
    return (agree / total) if total else 1.0


def skin_integrity() -> list[str]:
    problems = []
    for object_ in bpy.data.objects:
        if object_.type != "MESH":
            continue
        modifiers = [modifier for modifier in object_.modifiers if modifier.type == "ARMATURE"]
        if not modifiers:
            continue
        armature = modifiers[0].object
        if armature is None or armature.type != "ARMATURE":
            problems.append("{0}: 骨架修改器没有绑定骨架".format(object_.name))
            continue
        bones = {bone.name for bone in armature.data.bones}
        if not bones:
            problems.append("{0}: 绑定的骨架没有骨骼".format(object_.name))
        for group in object_.vertex_groups:
            if group.name not in bones:
                problems.append(
                    "{0}: 顶点组 {1} 在骨架 {2} 里没有对应骨骼".format(
                        object_.name, group.name, armature.name
                    )
                )
    return problems


def world_height() -> float:
    from mathutils import Vector

    values = []
    for object_ in bpy.data.objects:
        if object_.type != "MESH":
            continue
        for corner in object_.bound_box:
            values.append((object_.matrix_world @ Vector(corner)).z)
    return (max(values) - min(values)) if values else 0.0


def world_z_range(objects=None) -> tuple[float, float]:
    from mathutils import Vector

    values = []
    for object_ in (objects if objects is not None else bpy.data.objects):
        if object_.type != "MESH":
            continue
        for corner in object_.bound_box:
            values.append((object_.matrix_world @ Vector(corner)).z)
    return (min(values), max(values)) if values else (0.0, 0.0)


def import_path(path: Path, **overrides) -> str:
    options = {
        "filepath": str(path),
        "import_armatures": True,
        "import_textures": True,
        "pack_textures": True,
        "unit_scale": 1.0,
    }
    options.update(overrides)
    started = time.perf_counter()
    try:
        result = bpy.ops.import_scene.zipmod(**options)
        status = "FINISHED" if result == {"FINISHED"} else "CANCELLED"
    except RuntimeError as exc:
        status = "ERROR: {0}".format(exc)
    print("  -> {0} in {1:.2f}s: {2}".format(status, time.perf_counter() - started, path.name))
    return status


def main() -> int:
    print("Blender {0} | Python {1}".format(bpy.app.version_string, sys.version.split()[0]))
    bpy.ops.preferences.addon_enable(module="unity3d_assetbundle_importer")
    check(not operator_exists("import_scene.unity3d_assetbundle"), "旧的 FBX 路线已移除")
    check(operator_exists("import_scene.zipmod"), "直读操作符可用")

    single = ensure_fixtures()
    if not check(single is not None, "拿到固件（{0}）".format(ARCHIVE.name)):
        print("SKIP: 游戏目录里没有固件 zipmod")
        return 0

    # 1) 单个 AssetBundle：几何、材质、贴图、骨架
    reset_scene()
    if check(import_path(single) == "FINISHED", "单个 .unity3d 导入完成"):
        stats = scene_stats()
        print("    stats:", stats)
        check(stats["mesh_objects"] == 28, "28 个网格（实际 {0}）".format(stats["mesh_objects"]))
        check(stats["vertices"] == 50368, "50368 个顶点（实际 {0}）".format(stats["vertices"]))
        check(stats["uv_layers"] == stats["mesh_objects"], "每个网格都有 UV")
        check(stats["materials"] >= 10, "材质 >= 10（实际 {0}）".format(stats["materials"]))
        check(stats["images"] >= 8, "贴图 >= 8（实际 {0}）".format(stats["images"]))
        check(stats["packed_images"] == stats["images"], "贴图全部 pack 进 .blend")
        check(stats["armatures"] == 1, "合并成 1 套骨架（实际 {0}）".format(stats["armatures"]))
        check(stats["modifiers"] == stats["mesh_objects"], "每个网格都挂了骨架修改器")
        check(stats["vertex_groups"] > 0, "写入顶点组（实际 {0}）".format(stats["vertex_groups"]))
        check(stats["empties"] >= 20, "重建了 GameObject 层级空物体（实际 {0}）".format(stats["empties"]))
        check(
            "[YYG]ZYLZ" in stats["collections"],
            "每个 bundle 有自己的子集合（实际 {0}）".format(stats["collections"]),
        )
        names = {object_.name for object_ in bpy.data.objects}
        check("n_clothes_cf_00" in names, "保留了 Unity 层级节点名 n_clothes_cf_00")
        check(
            all(
                object_.parent is not None and object_.parent.type == "EMPTY"
                for object_ in bpy.data.objects
                if object_.type == "MESH"
            ),
            "每个网格都挂在 GameObject 空物体下",
        )
        agreement = winding_agreement()
        check(agreement > 0.9, "三角形绕序与法线一致：{0:.3f}".format(agreement))
        problems = skin_integrity()
        check(not problems, "蒙皮绑定自洽（{0} 个问题）".format(len(problems)))
        for problem in problems[:5]:
            print("    ", problem)
        bone_total = sum(
            len(object_.data.bones) for object_ in bpy.data.objects if object_.type == "ARMATURE"
        )
        rig = next(object_ for object_ in bpy.data.objects if object_.type == "ARMATURE")
        roots = [bone for bone in rig.data.bones if bone.parent is None]
        check(bone_total == 225, "骨架合并成 225 根骨（实际 {0}）".format(bone_total))
        check(
            len(roots) == 1,
            "骨架是一棵完整树、只有一个根骨（实际 {0}：{1}）".format(
                len(roots), [bone.name for bone in roots][:4]
            ),
        )
        depth = max((len(list(bone.parent_recursive)) for bone in rig.data.bones), default=0)
        check(depth >= 10, "骨骼层级有纵深（实际 {0} 层）".format(depth))

    # 2) 整个 zipmod：多 bundle
    reset_scene()
    if check(import_path(ARCHIVE) == "FINISHED", "整个 .zipmod 导入完成"):
        stats = scene_stats()
        print("    stats:", stats)
        check(stats["mesh_objects"] == 34, "34 个网格（实际 {0}）".format(stats["mesh_objects"]))
        check(stats["vertices"] == 128543, "128543 个顶点（实际 {0}）".format(stats["vertices"]))
        check(stats["armatures"] == 2, "2 套骨架（实际 {0}）".format(stats["armatures"]))
        check(
            {"[YYG]ZYLZ", "[YYG]ZYLZSP", "[YYG]ZYLZTF"} <= set(stats["collections"]),
            "每个 bundle 一个集合（实际 {0}）".format(stats["collections"]),
        )
        # 整包一次导入时，头发要挂到同一次导入里衣服带的角色骨上（这就是最容易漏的场景）。
        attached = sorted(
            object_.name
            for object_ in bpy.data.objects
            if object_.type == "EMPTY" and object_.parent_type == "BONE"
        )
        print("    整包导入后挂到骨骼:", attached)
        check(
            attached == ["[YYG]ZYLZTF"],
            "只挂头发；饰品留在主体坐标里（实际 {0}）".format(attached),
        )
        sp_collection = bpy.data.collections.get("[YYG]ZYLZSP")
        sp_root = bpy.data.objects.get("[YYG]ZYLZSP")
        check(
            sp_root is not None and sp_root.parent_type != "BONE",
            "饰品没有被挂到骨上（实际 {0}）".format(
                sp_root.parent_bone if sp_root and sp_root.parent_type == "BONE" else None
            ),
        )
        hair_collection = bpy.data.collections.get("[YYG]ZYLZTF")
        hair_meshes = [
            object_
            for object_ in (hair_collection.all_objects if hair_collection else [])
            if object_.type == "MESH"
        ]
        low, high = world_z_range(hair_meshes)
        print("    整包导入后头发 z 范围: {0:.2f} ~ {1:.2f}".format(low, high))
        check(low > 5.0 and high > 15.0, "整包导入头发也上头（{0:.2f} ~ {1:.2f}）".format(low, high))

    # 3) 异常路径必须干净取消
    reset_scene()
    check(import_path(LOCAL / "does_not_exist.zipmod") != "FINISHED", "不存在的路径取消")
    check(not bpy.data.objects and not bpy.data.collections, "取消后没有残留对象")

    reset_scene()
    broken = LOCAL / "broken.zipmod"
    broken.write_bytes(b"not a zip file at all")
    check(import_path(broken) != "FINISHED", "损坏的压缩包取消")
    check(not bpy.data.objects and not bpy.data.collections, "取消后没有残留集合")

    # 4) 导入缩放
    reset_scene()
    if check(import_path(single, unit_scale=0.1) == "FINISHED", "缩放 0.1 导入完成"):
        height = world_height()
        print("    world height: {0:.3f}".format(height))
        check(0.5 < height < 2.5, "缩放 0.1 后约为米级（实际 {0:.3f}）".format(height))

    # 5) 关掉骨骼时不建骨架
    reset_scene()
    if check(import_path(single, import_armatures=False) == "FINISHED", "关闭骨骼导入完成"):
        stats = scene_stats()
        check(stats["armatures"] == 0, "没有骨架（实际 {0}）".format(stats["armatures"]))
        check(stats["mesh_objects"] == 28, "网格仍完整（实际 {0}）".format(stats["mesh_objects"]))

    # 6) 局部坐标的头发：不挂 = 停在原点，挂到角色骨 = 上头
    hair = FIXTURE_DIR / "abdata" / "chara" / "YYG" / "[YYG]ZYLZTF.unity3d"
    reset_scene()
    if check(import_path(hair, attach_mode="NONE") == "FINISHED", "关闭挂载时导入头发"):
        low, high = world_z_range()
        print("    不挂载 z 范围: {0:.2f} ~ {1:.2f}".format(low, high))
        check(high < 5.0, "不挂载时头发停在原点附近（z 上限 {0:.2f}）".format(high))

    reset_scene()
    if check(import_path(single) == "FINISHED", "先导入带角色骨架的衣服"):
        rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
        check(rig is not None, "衣服导入了角色骨架")
        check(
            not any(object_.parent_type == "BONE" for object_ in bpy.data.objects),
            "已经在角色坐标里的衣服不挂骨骼",
        )
        if check(import_path(hair) == "FINISHED", "开着自动挂载导入头发"):
            roots = [o for o in bpy.data.objects if o.type == "EMPTY" and o.parent is rig]
            check(len(roots) == 1, "头发的根空物体挂到了角色骨架（实际 {0}）".format(len(roots)))
            if roots:
                root = roots[0]
                check(root.parent_type == "BONE", "父级类型是骨骼（实际 {0}）".format(root.parent_type))
                check(
                    root.parent_bone.startswith("cf_J_Head"),
                    "挂在头骨上（实际 {0}）".format(root.parent_bone),
                )
            # 只量头发自己的网格：它在自己的子集合里，场景里还有先导入的衣服。
            hair_collection = bpy.data.collections.get("[YYG]ZYLZTF")
            check(hair_collection is not None, "头发 bundle 有自己的子集合")
            hair_meshes = [
                object_
                for object_ in (hair_collection.all_objects if hair_collection else [])
                if object_.type == "MESH"
            ]
            check(len(hair_meshes) == 5, "头发网格都在头发子集合里（实际 {0}）".format(len(hair_meshes)))
            low, high = world_z_range(hair_meshes)
            print("    挂载后头发 z 范围: {0:.2f} ~ {1:.2f}".format(low, high))
            check(low > 5.0 and high > 15.0, "头发被抬到头部高度（{0:.2f} ~ {1:.2f}）".format(low, high))

    # 7) 整包导入：只挂局部坐标的 bundle，角色坐标的衣服不能跟着跑
    reset_scene()
    if check(import_path(single) == "FINISHED", "整包测试：先导入衣服提供角色骨架"):
        if check(import_path(ARCHIVE) == "FINISHED", "整包导入（衣服 + 饰品 + 头发）"):
            attached = sorted(
                object_.name
                for object_ in bpy.data.objects
                if object_.type == "EMPTY" and object_.parent_type == "BONE"
            )
            print("    挂到骨骼的 bundle:", attached)
            check(
                attached == ["[YYG]ZYLZTF"],
                "整包只挂头发（实际 {0}）".format(attached),
            )

    # 8) 有身体包时，饰品按 csv 声明的 N_* 挂点精确落位
    reset_scene()
    body = Path(r"F:\HY\HS22\HoneySelect2_ArcticFox\abdata\chara\oo_base.unity3d")
    if check(body.exists(), "身体固件存在") and check(import_path(body) == "FINISHED", "导入身体包"):
        node = bpy.data.objects.get("N_Earring_L")
        node_count = len(
            [object_ for object_ in bpy.data.objects if object_.type == "EMPTY" and object_.name.startswith("N_")]
        )
        check(node is not None, "身体包里的 N_* 挂点建出来了（实际 {0} 个）".format(node_count))
        if check(import_path(ARCHIVE) == "FINISHED", "再导入整包 zipmod"):
            sp_root = bpy.data.objects.get("[YYG]ZYLZSP")
            check(
                sp_root is not None
                and node is not None
                and node.matrix_world.translation.length < 1.0,
                "身体包里的 N_Earring_L 是贴地占位点（z={0:.3f}）".format(
                    node.matrix_world.translation.z if node else -1.0
                ),
            )
            check(
                sp_root is not None
                and not (sp_root.parent_type == "BONE"),
                "占位节点被识别，饰品保持自身坐标（实际父级 {0}）".format(
                    sp_root.parent.name if sp_root and sp_root.parent else None
                ),
            )
            if sp_root is not None:
                sp_collection = bpy.data.collections.get("[YYG]ZYLZSP")
                zs = [
                    (object_.matrix_world @ Vector(corner)).z
                    for object_ in (sp_collection.all_objects if sp_collection else [])
                    if object_.type == "MESH"
                    for corner in object_.bound_box
                ]
                print("    饰品 z 范围: {0:.2f} ~ {1:.2f}".format(min(zs), max(zs)))
                check(
                    -2.0 < min(zs) < 1.0,
                    "饰品留在主体坐标（脚部附近，实际 {0:.2f} ~ {1:.2f}）".format(
                        min(zs), max(zs)
                    ),
                )

    failed = [message for ok, message in RESULTS if not ok]
    print("RESULT: {0} passed, {1} failed".format(len(RESULTS) - len(failed), len(failed)))
    for message in failed:
        print("  FAILED:", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
