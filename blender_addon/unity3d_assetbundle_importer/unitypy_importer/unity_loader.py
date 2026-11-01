"""UnityPy bridge: dependency resolution, archive extraction, bundle discovery.

This module never imports bpy, so it can be exercised by a plain Python process.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipfile
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


def probe_unitypy(extra_search_path: str = "") -> tuple[bool, str]:
    """Return (available, message) without raising, for UI display."""
    try:
        module = import_unitypy(extra_search_path)
    except UnityPyMissing as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - UI must never crash
        return False, "{0}: {1}".format(type(exc).__name__, exc)
    version = getattr(module, "__version__", None) or getattr(module, "__VERSION__", "unknown")
    return True, "UnityPy {0} loaded from {1}".format(version, Path(module.__file__).parent)


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
        for member in handle.infolist():
            if member.is_dir():
                continue
            relative = _safe_relative(member.filename)
            if relative is None:
                result.warnings.append("Skipped unsafe archive path: {0}".format(member.filename))
                continue
            if PurePosixPath(relative).suffix.lower() not in BUNDLE_SUFFIXES:
                continue
            output = target.joinpath(*PurePosixPath(relative).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(member) as source, open(output, "wb") as destination:
                shutil.copyfileobj(source, destination, 1 << 20)
            result.bundles.append(BundleRef(path=output, display=relative, container=archive.name))

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
        if not result.bundles:
            result.warnings.append("No AssetBundle file found under {0}".format(source))
        return result

    suffix = source.suffix.lower()
    if suffix in ARCHIVE_SUFFIXES:
        _extract_archive(source, result, Path(extract_root) if extract_root else None)
    elif suffix in BUNDLE_SUFFIXES:
        result.bundles.append(BundleRef(path=source, display=source.name))
    else:
        raise ValueError(
            "Unsupported file type '{0}'. Expected one of {1} or {2}".format(
                suffix,
                ", ".join(ARCHIVE_SUFFIXES),
                ", ".join(BUNDLE_SUFFIXES),
            )
        )
    return result
