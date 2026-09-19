import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--blend-output", required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def principled(name, color, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError(f"Principled BSDF missing for {name}")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def ensure_mpfb_enabled():
    prefs = bpy.context.preferences

    for module_name in prefs.addons.keys():
        if str(module_name).split(".")[-1] == "mpfb":
            return str(module_name)

    repos = getattr(getattr(prefs, "extensions", None), "repos", [])
    candidates = []
    for repo in repos:
        if not getattr(repo, "enabled", True):
            continue
        repo_dir = Path(str(repo.directory)).expanduser()
        package_dir = repo_dir / "mpfb"
        manifest = package_dir / "blender_manifest.toml"
        if package_dir.is_dir() and manifest.is_file():
            candidates.append(f"bl_ext.{repo.module}.mpfb")

    if not candidates:
        raise RuntimeError("MPFB extension package not found; run ./install-mpfb.command")

    errors = []
    for module_name in candidates:
        try:
            result = bpy.ops.preferences.addon_enable(module=module_name)
            if "FINISHED" in result and module_name in bpy.context.preferences.addons.keys():
                return module_name
            errors.append(f"{module_name}: {result}")
        except Exception as error:
            errors.append(f"{module_name}: {type(error).__name__}: {error}")

    raise RuntimeError("MPFB extension could not be enabled: " + " | ".join(errors))


def require_scene_prop(scene, name):
    full = "MPFB_NH_" + name
    if not hasattr(scene, full):
        raise RuntimeError(
            f"MPFB New Human scene property missing: {full}. "
            "Extension loaded but New Human properties were not registered."
        )
    return full


def configure_native_child(scene):
    values = {
        "add_phenotype": True,
        "phenotype_gender": "female",
        "phenotype_age": "child",
        "phenotype_muscle": "minmuscle",
        "phenotype_weight": "averageweight",
        "phenotype_height": "minheight",
        "phenotype_proportions": "average",
        "phenotype_race": "asian",
        "phenotype_influence": 1.0,
        "add_breast": False,
        "scale_factor": "METER",
        "mask_helpers": True,
        "detailed_helpers": True,
        "extra_vertex_groups": True,
    }
    applied = {}
    for short_name, value in values.items():
        full = require_scene_prop(scene, short_name)
        setattr(scene, full, value)
        actual = getattr(scene, full)
        if actual != value:
            raise RuntimeError(
                f"MPFB property did not retain value: {full} expected={value!r} actual={actual!r}"
            )
        applied[full] = actual
    return applied


def evaluated_bounds(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    mins = Vector((
        min(p.x for p in corners),
        min(p.y for p in corners),
        min(p.z for p in corners),
    ))
    maxs = Vector((
        max(p.x for p in corners),
        max(p.y for p in corners),
        max(p.z for p in corners),
    ))
    return mins, maxs, corners


def normalize_height(obj, target_height=1.28):
    bpy.context.view_layer.update()
    mins, maxs, _ = evaluated_bounds(obj)
    height = maxs.z - mins.z
    if height <= 0:
        raise RuntimeError("MPFB child basemesh has invalid height")
    factor = target_height / height
    obj.scale *= factor
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    mins, _, _ = evaluated_bounds(obj)
    obj.location.z -= mins.z
    bpy.context.view_layer.update()


def light_anime_stylize(obj):
    """Small style push only after MPFB has created a real child phenotype."""
    mesh = obj.data
    zs = [v.co.z for v in mesh.vertices]
    if not zs:
        raise RuntimeError("MPFB child mesh contains no vertices")
    zmin, zmax = min(zs), max(zs)
    span = max(zmax - zmin, 1e-6)

    for v in mesh.vertices:
        t = (v.co.z - zmin) / span

        if t >= 0.835:
            center_z = zmin + span * 0.91
            dz = v.co.z - center_z
            v.co.x *= 1.10
            v.co.y *= 1.10
            v.co.z = center_z + dz * 1.04

        elif 0.64 <= t < 0.835:
            # Slightly soften the shoulder/chest width; MPFB child macro remains primary.
            v.co.x *= 0.96

        elif t < 0.46:
            # Very mild leg shortening for the reference's juvenile/chibi direction.
            v.co.z = zmin + (v.co.z - zmin) * 0.94

    mesh.update()
    normalize_height(obj, 1.28)


def create_native_child():
    module_name = ensure_mpfb_enabled()
    scene = bpy.context.scene
    applied = configure_native_child(scene)

    before_names = {obj.name for obj in bpy.data.objects}
    result = bpy.ops.mpfb.create_human()
    if "FINISHED" not in result:
        raise RuntimeError(f"MPFB create_human failed: {result}")

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    created_meshes = [
        obj for obj in bpy.data.objects
        if obj.name not in before_names and obj.type == "MESH"
    ]
    if not created_meshes:
        created_meshes = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if not created_meshes:
        raise RuntimeError("MPFB native child creation produced no mesh")

    base = max(created_meshes, key=lambda obj: len(obj.data.vertices))
    if len(base.data.vertices) < 1000:
        raise RuntimeError(f"MPFB child basemesh unexpectedly small: {len(base.data.vertices)} vertices")

    base.name = "ChildMPFBNativeBaseMesh"
    for obj in created_meshes:
        if obj != base:
            obj.hide_render = True
            obj.hide_set(True)

    return base, {
        "module": module_name,
        "operator_result": sorted(result),
        "base_vertices": len(base.data.vertices),
        "scene_properties": applied,
    }


def auto_frame(scene, cam, target, obj, margin=0.10):
    mins, maxs, corners = evaluated_bounds(obj)
    center = (mins + maxs) * 0.5
    target.location = center
    cam.location = Vector((center.x, mins.y - 2.0, center.z + 0.02))

    for _ in range(100):
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, cam, p) for p in corners]
        xs = [p.x for p in projected]
        ys = [p.y for p in projected]
        zs = [p.z for p in projected]
        if (
            min(xs) >= margin and max(xs) <= 1.0 - margin
            and min(ys) >= margin and max(ys) <= 1.0 - margin
            and min(zs) > 0.0
        ):
            return {
                "x_min": float(min(xs)),
                "x_max": float(max(xs)),
                "y_min": float(min(ys)),
                "y_max": float(max(ys)),
                "z_min": float(min(zs)),
            }
        cam.location.y -= 0.08
    raise RuntimeError("MPFB native child could not be auto-framed")


def main():
    args = parse_args()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 540
    scene.render.resolution_y = 960
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.world.color = (0.018, 0.022, 0.030)

    base, applied = create_native_child()
    normalize_height(base, 1.28)
    light_anime_stylize(base)

    skin = principled("ChildSkinV6", (0.69, 0.43, 0.36), 0.84)
    base.data.materials.clear()
    base.data.materials.append(skin)

    subdiv = base.modifiers.get("LookdevSubdivision") or base.modifiers.new(
        "LookdevSubdivision", "SUBSURF"
    )
    subdiv.levels = 1
    subdiv.render_levels = 2

    ground_mat = principled("Ground", (0.055, 0.040, 0.032), 0.96)
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(ground_mat)

    bpy.ops.object.light_add(type="AREA", location=(2.6, -1.5, 2.8))
    key = bpy.context.object
    key.data.energy = 390
    key.data.color = (1.0, 0.36, 0.16)
    key.data.size = 2.6

    bpy.ops.object.light_add(type="AREA", location=(-1.8, -3.0, 2.0))
    fill = bpy.context.object
    fill.data.energy = 340
    fill.data.color = (0.58, 0.72, 1.0)
    fill.data.size = 2.4

    target = bpy.data.objects.new("LookdevTarget", None)
    bpy.context.collection.objects.link(target)

    bpy.ops.object.camera_add(location=(0, -4, 1))
    cam = bpy.context.object
    cam.data.lens = 72
    cam.data.sensor_width = 36.0
    track = cam.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam

    framing = auto_frame(scene, cam, target, base, margin=0.10)

    print(
        "VIDEO_CREATOR_MPFB_NATIVE_CHILD_PASS "
        + json.dumps({
            "age": applied["scene_properties"]["MPFB_NH_phenotype_age"],
            "gender": applied["scene_properties"]["MPFB_NH_phenotype_gender"],
            "race": applied["scene_properties"]["MPFB_NH_phenotype_race"],
            "add_breast": applied["scene_properties"]["MPFB_NH_add_breast"],
            "vertices": applied["base_vertices"],
        }, ensure_ascii=False),
        flush=True,
    )
    print(
        f"VIDEO_CREATOR_CHILD_LOOKDEV_V6_FRAMING_PASS framing={framing}",
        flush=True,
    )

    output = Path(args.output).expanduser().resolve()
    blend = Path(args.blend_output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    blend.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size < 30000:
        raise RuntimeError("Child LookDev v6 render missing or unexpectedly small")

    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V6_PASS output={output}", flush=True)


if __name__ == "__main__":
    main()
