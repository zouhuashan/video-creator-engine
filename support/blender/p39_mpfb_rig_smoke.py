"""Build a local MPFB + Rigify humanoid feasibility asset for P39."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]


def args_after_separator():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    result = {"project": None, "character_id": "CHR-N0DBC8F583-AUTO-001"}
    index = 0
    while index < len(values):
        key = values[index]
        if key == "--project":
            result["project"] = Path(values[index + 1]).expanduser().resolve()
            index += 2
        elif key == "--character-id":
            result["character_id"] = values[index + 1]
            index += 2
        else:
            raise ValueError(f"unknown argument: {key}")
    if result["project"] is None:
        raise ValueError("--project is required")
    return result


def ensure_mpfb():
    if "bl_ext.blender_org.mpfb" not in bpy.context.preferences.addons:
        repos = getattr(getattr(bpy.context.preferences, "extensions", None), "repos", [])
        candidates = []
        for repo in repos:
            package = Path(str(repo.directory)).expanduser() / "mpfb"
            if package.is_dir() and (package / "blender_manifest.toml").is_file():
                candidates.append(f"bl_ext.{repo.module}.mpfb")
        for module in candidates:
            bpy.ops.preferences.addon_enable(module=module)
            if module in bpy.context.preferences.addons:
                break
    if not any(module.endswith(".mpfb") for module in bpy.context.preferences.addons.keys()):
        raise RuntimeError("MPFB extension is unavailable")
    if "rigify" not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module="rigify")
    if "rigify" not in bpy.context.preferences.addons:
        raise RuntimeError("Rigify could not be enabled")
    scene = bpy.context.scene
    settings = {
        "add_phenotype": True,
        "phenotype_gender": "male",
        "phenotype_age": "young",
        "phenotype_muscle": "averagemuscle",
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
    applied = {}
    for key, value in settings.items():
        name = "MPFB_NH_" + key
        if not hasattr(scene, name):
            raise RuntimeError(f"MPFB New Human property missing: {name}")
        setattr(scene, name, value)
        if getattr(scene, name) != value:
            raise RuntimeError(f"MPFB property rejected {name}={value}")
        applied[name] = value
    return applied


def bounds(obj):
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))), Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))


def make_material(name, color, *, metallic=0.0, roughness=0.72):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return material


def mesh_object(name, vertices, faces, material):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj


def ring_shell(name, profiles, material, sides=32):
    vertices = []
    faces = []
    for z, radius_x, radius_y in profiles:
        for index in range(sides):
            angle = 2.0 * 3.141592653589793 * index / sides
            vertices.append((radius_x * __import__("math").sin(angle), -radius_y * __import__("math").cos(angle), z))
    for row in range(len(profiles) - 1):
        for index in range(sides):
            a = row * sides + index
            b = row * sides + (index + 1) % sides
            c = b + sides
            d = a + sides
            faces.append((a, b, c, d))
    return mesh_object(name, vertices, faces, material)


def sleeve_mesh(name, sign, start, end, radius_start, radius_end, material, *, bands=8, sides=16):
    start_v, end_v = Vector(start), Vector(end)
    axis = (end_v - start_v).normalized()
    across = Vector((0.0, 1.0, 0.0))
    if abs(axis.dot(across)) > 0.95:
        across = Vector((0.0, 0.0, 1.0))
    across = (across - axis * axis.dot(across)).normalized()
    depth = axis.cross(across).normalized()
    vertices, faces = [], []
    for ring in range(bands + 1):
        amount = ring / bands
        center = start_v.lerp(end_v, amount)
        radius = radius_start + (radius_end - radius_start) * amount
        for index in range(sides):
            angle = 2.0 * 3.141592653589793 * index / sides
            point = center + across * (__import__("math").cos(angle) * radius) + depth * (__import__("math").sin(angle) * radius)
            vertices.append(tuple(point))
    for row in range(bands):
        for index in range(sides):
            a = row * sides + index
            b = row * sides + (index + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    return mesh_object(name, vertices, faces, material)


def add_hanfu_lookdev(rig, body, character_id):
    """Codex-authored procedural hair, layered robe, sleeves, cuffs, sash and face accents."""
    dark = make_material("LuZhao_NightIndigo", (0.035, 0.055, 0.105))
    inner = make_material("LuZhao_Ivory", (0.66, 0.66, 0.59))
    trim = make_material("LuZhao_AgedGold", (0.52, 0.29, 0.075), metallic=0.55, roughness=0.42)
    hair = make_material("LuZhao_InkHair", (0.018, 0.022, 0.032), roughness=0.5)
    skin = make_material("LuZhao_Skin", (0.54, 0.34, 0.28), roughness=0.82)
    eye = make_material("LuZhao_Eye", (0.025, 0.018, 0.02), roughness=0.35)
    body.data.materials.clear()
    body.data.materials.append(skin)
    body.data.materials.append(dark)
    # Tint the relaxed arms as part of the robe sleeves. This reuses the
    # character mesh, so fabric stays attached to elbows and wrists without
    # loose, unrigged sleeve geometry.
    for polygon in body.data.polygons:
        center = body.matrix_world @ polygon.center
        polygon.material_index = 1 if 0.20 < abs(center.x) < 0.59 and 0.88 < center.z < 1.40 else 0

    garments = [
        ring_shell("LuZhao_LongRobe", [(0.10, .43, .26), (.30, .39, .24), (.62, .31, .20), (.92, .25, .17), (1.18, .27, .17), (1.40, .31, .18)], dark),
        ring_shell("LuZhao_Belt", [(.91, .255, .178), (.94, .265, .184), (1.00, .255, .178), (1.03, .245, .174)], trim),
    ]
    # Ivory center panel follows the front (-Y) of the robe.
    panel_vertices = [(-.115, -.268, .12), (.115, -.268, .12), (.09, -.214, 1.34), (-.09, -.214, 1.34)]
    garments.append(mesh_object("LuZhao_IvoryFrontPanel", panel_vertices, [(0, 1, 2, 3)], inner))
    # Crossed collar lapels in the reference outfit.
    garments.append(mesh_object("LuZhao_CrossCollar", [(-.17,-.206,1.39),(-.055,-.246,1.39),(.16,-.205,1.17),(.07,-.215,1.10)], [(0,1,2,3)], inner))
    garments.append(mesh_object("LuZhao_InnerCollar", [(.17,-.206,1.39),(.055,-.247,1.39),(-.13,-.215,1.18),(-.06,-.217,1.11)], [(0,1,2,3)], dark))

    # Simple hair cap, tied crown and long rear lock. All are actual 3D meshes.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, location=(0.0, 0.025, 1.56))
    cap = bpy.context.object
    cap.name = "LuZhao_HairCap"
    cap.scale = (.145, .132, .175)
    cap.data.materials.append(hair)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=(0.0, .04, 1.72))
    knot = bpy.context.object
    knot.name = "LuZhao_TopKnot"
    knot.scale = (.068, .065, .115)
    knot.data.materials.append(hair)
    garments.extend((cap, knot))
    # Face accents are intentionally restrained at this feasibility stage.
    for side, label in ((-1, "L"), (1, "R")):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, location=(side*.052, -.145, 1.535))
        eye_obj = bpy.context.object
        eye_obj.name = f"LuZhao_Eye_{label}"
        eye_obj.scale = (.021, .012, .010)
        eye_obj.data.materials.append(eye)
        garments.append(eye_obj)

    # Keep the generated lookdev pieces in world scale and parent them to the
    # actor root. Joint deformation is a later iteration; root blocking remains shared.
    for obj in garments:
        world = obj.matrix_world.copy()
        obj.parent = rig
        obj.matrix_world = world
        # Blender's primitive add operator can leave the second eye at unit
        # scale when the active object changes between iterations. Set eye
        # geometry by world dimensions after parenting so a single accent
        # cannot cover the whole character.
        if obj.name.startswith("LuZhao_Eye_"):
            obj.dimensions = (0.042, 0.024, 0.020)
            bpy.context.view_layer.update()
            if max(obj.dimensions) > 0.06:
                raise RuntimeError(f"face accent has unexpected dimensions: {obj.name} {tuple(obj.dimensions)}")
        obj["character_id"] = character_id
        obj["lookdev_source"] = "CODEX_PROCEDURAL_HANFU_AND_HAIR"
    return len(garments)


def make_preview(project, base, rig, output, video_output):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("P39PreviewWorld")
    scene.world.color = (0.025, 0.035, 0.06)
    # Keep the Codex-authored skin, indigo fabric, ivory lining and gold trim.
    bpy.ops.object.camera_add(location=(3.2, -5.8, 2.55))
    camera = bpy.context.object
    camera.name = "P39PreviewCamera"
    direction = Vector((0.0, 0.0, 0.95)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 2.35
    scene.camera = camera
    bpy.ops.object.light_add(type="AREA", location=(-3.5, -4.0, 4.5))
    key = bpy.context.object
    key.data.energy = 500
    key.data.shape = "DISK"
    key.data.size = 4.0
    bpy.ops.object.light_add(type="AREA", location=(2.8, 2.0, 3.2))
    rim = bpy.context.object
    rim.data.energy = 650
    rim.data.size = 3.0
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    scene.frame_start = 1
    scene.frame_end = 49
    scene.render.fps = 24
    scene.render.resolution_percentage = 50
    scene.render.image_settings.file_format = "PNG"
    frame_prefix = video_output.with_suffix("")
    scene.render.filepath = str(frame_prefix) + "_"
    bpy.ops.render.render(animation=True)
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    if not Path(ffmpeg).is_file():
        raise RuntimeError("ffmpeg is required to package the local Rigify walk preview")
    subprocess.run([
        ffmpeg, "-y", "-framerate", "24", "-start_number", "1", "-i",
        str(frame_prefix) + "_%04d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(video_output),
    ], check=True, capture_output=True, text=True, timeout=120)
    for frame_file in video_output.parent.glob(video_output.stem + "_*.png"):
        frame_file.unlink(missing_ok=True)


def add_actor_motion_test(rig):
    scene = bpy.context.scene
    controls = {bone.name: bone for bone in rig.pose.bones}
    required = ("root", "foot_ik.L", "foot_ik.R", "upper_arm_fk.L", "upper_arm_fk.R")
    missing = [name for name in required if name not in controls]
    if missing:
        raise RuntimeError("Rigify walk controls missing: " + ", ".join(missing))
    cycle = ((1, -0.10, 0.0, 0.10), (13, 0.10, 0.14, 0.0), (25, -0.10, 0.0, 0.14), (37, 0.10, 0.14, 0.0), (49, 0.0, 0.0, 0.0))
    for frame, stride, left_lift, right_lift in cycle:
        scene.frame_set(frame)
        rig.location.x = 0.16 * (frame - 1) / 48.0
        rig.keyframe_insert(data_path="location", frame=frame, group="Walk Test")
        root = controls["root"]
        root.location = (0.08 * (frame - 1) / 48.0, 0.0, 0.0)
        root.keyframe_insert(data_path="location", frame=frame, group="Walk Test")
        for name, lift, offset in (("foot_ik.L", left_lift, stride), ("foot_ik.R", right_lift, -stride)):
            control = controls[name]
            control.location = (0.0, offset, lift)
            control.keyframe_insert(data_path="location", frame=frame, group="Walk Test")
        swing = 0.10 if (frame // 12) % 2 else -0.10
        for name, angle in (("upper_arm_fk.L", -swing), ("upper_arm_fk.R", swing)):
            control = controls[name]
            control.rotation_mode = "XYZ"
            control.rotation_euler.z = angle
            control.keyframe_insert(data_path="rotation_euler", frame=frame, group="Walk Test")
    scene.frame_set(1)


def main():
    config = args_after_separator()
    project = config["project"]
    character_id = config["character_id"]
    output_dir = project / "lookdev" / "3d-rigs" / character_id
    output_dir.mkdir(parents=True, exist_ok=True)
    blend_path = output_dir / "p39-mpfb-rigify-smoke-v6.blend"
    image_path = output_dir / "p39-rig-preview-v6.png"
    video_path = output_dir / "p39-rig-motion-v6.mp4"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene_settings = ensure_mpfb()
    before = set(bpy.data.objects.keys())
    result = bpy.ops.mpfb.create_human()
    if "FINISHED" not in result:
        raise RuntimeError(f"MPFB create_human failed: {result}")
    created = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]
    if not created:
        created = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if not created:
        raise RuntimeError("MPFB did not create a body mesh")
    base = max(created, key=lambda obj: len(obj.data.vertices))
    for obj in created:
        if obj != base:
            obj.hide_render = True
            obj.hide_set(True)
    base.name = "P39_MPFB_AsianMale_Body"
    base.data.name = "P39_MPFB_AsianMale_Mesh"
    base["character_id"] = character_id
    base["lookdev_source"] = "MPFB Asian male baseline; Codex generated the controlling art brief"
    lo, hi = bounds(base)
    height = hi.z - lo.z
    if len(base.data.vertices) < 5000 or not 1.2 <= height <= 2.3:
        raise RuntimeError(f"unexpected MPFB body dimensions: vertices={len(base.data.vertices)}, height={height:.3f}")

    bpy.ops.object.armature_human_metarig_add()
    metarig = bpy.context.object
    metarig.name = "P39_Rigify_Metarig"
    rig_points = [point for bone in metarig.data.bones for point in (bone.head_local, bone.tail_local)]
    rig_bottom = min(point.z for point in rig_points)
    rig_top = max(point.z for point in rig_points)
    rig_height = rig_top - rig_bottom
    scale = height / rig_height
    metarig.scale = (scale, scale, scale)
    metarig.location = ((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z - rig_bottom * scale)
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    metarig.select_set(True)
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.pose.rigify_generate()
    rig = bpy.context.object
    if rig.type != "ARMATURE" or rig == metarig:
        rig = next((obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj != metarig), None)
    if rig is None:
        raise RuntimeError("Rigify did not generate a usable control rig")
    rig.name = "P39_Rigify_ControlRig"
    metarig.hide_render = True
    metarig.hide_set(True)
    bpy.ops.object.select_all(action="DESELECT")
    base.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    modifiers = [mod for mod in base.modifiers if mod.type == "ARMATURE" and mod.object == rig]
    if not modifiers:
        raise RuntimeError("Rigify control rig was not bound to the MPFB body")
    deform_bones = [bone for bone in rig.data.bones if bone.use_deform]
    groups = {group.name: group for group in base.vertex_groups}
    weighted = {vertex.index for vertex in base.data.vertices if any(item.weight > 1e-7 for item in vertex.groups)}
    fallback_count = 0
    if deform_bones:
        for vertex in base.data.vertices:
            if vertex.index in weighted:
                continue
            point = base.matrix_world @ vertex.co
            nearest = None
            nearest_distance = float("inf")
            for bone in deform_bones:
                start = rig.matrix_world @ bone.head_local
                end = rig.matrix_world @ bone.tail_local
                segment = end - start
                amount = max(0.0, min(1.0, (point - start).dot(segment) / max(segment.length_squared, 1e-8)))
                distance_to_bone = (point - (start + segment * amount)).length_squared
                if distance_to_bone < nearest_distance:
                    nearest = bone
                    nearest_distance = distance_to_bone
            if nearest is not None:
                group = groups.get(nearest.name) or base.vertex_groups.new(name=nearest.name)
                group.add([vertex.index], 1.0, "REPLACE")
                fallback_count += 1
    weighted_after = {vertex.index for vertex in base.data.vertices if any(item.weight > 1e-7 for item in vertex.groups)}
    if len(weighted_after) < len(base.data.vertices):
        raise RuntimeError(f"rig weight binding incomplete: {len(weighted_after)}/{len(base.data.vertices)} vertices weighted")
    outfit_parts = add_hanfu_lookdev(rig, base, character_id)
    add_actor_motion_test(rig)
    rig.show_in_front = True
    rig["character_id"] = character_id
    rig["rig_type"] = "RIGIFY_HUMAN_METARIG"
    status = {
        "schema_version": 1,
        "status": "TECHNICAL_PASS_VISUAL_REJECTED",
        "character_id": character_id,
        "provider": "local_blender_mpfb_rigify",
        "model": "MPFB Asian male baseline + Rigify human metarig",
        "body_vertices": len(base.data.vertices),
        "body_height_m": round(height, 3),
        "rig_bones": len(rig.data.bones),
        "armature_bound": True,
        "codex_lookdev_parts": outfit_parts,
        "lookdev": "procedural indigo hanfu, integrated indigo sleeve material, ivory front panel, gold belt, tied hair and face accents",
        "motion_test": "2-second Rigify foot IK / arm FK walk-control smoke; robe shell remains actor-root attached",
        "weighted_vertices": len(weighted_after),
        "weight_fallback_vertices": fallback_count,
        "scene_properties": scene_settings,
        "local_only": True,
        "billable": False,
        "images_uploaded": False,
        "review_status": "REJECTED",
        "quality_note": "人物和袍身为粗糙程序化造型，视觉不符合成片要求；骨骼数据仅保留为技术参考。",
        "limitations": ["服装、发型和面部为 Codex 程序化初版，与角色卡仍需逐角度校准", "袍身和发饰随演员根节点移动，袍身尚未绑定关节或布料模拟", "走步为技术测试动作，自动权重仍需审看肩、肘、膝变形"]
    }
    make_preview(project, base, rig, image_path, video_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    status["blend"] = str(blend_path.relative_to(project))
    status["preview"] = str(image_path.relative_to(project))
    status["walk_preview"] = str(video_path.relative_to(project))
    (output_dir / "manifest.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("P39_RIG_SMOKE_PASS " + json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
