"""Probe a Unity .unity3d / AssetBundle and print what the Blender importer can use.

Usage: python tools/inspect_bundle.py <bundle-or-folder> [--limit N]
"""

from __future__ import annotations

import argparse
import collections
import sys

import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler


def safe(label, fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - probe tool, report anything
        print(f"    ! {label}: {type(exc).__name__}: {exc}")
        return None


def describe(obj, reader, limit):
    name = safe("name", lambda: reader.m_Name)
    print(f"  - {obj.type.name} name={name!r} path_id={obj.path_id}")
    if obj.type.name == "Mesh":
        # UnityPy 的 Mesh 要先过 MeshHandler 才有顶点数组，否则只会打印一堆假错误。
        safe("handler", lambda: MeshHandler(reader).process())
        verts = safe("m_VertexCount", lambda: len(reader.m_Vertices))
        print(f"    vertices={verts} submeshes={safe('sub', lambda: len(reader.m_SubMeshes))}")
        print(
            f"    uv={safe('uv', lambda: len(reader.m_UV0))}"
            f" bones={safe('bones', lambda: len(reader.m_BindPose))}"
            f" blendshapes={safe('shapes', lambda: len(reader.m_Shapes.shapes))}"
        )
    elif obj.type.name == "SkinnedMeshRenderer":
        print(
            f"    bones={safe('bones', lambda: len(reader.m_Bones))}"
            f" rootBone={safe('root', lambda: reader.m_RootBone.m_PathID)}"
            f" mesh={safe('mesh', lambda: reader.m_Mesh.m_PathID)}"
            f" materials={safe('mats', lambda: [m.m_PathID for m in reader.m_Materials])}"
        )
    elif obj.type.name == "MeshRenderer":
        print(f"    materials={safe('mats', lambda: [m.m_PathID for m in reader.m_Materials])}")
    elif obj.type.name == "Material":
        shader = safe("shader", lambda: reader.m_Shader.read().m_Name)
        print(f"    shader={shader!r} tex_envs={safe('texs', lambda: len(reader.m_SavedProperties.m_TexEnvs))}")
        safe("props", lambda: print("    floats=", dict(list(reader.m_SavedProperties.m_Floats.items())[:limit])))
    elif obj.type.name == "Texture2D":
        print(
            f"    size={safe('w', lambda: reader.m_Width)}x{safe('h', lambda: reader.m_Height)}"
            f" format={safe('fmt', lambda: reader.m_TextureFormat)}"
            f" stream={safe('stream', lambda: reader.m_StreamData.path if reader.m_StreamData else None)}"
        )
    elif obj.type.name == "GameObject":
        comps = safe("comps", lambda: [c.component.m_ClassID if hasattr(c, "component") else c for c in reader.m_Component])
        print(f"    components={comps}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--types", default="", help="comma separated filter")
    args = ap.parse_args()

    env = UnityPy.load(args.path)
    print(f"=== {args.path}")
    print(f"files: {list(env.files.keys()) if hasattr(env, 'files') else 'n/a'}")
    print(f"objects: {len(env.objects)}")
    print(f"container: {dict(list(getattr(env, 'container', {}).items())[:10])}")

    hist = collections.Counter(o.type.name for o in env.objects)
    print("types:", dict(hist.most_common()))

    want = {t.strip() for t in args.types.split(",") if t.strip()}
    shown = collections.Counter()
    for obj in env.objects:
        if want and obj.type.name not in want:
            continue
        if shown[obj.type.name] >= args.limit:
            continue
        shown[obj.type.name] += 1
        reader = safe("read", obj.read)
        if reader is None:
            continue
        describe(obj, reader, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
