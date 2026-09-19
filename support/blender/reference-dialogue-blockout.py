import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--blend-output")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def material(name, base, roughness=0.7, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*base, 1.0)
    m.roughness = roughness
    m.metallic = metallic
    return m


def add_sphere(name, loc, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def add_body(name, loc, radius, depth, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def add_eye(name, loc, scale=(0.07, 0.025, 0.11)):
    black = bpy.data.materials.get("EyeBlack") or material("EyeBlack", (0.006,0.008,0.012), 0.35)
    return add_sphere(name, loc, scale, black)


def key(obj, frame, **values):
    for prop, value in values.items():
        setattr(obj, prop, value)
        obj.keyframe_insert(data_path=prop, frame=frame)


def build_character_adult():
    skin = material("AdultSkin", (0.45,0.26,0.20), 0.82)
    cloth = material("AdultCloth", (0.045,0.055,0.065), 0.9)
    hair = material("AdultHair", (0.012,0.015,0.022), 0.5)
    leather = material("AdultLeather", (0.09,0.055,0.035), 0.55)

    root = bpy.data.objects.new("AdultRoot", None)
    bpy.context.collection.objects.link(root)
    root.location = (-0.72, 0.0, 0.0)

    body = add_body("AdultBody", (0.0,0.0,1.15), 0.38, 1.55, cloth)
    body.parent = root
    head = add_sphere("AdultHead", (0.0,-0.01,2.18), (0.34,0.29,0.43), skin)
    head.parent = root
    haircap = add_sphere("AdultHair", (0.0,0.04,2.31), (0.36,0.31,0.30), hair)
    haircap.parent = root

    for x in (-0.10,0.10):
        e = add_eye("AdultEye", (x,-0.285,2.22), (0.035,0.018,0.047))
        e.parent = root

    belt = add_body("AdultBelt", (0.0,0.0,0.83), 0.405, 0.16, leather)
    belt.parent = root

    arm_l = add_body("AdultArmL", (-0.48,-0.01,1.15), 0.115, 0.95, cloth)
    arm_l.rotation_euler = (0.0, math.radians(-10.0), math.radians(-7.0))
    arm_l.parent = root
    arm_r = add_body("AdultArmR", (0.48,-0.01,1.15), 0.115, 0.95, cloth)
    arm_r.rotation_euler = (0.0, math.radians(10.0), math.radians(7.0))
    arm_r.parent = root

    return root, head, body


def build_character_child():
    skin = material("ChildSkin", (0.72,0.48,0.40), 0.86)
    cloth = material("ChildCloth", (0.48,0.70,0.72), 0.92)
    hair = material("ChildHair", (0.018,0.021,0.028), 0.52)

    root = bpy.data.objects.new("ChildRoot", None)
    bpy.context.collection.objects.link(root)
    root.location = (0.72, -0.03, 0.0)

    body = add_body("ChildBody", (0.0,0.0,0.72), 0.26, 0.92, cloth)
    body.parent = root
    head = add_sphere("ChildHead", (0.0,-0.02,1.55), (0.46,0.40,0.49), skin)
    head.parent = root
    haircap = add_sphere("ChildHair", (0.0,0.03,1.72), (0.47,0.41,0.31), hair)
    haircap.parent = root

    for x in (-0.14,0.14):
        e = add_eye("ChildEye", (x,-0.405,1.60), (0.072,0.027,0.095))
        e.parent = root

    for x in (-0.24,0.24):
        bun = add_sphere("ChildHairBun", (x,0.06,1.94), (0.13,0.12,0.13), hair)
        bun.parent = root

    arm_l = add_body("ChildArmL", (-0.31,-0.03,0.82), 0.09, 0.62, cloth)
    arm_l.rotation_euler = (0.0, math.radians(-18.0), math.radians(-15.0))
    arm_l.parent = root
    arm_r = add_body("ChildArmR", (0.31,-0.03,0.82), 0.09, 0.62, cloth)
    arm_r.rotation_euler = (0.0, math.radians(18.0), math.radians(15.0))
    arm_r.parent = root

    return root, head, body, arm_r


def build_ground_and_background():
    ground_mat = material("Ground", (0.075,0.055,0.038), 0.95)
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0,0,0))
    ground = bpy.context.object
    ground.data.materials.append(ground_mat)

    silhouette = material("BackgroundSilhouette", (0.03,0.034,0.035), 0.95)
    for i, x in enumerate((-3.2,-2.2,1.9,2.8,3.6)):
        body = add_body(f"BGPerson{i}", (x,2.6 + (i%2)*0.8,0.78), 0.18, 1.45, silhouette)
        add_sphere(f"BGHead{i}", (x,2.6 + (i%2)*0.8,1.62), (0.17,0.17,0.20), silhouette)

    tent = material("Tent", (0.12,0.08,0.05), 0.98)
    for x in (-4.5,4.5):
        bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1.7, radius2=0.1, depth=2.2, location=(x,4.8,1.1), rotation=(0,0,math.radians(45)))
        bpy.context.object.data.materials.append(tent)


def main():
    a = args()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 540
    scene.render.resolution_y = 960
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 144
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 35
    scene.render.film_transparent = False
    scene.world.color = (0.055,0.035,0.025)

    build_ground_and_background()
    adult, adult_head, adult_body = build_character_adult()
    child, child_head, child_body, child_arm = build_character_child()

    # Reference-inspired sunset key + cooler face fill
    bpy.ops.object.light_add(type="AREA", location=(3.8,2.0,5.5))
    sun = bpy.context.object
    sun.data.energy = 1150
    sun.data.color = (1.0,0.48,0.20)
    sun.data.shape = "DISK"
    sun.data.size = 5.0
    look_at(sun, (0,0,1.3))

    bpy.ops.object.light_add(type="AREA", location=(-2.5,-4.0,3.4))
    fill = bpy.context.object
    fill.data.energy = 520
    fill.data.color = (0.55,0.68,1.0)
    fill.data.size = 4.0
    look_at(fill, (0,0,1.3))

    target = bpy.data.objects.new("DialogueTarget", None)
    bpy.context.collection.objects.link(target)
    target.location = (0.0, 0.0, 1.25)

    bpy.ops.object.camera_add(location=(0.0,-8.6,2.15))
    cam = bpy.context.object
    cam.data.lens = 52
    cam.data.sensor_width = 36.0
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = child_head
    cam.data.dof.aperture_fstop = 2.8
    track = cam.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam

    # restrained dialogue animation: child more expressive than adult
    key(adult_head, 1, rotation_euler=(0.0,0.0,math.radians(2.0)))
    key(adult_head, 48, rotation_euler=(math.radians(3.0),0.0,math.radians(-4.0)))
    key(adult_head, 96, rotation_euler=(math.radians(5.0),0.0,math.radians(-6.0)))
    key(adult_head, 144, rotation_euler=(math.radians(2.0),0.0,math.radians(-3.0)))

    key(child_head, 1, rotation_euler=(0.0,0.0,math.radians(-3.0)))
    key(child_head, 36, rotation_euler=(math.radians(-7.0),0.0,math.radians(7.0)))
    key(child_head, 84, rotation_euler=(math.radians(-4.0),0.0,math.radians(10.0)))
    key(child_head, 120, rotation_euler=(math.radians(-2.0),0.0,math.radians(3.0)))
    key(child_head, 144, rotation_euler=(0.0,0.0,math.radians(-2.0)))

    # cinematic push-in while Track To keeps the pair centered
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0.0,-7.65,2.08)
    cam.keyframe_insert(data_path="location", frame=144)

    # simple child speaking gesture; proxy-only timing validation
    child_arm.keyframe_insert(data_path="rotation_euler", frame=1)
    child_arm.rotation_euler = (math.radians(-5.0), math.radians(28.0), math.radians(-52.0))
    child_arm.keyframe_insert(data_path="rotation_euler", frame=54)
    child_arm.keyframe_insert(data_path="rotation_euler", frame=88)
    child_arm.rotation_euler = (0.0, math.radians(18.0), math.radians(15.0))
    child_arm.keyframe_insert(data_path="rotation_euler", frame=132)

    # hard camera-space gate: do not render 144 bad frames when subjects are off-screen
    scene.frame_set(1)
    bpy.context.view_layer.update()
    safe_points = {
        "adult_head": adult_head.matrix_world.translation,
        "adult_body": adult_body.matrix_world.translation,
        "child_head": child_head.matrix_world.translation,
        "child_body": child_body.matrix_world.translation,
    }
    projections = {}
    for name, point in safe_points.items():
        co = world_to_camera_view(scene, cam, point)
        projections[name] = (float(co.x), float(co.y), float(co.z))
        if not (0.08 <= co.x <= 0.92 and 0.08 <= co.y <= 0.92 and co.z > 0.0):
            raise RuntimeError(f"camera framing gate failed for {name}: {projections[name]}")

    adult_x = projections["adult_head"][0]
    child_x = projections["child_head"][0]
    if not adult_x < child_x:
        raise RuntimeError(f"expected adult-left/child-right composition, got adult={adult_x}, child={child_x}")
    print(f"VIDEO_CREATOR_REFERENCE_FRAMING_PASS projections={projections}")

    frames_dir = Path(a.frames_dir).expanduser().resolve()
    frames_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frames_dir / "frame_")
    if a.blend_output:
        blend_output = Path(a.blend_output).expanduser().resolve()
        blend_output.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))
    bpy.ops.render.render(animation=True)

    first_frame = frames_dir / "frame_0001.png"
    last_frame = frames_dir / "frame_0144.png"
    if not first_frame.is_file() or not last_frame.is_file():
        raise RuntimeError("expected PNG frame sequence was not created")
    print(f"VIDEO_CREATOR_REFERENCE_BLOCKOUT_FRAMES_PASS frames_dir={frames_dir}")


if __name__ == "__main__":
    main()
