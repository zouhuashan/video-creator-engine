extends Node2D

const TwoBoneIK = preload("res://../runtime/two_bone_ik.gd")

func _ready() -> void:
    var skeleton: Skeleton2D = Skeleton2D.new()
    skeleton.name = "Skeleton2D"
    add_child(skeleton)

    var upper: Bone2D = Bone2D.new()
    upper.name = "UpperArm"
    upper.position = Vector2(100.0, 100.0)
    upper.set_autocalculate_length_and_angle(false)
    upper.set_length(80.0)
    skeleton.add_child(upper)
    upper.rest = upper.transform

    var forearm: Bone2D = Bone2D.new()
    forearm.name = "Forearm"
    forearm.position = Vector2(80.0, 0.0)
    forearm.set_autocalculate_length_and_angle(false)
    forearm.set_length(60.0)
    upper.add_child(forearm)
    forearm.rest = forearm.transform

    var target: Vector2 = Vector2(190.0, 145.0)
    var result: Dictionary = TwoBoneIK.solve(
        upper.global_position,
        target,
        80.0,
        60.0,
        1.0
    )
    if not bool(result.get("ok", false)):
        push_error("IK solver failed")
        get_tree().quit(2)
        return

    upper.rotation = float(result["shoulder_rotation"])
    forearm.rotation = float(result["elbow_rotation"])

    var tip: Vector2 = forearm.to_global(Vector2(60.0, 0.0))
    var error_distance: float = tip.distance_to(target)
    if error_distance > 0.75:
        push_error("IK tip error=" + str(error_distance))
        get_tree().quit(3)
        return

    print("VIDEO_CREATOR_GODOT_IK_PASS error=", error_distance)
    get_tree().quit(0)
