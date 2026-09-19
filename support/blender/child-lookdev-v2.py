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


def principled(name, color, roughness=0.7, metallic=0.0, specular_ior=0.35):
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


def uv_sphere(name, loc, scale, mat, segments=64, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    smooth(obj)
    return obj


def tapered_head(name, loc, scale, mat):
    obj = uv_sphere(name, loc, scale, mat, 96, 48)
    mesh = obj.data
    z_values = [v.co.z for v in mesh.vertices]
    zmin, zmax = min(z_values), max(z_values)
    span = max(zmax - zmin, 1e-6)
    for v in mesh.vertices:
        t = (v.co.z - zmin) / span
        # fuller forehead/cheeks, smaller chin
        if t < 0.34:
            factor = 0.80 + 0.22 * (t / 0.34)
        elif t < 0.70:
            factor = 1.02 + 0.06 * math.sin((t - 0.34) / 0.36 * math.pi)
        else:
            factor = 1.00 - 0.05 * ((t - 0.70) / 0.30)
        v.co.x *= factor
        # soften lower face projection
        if t < 0.22:
            v.co.y *= 0.94
    mesh.update()
    return obj


def cone(name, loc, radius1, radius2, depth, mat, rotation=(0.0,0.0,0.0), vertices=64):
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        location=loc,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    smooth(obj)
    return obj


def cube(name, loc, scale, mat, rotation=(0.0,0.0,0.0), bevel=0.04):
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


def curve_stroke(name, points, mat, bevel=0.018):
    curve = bpy.data.curves.new(name + "Curve", type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel
    curve.bevel_resolution = 5
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def build_face():
    skin = principled("Skin", (0.82,0.54,0.46), 0.78, 0.0, 0.28)
    sclera_mat = principled("Sclera", (0.93,0.94,0.92), 0.45, 0.0, 0.20)
    iris_mat = principled("Iris", (0.055,0.042,0.035), 0.32)
    pupil_mat = principled("Pupil", (0.006,0.006,0.007), 0.22)
    catch_mat = principled("Catch", (1.0,1.0,1.0), 0.12)
    lash_mat = principled("Lash", (0.025,0.018,0.020), 0.50)
    lip_mat = principled("Lip", (0.38,0.08,0.10), 0.56)
    blush_mat = principled("Blush", (0.72,0.19,0.22), 0.86)

    head = tapered_head("ChildHead", (0.0,0.0,2.80), (0.63,0.52,0.67), skin)

    eye_y = -0.505
    for side, x in (("L",-0.225),("R",0.225)):
        uv_sphere(f"Sclera_{side}", (x,eye_y,2.87), (0.145,0.045,0.175), sclera_mat, 64, 32)
        uv_sphere(f"Iris_{side}", (x,eye_y-0.040,2.86), (0.102,0.025,0.128), iris_mat, 64, 32)
        uv_sphere(f"Pupil_{side}", (x,eye_y-0.057,2.86), (0.046,0.012,0.066), pupil_mat, 48, 24)
        uv_sphere(f"CatchBig_{side}", (x-0.030,eye_y-0.071,2.925), (0.024,0.008,0.032), catch_mat, 32, 16)
        uv_sphere(f"CatchSmall_{side}", (x+0.032,eye_y-0.070,2.825), (0.010,0.006,0.014), catch_mat, 24, 12)
        # soft upper lid / lash arc
        sx = -1 if side == "L" else 1
        curve_stroke(
            f"UpperLid_{side}",
            [
                (x-0.14, -0.548, 2.94),
                (x,      -0.565, 3.025),
                (x+0.14, -0.548, 2.94),
            ],
            lash_mat,
            0.020,
        )
        curve_stroke(
            f"Brow_{side}",
            [
                (x-0.12, -0.520, 3.12),
                (x,      -0.535, 3.15 + (0.015 if sx < 0 else 0.0)),
                (x+0.12, -0.520, 3.115),
            ],
            lash_mat,
            0.014,
        )

    # minimal nose and soft mouth line
    uv_sphere("Nose", (0.0,-0.532,2.66), (0.035,0.020,0.045), skin, 32, 16)
    curve_stroke(
        "Mouth",
        [(-0.09,-0.546,2.49),(0.0,-0.555,2.465),(0.09,-0.546,2.49)],
        lip_mat,
        0.016,
    )

    # cheeks, low relief
    uv_sphere("Blush_L", (-0.38,-0.485,2.59), (0.095,0.012,0.060), blush_mat, 32, 16)
    uv_sphere("Blush_R", (0.38,-0.485,2.59), (0.095,0.012,0.060), blush_mat, 32, 16)

    return head


def build_hair():
    hair = principled("Hair", (0.018,0.015,0.018), 0.42, 0.0, 0.42)
    ribbon = principled("Ribbon", (0.40,0.72,0.76), 0.65)
    gold = principled("HairGold", (0.55,0.28,0.055), 0.34, 0.32)

    uv_sphere("HairCap", (0.0,0.09,3.055), (0.655,0.545,0.49), hair)
    # irregular buns instead of perfect spheres
    bun_l = uv_sphere("Bun_L", (-0.40,0.06,3.43), (0.23,0.19,0.18), hair)
    bun_l.rotation_euler = (math.radians(8),0,math.radians(-12))
    bun_r = uv_sphere("Bun_R", (0.40,0.06,3.43), (0.22,0.20,0.18), hair)
    bun_r.rotation_euler = (math.radians(-5),0,math.radians(10))

    # grouped bangs with softer overlap
    bang_data = [
        (-0.34,3.16,0.13,0.30,-14),
        (-0.17,3.19,0.14,0.31,-7),
        (0.00,3.20,0.15,0.33,0),
        (0.18,3.18,0.14,0.31,7),
        (0.35,3.15,0.13,0.29,14),
    ]
    for x,z,sx,sz,rot in bang_data:
        obj = uv_sphere("Bang", (x,-0.455,z), (sx,0.047,sz), hair, 48, 24)
        obj.rotation_euler = (0.0,math.radians(rot),math.radians(rot*0.25))

    # curved side locks
    curve_stroke("SideLock_L",[(-0.52,-0.10,3.12),(-0.57,-0.14,2.80),(-0.53,-0.13,2.48)],hair,0.055)
    curve_stroke("SideLock_R",[(0.52,-0.10,3.12),(0.57,-0.14,2.80),(0.53,-0.13,2.48)],hair,0.055)

    cube("Ribbon_L", (-0.40,-0.06,3.30), (0.12,0.025,0.040), ribbon, rotation=(0,0,math.radians(-18)), bevel=0.022)
    cube("Ribbon_R", (0.40,-0.06,3.30), (0.12,0.025,0.040), ribbon, rotation=(0,0,math.radians(18)), bevel=0.022)
    uv_sphere("Ornament_L", (-0.40,-0.10,3.46), (0.045,0.028,0.045), gold, 32, 16)
    uv_sphere("Ornament_R", (0.40,-0.10,3.46), (0.045,0.028,0.045), gold, 32, 16)


def build_costume():
    pale = principled("RobePale", (0.48,0.72,0.75), 0.88)
    white = principled("RobeWhite", (0.83,0.84,0.78), 0.92)
    inner = principled("RobeInner", (0.70,0.82,0.80), 0.90)
    teal = principled("RobeTeal", (0.20,0.46,0.48), 0.82)
    sash = principled("Sash", (0.33,0.61,0.63), 0.80)

    cone("TorsoInner", (0.0,0.02,1.86), 0.30,0.24,1.00, inner)
    cone("TorsoOuter", (0.0,0.045,1.85), 0.35,0.27,1.04, pale)
    cone("SkirtOuter", (0.0,0.06,0.95), 0.68,0.31,1.45, pale)
    cone("SkirtInner", (0.0,-0.015,0.99), 0.48,0.24,1.30, white)

    # crossed collar / lapels
    cube("Collar_L", (-0.09,-0.315,2.26), (0.072,0.028,0.41), white, rotation=(math.radians(-2),math.radians(-10),math.radians(-18)), bevel=0.022)
    cube("Collar_R", (0.09,-0.320,2.26), (0.072,0.028,0.41), white, rotation=(math.radians(2),math.radians(10),math.radians(18)), bevel=0.022)

    # waist band and front hanging panels
    cube("WaistBand", (0.0,-0.05,1.42), (0.36,0.10,0.09), sash, bevel=0.035)
    cube("FrontPanelInner", (0.0,-0.34,1.00), (0.16,0.025,0.60), teal, bevel=0.025)
    cube("FrontPanelOuter", (0.0,-0.37,1.12), (0.11,0.018,0.47), white, bevel=0.020)

    skin = bpy.data.materials["Skin"]
    for side, x, sign in (("L",-0.47,-1),("R",0.47,1)):
        sleeve = cone(f"Sleeve_{side}", (x,0.02,1.88), 0.24,0.14,0.76, pale, rotation=(math.radians(90),0,math.radians(sign*14)))
        cuff = cone(f"Cuff_{side}", (x*1.52,-0.02,1.55), 0.27,0.16,0.60, white, rotation=(math.radians(90),0,math.radians(sign*18)))
        hand_x = -0.76 if side=="L" else 0.76
        uv_sphere(f"Hand_{side}", (hand_x,-0.11,1.48), (0.085,0.060,0.12), skin, 40, 20)

    for side, x in (("L",-0.18),("R",0.18)):
        cube(f"WaistRibbon_{side}", (x,0.15,0.78), (0.055,0.020,0.56), sash, rotation=(math.radians(-7),0,math.radians(-5 if x<0 else 5)), bevel=0.018)


def build_stage():
    ground = principled("Ground", (0.060,0.043,0.032), 0.96)
    bg = principled("Background", (0.028,0.032,0.040), 0.96)
    wood = principled("Wood", (0.10,0.055,0.030), 0.92)
    lantern = principled("Lantern", (0.55,0.18,0.035), 0.58)

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0))
    bpy.context.object.data.materials.append(ground)

    for i,x in enumerate((-2.8,-1.7,1.8,2.8)):
        cone(f"BG_{i}", (x,3.0+0.25*(i%2),0.80), 0.17,0.14,1.30,bg)

    for x in (-2.0,2.0):
        cone("Pole",(x,1.8,1.0),0.04,0.04,2.0,wood)
        uv_sphere("Lantern",(x,1.8,1.70),(0.17,0.17,0.23),lantern,32,16)


def setup_world():
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.020,0.024,0.032,1.0)
    bg.inputs["Strength"].default_value = 0.22


def main():
    a = parse_args()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 540
    scene.render.resolution_y = 960
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    setup_world()

    build_stage()
    head = build_face()
    build_hair()
    build_costume()

    # controlled warm rim
    bpy.ops.object.light_add(type="AREA", location=(3.8,1.5,4.8))
    key = bpy.context.object
    key.name = "WarmRim"
    key.data.energy = 520
    key.data.color = (1.0,0.36,0.12)
    key.data.shape = "DISK"
    key.data.size = 3.8
    look_at(key,(0.0,0.0,2.0))

    # cool-neutral face fill
    bpy.ops.object.light_add(type="AREA", location=(-2.2,-4.0,3.4))
    fill = bpy.context.object
    fill.name = "CoolFill"
    fill.data.energy = 360
    fill.data.color = (0.54,0.68,1.0)
    fill.data.size = 3.2
    look_at(fill,(0.0,-0.1,2.45))

    bpy.ops.object.light_add(type="AREA", location=(0.2,-4.7,3.2))
    eye = bpy.context.object
    eye.name = "EyeLight"
    eye.data.energy = 90
    eye.data.color = (1.0,0.78,0.64)
    eye.data.size = 1.2
    look_at(eye,(0.0,-0.1,2.75))

    target = bpy.data.objects.new("LookdevTarget",None)
    bpy.context.collection.objects.link(target)
    target.location = (0.0,0.0,2.0)

    bpy.ops.object.camera_add(location=(0.0,-7.15,2.48))
    cam = bpy.context.object
    cam.name = "Camera"
    cam.data.lens = 78
    cam.data.sensor_width = 36.0
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = head
    cam.data.dof.aperture_fstop = 3.0
    track = cam.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam

    bpy.context.view_layer.update()
    checks = {
        "head": head.matrix_world.translation,
        "torso": bpy.data.objects["TorsoOuter"].matrix_world.translation,
        "skirt": bpy.data.objects["SkirtOuter"].matrix_world.translation,
    }
    projected = {}
    for name,point in checks.items():
        co = world_to_camera_view(scene,cam,point)
        projected[name]=(float(co.x),float(co.y),float(co.z))
        if not (0.10 <= co.x <= 0.90 and 0.07 <= co.y <= 0.95 and co.z > 0.0):
            raise RuntimeError(f"child LookDev v2 framing gate failed for {name}: {projected[name]}")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V2_FRAMING_PASS projected={projected}")

    output = Path(a.output).expanduser().resolve()
    blend_output = Path(a.blend_output).expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    blend_output.parent.mkdir(parents=True,exist_ok=True)
    scene.render.filepath = str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size < 30000:
        raise RuntimeError("child LookDev v2 render missing or unexpectedly small")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V2_PASS output={output}")


if __name__ == "__main__":
    main()
