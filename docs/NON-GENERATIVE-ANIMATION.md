# Non-Generative Animation Routes

> Project: VideoCreator Engine  
> Status: ACTIVE ARCHITECTURE DECISION  
> Updated: 2026-09-18  
> Principle: non-generative first; remote AI video is optional enhancement only.

## Why this exists

VideoCreator Engine must be able to produce serialized animation even when no image-generation or video-generation API is available. Character identity, continuity, cost and resumability are easier to control when reusable assets are animated deterministically.

The existing Jing Hua Yuan pipeline already implements the first version of this approach: layered PNG character rigs, expression/mouth cues, reusable scene anchors, Pillow rendering, FFmpeg assembly, local TTS/subtitles and human review gates.

## Route hierarchy

| Route | Role | Best for | Automation | Current status |
| --- | --- | --- | --- | --- |
| `LOCAL_CUTOUT_RIG` | Default production route | dialogue, narration, subtle body motion, long-form serialized episodes | High | ACTIVE |
| `GODOT_CUTOUT` | Advanced 2D skeletal route | limbs, IK, mesh deformation, reusable action libraries, particles | High after rig setup | CANDIDATE |
| `BLENDER_GREASE_PENCIL` | 2D/2.5D cinematic route | hero shots, camera moves, hand-drawn effects, complex staging | Medium | CANDIDATE |
| `LIVE2D_CUBISM` | Character close-up route | face, expressions, eye blink, lip sync, hair/clothing physics | High after model setup | OPTIONAL / LICENSE REVIEW |
| `SPINE_SKELETAL` | Commercial skeletal route | full-body reusable actions, IK, runtime blending | High after rig setup | OPTIONAL / LICENSE REVIEW |
| `MANUAL_IMPORT` | Human-made fallback | key hero shots, outsourced animation, hand-drawn corrections | Low | ACTIVE |
| Remote AI video | Optional enhancement | shots that are uneconomical to rig manually | Variable | BLOCKED BY DEFAULT |

## Recommended VideoCreator architecture

### Level 0 — Motion comic / deterministic cutout

Keep the current local pipeline as the cheapest default:

- reusable transparent character layers;
- reusable backgrounds and foreground layers;
- camera pan / zoom / parallax;
- breathing, head/torso motion and simple secondary motion;
- expression swaps;
- mouth cues driven by the audio timeline;
- particles and scene-specific effects;
- FFmpeg mux, subtitles and QC.

Once an asset pack is approved, later episodes mostly reuse assets and parameters instead of generating new images.

### Level 1 — Godot 2D skeleton and IK

Use Godot only behind a render adapter. Scene/Shot JSON remains the business contract.

Target capabilities:

- Skeleton2D / Bone2D rigs;
- FK/IK limb control;
- Polygon2D mesh deformation;
- AnimationPlayer / AnimationTree clips;
- particles and reusable action presets;
- headless/offline rendering to a standard video or image sequence.

This is the preferred next technical experiment because it extends the existing cutout concept rather than replacing it.

### Level 2 — Blender Grease Pencil / 2.5D

Use for shots where flat cutout is visibly insufficient:

- custom hand-drawn motion;
- frame-by-frame accents;
- deformation and armature-driven strokes;
- 2.5D depth and camera movement;
- compositing, lighting and special effects.

The result still returns to VideoCreator as a versioned shot asset, so only that shot needs rerendering.

### Level 3 — Specialized character runtimes

**Live2D Cubism** is useful for dialogue-heavy close-ups because its runtime supports model parameters, motions, expression data, eye blinking, lip sync and physics. It should not become a hard dependency because its Core is proprietary and licensing must be reviewed before commercial deployment.

**Spine** is useful for full-body skeletal animation, reusable clips, IK and runtime blending. It is a strong optional commercial route but should remain behind an adapter and license gate.

### Level 4 — Remote generative video

Remote AI video is never the default fallback. It can only be selected when all of the following are true:

1. the shot is materially expensive or impossible in the deterministic routes;
2. the user explicitly authorizes upload;
3. the user explicitly authorizes possible billing;
4. identity / continuity references are available;
5. the generated output passes the same human review and QC gates as local outputs.

## P28 comparison change

The three representative P28 motion tests should compare **production routes**, not require three AI vendors.

Suggested comparison:

1. dialogue/subtle-motion shot → `LOCAL_CUTOUT_RIG`;
2. articulated body/action shot → `GODOT_CUTOUT` prototype;
3. cinematic/effect-heavy shot → `BLENDER_GREASE_PENCIL` or `MANUAL_IMPORT`.

Runway / Wan / Sora packages remain available as optional benchmarks only. They are not allowed to block the non-generative production route.

## Adapter contract

Every renderer should consume the same logical inputs and return the same output metadata:

- project_id / episode_id / scene_id / shot_id;
- input asset versions;
- render route and route version;
- deterministic seed when applicable;
- duration / fps / resolution;
- output asset reference;
- elapsed render time;
- external cost (zero for local routes unless separately recorded);
- review status and QC result.

No renderer is allowed to publish content directly.

## External technical references

- Blender Grease Pencil manual: https://docs.blender.org/manual/en/latest/grease_pencil/introduction.html
- Blender Grease Pencil animation: https://docs.blender.org/manual/en/latest/grease_pencil/animation/introduction.html
- Godot cutout animation: https://docs.godotengine.org/en/stable/tutorials/animation/cutout_animation.html
- Godot Skeleton2D/Bone2D: https://docs.godotengine.org/en/stable/classes/class_skeleton2d.html
- Live2D Cubism SDK motion: https://docs.live2d.com/en/cubism-sdk-manual/motion/
- Live2D Cubism original workflow: https://docs.live2d.com/en/cubism-sdk-manual/original-workflow/
- Spine runtimes: https://us.esotericsoftware.com/spine-runtimes
- Spine IK constraints: https://us.esotericsoftware.com/spine-ik-constraints
