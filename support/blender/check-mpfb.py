import importlib
import sys

import bpy


def discover_mpfb_root():
    candidates = set()

    for module_name in list(sys.modules):
        parts = module_name.split(".")
        if "mpfb" in parts:
            index = parts.index("mpfb")
            candidates.add(".".join(parts[:index + 1]))

    try:
        for addon_key in bpy.context.preferences.addons.keys():
            parts = str(addon_key).split(".")
            if "mpfb" in parts:
                index = parts.index("mpfb")
                candidates.add(".".join(parts[:index + 1]))
    except Exception:
        pass

    # Known Blender extension package form; harmless if unavailable.
    candidates.update({"bl_ext.blender_org.mpfb", "mpfb"})

    errors = []
    for root in sorted(candidates, key=len, reverse=True):
        try:
            importlib.import_module(root)
            return root
        except Exception as error:
            errors.append(f"{root}: {error}")

    raise RuntimeError("MPFB root package not importable: " + " | ".join(errors))


def dynamic_import(module_suffix, symbol):
    root = discover_mpfb_root()
    relative = module_suffix
    if relative.startswith("mpfb."):
        relative = relative[len("mpfb."):]
    module_name = f"{root}.{relative}"
    module = importlib.import_module(module_name)
    if not hasattr(module, symbol):
        raise RuntimeError(f"MPFB symbol unavailable: {module_name}.{symbol}")
    return getattr(module, symbol)


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

print("VIDEO_CREATOR_MPFB_PASS api=HumanService.create_human macro=TargetService.get_default_macro_info_dict", flush=True)
