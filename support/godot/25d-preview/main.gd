extends Node2D

var config: Dictionary = {}
var character_root: Node2D
var layer_nodes: Dictionary = {}
var layer_sprites: Dictionary = {}
var base_node_positions: Dictionary = {}
var base_sprite_positions: Dictionary = {}
var base_root_position: Vector2
var background_sprite: Sprite2D
var base_background_position: Vector2
var base_background_scale: Vector2
var elapsed: float = 0.0
var duration: float = 4.0
var output_size: Vector2 = Vector2(720.0, 1280.0)


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
    var output: Dictionary = config.get("output", {})
    output_size = Vector2(
        float(output.get("width", 720)),
        float(output.get("height", 1280))
    )

    _build_background()
    if not _build_character():
        get_tree().quit(5)
        return


func _build_background() -> void:
    var background: ColorRect = ColorRect.new()
    background.position = Vector2.ZERO
    background.size = output_size
    background.color = Color(0.025, 0.034, 0.052, 1.0)
    background.z_index = -100
    add_child(background)

    var background_data: Dictionary = config.get("background", {})
    var path: String = str(background_data.get("path", ""))
    if not path.is_empty():
        var texture: Texture2D = _load_texture(path)
        if texture != null:
            background_sprite = Sprite2D.new()
            background_sprite.texture = texture
            background_sprite.centered = true
            background_sprite.position = output_size * 0.5
            var texture_size: Vector2 = texture.get_size()
            var cover: float = maxf(output_size.x / texture_size.x, output_size.y / texture_size.y)
            cover *= float(background_data.get("zoom", 1.018))
            background_sprite.scale = Vector2(cover, cover)
            background_sprite.z_index = -95
            add_child(background_sprite)
            base_background_position = background_sprite.position
            base_background_scale = background_sprite.scale

    var dimmer: ColorRect = ColorRect.new()
    dimmer.position = Vector2.ZERO
    dimmer.size = output_size
    dimmer.color = Color(0.01, 0.018, 0.035, float(background_data.get("dimming", 0.12)))
    dimmer.z_index = -90
    add_child(dimmer)


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

    var framing: Dictionary = config.get("framing", {})
    var scale_value: float = (output_size.x / canvas_size.x) * float(framing.get("zoom", 1.34))
    character_root.scale = Vector2(scale_value, scale_value)
    character_root.z_index = 10
    var bounds: Dictionary = framing.get("content_bounds", {})
    var content_bottom: float = float(bounds.get("body_bottom", bounds.get("bottom", canvas_size.y * 0.72)))
    var bottom_overscan: float = float(framing.get("bottom_overscan_px", 20.0))
    var focus_x: float = float(framing.get("focus_x", canvas_size.x * 0.5))
    base_root_position = Vector2(
        output_size.x * 0.5 - focus_x * scale_value,
        output_size.y + bottom_overscan - content_bottom * scale_value
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


func _smoothstep(value: float) -> float:
    var x: float = clampf(value, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


func _process(delta: float) -> void:
    elapsed += delta
    if duration <= 0.0 or character_root == null:
        return

    var progress: float = clampf(elapsed / duration, 0.0, 1.0)
    var wave: float = sin(progress * TAU)
    var breath: float = sin(progress * TAU)

    if background_sprite != null:
        var push: float = _smoothstep(progress)
        background_sprite.scale = base_background_scale * (1.0 + push * 0.008)
        background_sprite.position = base_background_position + Vector2(-push * 1.8, push * 0.8)

    character_root.position = base_root_position + Vector2(wave * 0.55, -breath * 0.9)

    if layer_nodes.has("torso"):
        var torso: Node2D = layer_nodes["torso"] as Node2D
        torso.scale = Vector2(1.0 + breath * 0.001, 1.0 + breath * 0.003)
        torso.rotation = deg_to_rad(wave * 0.08)

    if layer_nodes.has("head"):
        var head: Node2D = layer_nodes["head"] as Node2D
        head.rotation = deg_to_rad(wave * 0.35)
        var head_base: Vector2 = base_node_positions["head"]
        head.position = head_base + Vector2(wave * 0.45, -breath * 0.55)

    if layer_nodes.has("upper_arm_l"):
        var upper_arm_l: Node2D = layer_nodes["upper_arm_l"] as Node2D
        upper_arm_l.rotation = deg_to_rad(wave * 0.18)
    if layer_nodes.has("forearm_l"):
        var forearm_l: Node2D = layer_nodes["forearm_l"] as Node2D
        forearm_l.rotation = deg_to_rad(sin(progress * TAU - 0.25) * 0.16)
    if layer_nodes.has("hand_l"):
        var hand_l: Node2D = layer_nodes["hand_l"] as Node2D
        hand_l.rotation = deg_to_rad(sin(progress * TAU - 0.4) * 0.12)

    if layer_nodes.has("upper_arm_r"):
        var upper_arm_r: Node2D = layer_nodes["upper_arm_r"] as Node2D
        upper_arm_r.rotation = deg_to_rad(wave * -0.16)
    if layer_nodes.has("forearm_r"):
        var forearm_r: Node2D = layer_nodes["forearm_r"] as Node2D
        forearm_r.rotation = deg_to_rad(sin(progress * TAU - 0.25) * -0.14)
    if layer_nodes.has("hand_r"):
        var hand_r: Node2D = layer_nodes["hand_r"] as Node2D
        hand_r.rotation = deg_to_rad(sin(progress * TAU - 0.4) * -0.11)

    for name_variant in layer_sprites.keys():
        var name: String = str(name_variant)
        var sprite: Sprite2D = layer_sprites[name] as Sprite2D
        var item: Dictionary = _layer_config(name)
        var depth: float = float(item.get("depth", 0.0))
        var secondary: float = float(item.get("secondary_motion", 0.0))
        var sprite_base: Vector2 = base_sprite_positions[name]
        sprite.position = sprite_base + Vector2(
            wave * depth * 0.8 + sin(progress * TAU - secondary) * secondary * 0.55,
            -breath * depth * 0.45
        )
        sprite.scale = Vector2.ONE
