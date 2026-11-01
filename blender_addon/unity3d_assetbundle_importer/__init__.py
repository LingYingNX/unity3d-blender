"""Unity3D / Zipmod 导入器：UnityPy 直读路线。

插件只在 `文件 > 导入` 里提供一个条目 `Zipmod / Unity3D（UnityPy 直读）`，不注册侧栏
面板、不生成中间 FBX。旧的 AssetStudio -> FBX 路线已从插件中移除，代码与转换器归档在
仓库 `legacy/assetstudio_fbx/`，需要时可以单独安装或恢复。
"""

bl_info = {
    "name": "Unity3D资源包导入器",
    "author": "Local",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "文件 > 导入 > Zipmod / Unity3D（UnityPy 直读）",
    "description": "用 UnityPy 直接读取 .zipmod / .unity3d，导入网格、材质、贴图与合并骨架蒙皮。",
    "category": "Import-Export",
}

from . import unitypy_importer


def register():
    unitypy_importer.register()


def unregister():
    unitypy_importer.unregister()


if __name__ == "__main__":
    register()
