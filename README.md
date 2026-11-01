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
- 导入面板支持手动输入缩放倍数，默认按 `10.0` 倍导入模型。
- 导入面板支持选择骨骼显示模式：八面锥、棍形、柔性骨骼、封套或线框。
- 导入面板默认清理无用空对象，压平过深的空对象层级，同时保留骨骼、网格体、骨骼挂点和带有动画或自定义属性的空对象。
- 插件界面名称和描述为中文。
- 在 `文件 > 导入` 里增加第二个条目 `Zipmod / Unity3D（UnityPy 直读）`：直接读取 `.zipmod`、`.zip`、`.unity3d`，不经 FBX，直接在 Blender 里建网格、材质、贴图和合并骨架蒙皮。

## 两条导入路线

同一个插件里有两个导入条目，按需要选：

| 条目 | 路径 | 适合 |
| --- | --- | --- |
| `Unity3D资源包 (.unity3d)` | AssetStudio 转换器 -> FBX -> Blender | 只要 FBX/静态网格，或需要转换器自带的贴图打包与空对象整理 |
| `Zipmod / Unity3D（UnityPy 直读）` | UnityPy 直接解析 AssetBundle | `.zipmod` 整包导入、需要骨骼蒙皮与顶点权重、不想落地中间 FBX |

直读路线的导入选项（在文件浏览器的导入面板里）：导入骨骼蒙皮、导入贴图、贴图打包进 `.blend`、贴图输出目录、导入缩放（HS2 几何约 10 单位每米，填 `0.1` 即换算成米）。

直读路线依赖 UnityPy。装一次即可（用 Blender 自带的 Python）：

```powershell
& '<Blender 安装目录>\<版本>\python\bin\python.exe' -m pip install --upgrade UnityPy
```

没有安装时导入会直接报错并提示这条命令。

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
3. 在导入面板输入缩放倍数，从骨骼显示模式下拉框选择模式，并按需切换空对象清理。
4. 点击导入，等待转换和 FBX 导入完成。
5. 保存 `.blend` 文件时，贴图已经通过 Blender 的 `pack()` 打包进文件。

### 直读路线的用法

1. 选择 `文件 > 导入 > Zipmod / Unity3D（UnityPy 直读）`。
2. 选择 `.zipmod`（整包，内部所有 AssetBundle 一起导入）、`.zip`、或单个 `.unity3d`。
3. 在右侧导入面板按需调整导入骨骼蒙皮、贴图、贴图打包、贴图输出目录、导入缩放。
4. 导入结果为来源命名的集合，集合下有一个空物体作为根（缩放作用在它上面），每个网格用 GameObject 原名命名，蒙皮网格挂 Armature 修改器。

## 验证

```powershell
# 菜单条目 / 操作符属性 / 无 N 面板 的回归测试
& '<Blender>' -b --factory-startup --python tests/test_menu_entries_headless.py

# 导入端到端测试（固件从真实 zipmod 现取现解）
& '<Blender>' -b --factory-startup --python tests/test_zipmod_import_headless.py

# 两者一起跑（仓库约定：GREEN/RED）
powershell -ExecutionPolicy Bypass -File tests/verify_zipmod_unitypy_import.ps1
```

实测数据（Blender 5.3.0 Beta / Python 3.13.13 / UnityPy 1.25.4）：

| 输入 | 结果 | 耗时 |
| --- | --- | --- |
| 单个 `.unity3d` | 28 网格 / 50368 顶点 / 78903 三角面 / 10 材质 / 8 贴图 / 1 套骨架（181 骨） | 约 4-5 s |
| 整个 `.zipmod`（3 个 bundle） | 34 网格 / 128543 顶点 / 160007 三角面 / 14 材质 / 16 贴图 / 2 套骨架 | 约 8-9 s |

其他已验证项：三角形绕序与顶点法线一致率 0.999；每个顶点组都能在骨架里找到同名骨骼；贴图导入后全部 pack；路径不存在 / 压缩包损坏时干净取消，不留残留对象。

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
- 直读路线不导入形态键（shape keys）、不还原 Unity 自定义 shader 的颜色演算、不导入 Cubemap / MonoBehaviour 物理（DynamicBone 等）与动画；只按 Unity 材质属性接基础色、法线、金属度、粗糙度和 `_Mode` 透明模式。
- 直读路线生成的骨架是每个 AssetBundle 自己骨骼的合并结果，没有对齐 HS2 角色本体骨架；把服装穿到已有角色上需要手工重定向或改骨架名。
- 部分游戏本体 bundle 会引用同目录下不存在的 `cab-*` 伴随文件，这类渲染器会被跳过并在控制台给出警告（例如 `abdata/chara/oo_base.unity3d` 为 68/70）。

## 许可证

本项目代码使用 MIT License。第三方组件许可见 `THIRD_PARTY_NOTICES.md`。
