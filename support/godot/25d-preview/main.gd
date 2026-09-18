extends Node2D

var config: Dictionary = {}
var character_root: Node2D
var layer_nodes: Dictionary = {}
var layer_sprites: Dictionary = {}
var base_node_positions: Dictionary = {}
var base_sprite_positions: Dictionary = {}
var base_root_position: Vector2
var elapsed: float = 0.0
var duration: float = 4.0


func _ready() -> void:
    var config_path: String = OS.get_environment("VIDEO_CREATOR_25D_CONFIG")
    if config_path.is_empty():
        push_error("VIDEO_CREATOR_25D_CONFIG is required")
        get_tree().quit(2)
        return

    var file: FileAccess = FileAccess.open(config_path, FileAccess.READ)
    if file == null:
        push_error("cannot open preview config")
        get_tree().quit(3)
        return

    var parsed: Variant = JSON.parse_string(file.get_as_text())
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("preview config must be a JSON object")
        get_tree().quit(4)
        return
    config = parsed
    duration = float(config.get("duration_seconds", 4.0))

    _build_background()
    if not _build_character():
        get_tree().quit(5)
        return
    _build_contact_shadow()


func _build_background() -> void:
    var background: ColorRect = ColorRect.new()
    background.position = Vector2.ZERO
    background.size = Vector2(720.0, 1280.0)
    background.color = Color(0.035, 0.045, 0.070, 1.0)
    background.z_index = -100
    add_child(background)

    var glow: Polygon2D = Polygon2D.new()
    var points: PackedVector2Array = PackedVector2Array()
    var segments: int = 48
    var center: Vector2 = Vector2(360.0, 520.0)
    var radius: Vector2 = Vector2(285.0, 410.0)
    for index in range(segments):
        var angle: float = TAU * float(index) / float(segments)
        points.append(center + Vector2(cos(angle) * radius.x, sin(angle) * radius.y))
    glow.polygon = points
    glow.color = Color(0.12, 0.16, 0.23, 0.34)
    glow.z_index = -90
    add_child(glow)


func _load_texture(path: String) -> Texture2D:
    var image: Image = Image.new()
    var error: Error = image.load(path)
    if error != OK:
        push_error("cannot load layer image: " + path)
        return null
    return ImageTexture.create_from_image(image)


func _build_character() -> bool:
    var canvas: Dictionary = config.get("canvas", {})
    var canvas_size: Vector2 = Vector2(float(canvas.get("width", 0)), float(canvas.get("height", 0)))
    if canvas_size.x <= 0.0 or canvas_size.y <= 0.0:
        push_error("invalid source canvas")
        return false

    character_root = Node2D.new()
    character_root.name = "CharacterRoot"
    add_child(character_root)

    var scale_value: float = minf(620.0 / canvas_size.x, 1120.0 / canvas_size.y)
    character_root.scale = Vector2(scale_value, scale_value)
    base_root_position = Vector2(
        (720.0 - canvas_size.x * scale_value) * 0.5,
        (1280.0 - canvas_size.y * scale_value) * 0.5 - 12.0
    )
    character_root.position = base_root_position

    var layers: Array = config.get("layers", [])
    var pending: Array = layers.duplicate(true)
    var guard: int = 0
    while not pending.is_empty() and guard < 64:
        guard += 1
        var progressed: bool = false
        for item_variant in pending.duplicate():
            var item: Dictionary = item_variant
            var name: String = str(item.get("name", ""))
            var parent_name: String = str(item.get("parent", ""))
            if not parent_name.is_empty() and not layer_nodes.has(parent_name):
                continue

            var pivot_data: Dictionary = item.get("pivot", {})
            var pivot: Vector2 = Vector2(float(pivot_data.get("x", 0)), float(pivot_data.get("y", 0)))
            var parent_node: Node2D = character_root
            if not parent_name.is_empty():
                parent_node = layer_nodes[parent_name] as Node2D
            var parent_pivot: Vector2 = Vector2.ZERO
            if not parent_name.is_empty():
                var parent_data: Dictionary = _layer_config(parent_name)
                var parent_pivot_data: Dictionary = parent_data.get("pivot", {})
                parent_pivot = Vector2(
                    float(parent_pivot_data.get("x", 0)),
                    float(parent_pivot_data.get("y", 0))
                )

            var node: Node2D = Node2D.new()
            node.name = name
            node.position = pivot if parent_name.is_empty() else pivot - parent_pivot
            parent_node.add_child(node)
            node.z_index = int(item.get("z_index", 0))
            layer_nodes[name] = node
            base_node_positions[name] = node.position

            var texture: Texture2D = _load_texture(str(item.get("path", "")))
            if texture == null:
                return false
            var sprite: Sprite2D = Sprite2D.new()
            sprite.texture = texture
            sprite.centered = false
            sprite.position = -pivot
            node.add_child(sprite)
            layer_sprites[name] = sprite
            base_sprite_positions[name] = sprite.position

            pending.erase(item_variant)
            progressed = true

        if not progressed:
            push_error("cannot resolve Rig V2 parent hierarchy")
            return false

    if not pending.is_empty():
        push_error("Rig V2 hierarchy is incomplete")
        return false

    return true


func _layer_config(name: String) -> Dictionary:
    for item_variant in config.get("layers", []):
        var item: Dictionary = item_variant
        if str(item.get("name", "")) == name:
            return item
    return {}


func _build_contact_shadow() -> void:
    if character_root == null:
        return
    var shadow: Polygon2D = Polygon2D.new()
    var points := PackedVector2Array()
    var segments: int = 40
    var canvas: Dictionary = config.get("canvas", {})
    var width: float = float(canvas.get("width", 1000))
    var height: float = float(canvas.get("height", 1600))
    var center: Vector2 = Vector2(width * 0.5, height * 0.88)
    var radius: Vector2 = Vector2(width * 0.22, height * 0.025)
    for index in range(segments):
        var angle: float = TAU * float(index) / float(segments)
        points.append(center + Vector2(cos(angle) * radius.x, sin(angle) * radius.y))
    shadow.polygon = points
    shadow.color = Color(0.0, 0.0, 0.0, 0.22)
    shadow.z_index = -20
    character_root.add_child(shadow)


func _smoothstep(value: float) -> float:
    var x: float = clampf(value, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


func _raise_curve(progress: float) -> float:
    if progress < 0.18:
        return 0.0
    if progress < 0.44:
        return _smoothstep((progress - 0.18) / 0.26)
    if progress < 0.72:
        return 1.0
    if progress < 0.94:
        return 1.0 - _smoothstep((progress - 0.72) / 0.22)
    return 0.0


func _process(delta: float) -> void:
    elapsed += delta
    if duration <= 0.0 or character_root == null:
        return

    var progress: float = fmod(elapsed, duration) / duration
    var wave: float = sin(progress * TAU)
    var breath: float = sin(progress * TAU * 2.0)
    var raise_amount: float = _raise_curve(progress)

    character_root.position = base_root_position + Vector2(wave * 5.5, cos(progress * TAU * 0.5) * 2.5)

    if layer_nodes.has("torso"):
        var torso: Node2D = layer_nodes["torso"] as Node2D
        torso.scale = Vector2(1.0 + breath * 0.004, 1.0 + breath * 0.009)
        torso.rotation = deg_to_rad(wave * 0.45)

    if layer_nodes.has("head"):
        var head: Node2D = layer_nodes["head"] as Node2D
        head.rotation = deg_to_rad(wave * 1.2)
        var head_base: Vector2 = base_node_positions["head"]
        head.position = head_base + Vector2(wave * 1.5, -breath * 1.2)

    if layer_nodes.has("upper_arm_l"):
        var upper_arm_l: Node2D = layer_nodes["upper_arm_l"] as Node2D
        upper_arm_l.rotation = deg_to_rad(-18.0 * raise_amount + wave * 1.4)
    if layer_nodes.has("forearm_l"):
        var forearm_l: Node2D = layer_nodes["forearm_l"] as Node2D
        forearm_l.rotation = deg_to_rad(-24.0 * raise_amount + sin(progress * TAU - 0.45) * 1.8)
    if layer_nodes.has("hand_l"):
        var hand_l: Node2D = layer_nodes["hand_l"] as Node2D
        hand_l.rotation = deg_to_rad(9.0 * raise_amount + sin(progress * TAU - 0.8) * 1.5)

    if layer_nodes.has("upper_arm_r"):
        var upper_arm_r: Node2D = layer_nodes["upper_arm_r"] as Node2D
        upper_arm_r.rotation = deg_to_rad(wave * -2.0)
    if layer_nodes.has("forearm_r"):
        var forearm_r: Node2D = layer_nodes["forearm_r"] as Node2D
        forearm_r.rotation = deg_to_rad(sin(progress * TAU - 0.35) * -2.6)
    if layer_nodes.has("hand_r"):
        var hand_r: Node2D = layer_nodes["hand_r"] as Node2D
        hand_r.rotation = deg_to_rad(sin(progress * TAU - 0.6) * -1.8)

    for name_variant in layer_sprites.keys():
        var name: String = str(name_variant)
        var sprite: Sprite2D = layer_sprites[name] as Sprite2D
        var item: Dictionary = _layer_config(name)
        var depth: float = float(item.get("depth", 0.0))
        var secondary: float = float(item.get("secondary_motion", 0.0))
        var sprite_base: Vector2 = base_sprite_positions[name]
        sprite.position = sprite_base + Vector2(
            wave * depth * 7.0 + sin(progress * TAU - secondary) * secondary * 1.8,
            cos(progress * TAU) * depth * 2.5
        )
        var squash: float = sin(progress * TAU * 1.7 - secondary) * secondary * 0.004
        sprite.scale = Vector2(1.0 + squash, 1.0 - squash * 0.7)
