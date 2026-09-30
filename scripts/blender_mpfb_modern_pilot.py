"""Render the P47-08 MPFB modern-character single-shot quality gate."""

from __future__ import annotations

import importlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments() -> tuple[Path, Path]:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(values) != 2:
        raise ValueError("expected PROJECT OUTPUT_DIR")
    return Path(values[0]).resolve(), Path(values[1]).resolve()


def material(name: str, color: tuple[float, float, float], *, roughness: float = 0.62, metallic: float = 0.0):
    value = bpy.data.materials.new(name)
    value.use_fake_user = True
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return value


def enable_mpfb():
    repos = getattr(getattr(bpy.context.preferences, "extensions", None), "repos", [])
    module = next((f"bl_ext.{repo.module}.mpfb" for repo in repos if (Path(str(repo.directory)) / "mpfb/blender_manifest.toml").is_file()), "")
    if not module:
        raise RuntimeError("MPFB extension is not installed")
    if module not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module=module)
    if module not in bpy.context.preferences.addons:
        raise RuntimeError("MPFB extension could not be enabled")
    return module


def create_human(module: str):
    scene = bpy.context.scene
    settings = {
        "add_phenotype": True,
        "phenotype_gender": "male",
        "phenotype_age": "young",
        "phenotype_muscle": "minmuscle",
        "phenotype_weight": "averageweight",
        "phenotype_height": "average",
        "phenotype_proportions": "average",
        "phenotype_race": "asian",
        "phenotype_influence": 1.0,
        "add_breast": False,
        "scale_factor": "METER",
        "mask_helpers": True,
        "detailed_helpers": True,
        "extra_vertex_groups": True,
    }
    for key, value in settings.items():
        name = "MPFB_NH_" + key
        if not hasattr(scene, name):
            raise RuntimeError(f"MPFB setting is unavailable: {name}")
        setattr(scene, name, value)
    before = set(bpy.data.objects)
    result = bpy.ops.mpfb.create_human()
    if "FINISHED" not in result:
        raise RuntimeError(f"MPFB human creation failed: {result}")
    candidates = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]
    body = max(candidates, key=lambda obj: len(obj.data.vertices))
    for obj in candidates:
        if obj != body:
            obj.hide_render = True
            obj.hide_set(True)
    body.name = "ChenHao_MPFB_Body"
    skin = material("ChenHao_Skin", (0.50, 0.29, 0.21), roughness=0.74)
    body.data.materials.clear()
    body.data.materials.append(skin)
    human_service = importlib.import_module(module + ".services.humanservice").HumanService
    # The default MakeHuman rig has native hand, eye, lid, jaw and facial
    # muscle controls.  P47-08 is a close performance test, so the smaller
    # game-engine skeleton used by earlier control shots is not sufficient.
    rig = human_service.add_builtin_rig(body, "default", import_weights=True)
    if rig is None:
        raise RuntimeError("MPFB default face rig could not be created")
    rig.name = "ChenHao_MPFB_DefaultFaceRig"
    return body, rig, settings, human_service


def mesh_bounds(obj) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return Vector(tuple(min(p[i] for p in points) for i in range(3))), Vector(tuple(max(p[i] for p in points) for i in range(3)))


def garment(body, rig, name: str, keep, mat, thickness: float = 0.008):
    vertices = [tuple(vertex.co) for vertex in body.data.vertices]
    body_group = body.vertex_groups.get("body")
    visible_vertices = set()
    if body_group is not None:
        for vertex in body.data.vertices:
            if any(item.group == body_group.index and item.weight > 0.5 for item in vertex.groups):
                visible_vertices.add(vertex.index)
    faces = []
    for polygon in body.data.polygons:
        center = body.matrix_world @ polygon.center
        # MPFB stores skirt, tights, genital, teeth and other fitting helpers
        # inside the base mesh.  The body modifier masks them, so garment
        # extraction must also restrict itself to the actual visible body.
        is_visible_body = not visible_vertices or all(index in visible_vertices for index in polygon.vertices)
        if is_visible_body and keep(center):
            faces.append(tuple(polygon.vertices))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.matrix_world = body.matrix_world.copy()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    for source_group in body.vertex_groups:
        target_group = obj.vertex_groups.new(name=source_group.name)
        for vertex in body.data.vertices:
            assignment = next((item for item in vertex.groups if item.group == source_group.index), None)
            if assignment is not None and assignment.weight > 0:
                target_group.add([vertex.index], assignment.weight, "REPLACE")
    armature = obj.modifiers.new("MPFB weights", "ARMATURE")
    armature.object = rig
    solidify = obj.modifiers.new("Fabric thickness", "SOLIDIFY")
    solidify.thickness = thickness
    solidify.offset = 1.0
    return obj, len(faces)


def rounded_box(name, location, scale, mat, bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel_mod = obj.modifiers.new("Soft edges", "BEVEL")
    bevel_mod.width = bevel
    bevel_mod.segments = 3
    obj.data.materials.append(mat)
    return obj


def parent_to_bone(obj, rig, bone: str):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    world = obj.matrix_world.copy()
    obj.parent = rig
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_world = world


def image_material(
    name: str,
    image_path: Path,
    *,
    roughness: float = .68,
    use_alpha: bool = False,
    normal_path: Path | None = None,
    subsurface: float = 0.0,
):
    value = bpy.data.materials.new(name)
    value.use_fake_user = True
    value.use_nodes = True
    nodes = value.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = roughness
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(image_path), check_existing=True)
    value.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    if "Subsurface Weight" in shader.inputs:
        shader.inputs["Subsurface Weight"].default_value = subsurface
    if normal_path and normal_path.is_file():
        normal_texture = nodes.new("ShaderNodeTexImage")
        normal_texture.image = bpy.data.images.load(str(normal_path), check_existing=True)
        normal_texture.image.colorspace_settings.name = "Non-Color"
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.inputs["Strength"].default_value = .45
        value.node_tree.links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
        value.node_tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
    if use_alpha:
        value.node_tree.links.new(texture.outputs["Alpha"], shader.inputs["Alpha"])
        if hasattr(value, "surface_render_method"):
            value.surface_render_method = "DITHERED"
    return value


def add_mhclo(human_service, body, path: Path, asset_type: str):
    before = {obj.name for obj in bpy.data.objects}
    human_service.add_mhclo_asset(
        str(path),
        body,
        asset_type=asset_type,
        subdiv_levels=1 if asset_type.lower() in {"hair", "eyes"} else 0,
        material_type="MAKESKIN",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    created = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]
    if not created:
        raise RuntimeError(f"MPFB did not create {asset_type}: {path.name}")
    return created


def add_look(body, rig, human_service, asset_root: Path):
    lo, hi = mesh_bounds(body)
    height = hi.z - lo.z
    leather = material("ChenHao_Shoes", (0.025, 0.022, 0.021), roughness=0.42)
    screen = material("PhoneScreen", (0.045, 0.18, 0.25), roughness=0.28, metallic=0.15)
    skin_texture = asset_root / "skins/young_asian_male/young_lightskinned_male_diffuse3.png"
    body.data.materials.clear()
    body.data.materials.append(image_material("ChenHao_AsianSkin", skin_texture, roughness=.63, subsurface=.055))
    suit = add_mhclo(human_service, body, asset_root / "clothes/male_casualsuit01/male_casualsuit01.mhclo", "Clothes")
    shoes = add_mhclo(human_service, body, asset_root / "clothes/shoes01/shoes01.mhclo", "Clothes")
    hair = add_mhclo(human_service, body, asset_root / "hair/short04/short04.mhclo", "Hair")
    eyes = add_mhclo(human_service, body, asset_root / "eyes/high-poly/high-poly.mhclo", "Eyes")
    suit_mat = image_material(
        "ChenHao_CasualSuit",
        asset_root / "clothes/male_casualsuit01/male_casualsuit01_diffuse.png",
        roughness=.68,
        normal_path=asset_root / "clothes/male_casualsuit01/male_casualsuit01_normal.png",
    )
    shoe_mat = image_material(
        "ChenHao_FormalShoes",
        asset_root / "clothes/shoes01/shoes01_diffuse.png",
        roughness=.46,
        normal_path=asset_root / "clothes/shoes01/shoes01_normal.png",
    )
    hair_mat = image_material("ChenHao_ShortHair", asset_root / "hair/short04/short04_diffuse.png", roughness=.52, use_alpha=True)
    eye_mat = image_material("ChenHao_BrownEyes", asset_root / "eyes/materials/brown_eye.png", roughness=.32, use_alpha=True)
    for objects, replacement in ((suit, suit_mat), (shoes, shoe_mat), (hair, hair_mat), (eyes, eye_mat)):
        for obj in objects:
            obj.data.materials.clear()
            obj.data.materials.append(replacement)
    # The previous pilot forced both arms through hand-written IK targets.  The
    # targets collapsed the shoulders and made the phone float.  Keep the
    # anatomically authored rest pose and bind the prop to the native wrist.
    wrist = rig.data.bones.get("wrist.L")
    if wrist is None:
        raise RuntimeError("MPFB default rig wrist is missing")
    wrist_world = rig.matrix_world @ wrist.center
    phone = rounded_box(
        "ChenHao_Phone",
        tuple(wrist_world + Vector((height*.018, -height*.018, height*.042))),
        (height*.030, height*.008, height*.055),
        leather,
        bevel=height*.006,
    )
    phone.data.materials.append(screen)
    phone.data.polygons[0].material_index = 1
    return {
        "height": height,
        "lo_z": lo.z,
        "assets": [obj.name for obj in suit + shoes + hair + eyes],
        "phone": phone,
    }


def key_rotation(bone, frame: int, xyz):
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = xyz
    bone.keyframe_insert(data_path="rotation_euler", frame=frame, group="P47-08 Acting")


def animate(rig, look):
    scene = bpy.context.scene
    # A restrained performance reads better than broad procedural gesturing:
    # read the phone, register the message, lift the eye line, then tighten the
    # fingers around the prop.  Every rotation stays within a few degrees of
    # the native anatomical pose.
    for frame, torso, head, wrist, jaw, eye, arm_delta in (
        (1,   (0, 0, math.radians(-1)), (math.radians(6), 0, math.radians(-2)), (0, 0, math.radians(-2)), math.radians(-2.4), math.radians(-2), 0),
        (36,  (math.radians(1), 0, math.radians(-1)), (math.radians(8), 0, math.radians(-1)), (math.radians(2), 0, math.radians(-1)), math.radians(-2.4), math.radians(-2), math.radians(1)),
        (72,  (0, 0, 0), (math.radians(2), math.radians(-2), 0), (math.radians(-2), 0, math.radians(3)), math.radians(-1.0), 0, math.radians(2)),
        (108, (math.radians(-1), 0, math.radians(1)), (math.radians(-4), math.radians(-3), math.radians(2)), (math.radians(-3), 0, math.radians(5)), math.radians(-1.5), math.radians(2), math.radians(1)),
        (144, (0, 0, math.radians(1)), (math.radians(-2), math.radians(-2), math.radians(1)), (math.radians(-2), 0, math.radians(4)), math.radians(-2.2), math.radians(1), 0),
    ):
        scene.frame_set(frame)
        key_rotation(rig.pose.bones["spine04"], frame, torso)
        key_rotation(rig.pose.bones["head"], frame, head)
        key_rotation(rig.pose.bones["wrist.L"], frame, wrist)
        key_rotation(rig.pose.bones["jaw"], frame, (jaw, 0, 0))
        key_rotation(rig.pose.bones["eye.L"], frame, (eye, 0, 0))
        key_rotation(rig.pose.bones["eye.R"], frame, (eye, 0, 0))
        key_rotation(rig.pose.bones["upperarm01.L"], frame, (0, 0, math.radians(-38) + arm_delta))
        key_rotation(rig.pose.bones["upperarm01.R"], frame, (0, 0, math.radians(38) - arm_delta*.35))
        curl = math.radians(12 if frame < 60 else 34)
        for name in (
            "finger2-1.L", "finger2-2.L", "finger3-1.L", "finger3-2.L",
            "finger4-1.L", "finger4-2.L", "finger5-1.L", "finger5-2.L",
        ):
            key_rotation(rig.pose.bones[name], frame, (curl, 0, 0))
    # Follow the deformed wrist at the same acting beats.  Explicit world-space
    # keys avoid Blender's bone-parent inverse ambiguity while keeping the prop
    # locked to the palm throughout this short gate shot.
    for frame in (1, 36, 72, 108, 144):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        wrist_world = rig.matrix_world @ rig.pose.bones["wrist.L"].head
        look["phone"].location = wrist_world + Vector((-look["height"]*.005, -look["height"]*.030, look["height"]*.034))
        look["phone"].keyframe_insert(data_path="location", frame=frame, group="P47-08 Phone Lock")
    scene.frame_set(1)


def add_environment(height: float):
    wall = material("OfficeWall", (0.32, 0.37, 0.42), roughness=.9)
    wood = material("DeskWood", (0.22, 0.10, 0.055), roughness=.7)
    window = material("WindowBlue", (0.12, 0.26, 0.36), roughness=.32, metallic=.05)
    rounded_box("OfficeBackWall", (0, .70, height*.78), (height*1.1, .05, height*.78), wall, bevel=.01)
    rounded_box("OfficeDesk", (0, -.42, height*.34), (height*.52, height*.16, height*.025), wood, bevel=.025)
    rounded_box("OfficeWindow", (-height*.52, .62, height*.91), (height*.28, .02, height*.32), window, bevel=.012)
    for x in (-height*.52,):
        rounded_box("WindowFrameV", (x, .59, height*.91), (.012, .018, height*.32), wall, bevel=.004)
        rounded_box("WindowFrameH", (x, .59, height*.91), (height*.28, .018, .012), wall, bevel=.004)


def configure_scene(output: Path, height: float):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 480
    scene.render.resolution_y = 854
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 144
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.world = bpy.data.worlds.new("P47_08_World")
    scene.world.color = (0.012, 0.018, 0.028)
    scene.view_settings.look = "AgX - Medium High Contrast"
    bpy.ops.object.camera_add(location=(height*.13, -height*1.72, height*.69))
    camera = bpy.context.object
    target = Vector((0, -height*.03, height*.69))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 72
    scene.camera = camera
    camera.keyframe_insert(data_path="location", frame=1, group="P47-08 Camera")
    camera.location.y += height*.08
    camera.keyframe_insert(data_path="location", frame=144, group="P47-08 Camera")
    for name, location, energy, color, size in (
        ("Key", (-height*1.1, -height*1.4, height*1.55), 155, (1.0, .76, .62), height*.9),
        ("Fill", (height*1.2, -height*.8, height*1.1), 62, (.52, .70, 1.0), height*.8),
        ("Rim", (0, height*.9, height*1.45), 180, (.66, .78, 1.0), height*.6),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.color = color
        light.data.shape = "DISK"
        light.data.size = size
        light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(output / "frames/frame_")


def render(output: Path):
    frames = output / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.frame_set(72)
    scene.render.filepath = str(output / "poster.png")
    bpy.ops.render.render(write_still=True)
    if os.environ.get("VIDEO_CREATOR_POSTER_ONLY") == "1":
        return
    scene.render.filepath = str(frames / "frame_")
    bpy.ops.render.render(animation=True)
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    subprocess.run([
        ffmpeg, "-y", "-framerate", "24", "-start_number", "1", "-i", str(frames / "frame_%04d.png"),
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output / "performance.mp4")
    ], check=True, timeout=240)


def main():
    project, output = arguments()
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    module = enable_mpfb()
    body, rig, settings, human_service = create_human(module)
    asset_root = project / "production/assets/characters/makehuman-system-cc0"
    if not (asset_root / "asset-manifest.json").is_file():
        raise RuntimeError("P47-08 MakeHuman system assets are not installed")
    look = add_look(body, rig, human_service, asset_root)
    add_environment(look["height"])
    animate(rig, look)
    configure_scene(output, look["height"])
    render(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "performance.blend"))
    report = {
        "schema_version": 1,
        "task": "P47-08",
        "status": "TECHNICAL_PASS_VISUAL_PENDING",
        "base": "MPFB native Asian young male",
        "rig": "MPFB default native face/hand rig and native weights",
        "body_vertices": len(body.data.vertices),
        "rig_bones": len(rig.data.bones),
        "duration_seconds": 6.0,
        "resolution": [480, 854],
        "fps": 24,
        "fitted_assets": look["assets"],
        "asset_manifest": str((asset_root / "asset-manifest.json").relative_to(project)),
        "performance": {
            "features": ["phone read", "head lift", "eye-line change", "jaw reaction", "left-hand grip"],
            "contact_pass": True,
            "contact_note": "Phone transform is keyed from the native left-wrist position at every acting beat.",
        },
        "face_limit": "Native eye and jaw controls are exercised; phoneme lip sync remains outside this single-shot gate.",
        "local_only": True,
        "billable": False,
        "images_uploaded": False,
        "human_review": "PENDING",
        "expansion_allowed": False,
        "limits": [
            "Generic MPFB identity is not the approved Chen Hao character design.",
            "Native jaw and eye controls are present, but production lip sync has not been authored.",
            "Story expansion remains locked until the Web visual review is explicitly passed.",
        ],
        "mpfb_settings": settings,
    }
    (output / "performance-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("P47_08_MFPB_PILOT_PASS " + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
