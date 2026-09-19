import json
import os
from pathlib import Path

import bpy


STATUS_PATH = Path(
    os.environ.get("VIDEO_CREATOR_MPFB_STATUS", "cache/mpfb-check.json")
).expanduser().resolve()


def discover_mpfb_module():
    prefs = bpy.context.preferences

    # Already-enabled add-ons are authoritative.
    for module_name in prefs.addons.keys():
        if str(module_name).split(".")[-1] == "mpfb":
            return str(module_name), "enabled"

    candidates = []
    repos = getattr(getattr(prefs, "extensions", None), "repos", [])
    for repo in repos:
        if not getattr(repo, "enabled", True):
            continue
        repo_dir = Path(str(repo.directory)).expanduser()
        package_dir = repo_dir / "mpfb"
        manifest = package_dir / "blender_manifest.toml"
        if package_dir.is_dir() and manifest.is_file():
            module_name = f"bl_ext.{repo.module}.mpfb"
            candidates.append((module_name, str(repo_dir), str(repo.module)))

    if not candidates:
        details = [
            {
                "name": str(repo.name),
                "module": str(repo.module),
                "directory": str(repo.directory),
                "enabled": bool(repo.enabled),
            }
            for repo in repos
        ]
        raise RuntimeError(
            "MPFB package directory not found in enabled extension repositories: "
            + json.dumps(details, ensure_ascii=False)
        )

    errors = []
    for module_name, repo_dir, repo_module in candidates:
        try:
            result = bpy.ops.preferences.addon_enable(module=module_name)
            if "FINISHED" not in result:
                errors.append(f"{module_name}: addon_enable={result}")
                continue
            if module_name not in bpy.context.preferences.addons.keys():
                errors.append(f"{module_name}: enabled result but missing from preferences.addons")
                continue
            return module_name, {
                "repo_directory": repo_dir,
                "repo_module": repo_module,
                "enable_result": sorted(result),
            }
        except Exception as error:
            errors.append(f"{module_name}: {type(error).__name__}: {error}")

    raise RuntimeError("MPFB extension could not be enabled: " + " | ".join(errors))


def probe_create_human():
    before_names = {obj.name for obj in bpy.data.objects}
    try:
        result = bpy.ops.mpfb.create_human()
        if "FINISHED" not in result:
            raise RuntimeError(f"mpfb.create_human returned {result}")

        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        created = [
            obj for obj in bpy.data.objects
            if obj.name not in before_names
        ]
        meshes = [obj for obj in created if obj.type == "MESH"]
        if not meshes:
            raise RuntimeError("mpfb.create_human finished but created no mesh")

        base = max(meshes, key=lambda obj: len(obj.data.vertices))
        if len(base.data.vertices) < 1000:
            raise RuntimeError(
                f"MPFB probe mesh unexpectedly small: {len(base.data.vertices)} vertices"
            )

        return {
            "result": sorted(result),
            "created_objects": len(created),
            "created_meshes": len(meshes),
            "base_vertices": len(base.data.vertices),
        }
    finally:
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        for obj in list(bpy.data.objects):
            if obj.name not in before_names:
                bpy.data.objects.remove(obj, do_unlink=True)


def main():
    module_name, discovery = discover_mpfb_module()

    # Real probe: do not trust bpy.ops proxy existence or RNA metadata alone.
    probe = probe_create_human()

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "status": "PASS",
                "module": module_name,
                "discovery": discovery,
                "operator": "mpfb.create_human",
                "probe": probe,
                "blender_version": list(bpy.app.version),
                "automation_mode": "extension_repo_discovery_plus_real_create_probe",
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(
        f"MPFB CHECK PASS module={module_name} "
        f"vertices={probe['base_vertices']} status={STATUS_PATH}",
        flush=True,
    )


if __name__ == "__main__":
    main()
