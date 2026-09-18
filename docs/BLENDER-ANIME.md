# Blender Anime Production Route

Status: CURRENT FINAL-IMAGE TARGET / FOUNDATION IN PROGRESS.

## Goal

Create a reusable local guofeng-anime pipeline that has real character volume and camera perspective while rendering with an intentionally 2D/anime visual language.

~~~text
3D Character
+ Armature / IK / Shape Keys
+ Hair / Cloth Secondary Motion
+ Toon / NPR
+ Line Art / Grease Pencil
+ Camera / Lighting / Scene
+ Guofeng FX / Compositing
= Final Shot
~~~

LOCAL_CUTOUT_RIG remains the Animatic route. GODOT_CUTOUT is retained as an experiment, not the final-image target.

## Production baseline

VideoCreator targets Blender 5.2 LTS on Apple Silicon. The automation deliberately stays inside the 5.2.x API window instead of silently following future major/minor releases.

Install:

~~~bash
./install-blender.command
~~~

Recheck:

~~~bash
./check-blender.command
~~~

Both commands force arm64 execution so they also work when the parent Terminal is running under Rosetta.

## Smoke contract

The first environment smoke does not claim anime quality. It only proves:

- Blender 5.2 LTS is available;
- arm64 execution works;
- background automation works;
- EEVEE can render;
- an Armature can be created;
- Camera and lights can be controlled;
- a PNG render can be written locally.

Smoke output:

~~~text
cache/blender-anime-smoke.png
~~~

## First quality milestone

Only one representative shot is built before scaling:

~~~text
Character: 百花仙子
Duration: target 6 seconds
Resolution: 1080×1920
FPS: 24

neutral breathing
→ elegant hand raise
→ head/eyes follow the hand
→ brief hold
→ hair and sleeve secondary motion
→ foreground petals
→ subtle real-camera push-in
~~~

Template:

~~~text
templates/blender-anime-demo.json
~~~

## Human visual gate

The demo is not accepted merely because Blender renders successfully. Human review must confirm:

- convincing body volume;
- real perspective instead of a flat card;
- readable costume layers and thickness;
- connected shoulder/elbow/wrist/head motion;
- intentionally anime/toon NPR values rather than generic 3D;
- clean line treatment;
- hair and sleeve secondary motion;
- foreground/midground/background separation;
- guofeng atmosphere and FX;
- no automatic publication.

## Reference-video rule

The TikTok short link supplied on 2026-09-19 could not be resolved in the current ChatGPT web environment. It has not been visually inspected. Upload the video itself or 2–3 representative frames before recording any claim that the Blender demo matches that exact style.

## What comes after environment PASS

1. Inspect the uploaded visual reference.
2. Freeze a style bible for face proportions, costume, palette, line art, light/shadow bands, camera and FX.
3. Build only Baihua Fairy model v0.
4. Rig and animate the 6-second shot.
5. Build NPR material and line-art treatment.
6. Add hair/sleeve secondary motion, camera and petals.
7. Render a review MP4.
8. Decide whether the route is visually good enough before adding a second character.
