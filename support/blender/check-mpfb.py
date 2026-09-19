import importlib
import json
import os
import sys
from pathlib import Path

import bpy


STATUS_PATH = Path(os.environ.get("VIDEO_CREATOR_MPFB_STATUS", "cache/mpfb-check.json")).expanduser().resolve()


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

    candidates.update({"bl_ext.blender_org.mpfb", "mpfb"})

    errors = []
    for root in sorted(candidates, key=len, reverse=True):
        try:
            importlib.import_module(root)
            return root
        except Exception as error:
            errors.append(f"{root}: {error}")

    raise RuntimeError("MPFB root package not importable: " + " | ".join(errors))


def import_symbol(root, relative_module, symbol):
    module_name = f"{root}.{relative_module}"
    module = importlib.import_module(module_name)
    if not hasattr(module, symbol):
        raise RuntimeError(f"MPFB symbol unavailable: {module_name}.{symbol}")
    return getattr(module, symbol)


def main():
    if not hasattr(bpy.ops, "mpfb") or not hasattr(bpy.ops.mpfb, "create_human"):
        raise RuntimeError("MPFB operator mpfb.create_human is not available")

    root = discover_mpfb_root()
    HumanService = import_symbol(root, "services.humanservice", "HumanService")
    TargetService = import_symbol(root, "services.targetservice", "TargetService")

    macro = TargetService.get_default_macro_info_dict()
    required = {"gender", "age", "muscle", "weight", "proportions", "height", "race"}
    missing = sorted(required - set(macro))
    if missing:
        raise RuntimeError(f"MPFB macro API incomplete: {missing}")
    if not callable(getattr(HumanService, "create_human", None)):
        raise RuntimeError("MPFB HumanService.create_human is unavailable")

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "status": "PASS",
                "root_package": root,
                "operator": "mpfb.create_human",
                "service_api": "HumanService.create_human",
                "macro_api": "TargetService.get_default_macro_info_dict",
                "macro_keys": sorted(macro.keys()),
                "blender_version": list(bpy.app.version),
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"MPFB CHECK PASS root={root} status={STATUS_PATH}", flush=True)


if __name__ == "__main__":
    main()
