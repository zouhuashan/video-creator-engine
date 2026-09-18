extends Node2D

@export var solver_script: Script

func _ready() -> void:
    var skeleton := Skeleton2D.new()
    skeleton.name = "Skeleton2D"
    add_child(skeleton)

    var upper := Bone2D.new()
    upper.name = "UpperArm"
    upper.position = Vector2(100, 100)
    upper.set_autocalculate_length_and_angle(false)
    upper.set_length(80.0)
    skeleton.add_child(upper)

    var forearm := Bone2D.new()
    forearm.name = "Forearm"
    forearm.position = Vector2(80, 0)
    forearm.set_autocalculate_length_and_angle(false)
    forearm.set_length(60.0)
    upper.add_child(forearm)

    var target := Vector2(190, 145)
    var solver = solver_script.new()
    var result: Dictionary = solver.solve(upper.global_position, target, 80.0, 60.0, 1.0)
    if not result.get("ok", false):
        push_error("IK solver failed")
        get_tree().quit(2)
        return

    upper.rotation = float(result["shoulder_rotation"])
    forearm.rotation = float(result["elbow_rotation"])
    var tip := forearm.to_global(Vector2(60, 0))
    var error := tip.distance_to(target)
    if error > 0.75:
        push_error("IK tip error=" + str(error))
        get_tree().quit(3)
        return

    print("VIDEO_CREATOR_GODOT_IK_PASS error=", error)
    get_tree().quit(0)
