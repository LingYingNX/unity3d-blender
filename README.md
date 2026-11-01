# Unity3D 模型导入 Blender

用 [UnityPy](https://github.com/K0lb3/UnityPy) 直接读 Unity `.zipmod` / `.unity3d`，把网格、UV、材质、贴图和骨骼蒙皮建进 Blender，不生成中间 FBX。插件只在 `文件 > 导入` 里加一个条目，不占侧栏面板。

```
文件 > 导入 > Zipmod / Unity3D（UnityPy 直读）
```

## 安装

1. 装依赖（一次即可）：`"<Blender 安装目录>\<版本>\python\bin\python.exe" -m pip install --upgrade UnityPy`
2. 用 `scripts/package_addon.ps1` 生成插件 zip（或用 Release 里的），Blender 里 `编辑 > 偏好设置 > 插件 > 安装...` 选中并启用。

## 用法

- 选文件：`.zipmod` / `.zip` / `.unity3d` / `.assetbundle` / `.bundle`；文件浏览器里 **Ctrl / Shift 多选就批量导入**，多选共用一套设置和一个总根。
- 结果结构：`来源集合 → 每个 bundle 一个子集合 → 总根空物体 → Unity 的 GameObject 层级 → 网格`。移动/缩放总根即可整体处理。
- 面板选项：导入骨骼蒙皮、导入贴图、贴图打包进 `.blend`、贴图输出目录、导入缩放（HS2 约 10 单位每米，填 `0.1` 换米）、挂到角色骨骼、目标骨架 / 目标骨骼、挂点偏移。

## 自动处理的行为

- 网格：顶点、UV、自定义法线，多子网格对应多材质槽；材质按 `_MainTex`、`_BumpMap`、`_Metallic`、`_Glossiness`、`_Mode` 接线，贴图解码后可 pack 进 `.blend`。
- 骨骼：SMR 引用的骨 + 缺失的中间节点合成一棵树；同一套骨架在包里被复制多份（每个服装部件一份）时按「骨名 + 世界矩阵」合并成一套，动根骨能带整只。
- 摆放：读 zipmod 的 `abdata/list/characustom/*.csv` 登记表 —— 衣服不挂（本来就在角色坐标）；头发挂头骨；饰品按 `Parent` 挂，挂点名先当骨名找、再查精确表、再按部位关键词（`head/earring` → 头，`kosi/waist` → 腰，`hand` → 手，`foot/toe` → 脚，`_L`/`_R` 优先同侧）映射到骨架里真实存在的骨；认不出来就保持原样，不硬塞。
- 失败回滚：路径不存在、压缩包损坏、一个网格都没导入时，本次新建的集合 / 物体 / 数据块全部清掉。

## 限制

- 不导入形态键、动画、物理（DynamicBone 等）、Cubemap；不还原 Unity 自定义 shader 的颜色演算，只按材质属性接线。
- 骨架按 bundle 合并，没有对齐角色本体骨架；把服装穿到已有角色上仍需手工重定向。
- 饰品的挂点在游戏里来自角色卡，包里只有贴地占位点，所以落点是**按名字近似**，不是精确复现；要精确就手动填「目标骨骼 / 挂点偏移」。

## 验证与许可

- 无头测试：`powershell -ExecutionPolicy Bypass -File tests/verify_zipmod_unitypy_import.ps1`（菜单/操作符回归 + 导入端到端，84 项断言）。
- 本项目代码 MIT，第三方许可见 `THIRD_PARTY_NOTICES.md`；仓库只含工具源码，不含任何游戏模型、贴图或 AssetBundle。
