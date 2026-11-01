"""UnityPy bridge: dependency resolution, archive extraction, bundle discovery.

This module never imports bpy, so it can be exercised by a plain Python process.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile
import csv
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

BUNDLE_SUFFIXES = (".unity3d", ".assetbundle", ".bundle")
ARCHIVE_SUFFIXES = (".zipmod", ".zip")

_unitypy = None


class UnityPyMissing(RuntimeError):
    """Raised when UnityPy cannot be imported by the running interpreter."""


def import_unitypy(extra_search_path: str = ""):
    """Import UnityPy once, optionally after adding an extra site-packages path."""
    global _unitypy
    if _unitypy is not None:
        return _unitypy

    if extra_search_path:
        candidate = os.path.abspath(os.path.expanduser(extra_search_path))
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)

    try:
        import UnityPy  # noqa: PLC0415 - deliberately lazy
    except Exception as exc:  # noqa: BLE001 - surface any import failure as one error
        raise UnityPyMissing(
            "UnityPy is not importable from {0}\n"
            "Install it into the Python Blender uses:\n"
            '  "{0}" -m pip install UnityPy\n'
            "Or set 'UnityPy search path' in the add-on preferences to an existing "
            "site-packages folder.\n"
            "Original error: {1}: {2}".format(sys.executable, type(exc).__name__, exc)
        ) from exc

    _unitypy = UnityPy
    return UnityPy


@dataclass(frozen=True)
class BundleRef:
    """One AssetBundle file that UnityPy can open."""

    path: Path
    display: str
    container: str = ""


@dataclass
class BundleSet:
    """Discovered bundles plus the temporary folders that back them."""

    bundles: list[BundleRef] = field(default_factory=list)
    characustom: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    _temp_dirs: list[Path] = field(default_factory=list)

    def cleanup(self) -> None:
        for directory in self._temp_dirs:
            shutil.rmtree(directory, ignore_errors=True)
        self._temp_dirs.clear()

    def __enter__(self) -> BundleSet:
        return self

    def __exit__(self, *_exc) -> bool:
        self.cleanup()
        return False


def _safe_relative(name: str) -> str | None:
    """Return an archive member path that is safe to extract, else None."""
    if not name or "\x00" in name:
        return None
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or path.drive:
        return None
    if any(part in ("..", "") for part in path.parts):
        return None
    return path.as_posix()


def _extract_archive(archive: Path, result: BundleSet, extract_root: Path | None) -> None:
    max_bytes = 8 * 1024 * 1024 * 1024  # shortcut: 单包解包上限 8 GiB，超过就拒绝
    if extract_root is None:
        target = Path(tempfile.mkdtemp(prefix="zipmod_import_"))
    else:
        target = Path(extract_root)
        target.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix="zipmod_import_", dir=target))
    result._temp_dirs.append(target)

    try:
        handle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise ValueError("{0} is not a readable zip archive: {1}".format(archive.name, exc)) from exc

    with handle:
        wanted = [
            member
            for member in handle.infolist()
            if not member.is_dir()
            and PurePosixPath(_safe_relative(member.filename) or "").suffix.lower()
            in BUNDLE_SUFFIXES + (".csv",)
        ]
        total = sum(member.file_size for member in wanted)
        if total > max_bytes:
            raise ValueError(
                "{0} 解包后约 {1:.1f} GiB，超过 {2:.0f} GiB 上限，已拒绝".format(
                    archive.name, total / (1024 ** 3), max_bytes / (1024 ** 3)
                )
            )
        free = shutil.disk_usage(target).free
        if total > free:
            raise ValueError(
                "{0} 解包需要 {1:.1f} GiB，超过剩余空间 {2:.1f} GiB".format(
                    archive.name, total / (1024 ** 3), free / (1024 ** 3)
                )
            )
        for member in handle.infolist():
            if member.is_dir():
                continue
            relative = _safe_relative(member.filename)
            if relative is None:
                result.warnings.append("Skipped unsafe archive path: {0}".format(member.filename))
                continue
            member_path = PurePosixPath(relative)
            is_bundle = member_path.suffix.lower() in BUNDLE_SUFFIXES
            is_list = member_path.suffix.lower() == ".csv" and "characustom" in member_path.parts
            if not (is_bundle or is_list):
                continue
            output = target.joinpath(*member_path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(member) as source, open(output, "wb") as destination:
                shutil.copyfileobj(source, destination, 1 << 20)
            if is_bundle:
                result.bundles.append(
                    BundleRef(path=output, display=relative, container=archive.name)
                )
            else:
                result.characustom.append(output)

    if not result.bundles:
        result.warnings.append(
            "No {0} file inside {1}".format(" / ".join(BUNDLE_SUFFIXES), archive.name)
        )


def collect_bundles(source: Path | str, extract_root: Path | str | None = None) -> BundleSet:
    """Find every Unity AssetBundle reachable from `source` (folder, archive or bundle)."""
    source = Path(source)
    result = BundleSet()
    if not source.exists():
        raise FileNotFoundError("Path not found: {0}".format(source))

    if source.is_dir():
        for candidate in sorted(source.rglob("*")):
            if candidate.is_file() and candidate.suffix.lower() in BUNDLE_SUFFIXES:
                result.bundles.append(
                    BundleRef(path=candidate, display=candidate.relative_to(source).as_posix())
                )
            elif (
                candidate.is_file()
                and candidate.suffix.lower() == ".csv"
                and "characustom" in candidate.parts
            ):
                result.characustom.append(candidate)
        if not result.bundles:
            result.warnings.append("No AssetBundle file found under {0}".format(source))
        return result

    suffix = source.suffix.lower()
    if suffix in ARCHIVE_SUFFIXES:
        _extract_archive(source, result, Path(extract_root) if extract_root else None)
    elif suffix in BUNDLE_SUFFIXES:
        result.bundles.append(BundleRef(path=source, display=source.name))
        result.characustom.extend(_find_characustom(source.parent))
    else:
        raise ValueError(
            "Unsupported file type '{0}'. Expected one of {1} or {2}".format(
                suffix,
                ", ".join(ARCHIVE_SUFFIXES),
                ", ".join(BUNDLE_SUFFIXES),
            )
        )
    return result


def _find_characustom(start: Path) -> list[Path]:
    """散装安装的单个 bundle，向上几层找 `list/characustom` 登记表。"""
    for parent in list(start.parents)[:4]:
        folder = parent / "list" / "characustom"
        if folder.is_dir():
            return sorted(folder.glob("*.csv"))
    return []


_CLOTHING_CATEGORIES = {
    "top",
    "bot",
    "bra",
    "under",
    "gloves",
    "shoes",
    "socks",
}


def bundle_key(path: str) -> str:
    """把 csv 里的 MainAB 或 bundle 的相对路径归一成同一个 key。"""
    name = path.replace("\\", "/").strip().lower()
    if name.startswith("abdata/"):
        name = name[len("abdata/") :]
    return name


def read_characustom(paths) -> dict[str, dict]:
    """读 characustom 列表，得出每个 bundle 的分类与声明的父节点。

    zipmod 的 `abdata/list/characustom/*.csv` 是游戏真正的登记表：头发一行带 SetHair，
    饰品一行带 Parent（该挂到角色哪个节点），衣服一行则靠角色骨架自己定位。
    """
    result: dict[str, dict] = {}
    for path in paths:
        try:
            handle = open(path, "r", encoding="utf-8-sig", errors="replace", newline="")
        except OSError:
            continue
        with handle:
            rows = list(csv.reader(handle))
        header_index = next(
            (index for index, row in enumerate(rows) if row and row[0].strip() == "ID"), None
        )
        if header_index is None:
            continue
        header = [cell.strip() for cell in rows[header_index]]
        category = path.stem.strip(" -").lower()
        for row in rows[header_index + 1:]:
            if not row or not row[0].strip():
                continue
            record = dict(zip(header, row))
            main_ab = (record.get("MainAB") or "").strip()
            if not main_ab:
                continue
            entry = result.setdefault(bundle_key(main_ab), {})
            entry.setdefault("categories", set()).add(category)
            if (record.get("SetHair") or "").strip():
                entry["hair"] = True
            parent = (record.get("Parent") or "").strip()
            if parent:
                entry["parent"] = parent
    return result


def bundle_role(entries: dict | None) -> str:
    """按登记表给 bundle 分类：hair / accessory / clothing / unknown。"""
    if not entries:
        return "unknown"
    if entries.get("hair"):
        return "hair"
    categories = entries.get("categories") or set()
    if entries.get("parent"):
        return "accessory"
    if categories & _CLOTHING_CATEGORIES:
        return "clothing"
    return "unknown"


# HS2/KK 的挂点（N_*，存在角色卡里、包里只有贴地占位点）对应到实际骨骼的候选链。
# 顺序即优先级，运行时按骨架里真实存在的骨挑第一个；表中没有的挂点会退回头骨。
_NODE_BONE_CANDIDATES = {
    "N_Head": ("cf_J_Head_s", "cf_J_Head"),
    "N_Hair": ("cf_J_Head_s", "cf_J_Head"),
    "N_Earring_L": ("cf_J_Head_s", "cf_J_Head"),
    "N_Earring_R": ("cf_J_Head_s", "cf_J_Head"),
    "N_Face": ("cf_J_Head_s", "cf_J_Head"),
    "N_Neck": ("cf_J_Neck", "cf_J_Head_s"),
    "N_Chest": ("cf_J_Spine02_s", "cf_J_Spine01_s"),
    "N_Mune_L": ("cf_J_Mune00_s_L", "cf_J_Spine02_s"),
    "N_Mune_R": ("cf_J_Mune00_s_R", "cf_J_Spine02_s"),
    "N_Back": ("cf_J_Spine02_s", "cf_J_Spine01_s"),
    "N_Waist": ("cf_J_Kosi01_s", "cf_J_Hips"),
    "N_Kosi01": ("cf_J_Kosi01_s", "cf_J_Hips"),
    "N_Kosi02": ("cf_J_Kosi02_s", "cf_J_Kosi01_s", "cf_J_Hips"),
    "N_Hip": ("cf_J_Hips", "cf_J_Kosi01_s"),
    "N_Arm_L": ("cf_J_ArmLow02_s_L", "cf_J_ArmLow01_s_L"),
    "N_Arm_R": ("cf_J_ArmLow02_s_R", "cf_J_ArmLow01_s_R"),
    "N_Elbo_L": ("cf_J_ArmElbo_low_s_L", "cf_J_ArmElboura_s_L"),
    "N_Elbo_R": ("cf_J_ArmElbo_low_s_R", "cf_J_ArmElboura_s_R"),
    "N_Hand_L": ("cf_J_Hand_Wrist_s_L", "cf_J_Hand_L"),
    "N_Hand_R": ("cf_J_Hand_Wrist_s_R", "cf_J_Hand_R"),
    "N_Leg_L": ("cf_J_LegLow01_s_L", "cf_J_LegUp01_s_L"),
    "N_Leg_R": ("cf_J_LegLow01_s_R", "cf_J_LegUp01_s_R"),
    "N_Ankle_L": ("cf_J_Ankle_L", "cf_J_Foot_L", "cf_J_Toes01_L", "cf_J_LegLow02_s_L"),
    "N_Ankle_R": ("cf_J_Ankle_R", "cf_J_Foot_R", "cf_J_Toes01_R", "cf_J_LegLow02_s_R"),
    "N_Foot_L": ("cf_J_Foot_L", "cf_J_Foot01_L", "cf_J_Ankle_L", "cf_J_Toes01_L"),
    "N_Foot_R": ("cf_J_Foot_R", "cf_J_Foot01_R", "cf_J_Ankle_R", "cf_J_Toes01_R"),
    "N_Toes_L": ("cf_J_Toes01_L", "cf_J_Foot_L"),
    "N_Toes_R": ("cf_J_Toes01_R", "cf_J_Foot_R"),
}


# 挂点名里的部位关键词 → 该部位的骨候选链。这样遇到没写在精确表里的新挂点（不同作者、
# 不同游戏）也能按名字自己认出来，不用每次补一条。
_REGION_KEYWORDS = (
    ("head", ("head", "hair", "face", "eye", "ear", "earring", "mouth", "nose", "cheek",
              "horn", "hat", "cap", "visor", "mask", "glasses", "crown", "halo", "ff", "ahoge")),
    ("neck", ("neck", "kubi", "collar")),
    ("chest", ("chest", "mune", "breast", "bust")),
    ("waist", ("waist", "kosi", "hip", "pelvis", "spine", "back", "belt", "skirt", "tail")),
    ("shoulder", ("shoulder", "kata")),
    ("arm", ("arm", "ude", "elbow", "elbo", "wrist", "forearm")),
    ("hand", ("hand", "te", "finger", "yubi")),
    ("leg", ("leg", "thigh", "knee", "ashi", "shin", "calf")),
    ("foot", ("foot", "ankle", "heel", "toe", "shoe", "sock", "boot")),
)

_REGION_BONES = {
    "head": ("cf_J_Head_s", "cf_J_Head", "cf_J_Neck"),
    "neck": ("cf_J_Neck", "cf_J_Head_s", "cf_J_Spine02_s"),
    "chest": ("cf_J_Spine02_s", "cf_J_Mune00_s_L", "cf_J_Spine01_s"),
    "waist": ("cf_J_Kosi01_s", "cf_J_Kosi02_s", "cf_J_Hips"),
    "shoulder": ("cf_J_ArmUp01_s_L", "cf_J_ArmUp01_s_R", "cf_J_Spine02_s"),
    "arm": ("cf_J_ArmLow02_s_L", "cf_J_ArmLow02_s_R", "cf_J_ArmLow01_s_L", "cf_J_ArmLow01_s_R"),
    "hand": ("cf_J_Hand_Wrist_s_L", "cf_J_Hand_Wrist_s_R", "cf_J_Hand_L", "cf_J_Hand_R"),
    "leg": ("cf_J_LegLow01_s_L", "cf_J_LegLow01_s_R", "cf_J_LegUp01_s_L", "cf_J_LegUp01_s_R"),
    "foot": ("cf_J_Foot_L", "cf_J_Foot_R", "cf_J_Ankle_L", "cf_J_Ankle_R",
             "cf_J_Toes01_L", "cf_J_Toes01_R", "cf_J_LegLow02_s_L", "cf_J_LegLow02_s_R"),
}


def node_side(declared: str) -> str:
    """挂点名里的左右标记：l / r / 空（中线）。"""
    name = (declared or "").lower()
    if name.endswith("_l") or "_l_" in name or "left" in name:
        return "l"
    if name.endswith("_r") or "_r_" in name or "right" in name:
        return "r"
    return ""


def node_region(declared: str) -> str:
    """按关键词判断挂点属于哪个部位；认不出来返回空。"""
    name = (declared or "").lower()
    for region, keywords in _REGION_KEYWORDS:
        for keyword in keywords:
            if keyword in name:
                return region
    return ""


def resolve_node_bone(declared: str, bone_names) -> str | None:
    """把 characustom 里的挂点名（N_Head、N_Earring_L…）解析成骨架里真实存在的骨名。

    顺序：同名骨 → 精确表 → 部位关键词（带左右过滤）→ 去掉 N_ 前缀的子串匹配。
    全部失败返回 None，让调用方保持原样并提示，而不是瞎猜一根骨。
    """
    if not declared:
        return None
    if declared in bone_names:
        return declared
    for candidate in _NODE_BONE_CANDIDATES.get(declared, ()):
        if candidate in bone_names:
            return candidate

    region = node_region(declared)
    side = node_side(declared)
    if region:
        candidates = _REGION_BONES.get(region, ())
        if side:
            sided = [name for name in candidates if name.endswith("_" + side.upper())]
            for name in sided:
                if name in bone_names:
                    return name
        for name in candidates:
            if name in bone_names:
                return name

    stripped = declared[2:] if declared.startswith("N_") else declared
    if stripped:
        for candidate in bone_names:
            if stripped.lower() in candidate.lower():
                return candidate
    return None
