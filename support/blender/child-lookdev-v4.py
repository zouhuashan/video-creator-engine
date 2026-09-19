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


def smooth(obj):
    if getattr(obj, "data", None) and hasattr(obj.data, "polygons"):
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def principled(name, color, roughness=0.7, metallic=0.0, specular_ior=0.28):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError(f"Principled BSDF missing for {name}")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular_ior
    return mat


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def evaluated_world_bbox_corners(objects):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    corners = []
    for obj in objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        bbox = getattr(evaluated, "bound_box", None)
        if not bbox:
            continue
        for corner in bbox:
            corners.append(evaluated.matrix_world @ Vector(corner))
    if not corners:
        raise RuntimeError("child LookDev auto-frame found no geometry bounds")
    return corners


def auto_frame_character(scene, cam, target, child_objects, safe_margin=0.08):
    bpy.context.view_layer.update()
    corners = evaluated_world_bbox_corners(child_objects)
    min_x = min(point.x for point in corners)
    max_x = max(point.x for point in corners)
    min_y = min(point.y for point in corners)
    max_y = max(point.y for point in corners)
    min_z = min(point.z for point in corners)
    max_z = max(point.z for point in corners)

    center = Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5))
    target.location = center
    cam.location.x = center.x
    cam.location.z = center.z + 0.03
    cam.location.y = min_y - 3.5

    best = None
    for _ in range(80):
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, cam, point) for point in corners]
        xs = [float(co.x) for co in projected]
        ys = [float(co.y) for co in projected]
        zs = [float(co.z) for co in projected]
        bounds = {
            "x_min": min(xs),
            "x_max": max(xs),
            "y_min": min(ys),
            "y_max": max(ys),
            "z_min": min(zs),
            "z_max": max(zs),
        }
        best = bounds
        if (
            bounds["x_min"] >= safe_margin
            and bounds["x_max"] <= 1.0 - safe_margin
            and bounds["y_min"] >= safe_margin
            and bounds["y_max"] <= 1.0 - safe_margin
            and bounds["z_min"] > 0.0
        ):
            return {
                "character_bounds": {
                    "x_min": min_x,
                    "x_max": max_x,
                    "y_min": min_y,
                    "y_max": max_y,
                    "z_min": min_z,
                    "z_max": max_z,
                },
                "camera_bounds": bounds,
                "camera_location": tuple(float(value) for value in cam.location),
                "target": tuple(float(value) for value in target.location),
            }
        cam.location.y -= 0.25

    raise RuntimeError(f"child LookDev v4 auto-frame could not fit character: {best}")


def uv_sphere(name, loc, scale, mat, segments=72, rings=36):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return smooth(obj)


def cube(name, loc, scale, mat, rotation=(0.0,0.0,0.0), bevel=0.03):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new("SoftBevel", "BEVEL")
        mod.width = bevel
        mod.segments = 4
    obj.data.materials.append(mat)
    return obj


def curve_strand(name, points, radii, mat, bevel=0.045):
    curve = bpy.data.curves.new(name + "Curve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 10
    curve.bevel_depth = bevel
    curve.bevel_resolution = 5
    curve.fill_mode = "FULL"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points)-1)
    for bp, co, radius in zip(spline.bezier_points, points, radii):
        bp.co = co
        bp.radius = radius
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def loft_ellipse(name, centers, widths, depths, mat, segments=18, subdiv=2):
    centers = [Vector(c) for c in centers]
    if not (len(centers) == len(widths) == len(depths)):
        raise ValueError("loft arrays must match")
    verts = []
    rings = []
    for i, center in enumerate(centers):
        if i == 0:
            tangent = centers[1] - centers[0]
        elif i == len(centers)-1:
            tangent = centers[-1] - centers[-2]
        else:
            tangent = centers[i+1] - centers[i-1]
        tangent = tangent.normalized()
        # perpendicular direction in image XZ plane
        perp = Vector((-tangent.z, 0.0, tangent.x))
        if perp.length < 1e-6:
            perp = Vector((1.0,0.0,0.0))
        perp.normalize()
        ring = []
        for s in range(segments):
            angle = math.tau * s / segments
            offset = perp * (math.cos(angle) * widths[i]) + Vector((0.0, math.sin(angle) * depths[i], 0.0))
            ring.append(len(verts))
            verts.append(tuple(center + offset))
        rings.append(ring)
    faces = []
    for r in range(len(rings)-1):
        a, b = rings[r], rings[r+1]
        for s in range(segments):
            sn = (s+1) % segments
            faces.append((a[s], a[sn], b[sn], b[s]))
    faces.append(tuple(reversed(rings[0])))
    faces.append(tuple(rings[-1]))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    smooth(obj)
    if subdiv > 0:
        mod = obj.modifiers.new("OrganicSubdivision", "SUBSURF")
        mod.levels = subdiv
        mod.render_levels = subdiv
    return obj


def tapered_head(name, loc, scale, mat):
    obj = uv_sphere(name, loc, scale, mat, 96, 48)
    mesh = obj.data
    zs = [v.co.z for v in mesh.vertices]
    zmin, zmax = min(zs), max(zs)
    span = max(zmax-zmin, 1e-6)
    for v in mesh.vertices:
        t = (v.co.z-zmin)/span
        if t < 0.26:
            factor = 0.70 + 0.31*(t/0.26)
        elif t < 0.68:
            factor = 1.01 + 0.045*math.sin((t-0.26)/0.42*math.pi)
        else:
            factor = 1.00 - 0.025*((t-0.68)/0.32)
        v.co.x *= factor
        if t < 0.22 and v.co.y < 0:
            v.co.y *= 0.91
    mesh.update()
    return obj


def build_face():
    skin = principled("Skin",(0.80,0.53,0.45),0.81,0.0,0.24)
    sclera = principled("Sclera",(0.94,0.95,0.93),0.48,0.0,0.16)
    iris = principled("Iris",(0.065,0.046,0.035),0.32,0.0,0.34)
    pupil = principled("Pupil",(0.006,0.006,0.008),0.22)
    catch = principled("Catch",(1.0,1.0,1.0),0.10)
    lash = principled("Lash",(0.020,0.015,0.018),0.50)
    lip = principled("Lip",(0.32,0.07,0.09),0.60)

    head = tapered_head("ChildHead",(0.0,0.0,2.79),(0.57,0.47,0.61),skin)

    eye_y = -0.462
    for side,x in (("L",-0.198),("R",0.198)):
        uv_sphere(f"Sclera_{side}",(x,eye_y,2.865),(0.112,0.033,0.135),sclera,64,32)
        uv_sphere(f"Iris_{side}",(x,eye_y-0.028,2.858),(0.073,0.016,0.091),iris,56,28)
        uv_sphere(f"Pupil_{side}",(x,eye_y-0.039,2.858),(0.030,0.008,0.044),pupil,40,20)
        uv_sphere(f"Catch_{side}",(x-0.022,eye_y-0.048,2.905),(0.015,0.005,0.021),catch,24,12)
        curve_strand(
            f"UpperLid_{side}",
            [(x-0.10,-0.489,2.928),(x,-0.505,2.978),(x+0.10,-0.489,2.928)],
            [0.75,1.0,0.75],lash,0.010
        )
        curve_strand(
            f"Brow_{side}",
            [(x-0.09,-0.458,3.075),(x,-0.470,3.095),(x+0.09,-0.458,3.073)],
            [0.7,1.0,0.7],lash,0.008
        )

    uv_sphere("Nose",(0.0,-0.470,2.665),(0.023,0.012,0.032),skin,28,14)
    curve_strand("Mouth",[(-0.065,-0.479,2.50),(0.0,-0.485,2.477),(0.065,-0.479,2.50)],[0.7,1.0,0.7],lip,0.010)
    return head


def build_hair():
    hair = principled("Hair",(0.015,0.012,0.016),0.42,0.0,0.40)
    ribbon = principled("Ribbon",(0.34,0.66,0.71),0.64)
    gold = principled("HairGold",(0.50,0.24,0.05),0.35,0.26)

    uv_sphere("HairCap",(0.0,0.095,3.02),(0.59,0.48,0.44),hair)
    uv_sphere("Bun_L",(-0.37,0.07,3.36),(0.19,0.16,0.15),hair,56,28)
    uv_sphere("Bun_R",(0.37,0.07,3.36),(0.19,0.17,0.15),hair,56,28)

    # tapered organic strands instead of cards/blocks
    curve_strand("Bang_L1",[(-0.43,-0.445,3.23),(-0.37,-0.485,3.12),(-0.30,-0.465,3.01)],[1.0,0.86,0.45],hair,0.070)
    curve_strand("Bang_L2",[(-0.25,-0.46,3.27),(-0.21,-0.495,3.14),(-0.16,-0.47,3.02)],[1.0,0.82,0.40],hair,0.066)
    curve_strand("Bang_C",[(0.0,-0.47,3.29),(0.0,-0.505,3.15),(0.0,-0.47,3.02)],[1.0,0.84,0.38],hair,0.072)
    curve_strand("Bang_R2",[(0.25,-0.46,3.27),(0.21,-0.495,3.14),(0.16,-0.47,3.02)],[1.0,0.82,0.40],hair,0.066)
    curve_strand("Bang_R1",[(0.43,-0.445,3.23),(0.37,-0.485,3.12),(0.30,-0.465,3.01)],[1.0,0.86,0.45],hair,0.070)

    curve_strand("SideLock_L",[(-0.50,-0.25,3.08),(-0.53,-0.31,2.80),(-0.48,-0.28,2.52)],[0.9,0.8,0.35],hair,0.055)
    curve_strand("SideLock_R",[(0.50,-0.25,3.08),(0.53,-0.31,2.80),(0.48,-0.28,2.52)],[0.9,0.8,0.35],hair,0.055)

    cube("Ribbon_L",(-0.37,-0.035,3.25),(0.10,0.022,0.034),ribbon,rotation=(0,0,math.radians(-18)),bevel=0.018)
    cube("Ribbon_R",(0.37,-0.035,3.25),(0.10,0.022,0.034),ribbon,rotation=(0,0,math.radians(18)),bevel=0.018)
    uv_sphere("Ornament_L",(-0.37,-0.09,3.40),(0.038,0.024,0.038),gold,28,14)
    uv_sphere("Ornament_R",(0.37,-0.09,3.40),(0.038,0.024,0.038),gold,28,14)


def build_costume():
    pale = principled("RobePale",(0.43,0.68,0.73),0.90)
    white = principled("RobeWhite",(0.84,0.85,0.81),0.93)
    inner = principled("RobeInner",(0.66,0.79,0.79),0.91)
    teal = principled("RobeTeal",(0.18,0.42,0.46),0.84)
    sash = principled("Sash",(0.30,0.56,0.60),0.83)
    skin = bpy.data.materials["Skin"]

    loft_ellipse("TorsoOuter",[(0,0,2.20),(0,0,1.88),(0,0,1.48)],[0.24,0.30,0.33],[0.16,0.19,0.21],pale,20,2)
    loft_ellipse("TorsoInner",[(0,-0.015,2.18),(0,-0.02,1.90),(0,-0.02,1.52)],[0.20,0.25,0.27],[0.13,0.15,0.17],inner,20,2)
    loft_ellipse("SkirtOuter",[(0,0.04,1.48),(0,0.05,0.95),(0,0.05,0.22)],[0.33,0.52,0.68],[0.22,0.30,0.38],pale,22,2)
    loft_ellipse("SkirtInner",[(0,-0.02,1.43),(0,-0.02,0.94),(0,-0.02,0.28)],[0.27,0.40,0.53],[0.17,0.22,0.28],white,22,2)

    cube("Collar_L",(-0.083,-0.285,2.24),(0.060,0.022,0.36),white,rotation=(math.radians(-2),math.radians(-8),math.radians(-18)),bevel=0.016)
    cube("Collar_R",(0.083,-0.289,2.24),(0.060,0.022,0.36),white,rotation=(math.radians(2),math.radians(8),math.radians(18)),bevel=0.016)

    cube("WaistBand",(0.0,-0.04,1.44),(0.33,0.075,0.065),sash,bevel=0.026)
    cube("FrontPanelInner",(0.0,-0.30,1.02),(0.14,0.020,0.54),teal,bevel=0.020)
    cube("FrontPanelOuter",(0.0,-0.326,1.12),(0.095,0.015,0.42),white,bevel=0.016)

    for side,sign in (("L",-1),("R",1)):
        centers=[
            (0.29*sign,0.00,1.95),
            (0.47*sign,-0.005,1.70),
            (0.60*sign,-0.015,1.40),
        ]
        widths=[0.15,0.21,0.30]
        depths=[0.11,0.15,0.19]
        loft_ellipse(f"SleeveOuter_{side}",centers,widths,depths,pale,18,2)
        cuff_centers=[
            (0.53*sign,-0.025,1.52),
            (0.62*sign,-0.035,1.35),
        ]
        loft_ellipse(f"Cuff_{side}",cuff_centers,[0.25,0.30],[0.16,0.19],white,18,2)
        uv_sphere(f"Hand_{side}",(0.66*sign,-0.105,1.20),(0.070,0.050,0.095),skin,40,20)

    for side,x in (("L",-0.17),("R",0.17)):
        curve_strand(
            f"WaistRibbon_{side}",
            [(x,0.09,1.36),(x*1.06,0.14,0.95),(x*1.18,0.16,0.55)],
            [1.0,0.8,0.45],sash,0.035
        )


def build_stage():
    ground = principled("Ground",(0.052,0.039,0.031),0.96)
    bg = principled("Background",(0.025,0.029,0.036),0.97)
    wood = principled("Wood",(0.09,0.05,0.028),0.92)
    lantern = principled("Lantern",(0.48,0.15,0.03),0.60)
    bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,0))
    bpy.context.object.data.materials.append(ground)
    for i,x in enumerate((-2.8,-1.7,1.8,2.8)):
        loft_ellipse(f"BG_{i}",[(x,3.0+0.25*(i%2),0.1),(x,3.0+0.25*(i%2),1.5)],[0.16,0.14],[0.12,0.10],bg,14,1)
    for x in (-2.0,2.0):
        loft_ellipse("Pole",[(x,1.8,0.0),(x,1.8,2.0)],[0.035,0.035],[0.035,0.035],wood,12,0)
        uv_sphere("Lantern",(x,1.8,1.68),(0.15,0.15,0.21),lantern,32,16)


def setup_world():
    world=bpy.context.scene.world
    world.use_nodes=True
    bg=world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value=(0.018,0.022,0.029,1.0)
    bg.inputs["Strength"].default_value=0.20


def main():
    a=parse_args()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene=bpy.context.scene
    scene.render.engine="BLENDER_EEVEE"
    scene.render.resolution_x=540
    scene.render.resolution_y=960
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGBA"
    scene.render.image_settings.color_depth="8"
    scene.render.film_transparent=False
    setup_world()

    build_stage()
    stage_object_names = {obj.name for obj in scene.objects}

    head=build_face()
    build_hair()
    build_costume()

    bpy.context.view_layer.update()
    child_objects = [
        obj for obj in scene.objects
        if obj.name not in stage_object_names and obj.type in {"MESH", "CURVE"}
    ]
    if not child_objects:
        raise RuntimeError("child LookDev v4 created no character geometry")

    bpy.ops.object.light_add(type="AREA",location=(3.4,1.7,4.7))
    key=bpy.context.object
    key.name="WarmRim"
    key.data.energy=390
    key.data.color=(1.0,0.33,0.09)
    key.data.shape="DISK"
    key.data.size=3.8
    look_at(key,(0.0,0.0,2.0))

    bpy.ops.object.light_add(type="AREA",location=(-2.2,-4.1,3.35))
    fill=bpy.context.object
    fill.name="CoolFill"
    fill.data.energy=420
    fill.data.color=(0.56,0.71,1.0)
    fill.data.size=3.2
    look_at(fill,(0.0,-0.08,2.42))

    bpy.ops.object.light_add(type="AREA",location=(0.2,-4.5,3.20))
    eye=bpy.context.object
    eye.name="EyeLight"
    eye.data.energy=58
    eye.data.color=(1.0,0.80,0.68)
    eye.data.size=1.0
    look_at(eye,(0.0,-0.08,2.76))

    target=bpy.data.objects.new("LookdevTarget",None)
    bpy.context.collection.objects.link(target)

    bpy.ops.object.camera_add(location=(0.0,-6.0,2.0))
    cam=bpy.context.object
    cam.name="Camera"
    cam.data.lens=72
    cam.data.sensor_width=36.0
    cam.data.dof.use_dof=True
    cam.data.dof.focus_object=head
    cam.data.dof.aperture_fstop=3.2
    track=cam.constraints.new(type="TRACK_TO")
    track.target=target
    track.track_axis="TRACK_NEGATIVE_Z"
    track.up_axis="UP_Y"
    scene.camera=cam

    framing = auto_frame_character(scene, cam, target, child_objects, safe_margin=0.08)
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V4_FRAMING_PASS framing={framing}")

    output=Path(a.output).expanduser().resolve()
    blend_output=Path(a.blend_output).expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    blend_output.parent.mkdir(parents=True,exist_ok=True)
    scene.render.filepath=str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size < 30000:
        raise RuntimeError("child LookDev v4 render missing or unexpectedly small")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V4_PASS output={output}")


if __name__=="__main__":
    main()
