class_name VideoCreatorTwoBoneIK
extends RefCounted

static func solve(
    origin: Vector2,
    target: Vector2,
    upper_length: float,
    lower_length: float,
    bend_sign: float = 1.0
) -> Dictionary:
    if upper_length <= 0.0 or lower_length <= 0.0:
        return {"ok": false, "error": "bone lengths must be positive"}

    var delta: Vector2 = target - origin
    var raw_distance: float = delta.length()
    var minimum: float = absf(upper_length - lower_length) + 0.0001
    var maximum: float = upper_length + lower_length - 0.0001
    var distance: float = clampf(raw_distance, minimum, maximum)

    var target_angle: float = atan2(delta.y, delta.x)
    var cos_shoulder: float = clampf(
        (upper_length * upper_length + distance * distance - lower_length * lower_length)
        / (2.0 * upper_length * distance),
        -1.0,
        1.0
    )
    var shoulder_offset: float = acos(cos_shoulder) * bend_sign
    var shoulder_rotation: float = target_angle - shoulder_offset

    var cos_elbow_internal: float = clampf(
        (upper_length * upper_length + lower_length * lower_length - distance * distance)
        / (2.0 * upper_length * lower_length),
        -1.0,
        1.0
    )
    var elbow_internal: float = acos(cos_elbow_internal)
    var elbow_rotation: float = (PI - elbow_internal) * bend_sign

    return {
        "ok": true,
        "shoulder_rotation": shoulder_rotation,
        "elbow_rotation": elbow_rotation,
        "clamped_distance": distance,
        "reachable": is_equal_approx(raw_distance, distance),
    }
