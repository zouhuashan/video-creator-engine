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


def mat(name, color, roughness=0.75, metallic=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1.0)
    m.roughness = roughness
    m.metallic = metallic
    return m


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def sphere(name, loc, scale, material, segments=64, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        location=loc,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def cone(name, loc, radius1, radius2, depth, material, rotation=(0.0,0.0,0.0), vertices=64):
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
    obj.data.materials.append(material)
    return obj


def cube(name, loc, scale, material, rotation=(0.0,0.0,0.0), bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0.0:
        mod = obj.modifiers.new("SoftBevel", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    obj.data.materials.append(material)
    return obj


def torus(name, loc, major, minor, material, rotation=(0.0,0.0,0.0), scale=(1.0,1.0,1.0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=64,
        minor_segments=16,
        location=loc,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def add_child_face():
    skin = mat("ChildSkin", (0.88, 0.62, 0.54), 0.82)
    eye_white = mat("EyeWhite", (0.96,0.97,0.96), 0.38)
    iris = mat("IrisDark", (0.028,0.024,0.026), 0.28)
    pupil = mat("Pupil", (0.004,0.004,0.005), 0.22)
    catch = mat("CatchLight", (1.0,1.0,1.0), 0.12)
    brow = mat("Brow", (0.055,0.035,0.03), 0.55)
    mouth = mat("Mouth", (0.42,0.10,0.12), 0.62)
    blush = mat("Blush", (0.92,0.28,0.32), 0.9)

    head = sphere("ChildHead", (0.0,0.0,2.82), (0.64,0.54,0.66), skin)

    eye_y = -0.505
    for side, x in (("L",-0.235),("R",0.235)):
        sclera = sphere(f"EyeWhite_{side}", (x,eye_y,2.86), (0.145,0.055,0.18), eye_white, 48, 24)
        iris_obj = sphere(f"Iris_{side}", (x,eye_y-0.048,2.86), (0.098,0.026,0.132), iris, 48, 24)
        pupil_obj = sphere(f"Pupil_{side}", (x,eye_y-0.068,2.86), (0.048,0.014,0.073), pupil, 40, 20)
        sphere(f"Catch_{side}", (x-0.03,eye_y-0.084,2.93), (0.026,0.010,0.034), catch, 32, 16)

    # brows / nose / mouth / cheek blush
    cube("Brow_L", (-0.235,-0.535,3.095), (0.12,0.018,0.018), brow, rotation=(math.radians(2),0,math.radians(-5)), bevel=0.02)
    cube("Brow_R", (0.235,-0.535,3.095), (0.12,0.018,0.018), brow, rotation=(math.radians(-2),0,math.radians(5)), bevel=0.02)
    sphere("Nose", (0.0,-0.545,2.67), (0.045,0.026,0.055), skin, 32, 16)
    torus("Mouth", (0.0,-0.552,2.50), 0.07, 0.014, mouth, rotation=(math.radians(90),0,0), scale=(1.1,1.0,0.55))
    sphere("Blush_L", (-0.38,-0.505,2.60), (0.105,0.016,0.075), blush, 32, 16)
    sphere("Blush_R", (0.38,-0.505,2.60), (0.105,0.016,0.075), blush, 32, 16)

    return head


def add_hair():
    hair = mat("Hair", (0.022,0.018,0.020), 0.46)
    ribbon = mat("Ribbon", (0.52,0.82,0.84), 0.66)
    gold = mat("HairGold", (0.62,0.39,0.10), 0.35, 0.18)

    sphere("HairCap", (0.0,0.10,3.03), (0.66,0.56,0.49), hair)
    sphere("Bun_L", (-0.43,0.03,3.43), (0.22,0.20,0.20), hair)
    sphere("Bun_R", (0.43,0.03,3.43), (0.22,0.20,0.20), hair)

    # bangs
    for x, rot in ((-0.34,-14),(-0.17,-7),(0.0,0),(0.17,7),(0.34,14)):
        bang = sphere("Bang", (x,-0.455,3.17), (0.14,0.055,0.30), hair, 48, 24)
        bang.rotation_euler = (0.0, math.radians(rot), math.radians(rot*0.4))

    # side locks
    for x in (-0.54,0.54):
        lock = cone("SideLock", (x,-0.13,2.68), 0.08, 0.035, 0.72, hair, rotation=(math.radians(4),0,math.radians(-8 if x<0 else 8)))
        lock.scale.z = 1.1

    # ribbons and ornaments
    cube("Ribbon_L", (-0.43,-0.02,3.26), (0.13,0.035,0.045), ribbon, rotation=(0,0,math.radians(-18)), bevel=0.025)
    cube("Ribbon_R", (0.43,-0.02,3.26), (0.13,0.035,0.045), ribbon, rotation=(0,0,math.radians(18)), bevel=0.025)
    sphere("Ornament_L", (-0.43,-0.13,3.47), (0.055,0.035,0.055), gold, 32, 16)
    sphere("Ornament_R", (0.43,-0.13,3.47), (0.055,0.035,0.055), gold, 32, 16)


def add_costume():
    pale = mat("RobePale", (0.62,0.83,0.84), 0.91)
    white = mat("RobeWhite", (0.86,0.88,0.84), 0.93)
    teal = mat("RobeTeal", (0.26,0.55,0.57), 0.86)
    sash = mat("Sash", (0.40,0.70,0.70), 0.82)

    # neck / torso / skirt gives ~1:3.3 total head-to-body read
    cone("Torso", (0.0,0.02,1.84), 0.34, 0.27, 1.05, pale)
    cone("SkirtOuter", (0.0,0.05,0.95), 0.66, 0.31, 1.42, pale)
    cone("SkirtInner", (0.0,-0.025,0.97), 0.47, 0.25, 1.34, white)

    # crossed collar
    cube("Collar_L", (-0.09,-0.315,2.25), (0.08,0.035,0.42), white, rotation=(math.radians(-2),math.radians(-12),math.radians(-18)), bevel=0.025)
    cube("Collar_R", (0.09,-0.32,2.25), (0.08,0.035,0.42), white, rotation=(math.radians(2),math.radians(12),math.radians(18)), bevel=0.025)

    # waist layers
    torus("WaistSash", (0.0,0.0,1.43), 0.34, 0.055, sash, rotation=(math.radians(90),0,0), scale=(1.0,0.72,1.0))
    cube("FrontPanel", (0.0,-0.34,1.03), (0.18,0.035,0.62), teal, bevel=0.035)

    # wide sleeves
    for side, x, zrot in (("L",-0.47,-14),("R",0.47,14)):
        upper = cone(f"SleeveUpper_{side}", (x,0.0,1.86), 0.21, 0.15, 0.72, pale, rotation=(math.radians(90),0,math.radians(zrot)))
        cuff = cone(f"SleeveCuff_{side}", (x*1.48,-0.03,1.55), 0.26, 0.16, 0.56, white, rotation=(math.radians(90),0,math.radians(zrot*1.25)))
        hand_x = -0.73 if side=="L" else 0.73
        sphere(f"Hand_{side}", (hand_x,-0.10,1.50), (0.09,0.07,0.13), bpy.data.materials["ChildSkin"], 40, 20)

    # trailing ribbons
    for side, x in (("L",-0.19),("R",0.19)):
        strip = cube(f"WaistRibbon_{side}", (x,0.16,0.80), (0.065,0.025,0.56), sash, rotation=(math.radians(-8),0,math.radians(-5 if x<0 else 5)), bevel=0.02)


def add_stage():
    ground = mat("Ground", (0.075,0.055,0.042), 0.95)
    bg = mat("Background", (0.035,0.042,0.052), 0.96)
    wood = mat("Wood", (0.12,0.07,0.04), 0.9)

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0))
    bpy.context.object.data.materials.append(ground)

    # distant silhouettes / lantern-like shapes for depth
    for i, x in enumerate((-2.8,-1.8,1.9,2.8)):
        cone(f"BG_{i}", (x,2.8 + 0.35*(i%2),0.82), 0.18, 0.15, 1.35, bg)

    for x in (-2.1,2.1):
        pole = cone("Pole", (x,1.7,1.0), 0.045, 0.045, 2.0, wood)
        sphere("Lantern", (x,1.7,1.72), (0.18,0.18,0.25), mat("LanternMat", (0.60,0.24,0.08), 0.65), 32, 16)


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
    scene.world.color = (0.025,0.028,0.035)

    add_stage()
    head = add_child_face()
    add_hair()
    add_costume()

    # warm sunset rim
    bpy.ops.object.light_add(type="AREA", location=(3.6,1.8,5.1))
    key = bpy.context.object
    key.data.energy = 1050
    key.data.color = (1.0,0.43,0.20)
    key.data.shape = "DISK"
    key.data.size = 4.2
    look_at(key, (0.0,0.0,2.0))

    # cool face fill
    bpy.ops.object.light_add(type="AREA", location=(-2.0,-3.8,3.2))
    fill = bpy.context.object
    fill.data.energy = 640
    fill.data.color = (0.62,0.76,1.0)
    fill.data.size = 3.0
    look_at(fill, (0.0,-0.1,2.3))

    # soft front eye light
    bpy.ops.object.light_add(type="AREA", location=(0.2,-4.6,3.4))
    eye = bpy.context.object
    eye.data.energy = 180
    eye.data.color = (1.0,0.82,0.72)
    eye.data.size = 1.4
    look_at(eye, (0.0,-0.1,2.65))

    target = bpy.data.objects.new("LookdevTarget", None)
    bpy.context.collection.objects.link(target)
    target.location = (0.0,0.0,2.0)

    bpy.ops.object.camera_add(location=(0.0,-7.0,2.50))
    cam = bpy.context.object
    cam.data.lens = 72
    cam.data.sensor_width = 36.0
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = head
    cam.data.dof.aperture_fstop = 2.6
    track = cam.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam

    # Keep v1 transform hierarchy flat. The still does not need runtime parenting,
    # and flat world-space transforms avoid accidental double transforms.

    bpy.context.view_layer.update()
    head_center = head.matrix_world.translation
    torso = bpy.data.objects.get("Torso")
    skirt = bpy.data.objects.get("SkirtOuter")
    checks = {
        "head": head_center,
        "torso": torso.matrix_world.translation if torso else Vector((0.0,0.0,1.84)),
        "skirt": skirt.matrix_world.translation if skirt else Vector((0.0,0.0,0.95)),
    }
    projected = {}
    for name, point in checks.items():
        co = world_to_camera_view(scene, cam, point)
        projected[name] = (float(co.x), float(co.y), float(co.z))
        if not (0.12 <= co.x <= 0.88 and 0.08 <= co.y <= 0.94 and co.z > 0.0):
            raise RuntimeError(f"child LookDev framing gate failed for {name}: {projected[name]}")
    if projected["head"][1] <= projected["torso"][1]:
        raise RuntimeError(f"child LookDev vertical framing invalid: {projected}")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_FRAMING_PASS projected={projected}")

    output = Path(a.output).expanduser().resolve()
    blend_output = Path(a.blend_output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    blend_output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size < 20000:
        raise RuntimeError("child LookDev render missing or unexpectedly small")
    print(f"VIDEO_CREATOR_CHILD_LOOKDEV_PASS output={output}")


if __name__ == "__main__":
    main()
