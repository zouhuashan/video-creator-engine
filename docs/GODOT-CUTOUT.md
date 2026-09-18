# Godot Cutout / Skeleton2D Route

Status: FOUNDATION_READY / local-only / non-generative.

## Production version

VideoCreator uses the stable Godot line only. The current minimum is **4.7.2**. Preview builds are intentionally rejected for production validation.

Godot remains behind the `adapters.motion.godot_cutout` boundary; Scene/Shot JSON and the VideoCreator project repository stay authoritative.

## Install and smoke check

On macOS:

```bash
./install-godot.command
./check-godot.command
```

The installer uses Homebrew when Godot is absent and then runs the repository smoke project under `support/godot/smoke`.

The smoke project proves that:

- the stable engine starts in CLI/headless mode;
- the project can be loaded;
- `Skeleton2D` and a `Bone2D` hierarchy are available;
- the adapter can build a deterministic local command.

It does **not** claim that a production character already has IK-ready artwork.

## Rig V2 readiness

Current Rig V1 assets use broad aligned layers such as:

```text
full
head
torso
lower
```

This is enough for the existing deterministic `LOCAL_CUTOUT_RIG` route but not enough for articulated arm/leg IK.

Check the actual project:

```bash
python3 scripts/godot_rig_readiness.py projects/jinghua-yuan-series
```

Profiles:

```text
LOCAL_CUTOUT_RIG
GODOT_UPPER_BODY_IK
GODOT_FULL_BODY_IK
```

Upper-body IK requires independent left/right upper arm, forearm and hand layers.

Full-body IK additionally requires pelvis, thighs, shins and feet.

## Rig V2 canonical layer names

```text
head
torso
pelvis
upper_arm_l
forearm_l
hand_l
upper_arm_r
forearm_r
hand_r
thigh_l
shin_l
foot_l
thigh_r
shin_r
foot_r
```

The existing `lower` layer remains valid for `LOCAL_CUTOUT_RIG`, but it does not count as independently articulated legs.

## Safety and production boundary

- local files only;
- no upload;
- no generative service;
- external cost recorded as zero;
- no automatic publishing;
- human review remains required;
- Godot output will return as a versioned shot asset instead of becoming a second project source of truth.

## Next implementation

The next implementation step is **Rig V2 segmentation + one representative upper-body IK character**. Only after one real character passes that route should VideoCreator build reusable Godot action clips and move to full-body IK.

Blender Grease Pencil stays the next higher-cost local route for shots that exceed the Godot cutout action library.
