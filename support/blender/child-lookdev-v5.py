import argparse
import importlib
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


def discover_mpfb_root():
    candidates = set()

    for module_name in list(sys.modules):
        parts = module_name.split(".")
        if "mpfb" in parts:
            index = parts.index("mpfb")
            candidates.add(".".join(parts[:index + 1]))

    try:
        for addon_key in bpy.context.preferences.addons.keys():
            parts = str(addon_key).split(".")
            if "mpfb" in parts:
                index = parts.index("mpfb")
                candidates.add(".".join(parts[:index + 1]))
    except Exception:
        pass

    # Known Blender extension package form; harmless if unavailable.
    candidates.update({"bl_ext.blender_org.mpfb", "mpfb"})

    errors = []
    for root in sorted(candidates, key=len, reverse=True):
        try:
            importlib.import_module(root)
            return root
        except Exception as error:
            errors.append(f"{root}: {error}")

    raise RuntimeError("MPFB root package not importable: " + " | ".join(errors))


def dynamic_import(module_suffix, symbol):
    root = discover_mpfb_root()
    relative = module_suffix
    if relative.startswith("mpfb."):
        relative = relative[len("mpfb."):]
    module_name = f"{root}.{relative}"
    module = importlib.import_module(module_name)
    if not hasattr(module, symbol):
        raise RuntimeError(f"MPFB symbol unavailable: {module_name}.{symbol}")
    return getattr(module, symbol)


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
        raise RuntimeError("MPFB child basemesh has invalid height")
    factor = target_height / height
    obj.scale *= factor
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    mins, maxs, _ = evaluated_bounds(obj)
    obj.location.z -= mins.z
    bpy.context.view_layer.update()


def auto_frame(scene, cam, target, obj, margin=0.10):
    mins, maxs, corners = evaluated_bounds(obj)
    center = (mins + maxs) * 0.5
    target.location = center
    cam.location = Vector((center.x, mins.y - 2.2, center.z + 0.02))
    for _ in range(80):
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, cam, p) for p in corners]
        xs = [p.x for p in projected]
        ys = [p.y for p in projected]
        zs = [p.z for p in projected]
        if (
            min(xs) >= margin and max(xs) <= 1.0-margin
            and min(ys) >= margin and max(ys) <= 1.0-margin
            and min(zs) > 0.0
        ):
            return {
                "x_min": float(min(xs)),
                "x_max": float(max(xs)),
                "y_min": float(min(ys)),
                "y_max": float(max(ys)),
                "z_min": float(min(zs)),
            }
        cam.location.y -= 0.12
    raise RuntimeError("MPFB child could not be auto-framed")


def create_mpfb_child():
    # MPFB Blender extensions are installed under a runtime-specific package prefix,
    # so use the same dynamic-import pattern as MPFB's official scripting samples.
    HumanService = dynamic_import("mpfb.services.humanservice", "HumanService")
    TargetService = dynamic_import("mpfb.services.targetservice", "TargetService")

    macro = TargetService.get_default_macro_info_dict()
    # MPFB macro ranges are numeric: gender 0=female, 1=male; age 0=child, 1=old.
    macro["gender"] = 0.0
    macro["age"] = 0.0
    macro["muscle"] = 0.15
    macro["weight"] = 0.45
    macro["proportions"] = 0.35
    macro["height"] = 0.20
    macro["cupsize"] = 0.0
    macro["firmness"] = 0.50
    macro["race"] = {
        "asian": 1.0,
        "caucasian": 0.0,
        "african": 0.0,
    }

    base = HumanService.create_human(
        mask_helpers=True,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=0.1,
        macro_detail_dict=macro,
    )
    if base is None or base.type != "MESH":
        raise RuntimeError("MPFB HumanService.create_human returned no basemesh")

    base.name = "ChildMPFBBaseMesh"
    applied = {
        "api": "HumanService.create_human",
        "gender": macro["gender"],
        "age": macro["age"],
        "muscle": macro["muscle"],
        "weight": macro["weight"],
        "proportions": macro["proportions"],
        "height": macro["height"],
        "race": dict(macro["race"]),
    }
    return base, applied


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

    base, applied = create_mpfb_child()
    normalize_height(base, 1.34)

    skin = principled("ChildSkin", (0.64, 0.38, 0.31), 0.82)
    base.data.materials.clear()
    base.data.materials.append(skin)

    # Add subdivision without destroying the real MPFB topology.
    subdiv = base.modifiers.get("LookdevSubdivision") or base.modifiers.new("LookdevSubdivision", "SUBSURF")
    subdiv.levels = 1
    subdiv.render_levels = 2

    # Simple floor only. V5 is a basemesh proof, not costume approval.
    ground_mat = principled("Ground", (0.055,0.040,0.032), 0.96)
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0,0,0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(ground_mat)

    bpy.ops.object.light_add(type="AREA", location=(2.8,-1.6,3.0))
    key = bpy.context.object
    key.data.energy = 430
    key.data.color = (1.0,0.36,0.16)
    key.data.size = 2.8

    bpy.ops.object.light_add(type="AREA", location=(-2.0,-3.2,2.2))
    fill = bpy.context.object
    fill.data.energy = 360
    fill.data.color = (0.58,0.72,1.0)
    fill.data.size = 2.5

    target = bpy.data.objects.new("LookdevTarget", None)
    bpy.context.collection.objects.link(target)

    bpy.ops.object.camera_add(location=(0,-4,1))
    cam = bpy.context.object
    cam.data.lens = 72
    cam.data.sensor_width = 36.0
    track = cam.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam

    framing = auto_frame(scene, cam, target, base, margin=0.10)
    print(f"VIDEO_CREATOR_MPFB_CHILD_FRAMING_PASS framing={framing} props={applied}")

    output = Path(args.output).expanduser().resolve()
    blend = Path(args.blend_output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    blend.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size < 30000:
        raise RuntimeError("MPFB child render missing or unexpectedly small")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V5_PASS output={output}")


if __name__ == "__main__":
    main()
