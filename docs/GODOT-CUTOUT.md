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

## Web Rig V2 分层

Godot 安装并通过 smoke 后，重启 VideoCreator Web：

```bash
./restart-web.command
```

打开：

```text
http://127.0.0.1:18765
```

进入 **角色美术**，在已有角色 Rig 卡片上点击：

```text
Rig V2 / Godot IK
```

浏览器会直接读取该角色 V1 Rig 的本地源图，不上传任何图片。当前上半身 IK 需要逐层标注：

```text
head
torso
upper_arm_l
forearm_l
hand_l
upper_arm_r
forearm_r
hand_r
```

操作方式：

1. 选择当前层。
2. 使用“勾轮廓”在原图上依次点击多边形点，至少 3 点。
3. 切换“点 Pivot”，为该层点击关节/旋转中心。
4. 所有 8 层完成后点击“生成 Rig V2”。
5. 后台生成项目内透明 PNG、Rig V2 spec、版本资产与 `character-rigs-v2.json`。
6. readiness 立即重新计算；只有实际层齐全才会显示 `GODOT_UPPER_BODY_IK = READY`。

标注几何会保存在：

```text
visual-bible/rig-v2-work/
```

所以页面刷新后可以继续，不需要重新从零标注。

## TwoBoneIK backend

首个生产 IK backend 使用 VideoCreator 自有的余弦定理解算器：

```text
support/godot/runtime/two_bone_ik.gd
```

它驱动 Godot 原生 `Skeleton2D + Bone2D`，避免把生产链唯一绑定到 Godot 当前仍标记为 Experimental 的 `SkeletonModification2DTwoBoneIK`。官方 TwoBoneIK 后续可作为可选 backend。

`./check-godot.command` 现在执行两个 smoke：

- Skeleton2D/Bone2D 基础 smoke；
- TwoBoneIK 端点到达目标的数值 smoke。

### Godot 4.7.2 strict GDScript

The IK runtime uses explicit static types for all numerical intermediates. In projects where `debug/gdscript/warnings/inference_on_variant` is configured as Error, expressions such as generic `abs()` or `clamp()` combined with inferred declarations can otherwise stop script loading. The solver therefore uses `absf`, `clampf`, and explicit `float` declarations.

Runtime-created `Bone2D` nodes also receive an explicit rest transform immediately after parenting. Godot documents the default `Bone2D.rest` as an all-zero Transform2D, while Skeleton2D keeps and uses bone rest poses; leaving that default in a programmatically built smoke skeleton can lead to non-invertible-transform errors.

## 新手引导与一键自动生成

Rig V2 工作台默认启用新手模式。首次打开一个尚未有 Rig V2 分层的角色时，Web 会自动请求本地几何草稿，不上传图片。

自动草稿基于：

- 源 PNG 的透明像素边界；
- V1 已验证的 head/torso 纵向比例；
- 正面人物的肩/肘/腕几何比例；
- 允许关节区域重叠的 Cutout 原则。

每层会显示自动置信度。头部/躯干通常为 HIGH，手臂为 MEDIUM，手部与宽袖通常为 LOW，因此这些位置仍建议人工看一眼。

工作台提供：

```text
新手模式：开/关
重新自动草稿
上一层 / 下一层
一键自动生成 Rig V2
```

“一键自动生成 Rig V2”会直接写入本地 Rig V2 资产并计算 `GODOT_UPPER_BODY_IK` readiness，但生成结果的人工审核状态始终为 `PENDING`。它不会自动批准资产，也不会触发发布。
