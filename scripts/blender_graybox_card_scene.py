#!/usr/bin/env python3
"""Render a graybox-controlled shot with Codex-generated 2.5D character cards."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import blender_graybox_scene as graybox  # noqa: E402


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--character-dir", required=True, type=Path)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def _emission_material(name: str, path: Path, *, alpha: bool) -> tuple[bpy.types.Material, bpy.types.Node]:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(path.resolve()), check_existing=True)
    coordinates = nodes.new("ShaderNodeTexCoord")
    material.node_tree.links.new(coordinates.outputs["UV"], texture.inputs["Vector"])
    material.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    if alpha:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        material.node_tree.links.new(texture.outputs["Alpha"], mix.inputs[0])
        material.node_tree.links.new(transparent.outputs["BSDF"], mix.inputs[1])
        material.node_tree.links.new(emission.outputs["Emission"], mix.inputs[2])
        material.node_tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
        if hasattr(material, "use_transparency_overlap"):
            material.use_transparency_overlap = False
    else:
        material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material, texture


def _plane(name: str, material: bpy.types.Material, parent, location, width: float, height: float):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(
        [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)],
        [],
        [(0, 1, 2, 3)],
    )
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index, uv in zip(polygon.loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
            uv_layer.data[loop_index].uv = uv
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    obj.scale = (width / 2.0, height / 2.0, 1.0)
    return obj


def _card_view(front: Vector, camera_direction: Vector) -> str:
    front.z = 0
    camera_direction.z = 0
    if front.length == 0 or camera_direction.length == 0:
        return "front"
    front.normalize()
    camera_direction.normalize()
    angle = math.degrees(math.acos(max(-1.0, min(1.0, front.dot(camera_direction)))))
    if angle < 25:
        return "front"
    if angle < 55:
        return "three_quarter"
    if angle < 125:
        return "profile"
    return "back"


def main() -> int:
    args = _arguments()
    spec_path = args.spec.expanduser().resolve()
    character_dir = args.character_dir.expanduser().resolve()
    background_path = args.background.expanduser().resolve()
    output = args.output.expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    manifest_path = character_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("review_status") not in {"PENDING", "APPROVED"}:
        raise RuntimeError("character card pack has an invalid review state")
    views = manifest.get("views") or {}
    view_paths = {name: character_dir / str((views.get(name) or {}).get("path") or "") for name in ("front", "three_quarter", "profile", "back")}
    if any(not path.is_file() for path in view_paths.values()) or not background_path.is_file():
        raise RuntimeError("character view cards or background plate are missing")

    graybox._clear()
    white = graybox._material("GrayboxWhite", (0.82, 0.84, 0.86, 1.0))
    gray = graybox._material("GrayboxGround", (0.32, 0.34, 0.38, 1.0))
    dark = graybox._material("GrayboxDirection", (0.16, 0.17, 0.19, 1.0))
    graybox._build_environment(white, gray, dark)
    root, body, head, left_arm, right_arm, left_leg, right_leg = graybox._build_actor(white, dark)
    graybox._animate_actor(spec, root, body, head, left_arm, right_arm, left_leg, right_leg)
    camera = graybox._build_camera(spec)

    # Keep all graybox parts animated as control objects, but render only the
    # transparent character card and a camera-facing scene plate.
    for obj in bpy.data.objects:
        obj.hide_render = True
    camera.hide_render = False
    root.hide_render = False

    images = {name: bpy.data.images.load(str(path), check_existing=True) for name, path in view_paths.items()}
    card_material, card_texture = _emission_material("CodexCharacterCard", view_paths["front"], alpha=True)
    # The scene reference is a fixed image plate, so place the character in
    # camera space and map the graybox path to a matching screen-space baseline.
    render_width, render_height = int(spec["width"]), int(spec["height"])
    distance = 80.0
    frame_height = distance * float(camera.data.sensor_width) / float(camera.data.lens)
    plane_height = frame_height
    plane_width = plane_height * render_width / render_height
    card_height = frame_height * 0.34
    card_width = card_height * (2.0 / 3.0)
    card = _plane("CodexCharacterBillboard", card_material, camera, (0.0, 0.0, -distance + 1.0), card_width, card_height)
    card.hide_render = False
    actor_spec = spec["actor"]
    def place_card_for_blocking(scene):
        fps = float(spec["fps"])
        elapsed = float(scene.frame_current - 1) / fps
        move_start = float(actor_spec.get("walk_start_time") or 0.0)
        move_end = float(actor_spec.get("stop_time") or move_start)
        denominator = move_end - move_start
        progress = 1.0 if denominator <= 1e-6 else (elapsed - move_start) / denominator
        progress = max(0.0, min(1.0, progress))
        feet_from_top = 0.78 + progress * 0.10
        card.location.y = (0.5 - feet_from_top) * frame_height + card_height / 2.0
        size_factor = 0.92 + 0.08 * progress
        card.scale.x = card_width / 2.0 * size_factor
        card.scale.y = card_height / 2.0 * size_factor

    plate_material, _ = _emission_material("CodexScenePlate", background_path, alpha=False)
    plate = _plane("CodexCameraBackground", plate_material, camera, (0.0, 0.0, -distance), plane_width, plane_height)
    plate.hide_render = False

    def update_card_view(scene, *_):
        place_card_for_blocking(scene)
        front_world = root.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))
        camera_direction = camera.matrix_world.translation - root.matrix_world.translation
        selected = _card_view(front_world.copy(), camera_direction.copy())
        card_texture.image = images[selected]

    bpy.app.handlers.frame_change_pre.append(update_card_view)
    scene = bpy.context.scene
    graybox._configure_scene(spec, output)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.world.color = (0.0, 0.0, 0.0)
    scene.eevee.taa_render_samples = 32
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix(".blend")))
    bpy.ops.render.render(animation=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Blender card preview produced no MP4")
    print(json.dumps({
        "status": "READY",
        "output": str(output),
        "duration_seconds": spec["duration_seconds"],
        "fps": spec["fps"],
        "visual_route": "CODEX_2_5D_CHARACTER_CARD",
        "source_character": manifest.get("character_id"),
        "character_card_review": manifest.get("review_status"),
        "background_plate": str(background_path),
        "limitations": ["single camera-facing character card", "camera-facing background plate", "no independent character limb deformation"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
