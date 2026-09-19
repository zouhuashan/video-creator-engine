import json
import os
from pathlib import Path

import bpy


STATUS_PATH = Path(
    os.environ.get("VIDEO_CREATOR_MPFB_STATUS", "cache/mpfb-check.json")
).expanduser().resolve()


def main():
    if not hasattr(bpy.ops, "mpfb") or not hasattr(bpy.ops.mpfb, "create_human"):
        raise RuntimeError("MPFB operator mpfb.create_human is not available")

    operator = bpy.ops.mpfb.create_human
    rna = operator.get_rna_type()
    properties = [
        prop.identifier
        for prop in rna.properties
        if prop.identifier != "rna_type"
    ]

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "status": "PASS",
                "operator": "mpfb.create_human",
                "operator_properties": sorted(properties),
                "blender_version": list(bpy.app.version),
                "automation_mode": "registered_operator_only",
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(
        f"MPFB CHECK PASS operator=mpfb.create_human status={STATUS_PATH}",
        flush=True,
    )


if __name__ == "__main__":
    main()
