"""回归测试：菜单条目和操作符属性必须符合 Blender 的 UI API。

`UILayout.operator()` 只接受固定关键字参数（operator / text / text_ctxt / translate /
icon / emboss / depress / icon_value / search_weight），自定义操作符属性必须设在
返回的 OperatorProperties 上。这里用一个签名严格对齐的假布局把违规写法直接打成 TypeError。

运行：
  blender -b --factory-startup --python tests/test_menu_entries_headless.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_addon"))

import bpy  # noqa: E402

import unity3d_assetbundle_importer as addon  # noqa: E402
from unity3d_assetbundle_importer import unitypy_importer  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, message: str) -> bool:
    print(("{0} {1}" if condition else "FAIL {1}").format("PASS", message))
    if not condition:
        FAILURES.append(message)
    return bool(condition)


def operator_exists(idname: str) -> bool:
    """bpy.ops 的属性访问永远成功，只有 get_rna_type() 才能证明操作符真的注册了。"""
    module, name = idname.split(".", 1)
    try:
        getattr(getattr(bpy.ops, module), name).get_rna_type()
    except Exception:  # noqa: BLE001 - 缺操作符时 Blender 抛 KeyError
        return False
    return True


class FakeOperatorProperties:
    """Blender 的 OperatorProperties：属性靠赋值设置。"""

    def __init__(self, operator_id: str):
        self.operator_id = operator_id
        self.values: dict[str, object] = {}

    def __setattr__(self, name, value):
        if name in {"operator_id", "values"}:
            object.__setattr__(self, name, value)
        else:
            self.values[name] = value


class FakeLayout:
    """签名与 Blender 5.3 的 UILayout.operator 完全一致。"""

    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []

    def operator(
        self,
        operator,
        text=None,
        text_ctxt=None,
        translate=True,
        icon=None,
        emboss=True,
        depress=False,
        icon_value=0,
        search_weight=0.0,
    ):
        self.calls.append((operator, text))
        return FakeOperatorProperties(operator)

    def label(self, text="", **kwargs):
        return None

    def prop(self, data, property, **kwargs):
        return None

    def column(self, **kwargs):
        return self

    def row(self, **kwargs):
        return self

    def box(self, **kwargs):
        return self

    def separator(self, **kwargs):
        return None


class FakeMenu:
    def __init__(self):
        self.layout = FakeLayout()


def main() -> int:
    print("Blender {0}".format(bpy.app.version_string))
    bpy.ops.preferences.addon_enable(module="unity3d_assetbundle_importer")

    check(
        not operator_exists("import_scene.unity3d_assetbundle"),
        "旧的 FBX 路线操作符已移除",
    )
    check(operator_exists("import_scene.zipmod"), "直读操作符已注册")
    check(
        not hasattr(addon, "UNITY3D_OT_import_assetbundle"),
        "插件里不再包含旧的 FBX 操作符类",
    )

    menu = FakeMenu()
    try:
        unitypy_importer.menu_func_import(menu, None)
        check(True, "菜单函数只用了合法参数")
    except TypeError as exc:
        check(False, "菜单函数参数非法: {0}".format(exc))

    registered = [call[0] for call in menu.layout.calls]
    check(
        registered == ["import_scene.zipmod"],
        "导入菜单里只注册一个条目（实际 {0}）".format(registered),
    )
    labels = {call[0]: call[1] for call in menu.layout.calls}
    print("菜单条目:", labels)

    operator = unitypy_importer.UNITYPY_OT_import_zipmod
    # 自定义属性挂在操作符 RNA 上，不在类的 bl_rna 上。
    operator_rna = bpy.ops.import_scene.zipmod.get_rna_type()
    properties = {prop.identifier for prop in operator_rna.properties}
    for attribute in (
        "import_armatures",
        "import_textures",
        "pack_textures",
        "texture_dir",
        "unit_scale",
        "attach_mode",
        "target_armature",
        "target_bone",
        "attach_offset",
        "filepath",
        "filter_glob",
    ):
        check(attribute in properties, "操作符属性 {0} 存在".format(attribute))
    check(
        ".zipmod" in operator_rna.properties["filter_glob"].default,
        "文件过滤器包含 .zipmod",
    )
    check(operator.bl_idname == "import_scene.zipmod", "操作符 id 未变")

    panels = [name for name in dir(bpy.types) if name.startswith("ZIPMOD_PT")]
    check(not panels, "没有额外的 N 面板（{0}）".format(panels))

    print("RESULT: {0} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
