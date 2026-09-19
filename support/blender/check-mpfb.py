import bpy

if not hasattr(bpy.ops, "mpfb") or not hasattr(bpy.ops.mpfb, "create_human"):
    raise RuntimeError("MPFB operator mpfb.create_human is not available")

print("VIDEO_CREATOR_MPFB_PASS operator=mpfb.create_human")
