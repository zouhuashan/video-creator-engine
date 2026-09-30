"""Fixed-rig modern story blocking used by the local episode preview.

This replaces the former sphere/cylinder actors with project-owned CC0 glTF
humanoids.  The renderer remains a control-quality local preview: the rigs,
camera, prop contact and continuity are useful, while final face/cloth detail
may still be replaced by a video provider after human approval.
"""

import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


def build(g):
    spec = g["spec"]
    D, FPS, F = g["D"], g["FPS"], g["F"]
    key, camera = g["key"], g["camera"]
    box, sphere, cylinder = g["_box"], g["_sphere"], g["_cylinder"]
    make_material = g["material"]
    assets = Path(spec["project_path"]) / "production/assets/characters/quaternius-cc0"
    if not (assets / "models/Superhero_Male_FullBody.gltf").is_file():
        raise RuntimeError("fixed humanoid assets are not installed for this project")

    def mat(name, color, roughness=.62, metallic=0.0):
        value = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        value.diffuse_color = (*color, 1)
        value.use_nodes = True
        node = value.node_tree.nodes.get("Principled BSDF")
        node.inputs["Base Color"].default_value = (*color, 1)
        node.inputs["Roughness"].default_value = roughness
        node.inputs["Metallic"].default_value = metallic
        return value

    skin_dark = mat("Mouth", (.19, .018, .02), .48)
    black = mat("Black", (.012, .016, .022), .38)
    warm = mat("WarmWall", (.28, .20, .16), .78)
    cool = mat("CoolWall", (.17, .22, .28), .78)
    floor_mat = mat("Floor", (.095, .085, .08), .72)
    wood = mat("Wood", (.24, .085, .035), .52)
    linen = mat("Linen", (.58, .46, .36), .72)
    metal = mat("Metal", (.15, .17, .20), .38, .25)
    paper_mat = mat("Paper", (.88, .84, .74), .84)
    screen_mat = mat("Screen", (.08, .42, .78), .32, .05)
    food_mat = mat("Food", (.62, .12, .035), .82)
    green = mat("Plant", (.035, .20, .075), .88)

    def key_bone(bone, t, rotation):
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = rotation
        bone.keyframe_insert(data_path="rotation_euler", frame=max(1, min(F, round(t * FPS) + 1)))

    def key_obj(obj, t, *, location=None, rotation=None, scale=None):
        frame = max(1, min(F, round(t * FPS) + 1))
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

    def bind(obj, armature, bone_name):
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

    def clothing_shell(actor, name, predicate, material):
        source = max(actor["meshes"], key=lambda item: len(item.data.vertices))
        shell = source.copy()
        shell.data = source.data.copy()
        shell.name = name
        bpy.context.collection.objects.link(shell)
        shell.data.materials.clear()
        shell.data.materials.append(material)
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
        solidify.thickness = .014
        solidify.offset = 1.0
        return shell

    def garments(actor, top, trousers, dress=False):
        clothing_shell(actor, actor["label"] + "_Top",
                       lambda p: (1.02 <= p.z <= 1.51 and abs(p.x) < .36) or
                                 (1.31 <= p.z <= 1.54 and abs(p.x) < .72), top)
        clothing_shell(actor, actor["label"] + "_Bottom", lambda p: .08 <= p.z <= 1.035, trousers)
        if dress:
            bpy.ops.mesh.primitive_cone_add(vertices=28, radius1=.39, radius2=.24, depth=.42,
                                            location=(0, .035, .88))
            skirt = bpy.context.object
            skirt.name = actor["label"] + "_Skirt"
            skirt.data.materials.append(trousers)
            bind(skirt, actor["rig"], "pelvis")

    def import_actor(label, female, location, yaw, top, trousers, hair_file, hair_color, dress=False):
        filename = "Superhero_Female_FullBody.gltf" if female else "Superhero_Male_FullBody.gltf"
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=str(assets / "models" / filename))
        imported = set(bpy.context.scene.objects) - before
        rig = next(obj for obj in imported if obj.type == "ARMATURE")
        meshes = [obj for obj in imported if obj.type == "MESH" and obj.parent == rig]
        rig.name = label + "_Rig"
        rig.location = location
        rig.rotation_euler[2] = yaw
        for obj in meshes:
            obj.name = label + "_" + obj.name
        eyes = next((obj for obj in meshes if "Eyes" in obj.name), None)
        brows = next((obj for obj in meshes if "Eyebrows" in obj.name), None)
        before_hair = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=str(assets / "hair" / hair_file))
        hair = next(obj for obj in set(bpy.context.scene.objects) - before_hair if obj.type == "MESH")
        hair.name = label + "_Hair"
        hair_mat = mat(label + "_HairMat", hair_color, .48)
        for slot in hair.material_slots:
            slot.material = hair_mat
        bind(hair, rig, "Head")
        # The source rig has no jaw or facial blendshapes.  A floating mouth
        # proxy was more distracting than useful in close-up, so the episode
        # blockout keeps the authored face intact until a real face rig exists.
        mouth = None
        actor = {"label": label, "rig": rig, "meshes": meshes, "eyes": eyes,
                 "brows": brows, "hair": hair, "mouth": mouth, "location": Vector(location), "yaw": yaw}
        garments(actor, top, trousers, dress)
        add_hand_ik(actor)
        return actor

    def add_hand_ik(actor):
        rig = actor["rig"]
        actor["hand_targets"] = {}
        for side in ("l", "r"):
            hand = rig.data.bones["hand_" + side]
            sign = 1 if hand.tail_local.x >= 0 else -1
            target = bpy.data.objects.new(actor["label"] + "_HandTarget_" + side, None)
            target.empty_display_type = "SPHERE"; target.empty_display_size = .025
            target.parent = rig; target.location = (sign * .29, -.08, 1.02)
            bpy.context.scene.collection.objects.link(target)
            pole = bpy.data.objects.new(actor["label"] + "_ElbowPole_" + side, None)
            pole.empty_display_type = "PLAIN_AXES"; pole.empty_display_size = .06
            pole.parent = rig; pole.location = (sign * .70, .22, 1.24)
            bpy.context.scene.collection.objects.link(pole)
            constraint = rig.pose.bones["hand_" + side].constraints.new("IK")
            constraint.name = actor["label"] + "_IK_" + side
            constraint.target = target; constraint.pole_target = pole
            constraint.chain_count = 3; constraint.iterations = 64
            constraint.pole_angle = math.radians(90 if sign > 0 else -90)
            actor["hand_targets"][side] = target

    names = {c["name"]: c["id"] for c in spec.get("characters", [])}
    casts = set(spec.get("cast_ids", []))
    actors = {}
    palette = {
        "陈浩": (False, mat("ChenKnit", (.055, .11, .20), .74), mat("ChenPants", (.018, .024, .038), .76), "Hair_SimpleParted.gltf", (.018, .012, .010), False),
        "林晓": (True, mat("LinKnit", (.31, .028, .045), .72), mat("LinSkirt", (.085, .018, .032), .78), "Hair_Buns.gltf", (.022, .012, .012), True),
        "主管": (False, mat("BossJacket", (.19, .20, .23), .66), mat("BossPants", (.055, .06, .075), .72), "Hair_SimpleParted.gltf", (.11, .10, .095), False),
    }

    def person(name, location, yaw=0, seated=False):
        if names.get(name) not in casts:
            return None
        female, top, trousers, hair_file, hair_color, dress = palette[name]
        actor = import_actor({"陈浩": "ChenHao", "林晓": "LinXiao", "主管": "Supervisor"}[name],
                             female, location, yaw, top, trousers, hair_file, hair_color, dress)
        actors[name] = actor
        pose = actor["rig"].pose.bones
        if seated:
            for side in ("l", "r"):
                key_bone(pose["thigh_" + side], 0, (-1.38, 0, 0))
                key_bone(pose["calf_" + side], 0, (1.35, 0, 0))
                key_bone(pose["foot_" + side], 0, (.10, 0, 0))
            key_bone(pose["spine_01"], 0, (.055, 0, 0))
            box(actor["label"] + "_ChairSeat", (location[0], location[1] + .02, .62), (.31, .30, .045), linen)
            box(actor["label"] + "_ChairBack", (location[0], location[1] + .28, .99), (.31, .045, .38), wood)
            # Rest forearms toward the tabletop/lap instead of letting the
            # source rig fall back to a T pose or splay both hands sideways.
            for target in actor["hand_targets"].values():
                target.location = (math.copysign(.19, target.location.x), -.25, .98)
        # Restrained breathing and gaze motion, instead of whole-body bobbing.
        for t, rot in ((0, (.025, 0, 0)), (D * .5, (-.018, 0, .015)), (D, (.018, 0, 0))):
            key_bone(pose["spine_02"], t, rot)
        for t, rot in ((0, (0, 0, 0)), (D * .45, (-.025, 0, .055)), (D, (0, 0, .02))):
            key_bone(pose["Head"], t, rot)
        blink(actor, min(D * .42, 1.55))
        return actor

    def blink(actor, t):
        eyes = actor.get("eyes")
        if not eyes:
            return
        original = tuple(eyes.scale)
        key_obj(eyes, max(0, t - .08), scale=original)
        key_obj(eyes, t, scale=(original[0], original[1], original[2] * .10))
        key_obj(eyes, min(D, t + .08), scale=original)

    def gesture(actor, side="r", amount=.5, start=.25):
        if not actor:
            return
        target = actor["hand_targets"][side]
        base = Vector(target.location)
        sign = 1 if base.x >= 0 else -1
        raised = Vector((sign * (.25 - .05 * amount), -.18 - .12 * amount, 1.06 + .24 * amount))
        key_obj(target, 0, location=base)
        key_obj(target, min(D * .36, start + .55), location=raised)
        key_obj(target, D * .72, location=raised + Vector((0, .02, -.025)))
        key_obj(target, D, location=base)

    def react(actor, worried=True):
        if not actor:
            return
        pose = actor["rig"].pose.bones
        for t, rot in ((0, (0, 0, 0)), (D * .48, ((.055 if worried else -.025), 0, .11)),
                       (D, ((.025 if worried else 0), 0, .035))):
            key_bone(pose["Head"], t, rot)
        if actor.get("brows"):
            base = tuple(actor["brows"].location)
            key_obj(actor["brows"], 0, location=base)
            key_obj(actor["brows"], D * .48, location=Vector(base) + Vector((0, 0, .010 if worried else -.005)))
            key_obj(actor["brows"], D, location=base)

    def attach_phone(actor):
        if not actor:
            return None
        target = actor["hand_targets"]["r"]
        base = Vector(target.location)
        lifted = Vector((base.x * .62, -.24, 1.32))
        key_obj(target, 0, location=lifted)
        key_obj(target, D, location=lifted + Vector((0, -.02, .025)))
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        phone = bpy.context.object; phone.name = actor["label"] + "_Phone"; phone.scale = (.042, .012, .078)
        phone.data.materials.append(black); phone.parent = target; phone.location = (0, -.025, 0)
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        display = bpy.context.object; display.name = actor["label"] + "_PhoneDisplay"; display.scale = (.035, .004, .068)
        display.data.materials.append(screen_mat); display.parent = target; display.location = (0, -.039, 0)
        react(actor, True)
        return phone

    def talk(actor):
        if not actor:
            return
        if actor.get("mouth") is None:
            return
        envelope = spec.get("mouth_envelope", [])
        if not envelope:
            envelope = [[0, 0], [D * .3, .7], [D * .6, .35], [D, 0]]
        for t, energy in envelope:
            key_obj(actor["mouth"], min(D, float(t)), scale=(1, 1, .38 + min(1, float(energy)) * 1.15))

    def walk(actor, start, end, begin=.05, stop=None):
        if not actor:
            return
        stop = stop or D * .72
        rig = actor["rig"]
        key_obj(rig, 0, location=start)
        key_obj(rig, begin, location=start)
        key_obj(rig, stop, location=end)
        key_obj(rig, D, location=end)
        pose = rig.pose.bones
        steps = max(3, int((stop - begin) / .34))
        for index in range(steps + 1):
            t = begin + (stop - begin) * index / steps
            swing = .34 if index % 2 == 0 else -.34
            for side, sign in (("l", 1), ("r", -1)):
                key_bone(pose["thigh_" + side], t, (swing * sign, 0, 0))
                key_bone(pose["calf_" + side], t, (max(0, -swing * sign * .75), 0, 0))
                hand = actor["hand_targets"][side]
                base = Vector((hand.location.x, -.08, 1.02))
                key_obj(hand, t, location=base + Vector((0, swing * sign * .10, .015 * (index % 2))))
        for side in ("l", "r"):
            key_bone(pose["thigh_" + side], stop, (0, 0, 0))
            key_bone(pose["calf_" + side], stop, (0, 0, 0))
            hand = actor["hand_targets"][side]
            key_obj(hand, stop, location=(hand.location.x, -.08, 1.02))

    def table(x=0, y=.2, z=.91, sx=1.05, sy=.48):
        box("TableTop", (x, y, z), (sx, sy, .055), wood)
        for dx in (-sx + .10, sx - .10):
            for dy in (-sy + .10, sy - .10):
                box("TableLeg", (x + dx, y + dy, z / 2), (.04, .04, z / 2), wood)

    # Shared set with stronger depth, cleaner silhouettes and practical light sources.
    box("Floor", (0, .7, -.07), (3.5, 3.3, .07), floor_mat)
    box("BackWall", (0, 2.85, 1.55), (3.5, .05, 1.55), cool if "office" in spec["action"] else warm)
    box("Window", (-1.55, 2.78, 1.82), (.82, .025, .66), screen_mat)
    for x in (-2.08, -1.55, -1.02):
        box("WindowBar", (x, 2.74, 1.82), (.018, .018, .67), linen)
    box("WindowBar", (-1.55, 2.74, 1.82), (.84, .018, .018), linen)

    act = spec["action"]
    props = {}
    if act == "modern_office":
        table(0, .42, .90, 1.0, .45)
        chen = person("陈浩", (-.62, -.34, 0), math.radians(-7), True)
        boss = person("主管", (.62, 1.18, 0), math.pi + math.radians(7), True)
        props["PROP_DOCUMENT"] = box("DismissalNotice", (0, .34, .972), (.16, .21, .008), paper_mat)
        box("Laptop", (.45, .67, 1.06), (.22, .03, .14), metal)
        if "推到" in spec.get("visual", ""):
            key_obj(props["PROP_DOCUMENT"], 0, location=(.28, .68, .972))
            key_obj(props["PROP_DOCUMENT"], D * .46, location=(-.18, .20, .972))
            key_obj(props["PROP_DOCUMENT"], D, location=(-.18, .20, .972))
            gesture(boss, amount=1.1)
        react(chen, True)
        react(boss, "避开" in spec.get("visual", ""))
    elif act == "modern_stairs":
        for i in range(7):
            box("StairStep", (0, .48 + i * .40, .10 + i * .17), (1.42, .20, .10 + i * .17), linen)
        lin = person("林晓", (-.22, .30, 0), 0, True)
        props["PROP_DOCUMENT"] = box("DismissalNotice", (-.05, .06, .88), (.14, .18, .008), paper_mat)
        attach_phone(lin)
        react(lin, True)
    elif act == "modern_store":
        table(-1.05, .10, .86, .53, .34)
        table(1.05, 1.48, .86, .53, .34)
        chen = person("陈浩", (-1.05, -.34, 0), 0, True)
        lin = person("林晓", (1.05, 1.02, 0), math.pi, True)
        for z in (.48, 1.0, 1.52):
            box("Shelf", (0, 1.04, z), (.32, .68, .032), metal)
            for i in range(4):
                cylinder("Bottle", (-.12, .58 + i * .30, z + .15), .038, .24, screen_mat)
                box("Goods", (.12, .58 + i * .30, z + .12), (.065, .07, .095), food_mat)
        cylinder("MineralWater", (-1.0, .10, 1.05), .045, .29, screen_mat)
        attach_phone(lin if names.get("林晓") == spec.get("character_id") else chen)
        react(chen, True); react(lin, True)
    elif act == "modern_door":
        box("HomeDoor", (-1.35, 2.70, 1.15), (.58, .08, 1.15), wood)
        box("Elevator", (1.25, 2.70, 1.15), (.62, .07, 1.15), metal)
        chen = person("陈浩", (-.72, .30, 0), math.radians(12))
        lin = person("林晓", (.78, 1.30, 0), math.pi + math.radians(-12))
        walk(lin, (.78, 1.30, 0), (.42, .56, 0), .05, D * .58)
        react(chen, False); react(lin, False)
    elif act in ("modern_dinner", "modern_system"):
        table(0, .30, .92, .82, .50)
        chen = person("陈浩", (-.58, .18, 0), math.radians(-7), True)
        lin = person("林晓", (.58, .18, 0), math.radians(7), True)
        for x in (-.32, .32):
            cylinder("Bowl", (x, -.04, 1.02), .13, .06, paper_mat)
            sphere("Food", (x, -.04, 1.06), (.09, .07, .025), food_mat)
        props["PROP_NOTICES"] = box("PocketNotice", (-.56, .18, .62), (.09, .014, .11), paper_mat)
        box("BagNotice", (.72, .23, .53), (.13, .045, .14), paper_mat)
        if act == "modern_system":
            props["PROP_PHONE"] = attach_phone(chen)
            react(lin, True)
        elif "夹了一块" in spec.get("visual", "") and lin:
            gesture(lin, amount=1.45)
            for offset in (-.012, .012):
                bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=.006, depth=.30, location=(0, 0, 0))
                stick = bpy.context.object; stick.name = "Chopstick"; stick.data.materials.append(wood)
                stick.parent = lin["hand_targets"]["r"]; stick.location = (offset, -.03, -.10); stick.rotation_euler.x = .48
        react(chen, True); react(lin, True)
    elif act == "modern_kitchen":
        box("KitchenCounter", (0, 1.34, .48), (1.30, .40, .48), wood)
        props["PROP_POT"] = sphere("OldPotBody", (0, 1.18, 1.08), (.28, .24, .11), metal)
        for x in (-.34, .34):
            box("PotHandle", (x, 1.18, 1.10), (.07, .04, .025), metal)
        chen = person("陈浩", (-.78, .24, 0), math.radians(8))
        props["PROP_PHONE"] = attach_phone(chen)
        react(chen, True)
        curve = bpy.data.curves.new("PotNumber", "FONT")
        curve.body = "1987-0416"; curve.size = .055
        number = bpy.data.objects.new("PotNumber", curve)
        bpy.context.collection.objects.link(number)
        number.location = (-.18, 1.035, 1.16)
        curve.materials.append(paper_mat)
    else:
        raise ValueError("Unknown modern scene " + act)

    speaker_name = next((c["name"] for c in spec.get("characters", []) if c["id"] == spec.get("character_id")), None)
    talk(actors.get(speaker_name))
    gesture(actors.get(speaker_name), amount=.85)

    bpy.context.view_layer.update()
    # Camera grammar: never push the low-poly face into an extreme full-screen closeup.
    framing = spec.get("framing") or "wide"
    focus = spec.get("focus_id", "")
    role = next((name for name, cid in names.items() if cid == focus), None)
    actor = actors.get(role)
    if framing in ("closeup", "medium") and actor:
        loc, yaw = actor["location"], actor["yaw"]
        distance = 1.65 if framing == "closeup" else 2.45
        height = 1.48 if framing == "closeup" else 1.26
        target = (loc.x, loc.y, height)
        start = (loc.x + math.sin(yaw) * distance, loc.y - math.cos(yaw) * distance, height + .12)
        end = (loc.x + math.sin(yaw) * (distance - .10), loc.y - math.cos(yaw) * (distance - .10), height + .08)
        camera(start, end, target, 58 if framing == "closeup" else 50)
    elif framing == "insert" and props.get(focus):
        target = props[focus].matrix_world.translation
        start = target + Vector((.30, -.78, .58))
        end = target + Vector((.22, -.66, .48))
        camera(tuple(start), tuple(end), tuple(target), 58)
    else:
        targets = [a["location"] + Vector((0, 0, 1.18)) for a in actors.values()]
        target = sum(targets, Vector()) / max(1, len(targets)) if targets else Vector((0, .7, 1.1))
        camera((.25, -4.65, 1.85), (.18, -4.30, 1.80), tuple(target), 48)

    # Warm key, cool fill and rim make body volume readable without increasing model complexity.
    for name, energy, color, location, size in (
        ("Key", 760, (1.0, .58, .38), (-1.8, -1.6, 3.0), 3.2),
        ("Fill", 420, (.32, .52, 1.0), (1.8, -.8, 2.2), 2.6),
        ("Rim", 520, (1.0, .31, .18), (0, 2.3, 2.5), 1.8),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy; data.color = color; data.shape = "DISK"; data.size = size
        lamp = bpy.data.objects.new(name, data); lamp.location = location
        bpy.context.scene.collection.objects.link(lamp)
        lamp.rotation_euler = (Vector((0, .4, 1.2)) - lamp.location).to_track_quat("-Z", "Y").to_euler()

    return {"actors": actors, "renderer": "fixed_humanoid", "asset_root": str(assets)}
