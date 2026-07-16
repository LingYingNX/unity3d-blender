# Unity3D Character Hierarchy Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export one coherent character FBX when an AssetBundle contains modular body, hair, shoe, wing, and accessory roots, then verify the assembled coordinates in Blender.

**Architecture:** Add a real-fixture Blender regression first. Replace per-root FBX conversion with AssetStudio's multi-`GameObject` converter behind a small grouping function, export the static rest pose, and retain the add-on's existing scale/display/cleanup behavior. The real-fixture test is an evidence gate: if merged export cannot recover attachment placement from bundle data, stop without adding filename or coordinate heuristics.

**Tech Stack:** .NET 8, C#, AssetStudio `ModelConverter`/`ModelExporter`, Blender 5.0.1 Python API, PowerShell regression scripts.

---

### Task 1: Pin the Current Coordinate Failure

**Files:**
- Create: `tests/verify_character_parts_align.ps1`
- Read: `tests/verify_addon_scale_and_bone_display.ps1`
- Read: `blender_addon/unity3d_assetbundle_importer/__init__.py`

- [ ] **Step 1: Write the failing real-fixture test**

Create a PowerShell test that requires `UNITY3D_TEST_SOURCE` and `UNITY3D_BLENDER_EXE`, copies the fixture to an ASCII temporary path, imports through the source add-on with `clear_scene=True`, `scale_factor=10.0`, and `cleanup_empty_hierarchy=False`, then inspects mesh world-space bounding boxes. Assert these intent-level conditions:

```python
assert root is not None
assert body_top_z > 1.4
assert hair_center_z > 1.0
assert head_accessory_min_z > 0.5
assert back_accessory_min_z > -0.5
assert wing_center_z > 0.5
assert shoe_max_z < 0.4
```

Identify fixture observations by mesh prefixes only inside this test: `operating_dress_`, `operating_hair_`, `operating_head_`, `operating_ornaments_`, `operating_wing_`, and `operating_shoes_`. Put generated Python and copied fixtures under `$env:TEMP` and remove them plus `__pycache__` in `finally`.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
$env:UNITY3D_TEST_SOURCE='C:\Users\LYNX\Desktop\[sakuraba]哥谭蝴蝶梦\abdata\chara\sakuraba\sakuraba_25-5-s01.unity3d'
$env:UNITY3D_BLENDER_EXE='E:\blender\blender-5.0.1-windows-x64\blender.exe'
rtk powershell -ExecutionPolicy Bypass -File tests\verify_character_parts_align.ps1
```

Expected: FAIL because hair/head/back accessory bounds remain near or below the character origin. Record the exact failing coordinate.

### Task 2: Restore a Rebuildable Converter

**Files:**
- Existing build entry: `scripts/build.ps1`
- Generated dependency checkout: `third_party/AssetStudio/` (ignored, do not commit)
- Build output: `blender_addon/unity3d_assetbundle_importer/tools/AssetBundleToBlender/`

- [ ] **Step 1: Restore AssetStudio source using the repository build entry**

Run:

```powershell
rtk powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Expected: AssetStudio is cloned under `third_party/AssetStudio`, `dotnet publish` succeeds, and the converter EXE is rebuilt. Do not stage the ignored dependency checkout or build-only cache files.

- [ ] **Step 2: Verify the unmodified rebuild keeps the test red**

Run the Task 1 command again.

Expected: the same coordinate assertion fails, proving the source build reproduces the deployed defect.

### Task 3: Merge Character Roots During FBX Conversion

**Files:**
- Modify: `src/AssetBundleToBlender/Program.cs:39`
- Test: `tests/verify_character_parts_align.ps1`

- [ ] **Step 1: Replace per-root export with one merged conversion**

Keep existing root discovery. Replace the `foreach (var root in roots)` FBX export loop with one conversion of the complete root list:

```csharp
var groupName = SafeName(Path.GetFileNameWithoutExtension(input));
var path = Path.Combine(fbxDir, groupName + ".fbx");
var converted = new ModelConverter(groupName, roots, ImageFormat.Png);
ModelExporter.ExportFbx(
    path,
    converted,
    eulerFilter: true,
    filterPrecision: 0.25f,
    allNodes: true,
    skins: true,
    animation: false,
    blendShape: true,
    castToBone: false,
    boneSize: 10f,
    exportAllUvsAsDiffuseMaps: false,
    scaleFactor: 1f,
    versionIndex: 3,
    isAscii: false);
fbxCount = 1;
Console.WriteLine($"FBX group: {path} ({roots.Count} roots)");
```

Preserve the existing exception boundary and report all root names when conversion fails. Do not add part-name matching or coordinate constants.

- [ ] **Step 2: Rebuild the converter**

Run:

```powershell
rtk powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Expected: `dotnet publish` exits 0 and updates the packaged converter.

- [ ] **Step 3: Run the coordinate regression**

Run the Task 1 command.

Expected: PASS for all coordinate assertions.

If it fails, capture the merged FBX coordinates and stop this plan. The approved design forbids inventing filename-specific offsets; the failure means the required attachment relation is absent or not yet resolved and needs a revised design.

- [ ] **Step 4: Commit the green converter slice**

```powershell
rtk git add src/AssetBundleToBlender/Program.cs tests/verify_character_parts_align.ps1 blender_addon/unity3d_assetbundle_importer/tools/AssetBundleToBlender
rtk git commit -m "Merge modular character roots"
```

### Task 4: Run Existing Blender Regressions

**Files:**
- Test: `tests/verify_addon_clear_scene_chinese.ps1`
- Test: `tests/verify_cleanup_empty_hierarchy.ps1`
- Test: `tests/verify_addon_scale_and_bone_display.ps1`
- Test: `tests/verify_addon_packs_textures_and_groups.ps1`

- [ ] **Step 1: Run tests that require no external fixture**

```powershell
$env:UNITY3D_BLENDER_EXE='E:\blender\blender-5.0.1-windows-x64\blender.exe'
rtk powershell -ExecutionPolicy Bypass -File tests\verify_addon_clear_scene_chinese.ps1
rtk powershell -ExecutionPolicy Bypass -File tests\verify_cleanup_empty_hierarchy.ps1
```

Expected: both exit 0.

- [ ] **Step 2: Run fixture-backed import regressions**

Set `UNITY3D_TEST_SOURCE` to the fixture from Task 1 and run:

```powershell
rtk powershell -ExecutionPolicy Bypass -File tests\verify_addon_scale_and_bone_display.ps1
rtk powershell -ExecutionPolicy Bypass -File tests\verify_addon_packs_textures_and_groups.ps1
```

Expected: both exit 0. If the older grouping test expects seven direct children, update only that assertion to require one assembled character import and retain its texture/source-directory checks.

- [ ] **Step 3: Run static checks**

```powershell
rtk python -m py_compile blender_addon\unity3d_assetbundle_importer\__init__.py
rtk git diff --check
```

Expected: both exit 0. Remove generated `__pycache__` afterward.

### Task 5: Deploy and Verify the Add-on

**Files:**
- Source: `blender_addon/unity3d_assetbundle_importer/`
- Deploy: `E:\blender\blender-5.0.1-windows-x64\portable\scripts\addons\unity3d_assetbundle_importer/`

- [ ] **Step 1: Copy the complete add-on tree to the required deployment directory**

Use `Copy-Item` for source files and converter artifacts. Preserve no stale converter DLLs from the previous build.

- [ ] **Step 2: Run the coordinate regression against the deployed add-on**

Parameterize the test's add-on root so the same Task 1 scenario runs against the deployment path.

Expected: PASS with the same assembled-coordinate assertions.

- [ ] **Step 3: Verify source/deployment parity and clean artifacts**

Compare SHA-256 for `__init__.py`, `AssetBundleToBlender.exe`, and `AssetBundleToBlender.dll`. Confirm no temporary fixture, diagnostic JSON, `__pycache__`, or debug journal remains.

- [ ] **Step 4: Commit deployment-facing test adjustments if needed**

```powershell
rtk git add tests README.md
rtk git commit -m "Verify assembled character import"
```

Skip this commit when Task 4 required no tracked adjustments.
