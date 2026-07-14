# Unity3D Character Hierarchy Export Design

## Problem

The converter currently exports every unresolved Unity root with mesh descendants as a separate FBX. A single character fixture produces seven FBX files for body clothing, shoes, hair, head accessories, wings, and back accessories. Each export starts at its own local origin and may contain an independent skeleton or animation pose.

Blender cannot reconstruct the missing cross-part hierarchy after import. At the add-on's default 10x scale, the body head bone is near Z `1.5935`, while the hair and head-accessory roots remain near Z `0`. Back accessories extend as low as Z `-9.6678`. Shoes and body clothing also contain different foot and toe rest poses.

## Goal

Export all parts that belong to one character through a shared Unity hierarchy so their transforms, attachment points, skins, and independent accessory rigs remain in the same coordinate system. The Blender add-on must import the merged result without filename-specific coordinate corrections.

## Non-Goals

- Do not hardcode offsets or part names such as `hair`, `head`, `back`, or `shoes`.
- Do not merge unrelated characters that happen to exist in the same AssetBundle.
- Do not replace AssetStudio's skinning, material, texture, animation, or FBX writer logic.
- Do not force every accessory onto the body armature when it has a legitimate independent rig.

## Architecture

### Character Group Discovery

Build a graph from loaded `GameObject` transforms. For each mesh-bearing object, walk all resolvable parents to its highest available ancestor. Use that ancestor as the initial character group root.

When multiple initial roots share skin bones or resolve to the same skeleton identity, union them into one character group. Skeleton identity is derived from resolved `SkinnedMeshRenderer.m_Bones` transforms, not names alone. This keeps body clothing and shoes together even when their immediate export roots differ.

Independent accessory rigs remain members of the same character group when their transform ancestry reaches the same character container. They retain their own bones inside the merged hierarchy.

### Merged FBX Export

For each character group, call AssetStudio's supported multi-`GameObject` `ModelConverter` constructor:

```csharp
new ModelConverter(groupName, groupRoots, ImageFormat.Png)
```

This creates one synthetic FBX root while preserving each selected Unity root's local transform below it. Export skins, blend shapes, and animations through the existing `ModelExporter.ExportFbx` settings.

Merged export is not assumed to manufacture attachment transforms that are absent from the bundle. After the first merged-export regression, inspect the resulting hierarchy. If an accessory root is still normalized to the origin, recover its placement only from resolvable Unity parent, renderer bone, root-bone, or bind-pose references. If none of those references identifies an attachment, report the component as unresolved rather than applying a fixture-specific coordinate.

If grouping cannot prove that roots belong together, export separate character-group FBX files rather than guessing. The converter should report group and member counts so diagnostics reveal what was merged.

### Blender Import

The add-on continues to import every FBX emitted by the converter for compatibility with bundles containing multiple characters. For the common single-character case, only one merged FBX is imported.

The add-on still creates its management Empty, applies the user-selected scale once at that root, applies the selected armature display mode, and optionally flattens structural Empty objects while preserving world matrices.

No Blender-side positional repair is added.

## Data Flow

1. Load the AssetBundle with `AssetsManager`.
2. Collect `GameObject`, `Transform`, renderer, mesh, and texture assets.
3. Discover mesh-bearing roots and resolvable ancestors.
4. Group roots by shared hierarchy and resolved skin-bone identity.
5. Convert each group with AssetStudio's multi-object converter.
6. Export one FBX per proven character group.
7. Import the resulting FBX files in Blender.
8. Apply display, cleanup, and root-scale options without changing surviving world transforms.

## Failure Handling

- A root with unresolved parent pointers is treated as a boundary, not automatically as a standalone character.
- A mesh with no resolved skin bones can join only through transform ancestry; otherwise it remains a separate group.
- A component with no hierarchy, root-bone, skin-bone, or bind-pose relationship cannot be positioned generically; the converter reports it as unresolved instead of silently placing it at the character origin.
- A group conversion failure reports all member root names and does not suppress successful unrelated groups.
- The converter returns failure only when neither FBX nor OBJ output succeeds, preserving current command-line behavior.

## Testing

### Focused Grouping Test

Create a deterministic test around character-group discovery using a small fixture graph. It must prove:

- roots sharing resolved skin bones become one group;
- independent roots with no hierarchy or shared bones remain separate;
- grouping does not depend on part filenames.

### Real AssetBundle Regression

Run the converter and Blender in background mode against the existing 53 MB fixture. The test must fail on the current exporter and pass after the fix by asserting:

- fewer character FBX outputs than the current seven-part split;
- every moved component's placement is traceable to a Unity hierarchy, bone, root-bone, or bind-pose reference;
- hair and head-accessory bounds are near the body head region after the default 10x scale;
- wing and back-accessory bounds no longer extend far outside the body coordinate frame;
- shoe meshes remain aligned with the body foot region;
- grouping and Empty cleanup preserve surviving object world matrices.

Exact object names may be used to identify observations in this fixture test, but production grouping logic must not use them.

### Existing Regression Suite

Retain checks for scale controls, bone display options, Chinese metadata, texture packing, source-directory cleanliness, and Empty hierarchy cleanup.

## Acceptance Criteria

- The fixture imports as an assembled character without manual repositioning.
- Hair is located at the head, shoes align with feet, wings remain behind the torso at the intended distance, and accessories no longer scatter below the body.
- Production code contains no fixture-specific filenames or coordinate constants.
- Converter build succeeds from source, Blender background regression passes, and the source/deployed add-on trees match after deployment.
