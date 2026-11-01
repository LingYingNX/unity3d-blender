"""Turn UnityPy bundle data into Blender meshes, materials, textures and armatures.

Unity is Y-up / left handed, Blender is Z-up / right handed. The basis change
`C` below is a pure rotation (determinant +1), so triangle winding is preserved:

    blender_xyz = (unity_x, -unity_z, unity_y)
"""

from __future__ import annotations

import importlib
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

_BASIS = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))
UNITY_TO_BLENDER = _BASIS.to_4x4()
UNITY_TO_BLENDER_VECTOR = _BASIS
BLENDER_TO_UNITY = UNITY_TO_BLENDER.transposed()

_INVALID_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WEIGHT_EPSILON = 1e-5

_mesh_handler = None


def mesh_handler_class():
    """Import UnityPy.helpers.MeshHelper.MeshHandler lazily."""
    global _mesh_handler
    if _mesh_handler is None:
        module = importlib.import_module("UnityPy.helpers.MeshHelper")
        _mesh_handler = module.MeshHandler
    return _mesh_handler


def sanitize(name: str, fallback: str = "unnamed") -> str:
    cleaned = _INVALID_NAME.sub("_", (name or "").strip())
    cleaned = cleaned.rstrip(". ")
    return cleaned[:120] or fallback


def unique_name(pools: dict[str, set[str]], kind: str, base: str, fallback: str = "unnamed") -> str:
    """按类别在名字池里取一个不重名的 Blender 名（物体/材质/贴图/骨架各一池）。"""
    name = sanitize(base, fallback)
    used = pools.setdefault(kind, set())
    candidate = name
    index = 1
    while candidate in used:
        index += 1
        candidate = "{0}.{1:03d}".format(name, index)
    used.add(candidate)
    return candidate


def attach_object_to_target(object_, target, bone_name: str | None = None, offset=(0.0, 0.0, 0.0)):
    """把物体挂到角色骨或挂点节点上，让它的世界原点落在目标位置。

    局部坐标的模型（HS2 的头发、饰品）在游戏里就是靠这种方式贴到角色上的：bundle 自己
    只带相对坐标，父变换来自角色。目标是骨架 + 骨名时用骨骼父级（Blender 骨骼父级的
    父空间原点在骨骼尾端），目标是空物体（HS2 的 N_* 挂点）时用对象父级。两种都不假设
    父空间约定：先实测父级矩阵，再反推 matrix_basis。
    """
    # 用世界缩放（可能来自上层总根，例如「导入缩放 0.1」），否则换父级时会把缩放丢掉。
    scale = object_.matrix_world.to_scale()
    object_.matrix_parent_inverse = Matrix.Identity(4)
    object_.matrix_basis = Matrix.Identity(4)
    if bone_name:
        bone = target.data.bones.get(bone_name)
        if bone is None:
            raise ValueError("骨架 {0} 里没有骨骼 {1}".format(target.name, bone_name))
        object_.parent = target
        object_.parent_type = "BONE"
        object_.parent_bone = bone_name
        offset_position = target.matrix_world @ bone.head_local
    else:
        object_.parent = target
        object_.parent_type = "OBJECT"
        offset_position = target.matrix_world.translation

    bpy.context.view_layer.update()
    parent_matrix = object_.matrix_world.copy()
    target_position = offset_position + Vector(offset)
    wanted = Matrix.Translation(target_position) @ Matrix.Diagonal(scale).to_4x4()
    object_.matrix_basis = parent_matrix.inverted() @ wanted
    bpy.context.view_layer.update()
    return target_position


@dataclass
class ImportOptions:
    import_armatures: bool = True
    import_textures: bool = True
    pack_textures: bool = True
    texture_dir: Path = Path(tempfile.gettempdir()) / "zipmod_import_textures"
    unit_scale: float = 1.0


@dataclass
class BundleReport:
    bundle: str = ""
    container: str = ""
    objects: int = 0
    meshes: int = 0
    vertices: int = 0
    triangles: int = 0
    materials: int = 0
    images: int = 0
    armatures: int = 0
    skinned: int = 0
    seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    object_names: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            "{0}: {1} object(s), {2} mesh(es), {3} vertices, {4} triangles, "
            "{5} material(s), {6} image(s), {7} armature(s) in {8:.1f}s".format(
                self.bundle,
                self.objects,
                self.meshes,
                self.vertices,
                self.triangles,
                self.materials,
                self.images,
                self.armatures,
                self.seconds,
            )
        )


@dataclass
class _SkinRequest:
    """A mesh waiting for the bundle armature, collected before any bone exists."""

    object: bpy.types.Object
    bones: list
    indices: list
    weights: list
    renderer_world: Matrix


class BundleImporter:
    """Import one AssetBundle into one Blender collection."""

    def __init__(
        self,
        unitypy,
        bundle_ref,
        options: ImportOptions,
        collection,
        parent=None,
        name_pools: dict[str, set[str]] | None = None,
    ):
        self.U = unitypy
        self.ref = bundle_ref
        self.options = options
        self.collection = collection
        self.parent = parent
        self.report = BundleReport(bundle=bundle_ref.display, container=bundle_ref.container)

        self._reader_cache: dict[tuple[int, int], object] = {}
        self._object_by_pid: dict[int, object] = {}
        self._go_name_cache: dict[int, str] = {}
        self._world_cache: dict[int, Matrix] = {}
        self._go_transform_cache: dict[int, int] = {}
        self._go_empties: dict[int, bpy.types.Object] = {}
        self._go_stack: set[int] = set()
        self._materials: dict[tuple[str, int], bpy.types.Material] = {}
        self._images: dict[tuple[str, int], bpy.types.Image | None] = {}
        self._armature: bpy.types.Object | None = None
        self._bone_names: dict[int, str] = {}
        self._armature_world = Matrix.Identity(4)
        self._name_pools: dict[str, set[str]] = name_pools if name_pools is not None else {}

        # Everything created here, so a failed import can be rolled back cleanly.
        self.created_objects: list[bpy.types.Object] = []
        self.created_meshes: list[bpy.types.Mesh] = []
        self.created_armatures: list[bpy.types.Armature] = []
        self.created_materials: list[bpy.types.Material] = []
        self.created_images: list[bpy.types.Image] = []

    # ---------------------------------------------------------------- plumbing

    def _unique_name(self, kind: str, base: str) -> str:
        return unique_name(self._name_pools, kind, base)

    def _deref(self, pptr):
        if pptr is None:
            return None
        key = (getattr(pptr, "m_FileID", 0), pptr.m_PathID)
        if pptr.m_PathID == 0:
            return None
        if key not in self._reader_cache:
            self._reader_cache[key] = pptr.read()
        return self._reader_cache[key]

    @staticmethod
    def _asset_id(unity_object) -> int:
        """Stable identity for a UnityPy object across names and Blender datablocks."""
        reader = getattr(unity_object, "object_reader", None)
        return getattr(reader, "path_id", id(unity_object))

    def _read_pid(self, path_id: int):
        if path_id not in self._object_by_pid:
            return None
        entry = self._object_by_pid[path_id]
        key = (0, path_id)
        if key not in self._reader_cache:
            self._reader_cache[key] = entry.read()
        return self._reader_cache[key]

    def _game_object_name(self, game_object_pid: int) -> str:
        if game_object_pid not in self._go_name_cache:
            data = self._read_pid(game_object_pid)
            self._go_name_cache[game_object_pid] = getattr(data, "m_Name", "") or ""
        return self._go_name_cache[game_object_pid]

    def _local_matrix(self, transform) -> Matrix:
        position = transform.m_LocalPosition
        rotation = transform.m_LocalRotation
        scale = transform.m_LocalScale
        loc = Matrix.Translation(Vector((position.x, position.y, position.z)))
        rot = Quaternion((rotation.w, rotation.x, rotation.y, rotation.z)).to_matrix().to_4x4()
        scl = Matrix.Diagonal(Vector((scale.x, scale.y, scale.z))).to_4x4()
        return loc @ rot @ scl

    def _transform_world(self, transform_pid: int, stack: tuple[int, ...] = ()) -> Matrix:
        """World matrix in Unity space, with a cycle guard."""
        if transform_pid in self._world_cache:
            return self._world_cache[transform_pid]
        if transform_pid == 0 or transform_pid in stack:
            return Matrix.Identity(4)
        transform = self._read_pid(transform_pid)
        if transform is None:
            return Matrix.Identity(4)
        local = self._local_matrix(transform)
        father = getattr(transform.m_Father, "m_PathID", 0)
        world = local if not father else self._transform_world(father, stack + (transform_pid,)) @ local
        self._world_cache[transform_pid] = world
        return world

    def _game_object_transform_pid(self, game_object_pid: int) -> int:
        if game_object_pid in self._go_transform_cache:
            return self._go_transform_cache[game_object_pid]
        pid = 0
        data = self._read_pid(game_object_pid)
        for pair in getattr(data, "m_Component", []) or []:
            component = getattr(pair, "component", None)
            if component is None:
                continue
            read = self._deref(component)
            if type(read).__name__ == "Transform":
                pid = component.m_PathID
                break
        self._go_transform_cache[game_object_pid] = pid
        return pid

    def _game_object_father(self, game_object_pid: int) -> int:
        """父级 GameObject 的 path_id；没有父级返回 0。"""
        transform = self._read_pid(self._game_object_transform_pid(game_object_pid))
        if transform is None:
            return 0
        father_pid = getattr(transform.m_Father, "m_PathID", 0)
        if not father_pid:
            return 0
        father = self._read_pid(father_pid)
        if father is None:
            return 0
        return getattr(father.m_GameObject, "m_PathID", 0)

    def _game_object_local_matrix(self, game_object_pid: int) -> Matrix:
        """GameObject 在父级坐标系里的变换（Unity 局部矩阵）。

        用局部矩阵而不是世界矩阵来摆放：Blender 对「有父级的物体」赋 matrix_world 时
        会按父级局部来解释，父级带缩放时会摆错；逐级给局部变换才和 Unity 的层级一致，
        导入缩放也由最外层根空物体统一生效。
        """
        transform = self._read_pid(self._game_object_transform_pid(game_object_pid))
        if transform is None:
            return Matrix.Identity(4)
        return self._local_matrix(transform)

    def _bone_object_name(self, transform_pid: int) -> str:
        """骨骼（Transform）对应 GameObject 的名字，也就是骨架里显示的骨名。"""
        transform = self._read_pid(transform_pid)
        if transform is None:
            return ""
        return self._game_object_name(getattr(transform.m_GameObject, "m_PathID", 0))

    @staticmethod
    def _skeleton_prefix(name: str) -> str:
        """同族骨名的前缀：cf_J_* 算一族，joint1…jointN 算一族。"""
        if (name or "").startswith("cf_J_"):
            return "cf_J_"
        match = re.match(r"[A-Za-z_]+", name or "")
        return match.group(0) if match else ""

    def _ensure_game_object_empty(self, game_object_pid: int):
        """按 Unity 的 GameObject 层级逐级补空物体，返回该 GameObject 对应的空物体。

        不做这一步的话，一个 prefab 导进来会变成一堆平铺的网格；补回来之后 Outliner 里
        就是 Unity 里那棵树（名字、层级、世界变换一致）。
        """
        if not game_object_pid:
            return self.parent
        if game_object_pid in self._go_empties:
            return self._go_empties[game_object_pid]
        # shortcut: 缓存只按 path_id 做键，bundle 引用第二个资产文件（m_FileID != 0）时可能串号；
        # 目前 HS2 的 mod 都是单文件包，遇到跨文件引用的包再补 (file_id, path_id) 键。
        if game_object_pid in self._go_stack:  # 数据成环时停止递归
            return self.parent

        self._go_stack.add(game_object_pid)
        try:
            father = self._game_object_father(game_object_pid)
            parent = self._ensure_game_object_empty(father) if father else self.parent
            empty = bpy.data.objects.new(
                self._unique_name("object", self._game_object_name(game_object_pid) or "GameObject"),
                None,
            )
            self.collection.objects.link(empty)
            self.created_objects.append(empty)
            if parent is not None:
                empty.parent = parent
            empty.matrix_basis = self._blender_matrix(self._game_object_local_matrix(game_object_pid))
            self._go_empties[game_object_pid] = empty
            return empty
        finally:
            self._go_stack.discard(game_object_pid)

    def _component_world(self, component) -> Matrix:
        game_object = getattr(component.m_GameObject, "m_PathID", 0)
        return self._transform_world(self._game_object_transform_pid(game_object))

    @staticmethod
    def _blender_matrix(unity_matrix: Matrix) -> Matrix:
        return UNITY_TO_BLENDER @ unity_matrix @ BLENDER_TO_UNITY

    # -------------------------------------------------------------------- run

    def run(self) -> BundleReport:
        started = time.perf_counter()
        environment = self.U.load(str(self.ref.path))
        self.environment = environment
        for entry in environment.objects:
            self._object_by_pid[entry.path_id] = entry

        pending: list[_SkinRequest] = []
        for entry in list(environment.objects):
            if entry.type.name not in ("MeshRenderer", "SkinnedMeshRenderer"):
                continue
            try:
                request = self._import_renderer(entry)
            except Exception as exc:  # noqa: BLE001 - one bad renderer must not abort the bundle
                message = "{0}: {1}: {2}".format(entry.type.name, type(exc).__name__, exc)
                if "not found in" in str(exc):
                    message += (
                        " (the bundle references a companion AssetBundle / CAB file that is"
                        " missing next to it, so this renderer was skipped)"
                    )
                self.report.errors.append(message)
                continue
            if request is not None:
                pending.append(request)

        self._import_attach_nodes()

        if pending and self.options.import_armatures:
            try:
                self._build_armature(pending)
            except Exception as exc:  # noqa: BLE001 - geometry stays usable without a rig
                self.report.errors.append("armature: {0}: {1}".format(type(exc).__name__, exc))
            else:
                for request in pending:
                    try:
                        self._bind_skin(request)
                    except Exception as exc:  # noqa: BLE001 - report, keep the geometry
                        self.report.errors.append(
                            "{0}: skinning failed: {1}: {2}".format(
                                request.object.name, type(exc).__name__, exc
                            )
                        )
        self.report.seconds = time.perf_counter() - started
        return self.report

    def _import_attach_nodes(self) -> None:
        """把 HS2 的 N_* 挂点节点（N_Head、N_Earring_L…）也建成空物体。

        这些节点只有 Transform、没有渲染器，所以不在渲染器祖先链里；可是饰品就是挂到它们
        上面的。不建出来，饰品就只能靠头骨近似。读一遍 GameObject 名字很便宜（几千个约
        0.01 秒），所以整包扫一遍。
        """
        for entry in self.environment.objects:
            if entry.type.name != "GameObject":
                continue
            if self._game_object_name(entry.path_id).startswith("N_"):
                self._ensure_game_object_empty(entry.path_id)

    # -------------------------------------------------------------- renderers

    def _import_renderer(self, entry) -> "_SkinRequest | None":
        renderer = entry.read()
        name = self._game_object_name(getattr(renderer.m_GameObject, "m_PathID", 0))
        mesh_data = self._deref(getattr(renderer, "m_Mesh", None))
        if mesh_data is None:
            self.report.warnings.append("{0}: renderer has no mesh".format(name or entry.type.name))
            return

        handler = mesh_handler_class()(mesh_data)
        handler.process()
        vertices = handler.m_Vertices or []
        if not vertices:
            self.report.warnings.append("{0}: empty mesh, skipped".format(name or mesh_data.m_Name))
            return

        uv0 = handler.m_UV0 or []
        has_uv = len(uv0) == len(vertices)
        normals = handler.m_Normals or []
        faces: list[tuple[int, int, int]] = []
        loop_uv: list[tuple[float, float]] = []
        face_slots: list[int] = []
        vertex_count = len(vertices)
        skipped_faces = 0
        for slot, triangles in enumerate(handler.get_triangles()):
            for triangle in triangles:
                if len(triangle) != 3:
                    skipped_faces += 1
                    continue
                if triangle[0] == triangle[1] or triangle[1] == triangle[2] or triangle[0] == triangle[2]:
                    continue  # degenerate triangle, carries no area
                if any(index >= vertex_count for index in triangle):
                    skipped_faces += 1
                    continue
                faces.append((triangle[0], triangle[1], triangle[2]))
                face_slots.append(slot)
                if has_uv:
                    loop_uv.extend((uv0[triangle[0]], uv0[triangle[1]], uv0[triangle[2]]))
        if skipped_faces:
            self.report.warnings.append(
                "{0}: {1} invalid triangle(s) skipped".format(name or mesh_data.m_Name, skipped_faces)
            )
        if not faces:
            self.report.warnings.append("{0}: no triangles, skipped".format(name or mesh_data.m_Name))
            return

        object_name = self._unique_name("object", name or mesh_data.m_Name or entry.type.name)
        mesh = bpy.data.meshes.new(object_name)
        blender_vertices = [
            tuple(UNITY_TO_BLENDER_VECTOR @ Vector((vertex[0], vertex[1], vertex[2])))
            for vertex in vertices
        ]
        mesh.from_pydata(blender_vertices, [], faces)
        mesh.validate(verbose=False)
        mesh.update()

        if len(mesh.polygons) != len(faces):
            # validate() 删面时不保证删在末尾，按面回查它原本属于哪个子网格，避免材质整体错位。
            slot_by_face: dict[tuple, int] = {}
            for slot, face in zip(face_slots, faces):
                slot_by_face.setdefault(tuple(face), slot)
                slot_by_face.setdefault(tuple(sorted(face)), slot)
            resolved: list[int] = []
            for polygon in mesh.polygons:
                vertices = tuple(polygon.vertices)
                slot = slot_by_face.get(vertices)
                if slot is None:
                    slot = slot_by_face.get(tuple(sorted(vertices)), 0)
                resolved.append(slot)
            face_slots = resolved
            self.report.warnings.append(
                "{0}: Blender dropped {1} polygon(s) during validation".format(
                    object_name, len(faces) - len(mesh.polygons)
                )
            )

        if has_uv and len(mesh.loops) == len(loop_uv):
            uv_layer = mesh.uv_layers.new(name="UVMap")
            flat_uv = [component for pair in loop_uv for component in pair]
            uv_layer.data.foreach_set("uv", flat_uv)

        if len(normals) == len(vertices) and hasattr(mesh, "normals_split_custom_set_from_vertices"):
            try:
                mesh.normals_split_custom_set_from_vertices(
                    [
                        tuple(UNITY_TO_BLENDER_VECTOR @ Vector((normal[0], normal[1], normal[2])))
                        for normal in normals
                    ]
                )
            except Exception:  # noqa: BLE001 - custom normals are cosmetic
                pass

        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))

        object_ = bpy.data.objects.new(object_name, mesh)
        self.collection.objects.link(object_)
        self.created_objects.append(object_)
        self.created_meshes.append(mesh)
        game_object_pid = getattr(renderer.m_GameObject, "m_PathID", 0)
        parent_empty = self._ensure_game_object_empty(self._game_object_father(game_object_pid))
        if parent_empty is not None:
            object_.parent = parent_empty
        object_.matrix_basis = self._blender_matrix(self._game_object_local_matrix(game_object_pid))

        self._assign_materials(object_, renderer, face_slots)

        self.report.objects += 1
        self.report.meshes += 1
        self.report.vertices += len(vertices)
        self.report.triangles += len(faces)
        self.report.object_names.append(object_name)
        return self._skin_request(object_, renderer, handler, len(vertices))

    # -------------------------------------------------------------- materials

    def _assign_materials(self, object_, renderer, face_slots) -> None:
        materials = []
        for pointer in getattr(renderer, "m_Materials", []) or []:
            material = self._material(self._deref(pointer))
            if material is not None:
                materials.append(material)
        for material in materials:
            object_.data.materials.append(material)
        if not materials:
            return
        limit = len(materials) - 1
        missing = sorted({slot for slot in face_slots if slot > limit})
        if missing:
            self.report.warnings.append(
                "{0}: 子网格 {1} 没有对应材质，这些面暂时用最后一个材质".format(
                    object_.name, missing
                )
            )
        object_.data.polygons.foreach_set(
            "material_index", [min(slot, limit) for slot in face_slots]
        )

    def _material(self, unity_material) -> bpy.types.Material | None:
        if unity_material is None:
            return None
        key = ("material", self._asset_id(unity_material))
        if key in self._materials:
            return self._materials[key]

        material = bpy.data.materials.new(
            self._unique_name("material", unity_material.m_Name or "material")
        )
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        shader = nodes.get("Principled BSDF") or nodes.new("ShaderNodeBsdfPrincipled")

        properties = unity_material.m_SavedProperties
        floats = dict(properties.m_Floats)
        colors = dict(properties.m_Colors)
        textures = dict(properties.m_TexEnvs)

        base_color = colors.get("_BaseColor") or colors.get("_Color")
        if base_color is not None and "Base Color" in shader.inputs:
            shader.inputs["Base Color"].default_value = (
                base_color.r,
                base_color.g,
                base_color.b,
                base_color.a,
            )
        metallic = floats.get("_Metallic")
        if metallic is not None and "Metallic" in shader.inputs:
            shader.inputs["Metallic"].default_value = metallic
        gloss = floats.get("_Glossiness")
        if gloss is not None and "Roughness" in shader.inputs:
            shader.inputs["Roughness"].default_value = max(0.0, min(1.0, 1.0 - gloss))

        mode = floats.get("_Mode")
        cutoff = floats.get("_Cutoff", 0.5)
        if mode is not None:
            if int(round(mode)) == 1:
                if hasattr(material, "blend_method"):
                    material.blend_method = "CLIP"
                if hasattr(material, "alpha_threshold"):
                    material.alpha_threshold = cutoff
            elif int(round(mode)) in (2, 3):
                if hasattr(material, "blend_method"):
                    material.blend_method = "BLEND"
                if hasattr(material, "surface_render_method"):
                    material.surface_render_method = "BLENDED"

        if self.options.import_textures:
            base_map = textures.get("_MainTex") or textures.get("_BaseMap")
            image = self._image(self._deref(getattr(base_map, "m_Texture", None)))
            if image is not None:
                texture_node = nodes.new("ShaderNodeTexImage")
                texture_node.image = image
                texture_node.location = (-500, 250)
                links.new(texture_node.outputs["Color"], shader.inputs["Base Color"])
                if "Alpha" in shader.inputs and getattr(material, "blend_method", "OPAQUE") in {"CLIP", "BLEND"}:
                    links.new(texture_node.outputs["Alpha"], shader.inputs["Alpha"])

            bump_map = textures.get("_BumpMap")
            normal_image = self._image(self._deref(getattr(bump_map, "m_Texture", None)), non_color=True)
            if normal_image is not None and "Normal" in shader.inputs:
                texture_node = nodes.new("ShaderNodeTexImage")
                texture_node.image = normal_image
                texture_node.location = (-500, -100)
                normal_node = nodes.new("ShaderNodeNormalMap")
                normal_node.location = (-250, -100)
                scale = floats.get("_BumpScale")
                if scale is not None:
                    normal_node.inputs["Strength"].default_value = scale
                links.new(texture_node.outputs["Color"], normal_node.inputs["Color"])
                links.new(normal_node.outputs["Normal"], shader.inputs["Normal"])

        self._materials[key] = material
        self.created_materials.append(material)
        self.report.materials += 1
        return material

    def _image(self, unity_texture, non_color: bool = False) -> bpy.types.Image | None:
        if unity_texture is None:
            return None
        key = ("image", self._asset_id(unity_texture))
        if key in self._images:
            return self._images[key]

        try:
            image_data = unity_texture.image
        except Exception as exc:  # noqa: BLE001 - unsupported formats must not abort the import
            self.report.warnings.append(
                "Texture {0} could not be decoded ({1}: {2})".format(
                    unity_texture.m_Name, type(exc).__name__, exc
                )
            )
            self._images[key] = None
            return None
        if image_data is None:
            self.report.warnings.append(
                "Texture {0} has no decodable image data".format(unity_texture.m_Name)
            )
            self._images[key] = None
            return None

        directory = Path(self.options.texture_dir)
        directory.mkdir(parents=True, exist_ok=True)
        # 带上 bundle 标识：贴图名和 path_id 只在单个 bundle 内唯一，只有它们会跨 mod 撞车。
        bundle_token = sanitize(Path(self.ref.display).stem, "bundle")
        path = directory / "{0}_{1}_{2}.png".format(
            bundle_token, sanitize(unity_texture.m_Name or "texture"), key[1]
        )
        image_data.convert("RGBA").save(path)

        blender_image = bpy.data.images.load(str(path), check_existing=True)
        self.created_images.append(blender_image)
        blender_image.name = self._unique_name(
            "image", "T_" + (unity_texture.m_Name or "texture")
        )
        if non_color:
            blender_image.colorspace_settings.name = "Non-Color"
        if self.options.pack_textures:
            try:
                blender_image.pack()
            except Exception:  # noqa: BLE001 - packing is optional
                pass
        self._images[key] = blender_image
        self.report.images += 1
        return blender_image

    # --------------------------------------------------------------- skinning

    def _skin_request(self, object_, renderer, handler, vertex_count):
        """Collect what is needed to rig a mesh; bones are built once per bundle."""
        if not self.options.import_armatures or type(renderer).__name__ != "SkinnedMeshRenderer":
            return None
        pointers = [p for p in getattr(renderer, "m_Bones", []) or [] if p is not None]
        bones = [(pointer, self._deref(pointer)) for pointer in pointers]
        bones = [(pointer, transform) for pointer, transform in bones if transform is not None]
        if not bones:
            self.report.warnings.append(
                "{0}: no bones on the SkinnedMeshRenderer, imported as static mesh".format(object_.name)
            )
            return None
        indices = handler.m_BoneIndices
        weights = handler.m_BoneWeights
        if not indices or not weights or len(indices) != vertex_count or len(weights) != vertex_count:
            self.report.warnings.append(
                "{0}: mesh has no skin weights, imported as static mesh".format(object_.name)
            )
            return None
        return _SkinRequest(
            object=object_,
            bones=bones,
            indices=indices,
            weights=weights,
            renderer_world=self._component_world(renderer),
        )

    def _build_armature(self, requests) -> None:
        """One armature per bundle, holding the union of every renderer's bones."""
        union: dict[int, object] = {}
        for request in requests:
            for pointer, transform in request.bones:
                union.setdefault(pointer.m_PathID, transform)

        # SMR 只引用自己用到的骨头，中间节点常常不在列表里；不补回来的话骨架会断成
        # 一堆根骨，动根骨带不动整只模型。这里把同族（cf_J_… / joint…）的祖先补进来。
        prefixes = {self._skeleton_prefix(self._bone_object_name(path_id)) for path_id in union}
        prefixes.discard("")
        for path_id in list(union):
            father_pid = getattr(union[path_id].m_Father, "m_PathID", 0)
            while father_pid and father_pid not in union:
                father = self._read_pid(father_pid)
                if father is None:
                    break
                if not any(
                    self._bone_object_name(father_pid).startswith(prefix) for prefix in prefixes
                ):
                    break
                union[father_pid] = father
                father_pid = getattr(father.m_Father, "m_PathID", 0)

        self._armature_world = requests[0].renderer_world
        inverse_world = self._armature_world.inverted_safe()
        rest = {path_id: self._transform_world(path_id) for path_id in union}

        # 同一套骨架在这个 bundle 里会被复制多份（一个服装部件一份，位置完全相同）。
        # 按「骨名 + 世界矩阵」合并成一套，否则会并排出现多个根骨，动一根带不动整只。
        keepers: dict[tuple, int] = {}
        representative: dict[int, int] = {}
        for path_id in union:
            matrix = rest[path_id]
            key = (
                self._bone_object_name(path_id),
                tuple(round(value, 4) for row in matrix for value in row),
            )
            representative[path_id] = keepers.setdefault(key, path_id)

        primary = [path_id for path_id in union if representative[path_id] == path_id]
        names: dict[int, str] = {}
        used: dict[str, int] = {}
        for path_id in primary:
            base = sanitize(self._bone_object_name(path_id), "bone")
            count = used.get(base, 0) + 1
            used[base] = count
            names[path_id] = base if count == 1 else "{0}.{1:03d}".format(base, count)
        for path_id, keeper in representative.items():
            names[path_id] = names[keeper]
        self._bone_names = names

        name = self._unique_name("armature", "{0}_rig".format(requests[0].object.name or "bundle"))
        armature_data = bpy.data.armatures.new(name)
        armature = bpy.data.objects.new(name, armature_data)
        self.collection.objects.link(armature)
        self.created_objects.append(armature)
        self.created_armatures.append(armature_data)
        if self.parent is not None:
            armature.parent = self.parent
        armature.matrix_basis = self._blender_matrix(self._armature_world)
        self._armature = armature

        positions = [
            self._blender_matrix(inverse_world @ matrix).to_translation() for matrix in rest.values()
        ]
        diagonal = 0.0
        if positions:
            minimum = Vector(min(position[i] for position in positions) for i in range(3))
            maximum = Vector(max(position[i] for position in positions) for i in range(3))
            diagonal = (maximum - minimum).length
        default_length = max(0.02, diagonal * 0.05)

        previous_active = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = armature
        armature.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            created: dict[int, object] = {}
            for path_id in primary:
                transform = union[path_id]
                matrix = self._blender_matrix(inverse_world @ rest[path_id])
                head = matrix.to_translation()
                rotation = matrix.to_3x3()
                direction = rotation @ Vector((0.0, 1.0, 0.0))
                if direction.length < 1e-6:
                    direction = Vector((0.0, 1.0, 0.0))
                length = default_length
                for child_pointer in getattr(transform, "m_Children", []) or []:
                    child_path = getattr(child_pointer, "m_PathID", 0)
                    if child_path in rest:
                        child_head = self._blender_matrix(
                            inverse_world @ rest[child_path]
                        ).to_translation()
                        distance = (child_head - head).length
                        if distance > 1e-5:
                            length = distance
                        break
                bone = armature_data.edit_bones.new(names[path_id])
                bone.head = head
                bone.tail = head + direction.normalized() * length
                bone.align_roll(rotation @ Vector((0.0, 0.0, 1.0)))
                bone.use_connect = False
                created[path_id] = bone

            for path_id in primary:
                father_pid = getattr(union[path_id].m_Father, "m_PathID", 0)
                keeper = representative.get(father_pid, father_pid)
                if keeper in created and keeper != path_id:
                    created[path_id].parent = created[keeper]
                    created[path_id].use_connect = False
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
            if previous_active is not None:
                bpy.context.view_layer.objects.active = previous_active

        self.report.armatures += 1

    def _bind_skin(self, request) -> None:
        groups = {}
        for index, (pointer, _transform) in enumerate(request.bones):
            name = self._bone_names.get(pointer.m_PathID)
            if name:
                # 合并过的重复骨可能同名：先找已有组，避免 Blender 生成 .001 把权重劈开。
                groups[index] = (
                    request.object.vertex_groups.get(name)
                    or request.object.vertex_groups.new(name=name)
                )
        if not groups:
            return

        bucket = {}
        for vertex_index, (bone_indices, bone_weights) in enumerate(
            zip(request.indices, request.weights)
        ):
            total = sum(weight for weight in bone_weights if weight > _WEIGHT_EPSILON)
            if total <= 0.0:
                continue
            for bone_index, weight in zip(bone_indices, bone_weights):
                if weight <= _WEIGHT_EPSILON or bone_index not in groups:
                    continue
                bucket.setdefault((bone_index, weight / total), []).append(vertex_index)
        for (bone_index, weight), vertex_indices in bucket.items():
            groups[bone_index].add(vertex_indices, weight, "REPLACE")

        modifier = request.object.modifiers.new(name="Armature", type="ARMATURE")
        modifier.object = self._armature
        self.report.skinned += 1
