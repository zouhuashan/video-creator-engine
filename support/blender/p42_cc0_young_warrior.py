"""Create a continuous 3D donghua pilot from the CC0 Young Warrior base."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector


FPS = 24
FRAME_END = 96
WIDTH = 480
HEIGHT = 854


def args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--character-id", default="CHR-N0DBC8F583-AUTO-001")
    parser.add_argument("--preview-only", action="store_true")
    return parser.parse_args(values)


def make_material(name, color, *, metallic=0.0, roughness=.55, emission=None, strength=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if emission is not None:
        channel = shader.inputs.get("Emission Color") or shader.inputs.get("Emission")
        if channel:
            channel.default_value = (*emission, 1.0)
        if shader.inputs.get("Emission Strength"):
            shader.inputs["Emission Strength"].default_value = strength
    return mat


def fabric(mat):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.0
    noise.inputs["Detail"].default_value = 3.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .18
    bump.inputs["Distance"].default_value = .35
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])


def smooth(obj):
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def modifiers(obj, *, solidify=0.0, bevel=0.0, subdivision=0):
    if solidify:
        mod = obj.modifiers.new("Cloth thickness", "SOLIDIFY")
        mod.thickness = solidify
        mod.offset = 0.0
    if bevel:
        mod = obj.modifiers.new("Tailored edge", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    if subdivision:
        mod = obj.modifiers.new("Surface subdivision", "SUBSURF")
        mod.levels = subdivision
        mod.render_levels = subdivision


def mesh(name, vertices, faces, mat):
    data = bpy.data.meshes.new(name + "Mesh")
    data.from_pydata(vertices, [], faces)
    data.materials.append(mat)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    smooth(obj)
    return obj


def rigid_skin(obj, armature, bone):
    if obj.type == "CURVE":
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.convert(target="MESH")
    group = obj.vertex_groups.new(name=bone)
    group.add([vertex.index for vertex in obj.data.vertices], 1.0, "REPLACE")
    mod = obj.modifiers.new("Young Warrior rig", "ARMATURE")
    mod.object = armature


def ring(name, profiles, mat, *, sides=48, opening=.0):
    angles = [opening / 2 + index / sides * (math.tau - opening) for index in range(sides + 1)]
    vertices = [(rx * math.sin(angle), -ry * math.cos(angle), z)
                for z, rx, ry in profiles for angle in angles]
    row = len(angles)
    faces = [(r * row + i, r * row + i + 1, (r + 1) * row + i + 1, (r + 1) * row + i)
             for r in range(len(profiles) - 1) for i in range(row - 1)]
    obj = mesh(name, vertices, faces, mat)
    modifiers(obj, solidify=1.1, bevel=.7, subdivision=1)
    return obj


def panel(name, x0, x1, y, top, bottom, mat, *, bow=6.0, rows=10):
    vertices = []
    for row in range(rows + 1):
        t = row / rows
        z = top + (bottom - top) * t
        center = (x0 + x1) / 2
        half = (x1 - x0) / 2 * (1 + .35 * t)
        ripple = math.sin(t * math.tau * 1.4) * 1.1
        vertices += [(center - half, y - bow * t + ripple, z),
                     (center + half, y - bow * t - ripple, z)]
    faces = [(row * 2, row * 2 + 1, row * 2 + 3, row * 2 + 2) for row in range(rows)]
    obj = mesh(name, vertices, faces, mat)
    modifiers(obj, solidify=1.0, bevel=.75, subdivision=1)
    return obj


def curve(name, points, mat, thickness):
    data = bpy.data.curves.new(name + "Curve", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = thickness
    data.bevel_resolution = 3
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for handle, point in zip(spline.bezier_points, points):
        handle.co = point
        handle.handle_left_type = "AUTO"
        handle.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def cube(name, location, scale, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    if bevel:
        modifiers(obj, bevel=bevel)
    return obj


def sphere(name, location, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=16, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    smooth(obj)
    return obj


def dress_character(armature):
    body = bpy.data.objects.get("body.001")
    head = bpy.data.objects.get("baseMesh1_A1.001")
    hair = bpy.data.objects.get("hair")
    eyes = [bpy.data.objects.get("eye.L"), bpy.data.objects.get("eye.R")]
    if body is None or head is None or hair is None or any(item is None for item in eyes):
        raise RuntimeError("CC0 Young Warrior mesh parts are incomplete")
    skin = make_material("P42CC0_Skin", (.52, .25, .15), roughness=.7)
    ink = make_material("P42CC0_Ink", (.009, .015, .028), roughness=.46)
    coat = make_material("P42CC0_Coat", (.055, .095, .18), roughness=.50)
    red = make_material("P42CC0_Cinnabar", (.42, .035, .045), roughness=.48)
    gold = make_material("P42CC0_Gold", (.50, .22, .045), metallic=.76, roughness=.33)
    ivory = make_material("P42CC0_Ivory", (.72, .60, .43), roughness=.57)
    eye = make_material("P42CC0_Eyes", (.025, .012, .010), roughness=.28)
    fabric(coat)
    fabric(red)
    for obj, mat in ((head, skin), (hair, ink), (eyes[0], eye), (eyes[1], eye)):
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        smooth(obj)
    body.data.materials.clear()
    body.data.materials.append(coat)
    body.data.materials.append(skin)
    # Native rig and topology supply fitted sleeves/trousers; reveal hands only.
    for polygon in body.data.polygons:
        center = polygon.center
        polygon.material_index = 1 if abs(center.x) > 61 and center.z > 110 else 0
    smooth(body)

    parts = []
    sash = ring("P42CC0_Sash", ((99, 24.5, 13), (103, 25.5, 13.5), (107, 24.5, 13)), red)
    rigid_skin(sash, armature, "Sacrum")
    parts.append(sash)
    panels = [
        panel("P42CC0_Panel_L", -22, -1, -12, 104, 42, coat, bow=5),
        panel("P42CC0_Panel_R", 1, 22, -12, 104, 42, coat, bow=5),
        panel("P42CC0_Panel_Red", -9, 9, -13.5, 102, 48, red, bow=6),
        panel("P42CC0_Panel_Back", -22, 22, 11, 104, 45, ink, bow=-3),
    ]
    for item in panels:
        rigid_skin(item, armature, "Sacrum")
        parts.append(item)
    for index, points in enumerate((
        ((-20, -15, 148), (-3, -17, 130), (12, -16, 109)),
        ((20, -15, 148), (4, -17.5, 130), (-10, -16, 112)),
    )):
        collar = curve(f"P42CC0_Collar_{index}", points, ivory if index == 0 else red, .72)
        rigid_skin(collar, armature, "Spine2")
        parts.append(collar)
    for x in (-27, 27):
        trim = curve(f"P42CC0_Trim_{x}", ((x, -16, 101), (x * 1.1, -19, 64), (x * 1.25, -21, 28)), gold, .65)
        rigid_skin(trim, armature, "Sacrum")
        parts.append(trim)
    return body, head, hair, parts


def add_ik(armature):
    targets = {}
    for side in ("L", "R"):
        bpy.ops.object.empty_add(type="SPHERE", radius=2.5)
        target = bpy.context.object
        target.name = f"P42CC0_HandTarget.{side}"
        targets[side] = target
        lower = armature.pose.bones[f"LowerArm.{side}"]
        constraint = lower.constraints.new("IK")
        constraint.name = "P42 continuous hand IK"
        constraint.target = target
        constraint.chain_count = 2
        constraint.iterations = 96
    return targets


def key_rotation(bone, frame, euler):
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = euler
    bone.keyframe_insert(data_path="rotation_euler", frame=frame, group="P42 CC0 Motion")


def animate(armature, parts):
    armature.animation_data_clear()
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0, 0, 0)
        bone.location = (0, 0, 0)
    targets = add_ik(armature)
    path = {
        1: {"L": (58, -2, 122), "R": (-58, -2, 122), "sacrum": (0, 0, 0), "spine": (0, 0, 0), "head": (0, 0, 0)},
        24: {"L": (42, -14, 128), "R": (-30, -20, 140), "sacrum": (0, 0, -.035), "spine": (.025, 0, -.05), "head": (-.06, .01, .05)},
        48: {"L": (25, -24, 138), "R": (-18, -28, 148), "sacrum": (.02, 0, -.08), "spine": (-.09, .02, -.10), "head": (-.11, .04, .13)},
        72: {"L": (31, -17, 143), "R": (-38, -12, 130), "sacrum": (0, 0, .16), "spine": (.02, -.02, .18), "head": (-.05, -.05, -.22)},
        96: {"L": (47, -6, 128), "R": (-46, -6, 128), "sacrum": (0, 0, .10), "spine": (0, 0, .10), "head": (-.035, -.02, -.12)},
    }
    for frame, pose in path.items():
        for side in ("L", "R"):
            targets[side].location = pose[side]
            targets[side].keyframe_insert(data_path="location", frame=frame, group="P42 CC0 Hand Paths")
        key_rotation(armature.pose.bones["Sacrum"], frame, pose["sacrum"])
        key_rotation(armature.pose.bones["Spine3"], frame, pose["spine"])
        key_rotation(armature.pose.bones["head"], frame, pose["head"])
    for obj in parts:
        if "Panel" not in obj.name:
            continue
        base = obj.rotation_euler.copy()
        for frame, amount in ((1, 0), (24, -.018), (48, .075), (72, -.055), (96, .012)):
            obj.rotation_euler = base
            obj.rotation_euler.y += amount
            obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="P42 CC0 Cloth Follow")


def stage_and_camera():
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    wood = make_material("P42CC0_Wood", (.10, .018, .012), roughness=.58)
    stone = make_material("P42CC0_Stone", (.035, .050, .065), roughness=.46)
    glow = make_material("P42CC0_Glow", (.55, .08, .018), roughness=.35, emission=(1, .12, .02), strength=4)
    cube("P42CC0_Floor", (0, 0, -5), (400, 400, 5), stone, 2)
    for x in (-130, 130):
        cube(f"P42CC0_Column{x}", (x, 72, 105), (16, 16, 115), wood, 2)
    cube("P42CC0_Beam", (0, 72, 205), (165, 20, 16), wood, 2)
    cube("P42CC0_Roof", (0, 78, 237), (198, 26, 9), wood, 2)
    for x in (-88, 88):
        sphere(f"P42CC0_Lantern{x}", (x, 44, 166), (13, 10, 18), glow)
        bpy.ops.object.light_add(type="POINT", location=(x, 25, 164))
        lamp = bpy.context.object
        lamp.data.energy = 14000
        lamp.data.color = (1, .16, .035)
        lamp.data.shadow_soft_size = 55
    bpy.ops.object.light_add(type="AREA", location=(-210, -270, 310))
    key = bpy.context.object
    key.data.energy = 180000
    key.data.shape = "DISK"
    key.data.size = 250
    key.data.color = (1, .30, .12)
    bpy.ops.object.light_add(type="AREA", location=(210, -100, 230))
    fill = bpy.context.object
    fill.data.energy = 130000
    fill.data.size = 220
    fill.data.color = (.16, .30, 1)
    bpy.ops.object.light_add(type="AREA", location=(0, 220, 280))
    rim = bpy.context.object
    rim.data.energy = 190000
    rim.data.size = 180
    rim.data.color = (1, .10, .02)
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(28), math.radians(-18), math.radians(-32)))
    sun = bpy.context.object
    sun.name = "P42CC0_WarmSun"
    sun.data.energy = 3.2
    sun.data.color = (1.0, .52, .30)
    sun.data.angle = math.radians(12)
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(65), math.radians(22), math.radians(138)))
    cool = bpy.context.object
    cool.name = "P42CC0_CoolFillSun"
    cool.data.energy = 1.45
    cool.data.color = (.22, .38, 1.0)
    cool.data.angle = math.radians(18)

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 127))
    focus = bpy.context.object
    focus.name = "P42CC0_CameraFocus"
    bpy.ops.object.camera_add(location=(128, -365, 184))
    camera = bpy.context.object
    camera.name = "P42CC0_Camera"
    camera.data.lens = 62
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = focus
    camera.data.dof.aperture_fstop = 4.5
    track = camera.constraints.new("TRACK_TO")
    track.target = focus
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    for frame, location in ((1, (128, -365, 184)), (24, (76, -342, 178)), (48, (18, -328, 176)),
                            (72, (-63, -342, 183)), (96, (-110, -366, 190))):
        camera.location = location
        camera.keyframe_insert(data_path="location", frame=frame, group="P42 CC0 Camera")
    return camera


def configure_scene(output):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(output)
    scene.world = bpy.data.worlds.get("P42CC0_World") or bpy.data.worlds.new("P42CC0_World")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (.003, .007, .018, 1)
    bg.inputs["Strength"].default_value = .25


def render_video(output_dir):
    scene = bpy.context.scene
    frames = output_dir / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    scene.render.filepath = str(frames / "frame-")
    bpy.ops.render.render(animation=True)
    silent = output_dir / "p42-cc0-3d-motion-silent.mp4"
    final = output_dir / "p42-cc0-3d-motion-v1.mp4"
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-start_number", "1",
                    "-i", str(frames / "frame-%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)], check=True)
    voice = output_dir.parents[2] / "production-pilot" / "audio" / "pilot-zm_010.wav"
    if voice.is_file():
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(voice),
                        "-filter_complex", "[1:a]adelay=350|350,loudnorm=I=-16:TP=-2:LRA=7[a]", "-map", "0:v", "-map", "[a]",
                        "-t", "4", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                        str(final)], check=True)
    else:
        silent.replace(final)
    shutil.rmtree(frames)
    silent.unlink(missing_ok=True)
    return final


def main():
    config = args()
    project = config.project.resolve()
    output_dir = project / "lookdev" / "3d-rigs" / config.character_id / "p42-cc0"
    output_dir.mkdir(parents=True, exist_ok=True)
    armature = bpy.data.objects.get("Armature")
    if armature is None:
        raise RuntimeError("CC0 Young Warrior armature missing")
    body, head, hair, parts = dress_character(armature)
    animate(armature, parts)
    camera = stage_and_camera()
    bpy.context.scene.camera = camera
    preview = output_dir / "p42-cc0-preview.png"
    configure_scene(preview)
    bpy.context.scene.frame_set(48)
    bpy.ops.render.render(write_still=True)
    blend = output_dir / "p42-cc0-young-warrior-v1.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    video = None if config.preview_only else render_video(output_dir)
    manifest = {
        "schema_version": 1,
        "status": "HUMAN_REVIEW_PENDING",
        "review_status": "PENDING",
        "provider": "local_blender_cc0_young_warrior",
        "source": "Base Rigged Stylized Humanoid Character (young warrior) by Girush",
        "license": "CC0 / Public Domain",
        "source_url": "https://opengameart.org/content/base-rigged-stylized-humanoid-character-yw",
        "character_id": config.character_id,
        "body_vertices": len(body.data.vertices),
        "head_vertices": len(head.data.vertices),
        "rig_bones": len(armature.data.bones),
        "lookdev_parts": len(parts),
        "continuous_motion": True,
        "motion_method": "native skinning + two-bone IK hand paths + spine/head keys + secondary robe motion",
        "camera_method": "continuous perspective orbit",
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "frames": FRAME_END,
        "duration_seconds": 4.0,
        "local_only": True,
        "billable": False,
        "preview": str(preview.relative_to(project)),
        "blend": str(blend.relative_to(project)),
        "video": str(video.relative_to(project)) if video else "",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("P42_CC0_3D_PASS " + json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
