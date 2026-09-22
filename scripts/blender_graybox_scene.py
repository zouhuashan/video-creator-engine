#!/usr/bin/env python3
"""Blender-side renderer for a deterministic gray/white blockout shot.

Run by Blender in background mode. No add-ons or UI interaction are required.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
from bpy_extras import anim_utils
from mathutils import Vector


def _args() -> tuple[Path, Path, Path | None]:
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("expected -- <spec.json> <output.mp4> [progress.json]")
    args = argv[argv.index("--") + 1 :]
    if len(args) not in {2, 3}:
        raise RuntimeError("expected graybox spec, output path and optional progress path")
    progress = Path(args[2]).resolve() if len(args) == 3 else None
    return Path(args[0]).resolve(), Path(args[1]).resolve(), progress


def _write_progress(path: Path | None, *, status: str, frame: int, total_frames: int, detail: str = "") -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "current_frame": int(frame),
        "total_frames": int(total_frames),
        "progress_percent": round((frame * 100.0 / total_frames), 1) if total_frames else 0.0,
        "detail": detail,
        "updated_at_epoch": time.time(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _install_progress_handlers(progress_path: Path | None, total_frames: int) -> None:
    def render_pre(scene, *_):
        _write_progress(
            progress_path,
            status="RUNNING",
            frame=max(0, int(scene.frame_current) - 1),
            total_frames=total_frames,
            detail=f"开始渲染第 {int(scene.frame_current)} / {total_frames} 帧",
        )

    def render_post(scene, *_):
        _write_progress(
            progress_path,
            status="RUNNING",
            frame=int(scene.frame_current),
            total_frames=total_frames,
            detail=f"已完成第 {int(scene.frame_current)} / {total_frames} 帧",
        )

    def render_complete(scene, *_):
        _write_progress(
            progress_path,
            status="PASS",
            frame=total_frames,
            total_frames=total_frames,
            detail="Blender 动画渲染完成",
        )

    bpy.app.handlers.render_pre.append(render_pre)
    bpy.app.handlers.render_post.append(render_post)
    bpy.app.handlers.render_complete.append(render_complete)


def _clear() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def _material(name: str, rgba: tuple[float, float, float, float]):
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = rgba
    return mat


def _box(name: str, location, scale, material, parent=None):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    return obj


def _sphere(name: str, location, scale, material, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    return obj


def _cylinder(name: str, location, radius: float, depth: float, material, parent=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    return obj


def _keyframe(obj, frame: int, *, location=None, rotation=None):
    if location is not None:
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
    if rotation is not None:
        obj.rotation_euler = rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def _linear(obj) -> None:
    """Set keyframe interpolation without depending on removed Blender 5.x Action.fcurves."""
    anim_data = getattr(obj, "animation_data", None)
    action = getattr(anim_data, "action", None) if anim_data else None
    if action is None:
        return

    curves = None

    # Blender <= 4.x legacy/compatibility API.
    try:
        curves = getattr(action, "fcurves", None)
    except Exception:
        curves = None

    # Blender 4.4+ slotted/layered actions; required on Blender 5.x where
    # Action.fcurves was removed.
    if curves is None:
        try:
            channelbag = anim_utils.animdata_get_channelbag_for_assigned_slot(anim_data)
            curves = getattr(channelbag, "fcurves", None) if channelbag is not None else None
        except Exception as error:
            print(f"[graybox] WARN: unable to resolve Action channelbag for {obj.name}: {error}")
            curves = None

    if curves is None:
        print(f"[graybox] WARN: no editable F-Curves found for {obj.name}; keeping Blender default interpolation")
        return

    try:
        for curve in curves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    except Exception as error:
        # Interpolation is a quality preference, not a render-critical step.
        # Never abort the whole graybox render because Blender changes animation APIs.
        print(f"[graybox] WARN: failed to force LINEAR interpolation for {obj.name}: {error}")


def _build_environment(white, gray):
    _box("Ground", (0, 0, -0.15), (7.0, 10.0, 0.15), gray)
    _box("BackWall", (0, 3.5, 2.1), (5.3, 0.22, 2.1), white)
    _box("GateLeft", (-2.35, 2.2, 2.2), (0.42, 0.42, 2.2), white)
    _box("GateRight", (2.35, 2.2, 2.2), (0.42, 0.42, 2.2), white)
    _box("GateLintel", (0, 2.2, 4.15), (2.8, 0.48, 0.34), white)
    _box("RoofBar", (0, 2.15, 4.65), (3.5, 0.68, 0.14), white)
    for index, x in enumerate((-4.2, 4.2)):
        _box(f"SideWall{index}", (x, 1.0, 1.35), (1.25, 3.0, 1.35), white)
    for index in range(3):
        _box(f"Step{index}", (0, 1.45 + index * 0.32, 0.06 + index * 0.08), (2.9 - index * 0.22, 0.48, 0.08), gray)


def _build_actor(white, dark):
    root = bpy.data.objects.new("ActorRoot", None)
    bpy.context.collection.objects.link(root)

    torso = _cylinder("Torso", (0, 0, 1.65), 0.34, 1.05, white, root)
    torso.scale.x = 0.82
    torso.scale.y = 0.55
    _sphere("Head", (0, 0, 2.48), (0.30, 0.27, 0.36), white, root)
    _cylinder("Neck", (0, 0, 2.10), 0.12, 0.28, white, root)

    # Hair mass gives the AI video model a clear head orientation cue.
    hair = _sphere("HairMass", (0, 0.05, 2.57), (0.34, 0.31, 0.32), dark, root)
    hair.scale.z = 1.05
    _box("FaceDirection", (0, -0.29, 2.45), (0.10, 0.04, 0.08), dark, root)

    left_arm = _cylinder("Arm.L", (-0.48, 0, 1.68), 0.105, 0.92, white, root)
    right_arm = _cylinder("Arm.R", (0.48, 0, 1.68), 0.105, 0.92, white, root)
    left_arm.rotation_euler.y = 0.08
    right_arm.rotation_euler.y = -0.08

    left_leg = _cylinder("Leg.L", (-0.18, 0, 0.72), 0.13, 1.25, white, root)
    right_leg = _cylinder("Leg.R", (0.18, 0, 0.72), 0.13, 1.25, white, root)
    _box("Foot.L", (-0.18, -0.12, 0.08), (0.14, 0.27, 0.09), white, root)
    _box("Foot.R", (0.18, -0.12, 0.08), (0.14, 0.27, 0.09), white, root)

    # A simple robe silhouette makes occlusion and cloth volume easier to read.
    bpy.ops.mesh.primitive_cone_add(vertices=20, radius1=0.62, radius2=0.34, depth=1.45, location=(0, 0, 1.05))
    robe = bpy.context.object
    robe.name = "Robe"
    robe.data.materials.append(white)
    robe.parent = root

    return root, left_arm, right_arm, left_leg, right_leg, hair


def _animate_actor(spec, root, left_arm, right_arm, left_leg, right_leg, hair):
    fps = int(spec["fps"])
    actor = spec["actor"]
    frame_end = int(round(float(spec["duration_seconds"]) * fps))
    stop_frame = int(round(float(actor["stop_time"]) * fps))
    look_frame = int(round(float(actor["look_up_time"]) * fps))
    hold_frame = int(round(float(actor["hold_time"]) * fps))

    start = Vector(actor["start"])
    stop = Vector(actor["stop"])
    _keyframe(root, 1, location=start)
    _keyframe(root, stop_frame, location=stop)
    _keyframe(root, frame_end, location=stop)
    _linear(root)

    # Readable walk cycle while the root advances.
    stride = max(8, round(fps * 0.45))
    frame = 1
    phase = 0
    while frame <= stop_frame:
        angle = 0.40 if phase % 2 == 0 else -0.40
        _keyframe(left_leg, frame, rotation=(angle, 0, 0))
        _keyframe(right_leg, frame, rotation=(-angle, 0, 0))
        _keyframe(left_arm, frame, rotation=(-angle * 0.45, 0.08, 0))
        _keyframe(right_arm, frame, rotation=(angle * 0.45, -0.08, 0))
        frame += stride
        phase += 1
    for obj in (left_leg, right_leg, left_arm, right_arm):
        _keyframe(obj, stop_frame, rotation=(0, obj.rotation_euler.y, 0))

    # Stop, subtle right-hand cue, then look upward.
    _keyframe(right_arm, stop_frame, rotation=(0, -0.08, 0))
    _keyframe(right_arm, look_frame, rotation=(-0.62, -0.10, -0.08))
    _keyframe(right_arm, hold_frame, rotation=(-0.62, -0.10, -0.08))
    _keyframe(hair, stop_frame, rotation=(0, 0, 0))
    _keyframe(hair, look_frame, rotation=(0.18, 0, 0))
    _keyframe(hair, hold_frame, rotation=(0.18, 0, 0))


def _build_camera(spec):
    cam_data = bpy.data.cameras.new("GrayboxCamera")
    cam = bpy.data.objects.new("GrayboxCamera", cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.data.lens = 52
    cam.data.sensor_width = 36

    target = bpy.data.objects.new("CameraTarget", None)
    bpy.context.collection.objects.link(target)
    target.location = Vector(spec["camera_path"]["target"])
    constraint = cam.constraints.new(type="TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"

    fps = int(spec["fps"])
    end_frame = int(round(float(spec["duration_seconds"]) * fps))
    _keyframe(cam, 1, location=Vector(spec["camera_path"]["start"]))
    _keyframe(cam, end_frame, location=Vector(spec["camera_path"]["end"]))
    _linear(cam)
    return cam


def _configure_scene(spec, output: Path):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = int(round(float(spec["duration_seconds"]) * int(spec["fps"])))
    scene.render.fps = int(spec["fps"])
    scene.render.resolution_x = int(spec["width"])
    scene.render.resolution_y = int(spec["height"])
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = False
    scene.render.film_transparent = False
    scene.world.color = (0.06, 0.06, 0.07)

    output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output)

    # Blender 5.x separates output media type from still-image file format.
    # ImageFormatSettings.file_format no longer accepts "FFMPEG"; select VIDEO
    # through media_type and keep container/codec settings under render.ffmpeg.
    image_settings = scene.render.image_settings
    if hasattr(image_settings, "media_type"):
        image_settings.media_type = "VIDEO"
    else:
        # Blender <= 4.x legacy API.
        image_settings.file_format = "FFMPEG"

    if scene.render.ffmpeg is None:
        raise RuntimeError("this Blender build does not expose FFmpeg video output")
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.gopsize = int(spec["fps"]) * 2
    scene.render.ffmpeg.audio_codec = "NONE"


def main() -> int:
    spec_path, output, progress_path = _args()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    total_frames = int(round(float(spec["duration_seconds"]) * int(spec["fps"])))
    _write_progress(progress_path, status="RUNNING", frame=0, total_frames=total_frames, detail="Blender 正在初始化白模场景")
    _clear()
    white = _material("GrayboxWhite", (0.82, 0.84, 0.86, 1.0))
    gray = _material("GrayboxGround", (0.32, 0.34, 0.38, 1.0))
    dark = _material("GrayboxDirection", (0.16, 0.17, 0.19, 1.0))
    _build_environment(white, gray)
    root, left_arm, right_arm, left_leg, right_leg, hair = _build_actor(white, dark)
    _animate_actor(spec, root, left_arm, right_arm, left_leg, right_leg, hair)
    _build_camera(spec)
    _configure_scene(spec, output)
    _install_progress_handlers(progress_path, total_frames)
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix(".blend")))
    _write_progress(progress_path, status="RUNNING", frame=0, total_frames=total_frames, detail="场景已完成，开始逐帧渲染")
    bpy.ops.render.render(animation=True)
    if not output.is_file():
        raise RuntimeError("Blender finished without producing the graybox MP4")
    print(json.dumps({"status": "PASS", "output": str(output), "frames": bpy.context.scene.frame_end}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
