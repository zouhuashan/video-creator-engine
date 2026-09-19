import argparse
import math
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
        raise RuntimeError("MPFB extension package not found in enabled repositories")

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


def normalize_height(obj, target_height=1.34):
    bpy.context.view_layer.update()
    mins, maxs, _ = evaluated_bounds(obj)
    height = maxs.z - mins.z
    if height <= 0:
        raise RuntimeError("MPFB basemesh has invalid height")
    factor = target_height / height
    obj.scale *= factor
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    mins, _, _ = evaluated_bounds(obj)
    obj.location.z -= mins.z
    bpy.context.view_layer.update()


def childify_basemesh(obj):
    """Stylize a continuous MPFB human mesh toward child proportions without remeshing."""
    mesh = obj.data
    zs = [vertex.co.z for vertex in mesh.vertices]
    if not zs:
        raise RuntimeError("MPFB basemesh has no vertices")
    zmin = min(zs)
    zmax = max(zs)
    span = max(zmax - zmin, 1e-6)

    # Approximate anatomical regions by normalized height.
    # The goal is only a child base-mesh checkpoint, not final face sculpting.
    for vertex in mesh.vertices:
        t = (vertex.co.z - zmin) / span

        if t >= 0.82:
            # Head: enlarge width/depth around an upper-body center.
            head_center_z = zmin + span * 0.90
            local_z = vertex.co.z - head_center_z
            vertex.co.x *= 1.12
            vertex.co.y *= 1.10
            vertex.co.z = head_center_z + local_z * 1.08

        elif 0.62 <= t < 0.82:
            # Neck/shoulders/chest: narrower, softer juvenile silhouette.
            blend = (t - 0.62) / 0.20
            vertex.co.x *= 0.90 + 0.04 * blend
            vertex.co.y *= 0.96

        elif 0.42 <= t < 0.62:
            # Waist/pelvis: compact torso.
            vertex.co.x *= 0.94
            vertex.co.y *= 0.96

        else:
            # Legs: shorten visually while preserving continuous topology.
            pelvis_z = zmin + span * 0.42
            vertex.co.z = zmin + (vertex.co.z - zmin) * 0.88
            if vertex.co.z > pelvis_z:
                vertex.co.z = pelvis_z + (vertex.co.z - pelvis_z) * 0.96

    mesh.update()

    # Renormalize to the desired child height after proportional edits.
    normalize_height(obj, 1.34)


def create_mpfb_basemesh():
    module_name = ensure_mpfb_enabled()
    before_names = {obj.name for obj in bpy.data.objects}

    result = bpy.ops.mpfb.create_human()
    if "FINISHED" not in result:
        raise RuntimeError(f"MPFB create_human failed: {result}")

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    created_meshes = [
        obj
        for obj in bpy.data.objects
        if obj.name not in before_names and obj.type == "MESH"
    ]
    if not created_meshes:
        created_meshes = [
            obj for obj in bpy.context.selected_objects if obj.type == "MESH"
        ]
    if not created_meshes:
        raise RuntimeError("MPFB create_human created no mesh")

    base = max(created_meshes, key=lambda obj: len(obj.data.vertices))
    base.name = "ChildMPFBBaseMesh"

    # Hide any helper mesh objects created alongside the base human.
    for obj in created_meshes:
        if obj != base:
            obj.hide_render = True
            obj.hide_set(True)

    return base, {
        "api": "bpy.ops.mpfb.create_human",
        "module": module_name,
        "created_mesh_count": len(created_meshes),
        "base_vertices": len(base.data.vertices),
    }


def auto_frame(scene, cam, target, obj, margin=0.10):
    mins, maxs, corners = evaluated_bounds(obj)
    center = (mins + maxs) * 0.5
    target.location = center
    cam.location = Vector((center.x, mins.y - 2.2, center.z + 0.02))

    for _ in range(100):
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, cam, p) for p in corners]
        xs = [p.x for p in projected]
        ys = [p.y for p in projected]
        zs = [p.z for p in projected]

        if (
            min(xs) >= margin
            and max(xs) <= 1.0 - margin
            and min(ys) >= margin
            and max(ys) <= 1.0 - margin
            and min(zs) > 0.0
        ):
            return {
                "x_min": float(min(xs)),
                "x_max": float(max(xs)),
                "y_min": float(min(ys)),
                "y_max": float(max(ys)),
                "z_min": float(min(zs)),
            }

        cam.location.y -= 0.10

    raise RuntimeError("MPFB child could not be auto-framed")


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

    base, applied = create_mpfb_basemesh()
    normalize_height(base, 1.60)
    childify_basemesh(base)

    skin = principled("ChildSkin", (0.64, 0.38, 0.31), 0.82)
    base.data.materials.clear()
    base.data.materials.append(skin)

    subdiv = (
        base.modifiers.get("LookdevSubdivision")
        or base.modifiers.new("LookdevSubdivision", "SUBSURF")
    )
    subdiv.levels = 1
    subdiv.render_levels = 2

    ground_mat = principled("Ground", (0.055, 0.040, 0.032), 0.96)
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(ground_mat)

    bpy.ops.object.light_add(type="AREA", location=(2.8, -1.6, 3.0))
    key = bpy.context.object
    key.data.energy = 430
    key.data.color = (1.0, 0.36, 0.16)
    key.data.size = 2.8

    bpy.ops.object.light_add(type="AREA", location=(-2.0, -3.2, 2.2))
    fill = bpy.context.object
    fill.data.energy = 360
    fill.data.color = (0.58, 0.72, 1.0)
    fill.data.size = 2.5

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
        f"VIDEO_CREATOR_MPFB_CHILD_FRAMING_PASS "
        f"framing={framing} props={applied}",
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
        raise RuntimeError("MPFB child render missing or unexpectedly small")

    print(
        f"VIDEO_CREATOR_CHILD_LOOKDEV_V5_PASS output={output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
