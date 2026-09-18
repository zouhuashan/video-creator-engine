extends Node2D

func _ready() -> void:
    var skeleton := get_node("Skeleton2D") as Skeleton2D
    if skeleton == null:
        push_error("Skeleton2D missing")
        get_tree().quit(2)
        return
    if skeleton.get_bone_count() < 2:
        push_error("Bone2D hierarchy missing")
        get_tree().quit(3)
        return
    print("VIDEO_CREATOR_GODOT_SMOKE_PASS bones=", skeleton.get_bone_count())
    get_tree().quit(0)
