"""Build the P43 local 3D donghua character pilot.

The script keeps the CC0 Young Warrior's native mesh, weights and skeleton, then
adds a fitted three-dimensional hanfu silhouette, stable elbow poles, facial
beats and overlapping body motion.  It is deliberately deterministic so the
same shot can be resumed or locally re-rendered without a video API.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector


_BASE_PATH = Path(__file__).with_name("p42_cc0_young_warrior.py")
_BASE_SPEC = importlib.util.spec_from_file_location("p42_cc0_young_warrior", _BASE_PATH)
if _BASE_SPEC is None or _BASE_SPEC.loader is None:
    raise RuntimeError(f"Cannot load P42 Blender helpers from {_BASE_PATH}")
base = importlib.util.module_from_spec(_BASE_SPEC)
_BASE_SPEC.loader.exec_module(base)


FPS = 24
FRAME_END = 120
WIDTH = 480
HEIGHT = 854


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--character-id", default="CHR-N0DBC8F583-AUTO-001")
    parser.add_argument("--preview-only", action="store_true")
    return parser.parse_args(values)


def clear_previous() -> None:
    for obj in list(bpy.data.objects):
        if obj.name.startswith(("P42CC0_", "P43_")) or obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)


def material(name, color, *, metallic=0.0, roughness=0.52, emission=None, strength=0.0):
    mat = base.make_material(name, color, metallic=metallic, roughness=roughness,
                             emission=emission, strength=strength)
    return mat


def dress_character(armature):
    body = bpy.data.objects.get("body.001")
    head = bpy.data.objects.get("baseMesh1_A1.001")
    hair = bpy.data.objects.get("hair")
    eyes = [bpy.data.objects.get("eye.L"), bpy.data.objects.get("eye.R")]
    if body is None or head is None or hair is None or any(item is None for item in eyes):
        raise RuntimeError("CC0 Young Warrior mesh parts are incomplete")

    skin = material("P43_Skin", (.50, .245, .15), roughness=.72)
    ink = material("P43_Ink", (.008, .013, .025), roughness=.42)
    blue = material("P43_DeepBlue", (.022, .055, .13), roughness=.56)
    blue2 = material("P43_MidBlue", (.045, .11, .23), roughness=.52)
    red = material("P43_Cinnabar", (.46, .026, .035), roughness=.50)
    gold = material("P43_AntiqueGold", (.52, .24, .055), metallic=.62, roughness=.34)
    ivory = material("P43_Ivory", (.72, .55, .34), roughness=.60)
    eye_mat = material("P43_Eyes", (.018, .008, .006), roughness=.25)
    lip_mat = material("P43_Mouth", (.17, .008, .012), roughness=.38)
    base.fabric(blue)
    base.fabric(blue2)
    base.fabric(red)

    for obj, mat in ((head, skin), (hair, ink), (eyes[0], eye_mat), (eyes[1], eye_mat)):
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        base.smooth(obj)
    body.data.materials.clear()
    body.data.materials.append(blue)
    body.data.materials.append(skin)
    # The native skinned body supplies fitted sleeves/trousers.  Only hands and
    # feet retain skin; the torso is covered by a separate 3D coat shell.
    for polygon in body.data.polygons:
        center = polygon.center
        polygon.material_index = 1 if (abs(center.x) > 60 and center.z > 109) else 0
    base.smooth(body)

    parts = []
    # A closed fitted torso and an opened conical skirt replace the old rigid
    # rectangular cards.  Both have real depth and preserve silhouette during
    # the camera orbit.
    skirt = base.ring(
        "P43_RobeSkirt",
        ((106, 25.3, 13.6), (94, 27.0, 15.0), (73, 31.0, 18.0),
         (48, 35.5, 21.5), (20, 39.5, 25.0)),
        blue,
        sides=72,
        opening=.72,
    )
    base.rigid_skin(skirt, armature, "Sacrum")
    parts.append(skirt)

    inner = base.ring(
        "P43_InnerSkirt",
        ((103, 22.0, 12.0), (74, 27.0, 16.0), (22, 34.0, 21.0)),
        ink,
        sides=64,
        opening=.24,
    )
    base.rigid_skin(inner, armature, "Sacrum")
    parts.append(inner)

    sash = base.ring("P43_Sash", ((103, 26.2, 14.2), (108, 26.7, 14.6), (113, 25.4, 13.7)),
                     red, sides=64, opening=.10)
    base.rigid_skin(sash, armature, "Sacrum")
    parts.append(sash)

    # Front tabards follow the pelvis but use tapered geometry and subtle bowing.
    tabard = base.panel("P43_FrontTabard", -10.5, 10.5, -15.0, 108, 39, red, bow=4.5, rows=18)
    base.rigid_skin(tabard, armature, "Sacrum")
    parts.append(tabard)
    back_tabard = base.panel("P43_BackTabard", -12, 12, 14.0, 106, 45, ink, bow=-2.5, rows=16)
    base.rigid_skin(back_tabard, armature, "Sacrum")
    parts.append(back_tabard)

    # Cross collar follows the upper torso and reads clearly at phone size.
    for index, points in enumerate((
        ((-18, -13.5, 149), (-4, -15.0, 132), (10, -15.2, 112)),
        ((18, -13.5, 149), (4, -15.3, 132), (-9, -15.4, 113)),
    )):
        collar = base.curve(f"P43_Collar_{index}", points, ivory if index == 0 else red, .54)
        base.rigid_skin(collar, armature, "Spine2")
        parts.append(collar)

    # Belt clasp and a side jade token provide readable, non-card-like detail.
    clasp = base.sphere("P43_BeltClasp", (0, -15.2, 107.2), (3.2, .9, 2.4), gold)
    base.rigid_skin(clasp, armature, "Sacrum")
    parts.append(clasp)
    token = base.sphere("P43_JadeToken", (18, -15.4, 91), (3.2, .8, 5.5), ivory)
    base.rigid_skin(token, armature, "Sacrum")
    parts.append(token)

    # Facial graphic elements are actual 3D meshes bound to the head bone.
    mouth = base.sphere("P43_Mouth", (0, -8.04, 167.25), (2.25, .18, .22), lip_mat)
    base.rigid_skin(mouth, armature, "head")
    parts.append(mouth)
    brows = []
    for side in (-1, 1):
        brow = base.curve(
            f"P43_Brow_{side}",
            ((side * 1.2, -7.92, 175.75), (side * 3.1, -7.76, 176.35), (side * 4.8, -7.25, 176.05)),
            ink,
            .18,
        )
        base.rigid_skin(brow, armature, "head")
        parts.append(brow)
        brows.append(brow)
    return body, head, hair, eyes, mouth, brows, parts


def add_ik(armature):
    targets, poles = {}, {}
    for side, sign in (("L", 1), ("R", -1)):
        bpy.ops.object.empty_add(type="SPHERE", radius=2.0)
        target = bpy.context.object
        target.name = f"P43_HandTarget.{side}"
        target.parent = armature
        targets[side] = target
        bpy.ops.object.empty_add(type="CUBE", radius=1.8)
        pole = bpy.context.object
        pole.name = f"P43_ElbowPole.{side}"
        pole.location = (sign * 74, 27, 138)
        pole.parent = armature
        poles[side] = pole
        lower = armature.pose.bones[f"LowerArm.{side}"]
        ik = lower.constraints.new("IK")
        ik.name = "P43 stable two-bone IK"
        ik.target = target
        ik.pole_target = pole
        ik.pole_angle = -math.pi / 2 if side == "L" else math.pi / 2
        ik.chain_count = 2
        ik.iterations = 128
    return targets, poles


def key_rotation(bone, frame, euler):
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = euler
    bone.keyframe_insert(data_path="rotation_euler", frame=frame, group="P43 Body Motion")


def animate(armature, eyes, mouth, brows, parts):
    armature.animation_data_clear()
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0, 0, 0)
        bone.location = (0, 0, 0)
    targets, poles = add_ik(armature)

    # Five-second control beat matching the target production grammar: enter
    # from the gate, take four deliberate steps, settle, then raise the gaze.
    # H3 owns final appearance; these keys own timing, path and body mechanics.
    poses = {
        1:   {"L": (35, -10, 108), "R": (-35, 10, 108), "root": (.01, 0, -.02),  "spine": (.02, 0, -.02),  "head": (.06, .01, .01)},
        14:  {"L": (35, 10, 109),  "R": (-35, -10, 108),"root": (-.015, 0, .025),"spine": (-.025, 0, .025),"head": (.055, .01, .01)},
        28:  {"L": (35, -11, 108), "R": (-35, 11, 109), "root": (.018, 0, -.018),"spine": (.03, 0, -.025), "head": (.045, .01, .01)},
        42:  {"L": (35, 11, 109),  "R": (-35, -11, 108),"root": (-.018, 0, .028),"spine": (-.03, 0, .03), "head": (.04, .01, .01)},
        56:  {"L": (35, -10, 108), "R": (-35, 10, 109), "root": (.015, 0, -.015),"spine": (.025, 0, -.02),"head": (.035, .01, .01)},
        70:  {"L": (35, 8, 108),   "R": (-35, -8, 108), "root": (-.012, 0, .018),"spine": (-.018, 0, .02),"head": (.03, .01, .01)},
        82:  {"L": (35, 0, 106),   "R": (-35, 0, 106),  "root": (0, 0, 0),     "spine": (.01, 0, 0),   "head": (.02, 0, 0)},
        96:  {"L": (35, 0, 106),   "R": (-35, 0, 106),  "root": (0, 0, 0),     "spine": (-.015, 0, 0), "head": (-.10, 0, 0)},
        108: {"L": (35, 0, 106),   "R": (-35, 0, 106),  "root": (0, 0, 0),     "spine": (-.025, 0, 0), "head": (-.24, 0, 0)},
        120: {"L": (35, 0, 106),   "R": (-35, 0, 106),  "root": (0, 0, 0),     "spine": (-.018, 0, 0), "head": (-.20, 0, 0)},
    }
    for frame, pose in poses.items():
        for side in ("L", "R"):
            targets[side].location = pose[side]
            targets[side].keyframe_insert(data_path="location", frame=frame, group="P43 Hand Paths")
        key_rotation(armature.pose.bones["Sacrum"], frame, pose["root"])
        key_rotation(armature.pose.bones["Spine3"], frame, pose["spine"])
        key_rotation(armature.pose.bones["head"], frame, pose["head"])
        hand_l = (-.04, .02, -.05)
        hand_r = (-.04, -.02, .05)
        key_rotation(armature.pose.bones["hand001.L"], frame, hand_l)
        key_rotation(armature.pose.bones["hand001.R"], frame, hand_r)

    # Root trajectory and walk-cycle mechanics.  The character advances in
    # world space; alternating femur/tibia arcs keep the stride readable.
    for frame, y, z in ((1, 72, 0), (14, 61, 1.2), (28, 49, 0), (42, 37, 1.25),
                        (56, 25, 0), (70, 15, 1.0), (82, 10, 0), (120, 10, 0)):
        armature.location = (0, y, z)
        armature.keyframe_insert(data_path="location", frame=frame, group="P43 Walk Path")
    stride = ((1, (-.28, 0, .015), (.28, 0, -.015), .08, .34),
              (14, (.05, 0, 0), (-.05, 0, 0), .24, .12),
              (28, (.29, 0, -.015), (-.29, 0, .015), .34, .08),
              (42, (-.04, 0, 0), (.04, 0, 0), .13, .25),
              (56, (-.27, 0, .012), (.27, 0, -.012), .08, .32),
              (70, (.04, 0, 0), (-.04, 0, 0), .22, .12),
              (82, (0, 0, 0), (0, 0, 0), .04, .04),
              (120, (0, 0, 0), (0, 0, 0), .02, .02))
    for frame, left, right, knee_l, knee_r in stride:
        key_rotation(armature.pose.bones["Femur.L"], frame, left)
        key_rotation(armature.pose.bones["Femur.R"], frame, right)
        key_rotation(armature.pose.bones["Tibia.L"], frame, (knee_l, 0, 0))
        key_rotation(armature.pose.bones["Tibia.R"], frame, (knee_r, 0, 0))

    # Blinks and simple local viseme pulses.  These are driven inside the same
    # timeline as the body and audio, ready to be replaced by phoneme data.
    for eye in eyes:
        for frame, z in ((1, 1), (26, 1), (27, .10), (29, 1), (73, 1), (74, .08), (76, 1), (120, 1)):
            eye.scale.z = z
            eye.keyframe_insert(data_path="scale", frame=frame, group="P43 Blinks")
    for frame, scale in ((1, .35), (82, .35), (120, .35)):
        mouth.scale.z = scale
        mouth.scale.x = 1.0 - min(.18, (scale - 1) * .07)
        mouth.keyframe_insert(data_path="scale", frame=frame, group="P43 Mouth")
    for brow in brows:
        base_rot = brow.rotation_euler.copy()
        for frame, tilt in ((1, 0), (48, -.035 if "_-1" in brow.name else .035),
                            (78, .07 if "_-1" in brow.name else -.07), (120, 0)):
            brow.rotation_euler = base_rot
            brow.rotation_euler.y += tilt
            brow.keyframe_insert(data_path="rotation_euler", frame=frame, group="P43 Expression")

    # Secondary garment motion lags behind body beats.
    for obj in parts:
        if not any(tag in obj.name for tag in ("Skirt", "Tabard")):
            continue
        base_rot = obj.rotation_euler.copy()
        for frame, amount in ((1, 0), (34, -.018), (52, .055), (70, .018), (86, -.065), (104, .035), (120, 0)):
            obj.rotation_euler = base_rot
            obj.rotation_euler.x += amount * .35
            obj.rotation_euler.y += amount
            obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="P43 Cloth Follow")

    # Natural, non-linear interpolation for every local animation curve.
    for owner in list(bpy.data.objects) + [armature]:
        action = owner.animation_data.action if owner.animation_data and owner.animation_data.action else None
        if not action:
            continue
        for curve in getattr(action, "fcurves", ()):
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"


def stage_and_camera():
    wood = material("P43_Wood", (.075, .012, .009), roughness=.60)
    stone = material("P43_Stone", (.025, .038, .060), roughness=.43)
    bronze = material("P43_Bronze", (.32, .10, .025), metallic=.58, roughness=.38)
    glow = material("P43_Glow", (.7, .06, .012), roughness=.3, emission=(1, .07, .01), strength=5)
    base.cube("P43_Floor", (0, 0, -5), (360, 330, 5), stone, 2)
    for x in (-125, 125):
        base.cube(f"P43_Column{x}", (x, 75, 107), (14, 14, 117), wood, 2)
        base.cube(f"P43_ColumnBand{x}", (x, 74, 105), (15, 15, 4), bronze, 1)
    base.cube("P43_Beam", (0, 75, 208), (155, 18, 14), wood, 2)
    base.cube("P43_Roof", (0, 80, 237), (190, 27, 8), wood, 2)
    for x in (-84, 84):
        base.sphere(f"P43_Lantern{x}", (x, 42, 164), (12, 9, 17), glow)
        bpy.ops.object.light_add(type="POINT", location=(x, 18, 163))
        lamp = bpy.context.object
        lamp.data.energy = 11000
        lamp.data.color = (1, .12, .025)
        lamp.data.shadow_soft_size = 52

    lights = (
        ("AREA", (-175, -220, 285), 150000, (1.0, .25, .10), 230),
        ("AREA", (175, -80, 225), 105000, (.14, .28, 1.0), 190),
        ("AREA", (0, 205, 275), 155000, (1.0, .08, .018), 170),
    )
    for kind, location, energy, color, size in lights:
        bpy.ops.object.light_add(type=kind, location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.color = color
        light.data.size = size
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(24), math.radians(-18), math.radians(-28)))
    key_sun = bpy.context.object
    key_sun.name = "P43_KeySun"
    key_sun.data.energy = 4.2
    key_sun.data.color = (1.0, .60, .38)
    key_sun.data.angle = math.radians(18)
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(62), math.radians(18), math.radians(145)))
    fill_sun = bpy.context.object
    fill_sun.name = "P43_FillSun"
    fill_sun.data.energy = 2.1
    fill_sun.data.color = (.34, .48, 1.0)
    fill_sun.data.angle = math.radians(22)

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 90))
    focus = bpy.context.object
    focus.name = "P43_CameraFocus"
    bpy.ops.object.camera_add(location=(48, -500, 150))
    camera = bpy.context.object
    camera.name = "P43_Camera"
    camera.data.lens = 58
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = focus
    camera.data.dof.aperture_fstop = 5.2
    track = camera.constraints.new("TRACK_TO")
    track.target = focus
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    for frame, location, focus_z in (
        (1, (48, -500, 150), 90), (32, (34, -490, 148), 94),
        (66, (10, -480, 147), 98), (84, (-12, -485, 149), 98),
        (120, (-38, -498, 153), 102),
    ):
        camera.location = location
        camera.keyframe_insert(data_path="location", frame=frame, group="P43 Camera")
        focus.location.z = focus_z
        focus.keyframe_insert(data_path="location", frame=frame, group="P43 Camera Focus")
    return camera


def configure_scene(output: Path) -> None:
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
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "Medium High Contrast"
    scene.world = bpy.data.worlds.get("P43_World") or bpy.data.worlds.new("P43_World")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (.002, .005, .015, 1)
    bg.inputs["Strength"].default_value = .32


def render_video(output_dir: Path) -> Path:
    scene = bpy.context.scene
    frames = output_dir / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    scene.render.filepath = str(frames / "frame-")
    bpy.ops.render.render(animation=True)
    silent = output_dir / "p43-3d-character-silent.mp4"
    final = output_dir / "p43-3d-character-v1.mp4"
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    subprocess.run([
        ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-start_number", "1",
        "-i", str(frames / "frame-%04d.png"), "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent),
    ], check=True)
    # The H3 control shot intentionally has no dialogue or music.  Audio is
    # mixed only after the generated visual passes review.
    silent.replace(final)
    shutil.rmtree(frames)
    silent.unlink(missing_ok=True)
    return final


def main() -> None:
    config = parse_args()
    project = config.project.resolve()
    output_dir = project / "lookdev" / "3d-rigs" / config.character_id / "p43"
    output_dir.mkdir(parents=True, exist_ok=True)
    clear_previous()
    armature = bpy.data.objects.get("Armature")
    if armature is None:
        raise RuntimeError("CC0 Young Warrior armature missing")
    body, head, hair, eyes, mouth, brows, parts = dress_character(armature)
    animate(armature, eyes, mouth, brows, parts)
    camera = stage_and_camera()
    bpy.context.scene.camera = camera
    preview = output_dir / "p43-preview.png"
    configure_scene(preview)
    bpy.context.scene.frame_set(66)
    bpy.ops.render.render(write_still=True)
    blend = output_dir / "p43-character-v1.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    video = None if config.preview_only else render_video(output_dir)
    manifest = {
        "schema_version": 1,
        "status": "HUMAN_REVIEW_PENDING",
        "review_status": "PENDING",
        "provider": "local_blender_cc0_p43",
        "source": "Base Rigged Stylized Humanoid Character (young warrior) by Girush",
        "license": "CC0 / Public Domain",
        "source_url": "https://opengameart.org/content/base-rigged-stylized-humanoid-character-yw",
        "character_id": config.character_id,
        "body_vertices": len(body.data.vertices),
        "head_vertices": len(head.data.vertices),
        "rig_bones": len(armature.data.bones),
        "lookdev_parts": len(parts),
        "continuous_motion": True,
        "motion_method": "native skinning + two-bone IK with elbow poles + planted weight shift + overlap",
        "facial_motion": "two blinks + closed mouth + brow accents",
        "garment_method": "native fitted body silhouette + opened radial robe shells + secondary follow-through",
        "camera_method": "continuous perspective dolly/orbit with focus animation",
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "frames": FRAME_END,
        "duration_seconds": 5.0,
        "local_only": True,
        "billable": False,
        "preview": str(preview.relative_to(project)),
        "blend": str(blend.relative_to(project)),
        "video": str(video.relative_to(project)) if video else "",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("P43_3D_CHARACTER_PASS " + json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
