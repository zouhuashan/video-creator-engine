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

## Build Rig V2

Generate an upper-body template for one character:

```bash
python3 scripts/build_character_rig_v2.py template \\
  --character-id CHR-JHY-BAIHUA \\
  --character-name 百花仙子 \\
  --rig-id RIG2-CHR-JHY-BAIHUA-UPPER-V1 \\
  --profile GODOT_UPPER_BODY_IK \\
  --output /tmp/baihua-rig-v2.json
```

Fill each layer's project-local transparent PNG path and joint pivot, then build:

```bash
python3 scripts/build_character_rig_v2.py build \\
  projects/jinghua-yuan-series \\
  --spec /tmp/baihua-rig-v2.json
```

All Rig V2 layers must share the same RGBA canvas. Pivots use canvas coordinates. The builder registers every layer as a versioned project asset and writes `visual-bible/character-rigs-v2.json` with joint chains and human review still `PENDING`.

The readiness command merges V1 and V2 manifests by character and prefers V2 when both exist, so a newly upgraded character immediately replaces its V1 readiness result without deleting the V1 asset history.

## Rosetta 终端与 Apple Silicon

如果当前 Terminal 本身运行在 Rosetta/x86_64，直接调用 `/opt/homebrew/bin/brew` 会被 Homebrew 拒绝。项目安装器因此固定使用：

```bash
/usr/bin/arch -arm64 /opt/homebrew/bin/brew install --cask godot
```

Godot 当前 Homebrew 分发为 cask，安装后默认提供：

```text
/Applications/Godot.app/Contents/MacOS/Godot
/opt/homebrew/bin/godot
```

版本检查和 headless smoke 同样强制 `arch -arm64`，因此无需先退出 Rosetta Terminal 才能运行本项目的 Godot 工具链。
