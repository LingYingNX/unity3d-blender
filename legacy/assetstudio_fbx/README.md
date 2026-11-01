# AssetStudio -> FBX 路线（归档）

这条路线是仓库早期发布的功能，已经从插件里移除，插件本体现在只提供
`文件 > 导入 > Zipmod / Unity3D（UnityPy 直读）` 一个入口。

保留的内容：

- `__init__.py`：原插件源码（`bl_info` 名称仍为 `Unity3D资源包导入器`）。
- `tools/AssetBundleToBlender/`：原随插件分发的转换器运行时，**已从仓库移除**（20 MB 二进制，连同
  历史一起不再随 clone 下载）。需要时用 `scripts/build.ps1` 重新生成到同一路径，`.gitignore`
  已忽略该目录。
- `tests/`：原先针对这条路线写的 PowerShell 校验脚本（其中的绝对路径按当时环境写死）。

想再用这条路线，把本目录当成一个独立插件放进 Blender 的 `scripts/addons` 并启用，
或者整体 `git revert` 移除它的那次提交。
