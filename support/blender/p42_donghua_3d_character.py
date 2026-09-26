"""Build the P42 local 3D donghua character and a continuous Rigify motion shot.

Run with the rejected P39 blend opened as the source.  The script reuses only
the weighted MPFB body and Rigify rig, then replaces the complete lookdev.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


FPS = 24
FRAME_END = 96
WIDTH = 480
HEIGHT = 854


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--character-id", default="CHR-N0DBC8F583-AUTO-001")
    parser.add_argument("--preview-only", action="store_true")
    return parser.parse_args(values)


def material(name: str, color: tuple[float, float, float], *, metallic: float = 0.0,
             roughness: float = 0.55, emission: tuple[float, float, float] | None = None,
             emission_strength: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if "Coat Weight" in shader.inputs:
        shader.inputs["Coat Weight"].default_value = 0.12
    if emission is not None:
        emission_input = shader.inputs.get("Emission Color") or shader.inputs.get("Emission")
        strength_input = shader.inputs.get("Emission Strength")
        if emission_input:
            emission_input.default_value = (*emission, 1.0)
        if strength_input:
            strength_input.default_value = emission_strength
    return mat


def add_fabric_surface(mat: bpy.types.Material) -> None:
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 85.0
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = .62
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .12
    bump.inputs["Distance"].default_value = .025
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])


def smooth(obj: bpy.types.Object) -> None:
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def add_modifiers(obj: bpy.types.Object, *, solidify: float = 0.0, bevel: float = 0.0,
                  subdivision: int = 0) -> None:
    if solidify:
        modifier = obj.modifiers.new("Fabric thickness", "SOLIDIFY")
        modifier.thickness = solidify
        modifier.offset = 0.0
    if bevel:
        modifier = obj.modifiers.new("Soft tailored edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    if subdivision:
        modifier = obj.modifiers.new("Tailored subdivision", "SUBSURF")
        modifier.levels = subdivision
        modifier.render_levels = subdivision


def mesh_object(name: str, vertices, faces, mat: bpy.types.Material) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    smooth(obj)
    return obj


def _distance_to_segment(point: Vector, start: Vector, end: Vector) -> float:
    segment = end - start
    if segment.length_squared < 1e-10:
        return (point - start).length
    amount = max(0.0, min(1.0, (point - start).dot(segment) / segment.length_squared))
    return (point - (start + segment * amount)).length


def repair_body_weights(body: bpy.types.Object, rig: bpy.types.Object) -> int:
    """Replace P39's empty DEF groups with deterministic major-bone weights."""
    for group in list(body.vertex_groups):
        if group.name.startswith("DEF-"):
            body.vertex_groups.remove(group)
    prefixes = (
        "DEF-spine", "DEF-pelvis", "DEF-thigh", "DEF-shin", "DEF-foot", "DEF-toe",
        "DEF-shoulder", "DEF-upper_arm", "DEF-forearm", "DEF-hand",
    )
    bones = [bone for bone in rig.data.bones if bone.use_deform and bone.name.startswith(prefixes)]
    if len(bones) < 20:
        raise RuntimeError(f"insufficient major deform bones: {len(bones)}")
    groups = {bone.name: body.vertex_groups.new(name=bone.name) for bone in bones}
    head_name = "DEF-spine.006"
    if head_name not in groups:
        raise RuntimeError("Rigify head deform bone missing")
    bm = bmesh.new()
    bm.from_mesh(body.data)
    deform = bm.verts.layers.deform.verify()
    bone_data = [(bone.name, bone.head_local.copy(), bone.tail_local.copy()) for bone in bones]
    for vertex in bm.verts:
        weights = vertex[deform]
        if vertex.co.z >= 1.385:
            weights[groups[head_name].index] = 1.0
            continue
        nearest = sorted(
            ((_distance_to_segment(vertex.co, start, end), name) for name, start, end in bone_data),
            key=lambda item: item[0],
        )[:3]
        raw = [(name, 1.0 / max(distance, .018) ** 2) for distance, name in nearest]
        total = sum(weight for _, weight in raw)
        for name, weight in raw:
            weights[groups[name].index] = weight / total
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return len(body.data.vertices)


def parent_to_bone(obj: bpy.types.Object, rig: bpy.types.Object, bone: str) -> None:
    """Rigid-skin an accessory to one deform bone in the rig's mesh space."""
    if obj.type == "CURVE":
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.convert(target="MESH")
    if obj.type != "MESH":
        raise RuntimeError(f"cannot bind non-mesh accessory: {obj.name}")
    group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
    group.add([vertex.index for vertex in obj.data.vertices], 1.0, "REPLACE")
    modifier = obj.modifiers.new("P42 Rigify binding", "ARMATURE")
    modifier.object = rig


def ring_shell(name: str, profiles, mat: bpy.types.Material, *, sides: int = 48,
               opening: float = 0.0) -> bpy.types.Object:
    vertices = []
    faces = []
    angles = []
    for index in range(sides + 1):
        amount = index / sides
        angle = opening / 2.0 + amount * (math.tau - opening)
        angles.append(angle)
    for z, radius_x, radius_y in profiles:
        for angle in angles:
            vertices.append((radius_x * math.sin(angle), -radius_y * math.cos(angle), z))
    row_size = len(angles)
    for row in range(len(profiles) - 1):
        for index in range(row_size - 1):
            a = row * row_size + index
            b = a + 1
            faces.append((a, b, b + row_size, a + row_size))
    obj = mesh_object(name, vertices, faces, mat)
    add_modifiers(obj, solidify=0.012, bevel=0.008, subdivision=1)
    return obj


def robe_panel(name: str, x0: float, x1: float, y: float, z_top: float, z_bottom: float,
               mat: bpy.types.Material, *, bow: float = 0.05, rows: int = 9) -> bpy.types.Object:
    vertices = []
    for row in range(rows + 1):
        amount = row / rows
        z = z_top + (z_bottom - z_top) * amount
        width_scale = 1.0 + 0.48 * amount
        center = (x0 + x1) / 2.0
        half = (x1 - x0) / 2.0 * width_scale
        ripple = math.sin(amount * math.pi * 2.3) * 0.018
        vertices.extend(((center - half, y - bow * amount + ripple, z),
                         (center + half, y - bow * amount - ripple, z)))
    faces = []
    for row in range(rows):
        a = row * 2
        faces.append((a, a + 1, a + 3, a + 2))
    obj = mesh_object(name, vertices, faces, mat)
    add_modifiers(obj, solidify=0.012, bevel=0.01, subdivision=1)
    return obj


def curve_strand(name: str, points, mat: bpy.types.Material, *, thickness: float = 0.012,
                 cyclic: bool = False) -> bpy.types.Object:
    curve = bpy.data.curves.new(name + "Curve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = thickness
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, value in zip(spline.bezier_points, points):
        point.co = value
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def add_uv_sphere(name: str, location, scale, mat: bpy.types.Material, *, segments: int = 32,
                  rings: int = 20) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    # Bone parenting can otherwise evaluate a stale primitive matrix and
    # restore unit scale, turning small facial/hair parts into giant spheres.
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.select_set(False)
    smooth(obj)
    return obj


def replace_lookdev(body: bpy.types.Object, rig: bpy.types.Object) -> list[bpy.types.Object]:
    for obj in list(bpy.data.objects):
        if obj.name.startswith("LuZhao_") and obj != body:
            bpy.data.objects.remove(obj, do_unlink=True)

    skin = material("P42_Skin", (0.36, 0.16, 0.10), roughness=0.72)
    ink = material("P42_InkBlack", (0.012, 0.018, 0.030), roughness=0.46)
    charcoal = material("P42_CharcoalSilk", (0.028, 0.042, 0.070), roughness=0.48)
    red = material("P42_CinnabarSilk", (0.31, 0.025, 0.035), roughness=0.44)
    gold = material("P42_AntiqueGold", (0.52, 0.27, 0.055), metallic=0.72, roughness=0.33)
    ivory = material("P42_Ivory", (0.80, 0.73, 0.60), roughness=0.60)
    white = material("P42_EyeWhite", (0.92, 0.90, 0.84), roughness=0.34)
    iris = material("P42_WarmIris", (0.12, 0.025, 0.018), roughness=0.28)
    add_fabric_surface(charcoal)
    add_fabric_surface(red)

    body.data.materials.clear()
    body.data.materials.append(skin)
    body.data.materials.append(charcoal)
    # Use the weighted body itself for fitted sleeves, trousers and boots.
    for polygon in body.data.polygons:
        center = polygon.center
        visible_skin = center.z > 1.39 or (abs(center.x) > 0.43 and center.z > 0.82)
        polygon.material_index = 0 if visible_skin else 1
    smooth(body)
    if not any(mod.type == "SUBSURF" for mod in body.modifiers):
        add_modifiers(body, subdivision=1)

    parts: list[bpy.types.Object] = []
    jacket = ring_shell(
        "P42_TailoredJacket",
        ((0.82, .245, .165), (1.00, .265, .175), (1.20, .285, .182), (1.35, .245, .165)),
        charcoal,
        opening=0.48,
    )
    parent_to_bone(jacket, rig, "DEF-spine.003")
    parts.append(jacket)

    sash = ring_shell("P42_WaistSash", ((.91, .258, .177), (.99, .265, .183), (1.05, .252, .176)), red, sides=48)
    parent_to_bone(sash, rig, "DEF-spine.002")
    parts.append(sash)

    left_panel = robe_panel("P42_RobePanel_L", -.28, -.015, -.186, .98, .12, charcoal, bow=.075)
    right_panel = robe_panel("P42_RobePanel_R", .015, .28, -.186, .98, .12, charcoal, bow=.075)
    inner_panel = robe_panel("P42_RobePanel_Inner", -.12, .12, -.204, .96, .18, red, bow=.088)
    back_panel = robe_panel("P42_RobePanel_Back", -.24, .24, .155, .98, .18, ink, bow=-.04)
    for panel in (left_panel, right_panel, inner_panel, back_panel):
        parent_to_bone(panel, rig, "DEF-spine.002")
        parts.append(panel)

    # Cross collar and front embroidery lines.
    for index, points in enumerate((
        ((-.19, -.194, 1.34), (-.02, -.217, 1.18), (.12, -.208, 1.04)),
        ((.19, -.194, 1.34), (.03, -.221, 1.18), (-.08, -.211, 1.07)),
    )):
        strand = curve_strand(f"P42_Collar_{index}", points, ivory if index == 0 else red, thickness=.011)
        parent_to_bone(strand, rig, "DEF-spine.003")
        parts.append(strand)
    for x in (-.235, .235):
        edge = curve_strand(f"P42_GoldEdge_{'L' if x < 0 else 'R'}", ((x, -.202, .94), (x * 1.18, -.237, .52), (x * 1.42, -.255, .16)), gold, thickness=.009)
        parent_to_bone(edge, rig, "DEF-spine.002")
        parts.append(edge)

    # Cuffs follow the actual forearm bones; the weighted fitted sleeves remain underneath.
    for side, sign in (("L", -1), ("R", 1)):
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=.052, radius2=.075, depth=.15,
                                        location=(sign * .48, -.01, 1.01), rotation=(0.0, math.pi / 2.0, 0.0))
        cuff = bpy.context.object
        cuff.name = f"P42_WideCuff_{side}"
        cuff.data.materials.append(charcoal)
        smooth(cuff)
        add_modifiers(cuff, bevel=.008)
        parent_to_bone(cuff, rig, f"DEF-forearm.{side}")
        parts.append(cuff)

    # Restrained scalp volume plus individual hair ribbons gives a readable 3D silhouette.
    cap = add_uv_sphere("P42_HairCap", (0.0, .005, 1.565), (.112, .102, .142), ink)
    parent_to_bone(cap, rig, "DEF-spine.006")
    parts.append(cap)
    hair_paths = [
        ((-.075, -.112, 1.66), (-.085, -.174, 1.59), (-.070, -.187, 1.50)),
        ((-.035, -.125, 1.67), (-.043, -.184, 1.60), (-.028, -.192, 1.52)),
        ((.010, -.128, 1.67), (.004, -.188, 1.60), (.020, -.190, 1.51)),
        ((.055, -.116, 1.66), (.065, -.180, 1.59), (.075, -.179, 1.49)),
        ((-.095, -.02, 1.62), (-.135, -.04, 1.48), (-.145, .00, 1.30)),
        ((.095, -.02, 1.62), (.135, -.04, 1.48), (.145, .00, 1.30)),
        ((-.055, .07, 1.63), (-.08, .12, 1.40), (-.10, .13, 1.12)),
        ((.055, .07, 1.63), (.08, .12, 1.40), (.10, .13, 1.12)),
    ]
    for index, points in enumerate(hair_paths):
        strand = curve_strand(f"P42_HairStrand_{index:02d}", points, ink, thickness=.008 if index < 4 else .013)
        parent_to_bone(strand, rig, "DEF-spine.006")
        parts.append(strand)
    knot = add_uv_sphere("P42_HairKnot", (0.0, .025, 1.708), (.060, .055, .078), ink, segments=28, rings=16)
    parent_to_bone(knot, rig, "DEF-spine.006")
    parts.append(knot)
    ornament = add_uv_sphere("P42_HairOrnament", (0.0, -.014, 1.742), (.019, .014, .044), gold, segments=20, rings=12)
    parent_to_bone(ornament, rig, "DEF-spine.006")
    parts.append(ornament)

    return parts


def add_cube(name: str, location, scale, mat: bpy.types.Material, bevel: float = 0.0) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    if bevel:
        add_modifiers(obj, bevel=bevel)
    return obj


def build_stage() -> None:
    wood = material("P42_SetWood", (0.12, 0.025, 0.018), roughness=.58)
    stone = material("P42_SetStone", (0.055, 0.072, 0.085), roughness=.82)
    bronze = material("P42_SetBronze", (0.23, 0.095, 0.025), metallic=.44, roughness=.42)
    lantern_mat = material("P42_LanternGlow", (0.58, 0.09, 0.025), roughness=.38,
                           emission=(1.0, .18, .035), emission_strength=5.0)
    floor = add_cube("P42_WetStoneFloor", (0, 0, -.055), (4.0, 4.0, .05), stone, .025)
    floor.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .32
    for x in (-1.25, 1.25):
        add_cube(f"P42_GateColumn_{x}", (x, .72, 1.05), (.16, .16, 1.15), wood, .025)
    add_cube("P42_GateBeam", (0, .72, 2.05), (1.6, .19, .17), wood, .03)
    add_cube("P42_UpperBeam", (0, .74, 2.36), (1.9, .22, .10), wood, .02)
    for x in (-.83, .83):
        lantern = add_uv_sphere(f"P42_Lantern_{x}", (x, .48, 1.62), (.13, .10, .19), lantern_mat, segments=24, rings=12)
        add_cube(f"P42_LanternCap_{x}", (x, .48, 1.83), (.06, .05, .025), bronze, .01)
        bpy.ops.object.light_add(type="POINT", location=(x, .28, 1.60))
        light = bpy.context.object
        light.name = f"P42_LanternLight_{x}"
        light.data.energy = 120
        light.data.color = (1.0, .24, .07)
        light.data.shadow_soft_size = .7


def insert_bone_key(rig: bpy.types.Object, frame: int, rotations: dict[str, tuple[float, float, float]],
                    locations: dict[str, tuple[float, float, float]]) -> None:
    for name, value in rotations.items():
        bone = rig.pose.bones.get(name)
        if bone is None:
            continue
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = value
        bone.keyframe_insert(data_path="rotation_euler", frame=frame, group="P42 Continuous Motion")
    for name, value in locations.items():
        bone = rig.pose.bones.get(name)
        if bone is None:
            continue
        bone.location = value
        bone.keyframe_insert(data_path="location", frame=frame, group="P42 Continuous Motion")


def insert_hand_target(rig: bpy.types.Object, frame: int, name: str,
                       position: tuple[float, float, float]) -> None:
    """Key an IK hand target in armature space for predictable screen motion."""
    bone = rig.pose.bones.get(name)
    if bone is None:
        raise RuntimeError(f"missing IK control: {name}")
    matrix = bone.matrix.copy()
    matrix.translation = Vector(position)
    bone.matrix = matrix
    bone.keyframe_insert(data_path="location", frame=frame, group="P42 Continuous Motion")
    if bone.rotation_mode == "QUATERNION":
        bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group="P42 Continuous Motion")
    else:
        bone.keyframe_insert(data_path="rotation_euler", frame=frame, group="P42 Continuous Motion")


def animate_character(rig: bpy.types.Object, parts: list[bpy.types.Object]) -> None:
    rig.animation_data_clear()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    for side in ("L", "R"):
        parent = rig.pose.bones.get(f"upper_arm_parent.{side}")
        if parent is not None and "IK_FK" in parent:
            parent["IK_FK"] = 1.0
            parent.keyframe_insert(data_path='["IK_FK"]', frame=1, group="P42 Continuous Motion")
            parent.keyframe_insert(data_path='["IK_FK"]', frame=FRAME_END, group="P42 Continuous Motion")
    poses = {
        1: {
            "rot": {"root": (0, 0, 0), "torso": (0, 0, 0), "chest": (0, 0, 0), "head": (0, 0, 0),
                    "upper_arm_fk.L": (0, 0, .12), "upper_arm_fk.R": (0, 0, -.12),
                    "forearm_fk.L": (0, 0, 0), "forearm_fk.R": (0, 0, 0)},
            "loc": {"root": (0, 0, 0), "foot_ik.L": (0, -.08, 0), "foot_ik.R": (0, .08, 0)},
        },
        24: {
            "rot": {"root": (0, 0, -.03), "torso": (.03, 0, -.06), "chest": (0, .03, -.04), "head": (-.08, .02, .05),
                    "upper_arm_fk.L": (-.06, -.10, .20), "upper_arm_fk.R": (-.18, .54, -.34),
                    "forearm_fk.L": (0, 0, -.10), "forearm_fk.R": (-.18, .72, -.12),
                    "hand_fk.R": (0, .18, -.10)},
            "loc": {"root": (0, -.025, .008), "foot_ik.L": (0, -.08, 0), "foot_ik.R": (0, .08, 0)},
        },
        48: {
            "rot": {"root": (.04, 0, -.10), "torso": (-.14, .02, -.15), "chest": (-.10, .05, -.13), "head": (-.16, .05, .18),
                    "upper_arm_fk.L": (-.15, -.45, .36), "upper_arm_fk.R": (-.25, .45, -.48),
                    "forearm_fk.L": (.08, -.52, .18), "forearm_fk.R": (-.12, .60, -.18),
                    "hand_fk.L": (0, -.18, .10), "hand_fk.R": (0, .22, -.14)},
            "loc": {"root": (.025, .055, .018), "foot_ik.L": (0, -.12, 0), "foot_ik.R": (0, .14, .055)},
        },
        72: {
            "rot": {"root": (0, 0, .18), "torso": (.02, -.02, .24), "chest": (.02, -.04, .18), "head": (-.07, -.06, -.28),
                    "upper_arm_fk.L": (-.08, -.25, .30), "upper_arm_fk.R": (-.12, .20, -.26),
                    "forearm_fk.L": (.03, -.36, .10), "forearm_fk.R": (-.05, .34, -.12)},
            "loc": {"root": (-.035, .09, .012), "foot_ik.L": (0, -.15, .045), "foot_ik.R": (0, .16, 0)},
        },
        96: {
            "rot": {"root": (0, 0, .12), "torso": (0, 0, .14), "chest": (0, -.02, .10), "head": (-.05, -.02, -.18),
                    "upper_arm_fk.L": (-.03, -.12, .18), "upper_arm_fk.R": (-.05, .10, -.18),
                    "forearm_fk.L": (0, -.14, .04), "forearm_fk.R": (0, .16, -.04)},
            "loc": {"root": (-.025, .075, 0), "foot_ik.L": (0, -.13, 0), "foot_ik.R": (0, .15, 0)},
        },
    }
    for frame, pose in poses.items():
        scene.frame_set(frame)
        insert_bone_key(rig, frame, pose["rot"], pose["loc"])
    hand_targets = {
        1: {"hand_ik.L": (.43, -.02, .98), "hand_ik.R": (-.43, -.02, .98)},
        24: {"hand_ik.L": (.38, -.08, 1.08), "hand_ik.R": (-.20, -.24, 1.30)},
        48: {"hand_ik.L": (.27, -.24, 1.23), "hand_ik.R": (-.12, -.30, 1.39)},
        72: {"hand_ik.L": (.30, -.17, 1.28), "hand_ik.R": (-.31, -.12, 1.16)},
        96: {"hand_ik.L": (.39, -.05, 1.07), "hand_ik.R": (-.38, -.05, 1.08)},
    }
    for frame, targets in hand_targets.items():
        scene.frame_set(frame)
        for name, position in targets.items():
            insert_hand_target(rig, frame, name, position)

    # Hair and robe panels retain secondary motion while the skeleton leads.
    secondary = [obj for obj in parts if "RobePanel" in obj.name or "HairStrand" in obj.name]
    for obj in secondary:
        base = obj.rotation_euler.copy()
        for frame, sway in ((1, 0.0), (24, -.025), (48, .10), (72, -.075), (96, .02)):
            obj.rotation_euler = base
            obj.rotation_euler.y += sway * (1.0 if "RobePanel" in obj.name else .55)
            obj.rotation_euler.x += math.sin(frame * .09 + len(obj.name)) * .018
            obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="P42 Secondary Motion")

    # Blender 5 layered Actions no longer expose Action.fcurves directly.
    # Newly inserted keys use Bezier interpolation by default, which is the
    # continuous motion contract required by this pilot.


def setup_render(output_dir: Path) -> bpy.types.Object:
    for obj in list(bpy.data.objects):
        if obj.type in {"LIGHT", "CAMERA"} or obj.name.startswith("P42_Set") or obj.name.startswith("P42_Gate") or obj.name.startswith("P42_Lantern") or obj.name == "P42_WetStoneFloor":
            bpy.data.objects.remove(obj, do_unlink=True)
    build_stage()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.world = bpy.data.worlds.get("P42World") or bpy.data.worlds.new("P42World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (.004, .009, .022, 1.0)
    background.inputs["Strength"].default_value = .28

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.4, 3.8))
    key = bpy.context.object
    key.name = "P42_Key"
    key.data.energy = 680
    key.data.shape = "DISK"
    key.data.size = 3.0
    key.data.color = (1.0, .34, .16)
    bpy.ops.object.light_add(type="AREA", location=(2.4, -1.2, 2.6))
    fill = bpy.context.object
    fill.name = "P42_Fill"
    fill.data.energy = 520
    fill.data.size = 2.6
    fill.data.color = (.16, .28, 1.0)
    bpy.ops.object.light_add(type="AREA", location=(0, 2.2, 3.0))
    rim = bpy.context.object
    rim.name = "P42_Rim"
    rim.data.energy = 850
    rim.data.size = 2.0
    rim.data.color = (1.0, .12, .035)

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 1.27))
    target = bpy.context.object
    target.name = "P42_CameraTarget"
    bpy.ops.object.camera_add(location=(1.05, -2.95, 1.78))
    camera = bpy.context.object
    camera.name = "P42_Camera"
    camera.data.lens = 62
    camera.data.sensor_width = 36
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = target
    camera.data.dof.aperture_fstop = 4.0
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    for frame, location in ((1, (1.05, -2.95, 1.78)), (24, (.65, -2.78, 1.72)),
                            (48, (.18, -2.68, 1.69)), (72, (-.52, -2.78, 1.78)),
                            (96, (-.88, -2.96, 1.86))):
        camera.location = location
        camera.keyframe_insert(data_path="location", frame=frame, group="P42 Camera Orbit")
    scene.camera = camera
    scene.render.filepath = str(output_dir / "p42-3d-donghua-preview.png")
    return camera


def render_video(output_dir: Path) -> Path:
    scene = bpy.context.scene
    frame_dir = output_dir / "p42-frames"
    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True)
    scene.render.filepath = str(frame_dir / "frame-")
    bpy.ops.render.render(animation=True)
    silent = output_dir / "p42-3d-motion-v1-silent.mp4"
    final = output_dir / "p42-3d-motion-v1.mp4"
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    subprocess.run([
        ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-start_number", "1",
        "-i", str(frame_dir / "frame-%04d.png"), "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent),
    ], check=True)
    voice = output_dir.parents[1] / "production-pilot" / "audio" / "pilot-zm_010.wav"
    if voice.is_file():
        subprocess.run([
            ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(voice),
            "-filter_complex", "[1:a]adelay=420|420,volume=1.0[a]", "-map", "0:v", "-map", "[a]",
            "-t", str(FRAME_END / FPS), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", str(final),
        ], check=True)
    else:
        silent.replace(final)
    shutil.rmtree(frame_dir)
    silent.unlink(missing_ok=True)
    return final


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    output_dir = project / "lookdev" / "3d-rigs" / args.character_id / "p42"
    output_dir.mkdir(parents=True, exist_ok=True)
    body = bpy.data.objects.get("P39_MPFB_AsianMale_Body")
    rig = bpy.data.objects.get("P39_Rigify_ControlRig")
    if body is None or rig is None:
        raise RuntimeError("P39 weighted MPFB body and Rigify rig are required")
    weighted_vertices = repair_body_weights(body, rig)
    parts = replace_lookdev(body, rig)
    animate_character(rig, parts)
    setup_render(output_dir)
    preview = output_dir / "p42-3d-donghua-preview.png"
    bpy.context.scene.frame_set(48)
    bpy.context.scene.render.filepath = str(preview)
    bpy.ops.render.render(write_still=True)
    blend = output_dir / "p42-3d-character-v1.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    video = None if args.preview_only else render_video(output_dir)
    manifest = {
        "schema_version": 1,
        "status": "HUMAN_REVIEW_PENDING",
        "review_status": "PENDING",
        "provider": "local_blender_mpfb_rigify_p42",
        "character_id": args.character_id,
        "body_vertices": len(body.data.vertices),
        "weighted_vertices": weighted_vertices,
        "rig_bones": len(rig.data.bones),
        "lookdev_parts": len(parts),
        "continuous_motion": True,
        "motion_method": "Rigify skeleton with Bezier interpolation and secondary robe/hair motion",
        "camera_method": "continuous perspective orbit with tracked focus",
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "frames": FRAME_END,
        "duration_seconds": FRAME_END / FPS,
        "local_only": True,
        "billable": False,
        "preview": str(preview.relative_to(project)),
        "blend": str(blend.relative_to(project)),
        "video": str(video.relative_to(project)) if video else "",
        "limitations": [
            "P42 uses a locally generated MPFB/Rigify character and procedural hanfu; identity still requires human visual review",
            "Robe secondary motion is art-directed bone/object animation rather than a baked cloth simulation",
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("P42_3D_DONGHUA_PASS " + json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
