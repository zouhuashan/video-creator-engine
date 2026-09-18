import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main():
    args = parse_args()
    version = tuple(bpy.app.version)
    if not ((5, 2, 0) <= version < (5, 3, 0)):
        raise RuntimeError(f"Blender 5.2 LTS required, found {version}")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 360
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.018, 0.024, 0.04)

    bpy.ops.object.armature_add(enter_editmode=True, location=(0.0, 0.0, 0.0))
    armature = bpy.context.object
    armature.name = "VC_Armature"
    edit_bone = armature.data.edit_bones[0]
    edit_bone.name = "root"
    edit_bone.head = (0.0, 0.0, 0.0)
    edit_bone.tail = (0.0, 0.0, 1.7)
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        location=(0.0, 0.0, 1.75),
        scale=(0.48, 0.38, 0.58),
    )
    head = bpy.context.object
    head.name = "AnimeHead"

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48,
        radius=0.42,
        depth=1.45,
        location=(0.0, 0.0, 0.75),
    )
    body = bpy.context.object
    body.name = "AnimeBody"

    material = bpy.data.materials.new("VC_Toon_Base")
    material.diffuse_color = (0.42, 0.13, 0.2, 1.0)
    material.roughness = 0.82
    head.data.materials.append(material)
    body.data.materials.append(material)

    bpy.ops.object.light_add(type="AREA", location=(2.8, -3.0, 4.6))
    key = bpy.context.object
    key.data.energy = 900
    key.data.shape = "DISK"
    key.data.size = 4.0
    look_at(key, (0.0, 0.0, 1.0))

    bpy.ops.object.light_add(type="AREA", location=(-2.0, 1.0, 2.8))
    fill = bpy.context.object
    fill.data.energy = 420
    fill.data.size = 3.5
    look_at(fill, (0.0, 0.0, 1.1))

    bpy.ops.object.camera_add(location=(0.0, -7.2, 2.3))
    camera = bpy.context.object
    camera.data.lens = 58
    look_at(camera, (0.0, 0.0, 1.0))
    scene.camera = camera

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)

    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("Blender smoke render was not created")
    if armature.type != "ARMATURE":
        raise RuntimeError("Armature smoke object is invalid")
    print(f"VIDEO_CREATOR_BLENDER_ANIME_SMOKE_PASS output={output}")


if __name__ == "__main__":
    main()
