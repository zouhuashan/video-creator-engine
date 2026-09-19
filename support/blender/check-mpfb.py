import importlib
import sys

import bpy


def dynamic_import(module_suffix, symbol):
    for module_name in list(sys.modules):
        if module_name.endswith(module_suffix):
            module = importlib.import_module(module_name)
            if hasattr(module, symbol):
                return getattr(module, symbol)
    raise RuntimeError(f"MPFB module/symbol unavailable: {module_suffix}.{symbol}")


if not hasattr(bpy.ops, "mpfb") or not hasattr(bpy.ops.mpfb, "create_human"):
    raise RuntimeError("MPFB operator mpfb.create_human is not available")

HumanService = dynamic_import("mpfb.services.humanservice", "HumanService")
TargetService = dynamic_import("mpfb.services.targetservice", "TargetService")

macro = TargetService.get_default_macro_info_dict()
required = {"gender", "age", "muscle", "weight", "proportions", "height", "race"}
missing = sorted(required - set(macro))
if missing:
    raise RuntimeError(f"MPFB macro API incomplete: {missing}")
if not callable(getattr(HumanService, "create_human", None)):
    raise RuntimeError("MPFB HumanService.create_human is unavailable")

print("VIDEO_CREATOR_MPFB_PASS api=HumanService.create_human macro=TargetService.get_default_macro_info_dict")
