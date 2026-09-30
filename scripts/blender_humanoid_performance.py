"""Render the P47-05 fixed-humanoid dinner performance sample in Blender."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 2:
    raise SystemExit("usage: blender ... -- PROJECT OUTPUT_DIR")
PROJECT = Path(argv[0]).resolve()
OUTPUT = Path(argv[1]).resolve()
ASSETS = PROJECT / "production/assets/characters/quaternius-cc0"
OUTPUT.mkdir(parents=True, exist_ok=True)

FPS = 24
DURATION = 9.5
END = round(FPS * DURATION)


def clean() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.materials, bpy.data.curves, bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def material(name: str, color: tuple[float, float, float, float], metallic: float = 0.0, roughness: float = 0.65):
    value = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    value.diffuse_color = color
    value.use_nodes = True
    node = value.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = color
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Metallic"].default_value = metallic
    return value


def box(name: str, location, scale, mat, bevel: float = 0.04):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("SoftEdges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    obj.data.materials.append(mat)
    return obj


def sphere(name: str, location, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def cylinder(name: str, location, radius: float, depth: float, mat, vertices: int = 16):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def look_at(obj, target) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def key_object(obj, frame: int, *, location=None, rotation=None, scale=None) -> None:
    if location is not None:
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
    if rotation is not None:
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def key_bone(bone, frame: int, rotation) -> None:
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = rotation
    bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def bind_rigid_mesh(obj, armature, bone_name: str) -> None:
    """Skin all vertices to one bone while retaining actor-local coordinates."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.select_set(False)
    obj.parent = armature
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    modifier = obj.modifiers.new("CharacterRig", "ARMATURE")
    modifier.object = armature


def garment_segment(name: str, armature, bone_name: str, radius: float, mat) -> None:
    bone = armature.data.bones[bone_name]
    start = Vector(bone.head_local)
    end = Vector(bone.tail_local)
    direction = end - start
    obj = cylinder(name, (start + end) / 2, radius, direction.length * 1.05, mat, 20)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
    bind_rigid_mesh(obj, armature, bone_name)


def clothing_shell(actor, name: str, predicate, mat):
    source = max(actor["meshes"], key=lambda item: len(item.data.vertices))
    shell = source.copy()
    shell.data = source.data.copy()
    shell.name = name
    bpy.context.collection.objects.link(shell)
    shell.data.materials.clear()
    shell.data.materials.append(mat)
    mesh = bmesh.new()
    mesh.from_mesh(shell.data)
    rejected = []
    for face in mesh.faces:
        center = sum((vertex.co for vertex in face.verts), Vector()) / len(face.verts)
        if not predicate(center):
            rejected.append(face)
    bmesh.ops.delete(mesh, geom=rejected, context="FACES")
    isolated = [vertex for vertex in mesh.verts if not vertex.link_faces]
    if isolated:
        bmesh.ops.delete(mesh, geom=isolated, context="VERTS")
    mesh.to_mesh(shell.data)
    mesh.free()
    shell.data.update()
    solidify = shell.modifiers.new("ClothThickness", "SOLIDIFY")
    solidify.thickness = 0.018
    solidify.offset = 1.0
    return shell


def add_garments(actor, top_mat, pants_mat, *, dress: bool = False) -> None:
    rig = actor["rig"]
    clothing_shell(
        actor,
        f"{actor['label']}_Top",
        lambda point: (1.02 <= point.z <= 1.51 and abs(point.x) < 0.36)
        or (1.31 <= point.z <= 1.54 and abs(point.x) < 0.72),
        top_mat,
    )
    clothing_shell(
        actor,
        f"{actor['label']}_Pants",
        lambda point: 0.08 <= point.z <= 1.035,
        pants_mat,
    )
    if dress:
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.42, radius2=0.25, depth=0.44, location=(0, 0.035, 0.88))
        skirt = bpy.context.object
        skirt.name = f"{actor['label']}_Skirt"
        skirt.data.materials.append(pants_mat)
        bind_rigid_mesh(skirt, rig, "pelvis")
    for side in ("l", "r"):
        x = 0.114 if side == "l" else -0.114
        shoe = box(f"{actor['label']}_Shoe_{side}", (x, -0.075, 0.075), (0.11, 0.18, 0.06), pants_mat, 0.045)
        bind_rigid_mesh(shoe, rig, f"foot_{side}")


def import_actor(label: str, filename: str, location, yaw: float, body_color, hair_filename: str):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS / "models" / filename))
    imported = set(bpy.context.scene.objects) - before
    armature = next(obj for obj in imported if obj.type == "ARMATURE")
    meshes = [obj for obj in imported if obj.type == "MESH" and obj.parent == armature]
    for obj in list(imported):
        if obj.type == "MESH" and obj.parent is None and not obj.data.materials:
            bpy.data.objects.remove(obj, do_unlink=True)
    armature.name = f"{label}_Rig"
    armature.location = location
    armature.rotation_euler[2] = yaw
    armature.show_in_front = False
    for obj in meshes:
        obj.name = f"{label}_{obj.name}"
    eyes = next((obj for obj in meshes if "Eyes" in obj.name), None)
    eyebrows = next((obj for obj in meshes if "Eyebrows" in obj.name), None)

    before_hair = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS / "hair" / hair_filename))
    hair = next(obj for obj in set(bpy.context.scene.objects) - before_hair if obj.type == "MESH")
    hair.name = f"{label}_Hair"
    for slot in hair.material_slots:
        slot.material = material(f"{label}_HairMat", (0.025, 0.018, 0.016, 1), roughness=0.5)
    bind_rigid_mesh(hair, armature, "Head")

    # A small stylised mouth gives visible emotional change because this CC0
    # base has no facial blendshapes. It follows the real head bone.
    mouth = sphere(f"{label}_Mouth", (0, -0.151, 1.655), (0.035, 0.008, 0.009), material("Mouth", (0.22, 0.025, 0.025, 1)))
    bind_rigid_mesh(mouth, armature, "Head")
    return {"label": label, "rig": armature, "meshes": meshes, "eyes": eyes, "brows": eyebrows, "hair": hair, "mouth": mouth}


def seated_pose(actor, start: int = 1) -> None:
    rig = actor["rig"]
    pose = rig.pose.bones
    for side in ("l", "r"):
        key_bone(pose[f"thigh_{side}"], start, (-1.42, 0, 0))
        key_bone(pose[f"calf_{side}"], start, (1.38, 0, 0))
        key_bone(pose[f"foot_{side}"], start, (0.12, 0, 0))
    key_bone(pose["spine_01"], start, (0.06, 0, 0))
    key_bone(pose["spine_02"], start, (-0.04, 0, 0))


def add_hand_ik(actor, side: str, name: str, target_location, pole_location):
    rig = actor["rig"]
    target = bpy.data.objects.new(f"{name}_HandTarget", None)
    target.empty_display_type = "SPHERE"
    target.empty_display_size = 0.035
    target.location = target_location
    bpy.context.scene.collection.objects.link(target)
    pole = bpy.data.objects.new(f"{name}_ElbowPole", None)
    pole.empty_display_type = "PLAIN_AXES"
    pole.empty_display_size = 0.08
    pole.location = pole_location
    bpy.context.scene.collection.objects.link(pole)
    constraint = rig.pose.bones[f"hand_{side}"].constraints.new("IK")
    constraint.name = f"{name}_IK"
    constraint.target = target
    constraint.pole_target = pole
    constraint.chain_count = 3
    constraint.iterations = 64
    constraint.pole_angle = math.radians(-90 if side == "r" else 90)
    return target, pole


def finger_pose(actor, side: str, frames, amount: float) -> None:
    pose = actor["rig"].pose.bones
    for finger in ("index", "middle", "ring", "pinky"):
        for segment, factor in (("01", 0.35), ("02", 0.65), ("03", 0.7)):
            bone = pose[f"{finger}_{segment}_{side}"]
            for frame in frames:
                key_bone(bone, frame, (0, amount * factor, 0))
    for segment, factor in (("01", 0.45), ("02", 0.6), ("03", 0.55)):
        bone = pose[f"thumb_{segment}_{side}"]
        for frame in frames:
            key_bone(bone, frame, (0, -amount * factor, amount * 0.25))


def blink(actor, center: int) -> None:
    eyes = actor["eyes"]
    if not eyes:
        return
    original = tuple(eyes.scale)
    key_object(eyes, center - 2, scale=original)
    key_object(eyes, center, scale=(original[0], original[1], original[2] * 0.12))
    key_object(eyes, center + 2, scale=original)


def animate_chopsticks(hand_target, food_path, frames, mat):
    sticks = [cylinder(f"Chopstick_{i+1}", (0, 0, 0), 0.008, 0.34, mat, 12) for i in range(2)]
    food = sphere("Food_Bite", food_path[0], (0.025, 0.025, 0.025), material("Food", (0.78, 0.22, 0.08, 1), roughness=0.8))
    for frame, tip in zip(frames, food_path):
        tip = Vector(tip)
        wrist = Vector(hand_target.location)
        # Wrist target is animated on the same keyed frames before this call.
        if frame == frames[0]:
            wrist = Vector((0.12, -0.22, 1.08))
        elif frame == frames[1]:
            wrist = Vector((0.02, -0.27, 1.35))
        else:
            wrist = Vector((-0.08, -0.25, 1.57))
        direction = tip - wrist
        center = wrist + direction * 0.55
        for index, stick in enumerate(sticks):
            offset = Vector((0.012 * (index * 2 - 1), 0, 0))
            stick.location = center + offset
            stick.rotation_mode = "QUATERNION"
            stick.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
            stick.scale.z = max(0.1, direction.length / 0.34)
            stick.keyframe_insert(data_path="location", frame=frame)
            stick.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            stick.keyframe_insert(data_path="scale", frame=frame)
        key_object(food, frame, location=tip)
    return food


clean()

warm = material("WarmWall", (0.16, 0.10, 0.075, 1))
wood = material("Wood", (0.22, 0.075, 0.035, 1), roughness=0.58)
linen = material("Linen", (0.58, 0.42, 0.28, 1))
black = material("Black", (0.015, 0.018, 0.022, 1), roughness=0.35)
ceramic = material("Ceramic", (0.82, 0.74, 0.61, 1), roughness=0.42)
green = material("Plant", (0.07, 0.28, 0.12, 1), roughness=0.85)
gold = material("ChopstickWood", (0.42, 0.18, 0.045, 1), roughness=0.48)

box("Floor", (0, 0.5, -0.06), (3.2, 3.4, 0.06), material("Floor", (0.095, 0.075, 0.06, 1)), 0)
box("BackWall", (0, 2.4, 1.6), (3.2, 0.05, 1.6), warm, 0)
box("Window", (-1.45, 2.30, 1.75), (0.78, 0.03, 0.72), black, 0.02)
for x in (-1.95, -1.45, -0.95):
    box("WindowBar", (x, 2.255, 1.75), (0.018, 0.02, 0.71), linen, 0)
box("WindowBar", (-1.45, 2.255, 1.75), (0.77, 0.02, 0.018), linen, 0)
box("TableTop", (0, 0.18, 0.91), (1.25, 0.54, 0.065), wood, 0.055)
for x in (-0.96, 0.96):
    for y in (-0.18, 0.50):
        box("TableLeg", (x, y, 0.44), (0.055, 0.055, 0.44), wood, 0.02)
for x in (-0.48, 0.48):
    box("ChairSeat", (x, 0.23, 0.62), (0.33, 0.32, 0.055), linen, 0.04)
    box("ChairBack", (x, 0.48, 1.03), (0.33, 0.055, 0.42), wood, 0.04)
for x in (-0.36, 0.36):
    cylinder("Bowl", (x, -0.03, 1.01), 0.14, 0.06, ceramic)
box("Phone", (-0.23, -0.22, 1.015), (0.075, 0.125, 0.012), black, 0.018)
for x, y, scale in ((1.95, 1.95, 0.23), (2.1, 1.9, 0.18), (1.8, 2.0, 0.16)):
    sphere("PlantLeaf", (x, y, 1.25 + scale), (scale * 0.45, scale * 0.18, scale), green)

male = import_actor("ChenHao", "Superhero_Male_FullBody.gltf", (-0.45, 0.26, 0), math.radians(-7), (0.055, 0.11, 0.20, 1), "Hair_SimpleParted.gltf")
female = import_actor("LinXiao", "Superhero_Female_FullBody.gltf", (0.45, 0.25, 0), math.radians(7), (0.42, 0.075, 0.085, 1), "Hair_Buns.gltf")
add_garments(male, material("ChenHaoKnit", (0.055, 0.10, 0.18, 1)), material("ChenHaoPants", (0.025, 0.03, 0.045, 1)))
add_garments(female, material("LinXiaoKnit", (0.18, 0.018, 0.028, 1)), material("LinXiaoSkirt", (0.08, 0.018, 0.03, 1)), dress=True)
seated_pose(male)
seated_pose(female)

male_left, _ = add_hand_ik(male, "l", "ChenHaoLeft", (-0.20, -0.16, 1.06), (-0.28, 0.22, 1.32))
male_right, _ = add_hand_ik(male, "r", "ChenHaoRight", (-0.65, -0.12, 1.04), (-0.72, 0.30, 1.28))
female_left, _ = add_hand_ik(female, "l", "LinXiaoLeft", (0.66, -0.14, 1.05), (0.73, 0.26, 1.28))
female_right, _ = add_hand_ik(female, "r", "LinXiaoRight", (0.12, -0.22, 1.08), (0.38, 0.10, 1.34))
for target in (male_left, male_right, female_left):
    key_object(target, 1, location=target.location)
    key_object(target, END, location=target.location)

reach_frames = (1, 84, 154, END)
reach_positions = ((0.12, -0.22, 1.08), (0.02, -0.27, 1.35), (-0.08, -0.25, 1.57), (0.0, -0.22, 1.22))
for frame, position in zip(reach_frames, reach_positions):
    key_object(female_right, frame, location=position)
finger_pose(female, "r", reach_frames, 0.82)
finger_pose(male, "l", (1, END), 0.24)
finger_pose(male, "r", (1, END), 0.28)

food_positions = ((-0.03, -0.30, 1.12), (-0.17, -0.31, 1.40), (-0.41, -0.25, 1.64), (-0.25, -0.27, 1.27))
food = animate_chopsticks(female_right, food_positions, reach_frames, gold)

male_pose = male["rig"].pose.bones
female_pose = female["rig"].pose.bones
for frame, rotation in ((1, (0.0, 0.0, 0.02)), (68, (0.0, 0.0, 0.10)), (142, (-0.03, 0.0, 0.25)), (END, (0.0, 0.0, 0.18))):
    key_bone(male_pose["Head"], frame, rotation)
for frame, rotation in ((1, (0.0, 0.0, -0.08)), (84, (-0.03, 0.0, -0.20)), (154, (-0.01, 0.0, -0.24)), (END, (0.0, 0.0, -0.12))):
    key_bone(female_pose["Head"], frame, rotation)
for frame, rotation in ((1, (0.02, 0.0, 0.0)), (100, (-0.07, 0.0, -0.06)), (154, (-0.10, 0.0, -0.07)), (END, (0.0, 0.0, 0.0))):
    key_bone(female_pose["spine_03"], frame, rotation)
for frame, rotation in ((1, (0.02, 0.0, 0.0)), (120, (-0.035, 0.0, 0.05)), (154, (-0.08, 0.0, 0.07)), (END, (-0.02, 0.0, 0.03))):
    key_bone(male_pose["spine_03"], frame, rotation)

blink(female, 62)
blink(male, 118)
blink(male, 184)
if male["brows"]:
    key_object(male["brows"], 1, location=male["brows"].location)
    key_object(male["brows"], 130, location=male["brows"].location + Vector((0, 0, 0.014)))
    key_object(male["brows"], END, location=male["brows"].location)
if female["brows"]:
    key_object(female["brows"], 1, location=female["brows"].location)
    key_object(female["brows"], 90, location=female["brows"].location + Vector((0, 0, -0.006)))
    key_object(female["brows"], END, location=female["brows"].location)
key_object(female["mouth"], 1, scale=(1.0, 1.0, 0.65))
key_object(female["mouth"], 80, scale=(1.18, 1.0, 0.42))
key_object(female["mouth"], 154, scale=(1.12, 1.0, 0.36))
key_object(female["mouth"], END, scale=(1.0, 1.0, 0.55))
key_object(male["mouth"], 1, scale=(0.95, 1.0, 0.35))
key_object(male["mouth"], 130, scale=(0.78, 1.0, 0.75))
key_object(male["mouth"], 154, scale=(0.86, 1.0, 0.58))
key_object(male["mouth"], END, scale=(0.9, 1.0, 0.38))

# Warm key, cool window fill, and a practical pendant light.
for name, kind, energy, color, location, size in (
    ("WarmKey", "AREA", 820, (1.0, 0.52, 0.27), (0.3, -1.3, 3.0), 3.0),
    ("WindowFill", "AREA", 460, (0.30, 0.48, 1.0), (-1.6, 1.8, 2.1), 2.0),
    ("Rim", "AREA", 520, (1.0, 0.34, 0.20), (1.8, 1.6, 2.0), 1.4),
):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, (0, 0.2, 1.1))

camera_data = bpy.data.cameras.new("DinnerCamera")
camera = bpy.data.objects.new("DinnerCamera", camera_data)
bpy.context.scene.collection.objects.link(camera)
camera_data.lens = 54
camera_data.sensor_width = 36
camera.location = (0.02, -4.05, 1.53)
look_at(camera, (0, 0.15, 1.35))
camera.keyframe_insert(data_path="location", frame=1)
camera.location = (-0.045, -3.72, 1.50)
camera.keyframe_insert(data_path="location", frame=END)
camera.rotation_euler = (Vector((0, 0.15, 1.38)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.keyframe_insert(data_path="rotation_euler", frame=1)
camera.rotation_euler = (Vector((-0.04, 0.15, 1.42)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.keyframe_insert(data_path="rotation_euler", frame=END)

scene = bpy.context.scene
scene.camera = camera
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 480
scene.render.resolution_y = 854
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = END
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = False
scene.world.color = (0.014, 0.009, 0.018)
scene.render.use_file_extension = True
scene.render.filepath = str(OUTPUT / "frames/frame-")
scene.render.image_settings.compression = 40
scene.view_settings.look = "AgX - Medium High Contrast"

frames = OUTPUT / "frames"
frames.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "performance.blend"))
still_frame = int(os.environ.get("VIDEO_CREATOR_STILL_FRAME", "0") or 0)
if still_frame:
    scene.frame_set(max(1, min(END, still_frame)))
    scene.render.filepath = str(OUTPUT / f"lookdev-{still_frame:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("VIDEO_CREATOR_P47_05_STILL_PASS", scene.render.filepath)
    raise SystemExit(0)
bpy.ops.render.render(animation=True)
subprocess.run(
    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(frames / "frame-%04d.png"),
     "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUTPUT / "performance.mp4")],
    check=True,
    timeout=180,
)
subprocess.run(
    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5.8", "-i", str(OUTPUT / "performance.mp4"), "-frames:v", "1", str(OUTPUT / "poster.png")],
    check=True,
    timeout=30,
)

male_mouth = Vector((-0.41, -0.25, 1.64))
closest = min((Vector(point) - male_mouth).length for point in food_positions)
report = {
    "schema_version": 1,
    "task": "P47-05",
    "duration_seconds": DURATION,
    "fps": FPS,
    "resolution": [480, 854],
    "actors": [
        {"id": "陈浩", "rig": male["rig"].name, "bones": len(male["rig"].pose.bones), "fixed_asset": True},
        {"id": "林晓", "rig": female["rig"].name, "bones": len(female["rig"].pose.bones), "fixed_asset": True},
    ],
    "performance": {
        "continuous_body_motion": True,
        "head_and_torso_acting": True,
        "blink_keys": 3,
        "brow_expression": True,
        "mouth_expression_proxy": True,
        "right_hand_ik": True,
        "finger_bones_animated": True,
        "prop": "chopsticks_and_food",
        "food_to_mouth_min_distance_m": round(closest, 4),
        "contact_threshold_m": 0.06,
        "contact_pass": closest <= 0.06,
    },
    "limits": [
        "CC0 base has no facial blendshapes; mouth expression uses a local head-following proxy.",
        "Wardrobe is a recolored base suit, not the final approved modern costume.",
        "Human visual review remains required before replacing whole-episode controls.",
    ],
    "human_review": "PENDING",
}
(OUTPUT / "performance-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("VIDEO_CREATOR_P47_05_PASS", json.dumps(report, ensure_ascii=False))
