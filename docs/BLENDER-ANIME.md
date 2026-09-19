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

## Uploaded reference style lock

The user-uploaded reference has now been inspected directly. The target is not generic toon 3D. It combines a semi-realistic adult male with a deliberately more chibi/juvenile girl, warm sunset rim light, shallow depth of field, historical-camp staging and dialogue-first acting.

The machine-readable reference is:

```text
config/style-ref-guofeng-dialogue-001.json
```

The first demo is now:

```text
DEMO-BLENDER-DIALOGUE-001
```

Run the proxy blockout after Blender installation:

```bash
./render-reference-demo.command
```

Outputs:

```text
cache/reference-dialogue-blockout.mp4
cache/reference-dialogue-blockout.blend
```

The blockout is intentionally simple geometry. It validates only composition, relative body proportions, adult/child style contrast, eye-line relationship, sunset key/fill, depth of field, camera push and six-second dialogue pacing. It must not be judged as final character quality.

Once the blockout is accepted, the next asset work is two real LookDev characters, not more proxy animation.

### Blender 5.2 image-sequence output

The reference blockout deliberately does not use Blender's internal FFmpeg output API. Blender 5.2 separates media type from image file format, so the project uses the more stable production pattern:

```text
Blender 5.2
→ PNG frame sequence
→ validate 144/144 frames
→ project FFmpeg
→ H.264 yuv420p MP4
```

Temporary frames are written to:

```text
cache/reference-dialogue-blockout-frames/
```

This is also the preferred basis for longer final renders because a failed or interrupted encode does not invalidate already-rendered frames.

### Blockout framing gate

The reference blockout now validates composition before rendering the full 144-frame sequence. Adult head/body and child head/body are projected through the active camera and must stay inside an 8%–92% normalized safe frame with positive depth. The adult head must also remain to the left of the child head.

The camera uses a Track To constraint aimed at a dialogue-center Empty, so the push-in changes distance without losing the pair.

A valid run must emit:

```text
VIDEO_CREATOR_REFERENCE_FRAMING_PASS
VIDEO_CREATOR_REFERENCE_BLOCKOUT_FRAMES_PASS
```

Without the framing marker, `render-reference-demo.command` fails before encoding the MP4.

## P28-02 Child LookDev v1

P28-02 now has an executable local Blender LookDev pass rather than a prose-only specification.

Run:

```bash
./render-child-lookdev.command
```

Outputs:

```text
renders/lookdev/child-lookdev-v1.png
renders/lookdev/child-lookdev-v1.blend
```

The first pass locks child-specific proportions, large eyes/catchlights, soft round cheeks, minimal nose/mouth, double-bun hair silhouette, pale cyan/white layered costume and the reference warm-rim/cool-fill lighting language. A camera-space gate prevents an off-frame character from being reported as a valid render.

A successful command means only **technical render PASS**. Human visual review remains PENDING until the still is inspected against the uploaded reference.

### Child LookDev v2

After visual review of v1, P28-02 remains open and moves to v2 rather than advancing to the adult character.

Run:

```bash
./render-child-lookdev-v2.command
```

Outputs:

```text
renders/lookdev/child-lookdev-v2.png
renders/lookdev/child-lookdev-v2.blend
```

V2 upgrades the child from a gray toy-like proxy toward an actual colored LookDev: Principled node materials, tapered soft face, layered eye structure with catchlights and upper lids, softer mouth/brows, grouped bangs and curved side locks, irregular double buns, layered pale-cyan/white hanfu, and controlled warm-rim/cool-fill lighting. Technical render success does not close P28-02; human review remains required.
