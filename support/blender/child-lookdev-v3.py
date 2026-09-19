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


def principled(name, color, roughness=0.7, metallic=0.0, specular_ior=0.3):
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


def uv_sphere(name, loc, scale, mat, segments=72, rings=36):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        location=loc,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    smooth(obj)
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


def cube(name, loc, scale, mat, rotation=(0.0,0.0,0.0), bevel=0.035):
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


def curve_stroke(name, points, mat, bevel=0.014):
    curve = bpy.data.curves.new(name + "Curve", type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel
    curve.bevel_resolution = 4
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points)-1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def ribbon_lock(name, points, widths, mat, thickness=0.022):
    if len(points) != len(widths) or len(points) < 2:
        raise ValueError("ribbon_lock requires matching points/widths")
    pts = [Vector(p) for p in points]
    verts = []
    for i, p in enumerate(pts):
        if i == 0:
            tangent = (pts[1] - pts[0]).normalized()
        elif i == len(pts)-1:
            tangent = (pts[-1] - pts[-2]).normalized()
        else:
            tangent = (pts[i+1] - pts[i-1]).normalized()
        side = Vector((tangent.z, 0.0, -tangent.x))
        if side.length < 1e-6:
            side = Vector((1.0,0.0,0.0))
        side.normalize()
        w = widths[i]
        verts.append(tuple(p + side*w))
        verts.append(tuple(p - side*w))
    faces = []
    for i in range(len(pts)-1):
        a = i*2
        faces.append((a,a+1,a+3,a+2))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    solid = obj.modifiers.new("HairThickness", "SOLIDIFY")
    solid.thickness = thickness
    bevel = obj.modifiers.new("HairBevel", "BEVEL")
    bevel.width = 0.016
    bevel.segments = 3
    return obj


def tapered_head(name, loc, scale, mat):
    obj = uv_sphere(name, loc, scale, mat, 96, 48)
    mesh = obj.data
    zs = [v.co.z for v in mesh.vertices]
    zmin, zmax = min(zs), max(zs)
    span = max(zmax-zmin, 1e-6)
    for v in mesh.vertices:
        t = (v.co.z-zmin)/span
        if t < 0.28:
            factor = 0.74 + 0.28*(t/0.28)
        elif t < 0.68:
            factor = 1.02 + 0.05*math.sin((t-0.28)/0.40*math.pi)
        else:
            factor = 1.00 - 0.035*((t-0.68)/0.32)
        v.co.x *= factor
        if v.co.y < 0 and t < 0.30:
            v.co.y *= 0.93
    mesh.update()
    return obj


def build_face():
    skin = principled("Skin",(0.82,0.55,0.47),0.80,0.0,0.26)
    sclera = principled("Sclera",(0.94,0.95,0.93),0.46,0.0,0.18)
    iris = principled("Iris",(0.075,0.055,0.040),0.31,0.0,0.36)
    pupil = principled("Pupil",(0.006,0.006,0.008),0.22)
    white = principled("Catch",(1.0,1.0,1.0),0.10)
    lash = principled("Lash",(0.022,0.016,0.018),0.48)
    lip = principled("Lip",(0.34,0.075,0.09),0.58)

    head = tapered_head("ChildHead",(0.0,0.0,2.80),(0.585,0.48,0.625),skin)
    uv_sphere("Ear_L",(-0.55,0.02,2.78),(0.075,0.045,0.105),skin,40,20)
    uv_sphere("Ear_R",(0.55,0.02,2.78),(0.075,0.045,0.105),skin,40,20)

    eye_y = -0.472
    for side,x in (("L",-0.205),("R",0.205)):
        uv_sphere(f"Sclera_{side}",(x,eye_y,2.875),(0.122,0.038,0.148),sclera,64,32)
        uv_sphere(f"Iris_{side}",(x,eye_y-0.032,2.865),(0.081,0.019,0.102),iris,56,28)
        uv_sphere(f"Pupil_{side}",(x,eye_y-0.045,2.865),(0.034,0.010,0.050),pupil,40,20)
        uv_sphere(f"Catch_{side}",(x-0.024,eye_y-0.054,2.918),(0.018,0.006,0.024),white,24,12)
        curve_stroke(
            f"UpperLid_{side}",
            [(x-0.115,-0.503,2.945),(x,-0.522,3.000),(x+0.115,-0.503,2.945)],
            lash,0.014
        )
        curve_stroke(
            f"Brow_{side}",
            [(x-0.10,-0.474,3.105),(x,-0.488,3.125),(x+0.10,-0.474,3.102)],
            lash,0.011
        )

    uv_sphere("Nose",(0.0,-0.482,2.675),(0.026,0.015,0.035),skin,28,14)
    curve_stroke("Mouth",[(-0.075,-0.493,2.50),(0.0,-0.501,2.475),(0.075,-0.493,2.50)],lip,0.012)
    return head


def build_hair():
    hair = principled("Hair",(0.016,0.013,0.017),0.43,0.0,0.42)
    ribbon = principled("Ribbon",(0.35,0.67,0.72),0.64)
    gold = principled("HairGold",(0.50,0.25,0.05),0.34,0.28)

    uv_sphere("HairCap",(0.0,0.10,3.055),(0.61,0.50,0.455),hair)
    bun_l = uv_sphere("Bun_L",(-0.39,0.075,3.39),(0.21,0.17,0.16),hair)
    bun_l.rotation_euler=(math.radians(8),math.radians(-5),math.radians(-12))
    bun_r = uv_sphere("Bun_R",(0.39,0.075,3.39),(0.20,0.18,0.16),hair)
    bun_r.rotation_euler=(math.radians(-5),math.radians(4),math.radians(10))

    ribbon_lock("Bang_L1",[(-0.43,-0.49,3.28),(-0.38,-0.51,3.15),(-0.31,-0.49,3.02)],[0.095,0.105,0.070],hair)
    ribbon_lock("Bang_L2",[(-0.25,-0.50,3.31),(-0.22,-0.52,3.17),(-0.18,-0.50,3.03)],[0.090,0.100,0.065],hair)
    ribbon_lock("Bang_C",[(0.00,-0.505,3.33),(0.00,-0.525,3.18),(0.00,-0.505,3.04)],[0.105,0.115,0.070],hair)
    ribbon_lock("Bang_R2",[(0.25,-0.50,3.31),(0.22,-0.52,3.17),(0.18,-0.50,3.03)],[0.090,0.100,0.065],hair)
    ribbon_lock("Bang_R1",[(0.43,-0.49,3.28),(0.38,-0.51,3.15),(0.31,-0.49,3.02)],[0.095,0.105,0.070],hair)

    ribbon_lock("SideLock_L",[(-0.50,-0.32,3.10),(-0.54,-0.34,2.82),(-0.49,-0.30,2.50)],[0.070,0.080,0.055],hair,0.026)
    ribbon_lock("SideLock_R",[(0.50,-0.32,3.10),(0.54,-0.34,2.82),(0.49,-0.30,2.50)],[0.070,0.080,0.055],hair,0.026)

    cube("Ribbon_L",(-0.39,-0.04,3.27),(0.105,0.025,0.035),ribbon,rotation=(0,0,math.radians(-18)),bevel=0.020)
    cube("Ribbon_R",(0.39,-0.04,3.27),(0.105,0.025,0.035),ribbon,rotation=(0,0,math.radians(18)),bevel=0.020)
    uv_sphere("Ornament_L",(-0.39,-0.10,3.43),(0.040,0.026,0.040),gold,28,14)
    uv_sphere("Ornament_R",(0.39,-0.10,3.43),(0.040,0.026,0.040),gold,28,14)


def build_costume():
    pale = principled("RobePale",(0.44,0.69,0.74),0.89)
    white = principled("RobeWhite",(0.84,0.84,0.79),0.93)
    inner = principled("RobeInner",(0.68,0.80,0.79),0.91)
    teal = principled("RobeTeal",(0.19,0.43,0.47),0.84)
    sash = principled("Sash",(0.31,0.57,0.61),0.82)
    skin = bpy.data.materials["Skin"]

    cone("TorsoInner",(0.0,0.02,1.84),0.28,0.23,1.00,inner)
    cone("TorsoOuter",(0.0,0.045,1.84),0.34,0.265,1.04,pale)
    cone("SkirtOuter",(0.0,0.06,0.94),0.66,0.31,1.43,pale)
    cone("SkirtInner",(0.0,-0.01,0.98),0.46,0.24,1.28,white)

    cube("Collar_L",(-0.085,-0.300,2.25),(0.068,0.024,0.39),white,rotation=(math.radians(-2),math.radians(-9),math.radians(-18)),bevel=0.018)
    cube("Collar_R",(0.085,-0.305,2.25),(0.068,0.024,0.39),white,rotation=(math.radians(2),math.radians(9),math.radians(18)),bevel=0.018)

    cube("WaistBand",(0.0,-0.045,1.41),(0.34,0.085,0.075),sash,bevel=0.030)
    cube("FrontPanelInner",(0.0,-0.315,1.00),(0.15,0.022,0.57),teal,bevel=0.022)
    cube("FrontPanelOuter",(0.0,-0.345,1.10),(0.105,0.017,0.45),white,bevel=0.018)

    # wide cloth sleeves: vertical drooping masses, not tubes pointing at camera
    for side,sign in (("L",-1),("R",1)):
        x = 0.47*sign
        upper = uv_sphere(f"UpperSleeve_{side}",(x,0.02,1.90),(0.24,0.18,0.30),pale,56,28)
        upper.rotation_euler=(math.radians(6),math.radians(sign*6),math.radians(sign*8))
        lower = uv_sphere(f"LowerSleeve_{side}",(0.62*sign,-0.01,1.56),(0.31,0.19,0.38),white,56,28)
        lower.rotation_euler=(math.radians(8),math.radians(sign*5),math.radians(sign*10))
        uv_sphere(f"Hand_{side}",(0.73*sign,-0.10,1.30),(0.075,0.055,0.105),skin,40,20)

    for side,x in (("L",-0.18),("R",0.18)):
        cube(f"WaistRibbon_{side}",(x,0.15,0.77),(0.052,0.018,0.53),sash,rotation=(math.radians(-7),0,math.radians(-5 if x<0 else 5)),bevel=0.016)


def build_stage():
    ground = principled("Ground",(0.055,0.040,0.032),0.96)
    bg = principled("Background",(0.026,0.030,0.037),0.97)
    wood = principled("Wood",(0.09,0.05,0.028),0.92)
    lantern = principled("Lantern",(0.50,0.16,0.035),0.58)

    bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,0))
    bpy.context.object.data.materials.append(ground)
    for i,x in enumerate((-2.8,-1.7,1.8,2.8)):
        cone(f"BG_{i}",(x,3.0+0.25*(i%2),0.80),0.17,0.14,1.30,bg)
    for x in (-2.0,2.0):
        cone("Pole",(x,1.8,1.0),0.04,0.04,2.0,wood)
        uv_sphere("Lantern",(x,1.8,1.70),(0.16,0.16,0.22),lantern,32,16)


def setup_world():
    world=bpy.context.scene.world
    world.use_nodes=True
    bg=world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value=(0.018,0.022,0.030,1.0)
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
    head=build_face()
    build_hair()
    build_costume()

    bpy.ops.object.light_add(type="AREA",location=(3.6,1.6,4.8))
    key=bpy.context.object
    key.name="WarmRim"
    key.data.energy=430
    key.data.color=(1.0,0.34,0.10)
    key.data.shape="DISK"
    key.data.size=3.8
    look_at(key,(0.0,0.0,2.0))

    bpy.ops.object.light_add(type="AREA",location=(-2.2,-4.0,3.35))
    fill=bpy.context.object
    fill.name="CoolFill"
    fill.data.energy=390
    fill.data.color=(0.56,0.70,1.0)
    fill.data.size=3.2
    look_at(fill,(0.0,-0.08,2.45))

    bpy.ops.object.light_add(type="AREA",location=(0.2,-4.6,3.25))
    eye=bpy.context.object
    eye.name="EyeLight"
    eye.data.energy=70
    eye.data.color=(1.0,0.80,0.68)
    eye.data.size=1.1
    look_at(eye,(0.0,-0.08,2.78))

    target=bpy.data.objects.new("LookdevTarget",None)
    bpy.context.collection.objects.link(target)
    target.location=(0.0,0.0,1.98)

    bpy.ops.object.camera_add(location=(0.0,-7.25,2.48))
    cam=bpy.context.object
    cam.name="Camera"
    cam.data.lens=82
    cam.data.sensor_width=36.0
    cam.data.dof.use_dof=True
    cam.data.dof.focus_object=head
    cam.data.dof.aperture_fstop=3.2
    track=cam.constraints.new(type="TRACK_TO")
    track.target=target
    track.track_axis="TRACK_NEGATIVE_Z"
    track.up_axis="UP_Y"
    scene.camera=cam

    bpy.context.view_layer.update()
    checks={
        "head":head.matrix_world.translation,
        "torso":bpy.data.objects["TorsoOuter"].matrix_world.translation,
        "skirt":bpy.data.objects["SkirtOuter"].matrix_world.translation,
    }
    projected={}
    for name,point in checks.items():
        co=world_to_camera_view(scene,cam,point)
        projected[name]=(float(co.x),float(co.y),float(co.z))
        if not (0.10 <= co.x <= 0.90 and 0.07 <= co.y <= 0.95 and co.z > 0.0):
            raise RuntimeError(f"child LookDev v3 framing gate failed for {name}: {projected[name]}")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V3_FRAMING_PASS projected={projected}")

    output=Path(a.output).expanduser().resolve()
    blend_output=Path(a.blend_output).expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    blend_output.parent.mkdir(parents=True,exist_ok=True)
    scene.render.filepath=str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size < 30000:
        raise RuntimeError("child LookDev v3 render missing or unexpectedly small")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_V3_PASS output={output}")


if __name__=="__main__":
    main()
