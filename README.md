# Unity3D 模型导入 Blender

Blender 插件：用 [UnityPy](https://github.com/K0lb3/UnityPy) 直接读取 Unity `.zipmod` /
`.unity3d` AssetBundle，把网格、UV、材质、贴图和骨骼蒙皮直接建进 Blender 场景，不生成中间 FBX。

插件在 Blender 的 `文件 > 导入` 里提供一个条目，不注册侧栏面板：

```
文件 > 导入 > Zipmod / Unity3D（UnityPy 直读）
```

## 功能

- 一个条目同时吃 `.zipmod`、`.zip`、`.unity3d`、`.assetbundle`、`.bundle`；`.zipmod` 会先解包，把包里所有 AssetBundle 一起导入。
- 直接建网格：顶点、UV、法线（作为自定义法线）、多个子网格对应多个材质槽。
- 材质按 Unity 属性接线：`_MainTex` 基础色、`_BumpMap` 法线、`_Metallic`/`_Glossiness`、`_Cutoff` 与 `_Mode` 透明模式。
- 贴图解码后写 PNG，并在导入时打包进 `.blend`，避免保存后丢图。
- `SkinnedMeshRenderer` 的骨骼合并成一套骨架（一个 AssetBundle 一套），写入顶点权重并挂 Armature 修改器。
- 按 Unity 的 GameObject 层级重建空物体树：父节点、名字、局部变换都跟 prefab 一致，Outliner 里不再是平铺的一堆网格；每个 AssetBundle 单独放进一个子集合（如 `[YYG]ZYLZTF`）。
- 挂载按 zipmod 自带的 `abdata/list/characustom/*.csv` 判定：头发（`SetHair` 行）挂头骨（`cf_J_Head`，缺了就试 `cf_J_Head_s`）；饰品（`Parent` 行）挂它声明的那根节点；衣服靠角色骨架自己定位、不挂。没有登记信息的 bundle 退回启发式（自带 `cf_J_*` 骨的不挂，其余当局部坐标挂头骨）。饰品声明的节点不在骨架里时**不挂**并给出提示，不会硬塞到头骨上。
- 骨骼：把 SMR 没引用的中间节点补进骨架、按「骨名 + 世界矩阵」合并重复的骨架副本。这套衣服实测从 181 骨 / 6 个并列根骨变成 **225 骨 / 1 个根骨 `cf_J_Hips` / 层级深度 21**，动一根根骨就能带整只模型。
- 导入缩放：HS2 几何约 10 单位每米，填 `0.1` 即换算成米；默认 `1.0` 保持原尺度。
- 失败回滚：路径不存在、压缩包损坏、解出 0 个网格时，本次新建的集合、物体、网格、骨架、材质、贴图全部清掉，不留半成品。
- 插件界面名称、菜单条目与操作符提示为中文。

## 依赖

需要 UnityPy 装进 Blender 自带的 Python（一次即可）：

```powershell
& '<Blender 安装目录>\<版本>\python\bin\python.exe' -m pip install --upgrade UnityPy
```

没装时导入会直接报错并提示这条命令。卸载：把 `install` 换成 `uninstall UnityPy`。

## 安装

1. 下载 Release 里的 `unity3d_assetbundle_importer_blender_addon.zip`，或本地运行 `scripts/package_addon.ps1` 生成。
2. Blender：`编辑 > 偏好设置 > 插件 > 安装...`（Blender 4.2+ 在 `获取扩展 > 安装...`）。
3. 选中 zip，启用 `Unity3D资源包导入器`。

## 使用

1. 选择 `文件 > 导入 > Zipmod / Unity3D（UnityPy 直读）`。
2. 选文件：`.zipmod` 整包导入；也可以直接选单个 `.unity3d`。
3. 在右侧导入面板调整：导入骨骼蒙皮、导入贴图、贴图打包进 `.blend`、贴图输出目录、导入缩放。
4. 导入结果的结构：`来源集合（如 [YYG]-…zipmod）` → `每个 bundle 的子集合（如 [YYG]ZYLZTF）` → `bundle 根空物体（缩放作用在它身上）` → `Unity 的 GameObject 层级空物体` → `网格对象`。
5. 网格用 GameObject 原名命名，蒙皮网格挂 Armature 修改器；局部坐标的头发/饰品会自动挂到角色头骨（见上）。

散装安装的 mod（`abdata/chara/<作者>/*.unity3d`）逐个文件导入即可。

### 头发、饰品为什么需要"挂骨骼"

HS2 的头发/饰品 prefab 只带相对坐标：网格和自带骨架都在原点附近，游戏运行时把这个 prefab 挂到角色骨上（`-TF.csv` 表头里的 `SetHair` 列就是这个分类），才会出现在头上。直接单放这个 bundle，在 Unity 里也同样是待在原地。

实测（同一个 zipmod 的三个 bundle）：

| bundle | 网格 Y 范围（角色总高约 15.9） | 骨架 | 导入行为 |
| --- | --- | --- | --- |
| `[YYG]ZYLZ.unity3d` 衣服 | -0.7 ~ 15.8 | `cf_J_*` 角色骨 | 已在角色坐标，不挂 |
| `[YYG]ZYLZSP.unity3d` 饰品 | -1.2 ~ 0.7 | 无骨骼 | 按 csv 声明挂 `N_Earring_L`；该节点不在导入的骨架里，于是不挂并提示 |
| `[YYG]ZYLZTF.unity3d` 头发 | -9.2 ~ 2.1 | `joint1…joint32` | 自动挂到头骨 |

导入面板里可以改：`挂到角色骨骼`（自动/不挂）、`目标骨架`、`目标骨骼`、`挂点偏移`。想手动做也一样：把该 bundle 的根空物体用骨骼父级挂到指定的骨上。

## 验证

```powershell
# 菜单条目 / 操作符属性 / 无侧栏面板 的回归测试
& '<Blender>' -b --factory-startup --python tests/test_menu_entries_headless.py

# 导入端到端（固件从真实 zipmod 现取现解）
& '<Blender>' -b --factory-startup --python tests/test_zipmod_import_headless.py

# 两个一起跑，仓库约定 GREEN / RED
powershell -ExecutionPolicy Bypass -File tests/verify_zipmod_unitypy_import.ps1
```

实测（Blender 5.3.0 Beta / Python 3.13.13 / UnityPy 1.25.4）：

| 输入 | 结果 | 耗时 |
| --- | --- | --- |
| 单个 `.unity3d` | 28 网格 / 50368 顶点 / 78903 三角面 / 10 材质 / 8 贴图 / 1 套骨架（181 骨） | 约 4-5 s |
| 整个 `.zipmod`（3 个 bundle） | 34 网格 / 128543 顶点 / 160007 三角面 / 14 材质 / 16 贴图 / 2 套骨架 | 约 8-9 s |

其他已验证项：三角形绕序与顶点法线一致率 0.999；每个顶点组都能在骨架里找到同名骨骼；贴图导入后全部 pack；异常路径干净取消。

## 归档：AssetStudio -> FBX 路线

仓库早期版本走的是 AssetStudio 转 FBX 再导入，并附带 `AssetBundleToBlender.exe`。这条路线
已经从插件中移除（插件现在只有一个导入入口），源码、转换器和旧校验脚本归档在
`legacy/assetstudio_fbx/`，需要时可以单独安装该目录或整体 `git revert` 恢复。

想重建那个转换器：`third_party/AssetStudio` 准备好后运行 `scripts/build.ps1`，输出到
`legacy/assetstudio_fbx/tools/AssetBundleToBlender`。

## 打包插件

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_addon.ps1
```

输出 `dist/unity3d_assetbundle_importer_blender_addon.zip`（只含插件本体，不含转换器）。

## 注意事项

- 本项目只分发工具源码和插件，不包含任何游戏模型、贴图、AssetBundle 或提取后的资源。请只转换和分发你有权使用的资源。
- 不导入形态键（shape keys）、不还原 Unity 自定义 shader 的颜色演算、不导入 Cubemap / MonoBehaviour 物理（DynamicBone 等）与动画。
- 生成的骨架是每个 AssetBundle 自己骨骼的合并结果，没有对齐 HS2 角色本体骨架；把服装穿到已有角色上需要手工重定向或改骨架名。
- 部分游戏本体 bundle 会引用同目录下不存在的 `cab-*` 伴随文件，这类渲染器会被跳过并在控制台给出警告（例如 `abdata/chara/oo_base.unity3d` 为 68/70）。
- Unity AssetBundle 的内部层级差异较大，部分模型可能需要在 Blender 中手动调整骨架、材质或部件位置。
- 当前预编译与实测环境为 Windows + Blender 5.3。

## 许可证

本项目代码使用 MIT License。第三方组件许可见 `THIRD_PARTY_NOTICES.md`。
