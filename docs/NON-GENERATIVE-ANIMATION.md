# Non-Generative Animation Routes

> Project: VideoCreator Engine  
> Status: ACTIVE ARCHITECTURE DECISION  
> Updated: 2026-09-19  
> Principle: use deterministic local tools for reusable production; final publish remains human-confirmed.

## Current route hierarchy

| Route | Role | Current status |
| --- | --- | --- |
| LOCAL_CUTOUT_RIG | Animatic, dialogue blocking, timing preview | ACTIVE |
| BLENDER_ANIME | Final-image target: 3D character + NPR/toon + line art + camera + FX | CANDIDATE / CURRENT NEXT |
| GODOT_CUTOUT | Archived experiment for 2D skeletal/cutout research | EXPERIMENTAL_DEFERRED |
| BLENDER_GREASE_PENCIL | Line-art, hand-drawn accents and FX around Blender Anime | OPTIONAL |
| LIVE2D_CUBISM | Dialogue close-up specialty route | OPTIONAL / LICENSE REVIEW |
| SPINE_SKELETAL | Commercial skeletal specialty route | OPTIONAL / LICENSE REVIEW |
| MANUAL_IMPORT | Human-made or outsourced fallback | ACTIVE |
| REMOTE_AI_VIDEO | Exceptional-shot option only | OPTIONAL_BLOCKED |

## Why the hierarchy changed

The Jing Hua Yuan pilot proved that a single front-facing illustration can be segmented and moved, but that workflow does not contain the real geometry needed for convincing volume, perspective changes, clothing thickness or turns. More cutout complexity does not remove that ceiling.

Therefore LOCAL_CUTOUT_RIG remains useful, but only as an Animatic and timing system. GODOT_CUTOUT is retained for experiments and is no longer the final-image target.

## Animatic route

LOCAL_CUTOUT_RIG remains the cheap deterministic front end:

- storyboard timing;
- dialogue blocking;
- mouth and expression cues;
- rough camera moves;
- subtitle and audio synchronization;
- shot duration decisions;
- episode assembly before expensive final rendering.

Once the director timing is accepted, only selected shots move to final rendering.

## Final-image route: Blender Anime

The production target is a real 3D-to-2D/NPR pipeline:

~~~text
3D character
→ Armature / IK / Shape Keys
→ hair and cloth secondary motion
→ Toon / NPR shading
→ line art / Grease Pencil accents
→ camera + lighting + scene depth
→ guofeng FX + compositing
→ final shot asset
~~~

The first validation target is intentionally small: one 5–8 second Baihua Fairy shot. Do not scale to all nine characters until that shot passes human visual review.

## Blender Grease Pencil role

Grease Pencil is not a replacement for the 3D character body. It is an enhancement layer for:

- clean line art;
- hand-drawn accents;
- hair/sleeve exaggeration;
- impact frames;
- smoke, petals, ink and calligraphic FX;
- selective 2D corrections over a 3D render.

## Godot route

The existing Godot code is preserved for learning and experiments. It is not deleted, because it remains useful for 2D skeletal research and low-cost motion tests. It is not the current production target.

## Remote generative video

Remote AI video remains blocked by default. It can only be used when upload and possible billing are explicitly authorized, and it never bypasses human review.

## Reference matching

A reference URL must be actually inspectable before VideoCreator claims that it can reproduce that exact style. If a short-link video cannot be resolved, upload the video file or representative frames. Exact style decomposition should then record character design, shading, line treatment, camera, motion, FX, compositing and scene depth separately.

## P28 relationship

The existing five local masters remain technically complete but human review stays PENDING. Blender Anime work is a quality-route validation and does not retroactively approve or replace the existing P28 review gate.

## Adapter contract

Every final renderer still consumes the shared shot contract and returns versioned output metadata including project/episode/scene/shot IDs, input asset versions, route/version, duration, fps, resolution, output asset, elapsed render time, external cost, review status and QC result.

No renderer may publish content directly.

## External technical references

- Blender releases: https://www.blender.org/releases/
- Blender 5.2 LTS: https://www.blender.org/releases/5-2/
- Blender EEVEE: https://docs.blender.org/manual/en/5.2/render/eevee/index.html
- Blender rendering manual: https://docs.blender.org/manual/en/5.2/render/index.html
- Godot cutout animation: https://docs.godotengine.org/en/stable/tutorials/animation/cutout_animation.html
