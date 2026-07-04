# Unity3D 模型导入 Blender

Blender 插件和本地转换器，用于把 Unity `.unity3d` / AssetBundle 文件临时转换为 FBX 后直接导入 Blender。

## 代码来源说明

本项目的 AssetBundle 解析、模型转换和贴图导出能力基于 [AssetStudio](https://github.com/Perfare/AssetStudio) 的代码和库构建。AssetStudio 使用 MIT License，本仓库已在 `THIRD_PARTY_NOTICES.md` 中保留其版权和许可证声明。

本仓库没有使用或打包 AssetRipper；AssetRipper 仅在早期方案调研中参考过。

## 功能

- 在 Blender 菜单 `文件 > 导入 > Unity3D资源包 (.unity3d)` 中选择 `.unity3d`、`.ab` 或 `.bundle` 文件。
- 转换过程使用系统临时目录，不在原始文件目录留下解包文件。
- 导入完成后自动打包贴图到当前 `.blend` 文件，减少外部图片丢失。
- 将头发、衣服等拆分出的 FBX 部件挂到同一个角色 Empty 层级下，便于整体移动和管理。
- 插件界面名称和描述为中文。

## 安装

推荐直接下载 Release 中的 `unity3d_assetbundle_importer_blender_addon.zip`。

1. 打开 Blender。
2. 进入 `编辑 > 偏好设置 > 插件 > 安装...`。
3. 选择下载的 zip 文件。
4. 启用 `Unity3D资源包导入器`。

zip 内已包含 Windows 版 `AssetBundleToBlender.exe` 转换器，不需要另外配置本机路径。

## 使用

1. 在 Blender 中选择 `文件 > 导入 > Unity3D资源包 (.unity3d)`。
2. 选择 Unity AssetBundle 文件。
3. 等待转换和 FBX 导入完成。
4. 保存 `.blend` 文件时，贴图已经通过 Blender 的 `pack()` 打包进文件。

## 从源码构建转换器

转换器源码位于 `src/AssetBundleToBlender`。构建前需要准备 AssetStudio 源码：

```powershell
git clone https://github.com/Perfare/AssetStudio.git third_party/AssetStudio
dotnet publish src/AssetBundleToBlender/AssetBundleToBlender.csproj -c Release -r win-x64 --self-contained false -o blender_addon/unity3d_assetbundle_importer/tools/AssetBundleToBlender
```

也可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

## 打包插件

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_addon.ps1
```

输出文件位于 `dist/unity3d_assetbundle_importer_blender_addon.zip`。

## 注意事项

- 本项目只分发工具源码和插件，不包含任何游戏模型、贴图、AssetBundle 或提取后的资源。
- 请只转换和分发你有权使用的资源。
- Unity AssetBundle 的内部层级差异较大，部分模型可能需要在 Blender 中手动调整骨架、材质或部件位置。
- 当前预编译运行时面向 Windows + Blender。

## 许可证

本项目代码使用 MIT License。第三方组件许可见 `THIRD_PARTY_NOTICES.md`。
