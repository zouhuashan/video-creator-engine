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

### Child LookDev v3

V3 is the direct response to the user-reviewed v2 still. It keeps the successful color/lighting foundation but attacks the remaining toy/mascot read.

Run:

```bash
./render-child-lookdev-v3.command
```

Outputs:

```text
renders/lookdev/child-lookdev-v3.png
renders/lookdev/child-lookdev-v3.blend
```

V3 reduces eye/head scale, strengthens the child-face taper, removes raised blush discs, replaces vertical capsule bangs with flat ribbon hair locks, and replaces tube-like sleeves with drooping cloth masses. Technical render success does not close P28-02; human review remains required.

### Child LookDev v4

V4 changes the modeling strategy rather than incrementally adjusting v3 primitives.

Run:

```bash
./render-child-lookdev-v4.command
```

Outputs:

```text
renders/lookdev/child-lookdev-v4.png
renders/lookdev/child-lookdev-v4.blend
```

The main change is organic geometry generation: tapered Bezier hair strands replace block/card bangs, while torso, skirt and bell sleeves are built from continuous lofted elliptical sections with subdivision and smooth shading. The child face keeps a smaller integrated eye system and stronger chin taper. If this still reads as a procedural toy after human review, the next iteration will move to a real editable base-mesh/sculpt workflow rather than continuing to stack procedural primitives.

#### V4 automatic character framing

V4 no longer assumes a fixed character height. After organic Mesh/Curve geometry is built, the script evaluates the actual Blender dependency graph, collects the character's world-space bounding-box corners, centers the camera target on those bounds, and moves the portrait camera backward until every corner fits inside an 8% normalized safe frame.

This replaces the previous three-center-point gate and prevents longer lofted skirts, sleeves or hair curves from silently falling outside the frame.

### Child LookDev v5 — MPFB real basemesh

V4 confirmed that procedural primitive/loft modeling still reads as a toy. P28-02 therefore stops that strategy and switches to a real continuous human base mesh through MPFB.

First-time setup:

```bash
./install-mpfb.command
```

Environment check:

```bash
./check-mpfb.command
```

Render v5:

```bash
./render-child-lookdev-v5.command
```

Outputs:

```text
renders/lookdev/child-lookdev-v5.png
renders/lookdev/child-lookdev-v5.blend
```

V5 deliberately validates the underlying continuous child basemesh before costume/hair polish. It uses MPFB child phenotype settings and preserves real face, shoulder, arm and hand topology. The image is a base-mesh quality gate, not a final costume approval.

#### V5 MPFB service API

V5 automation uses MPFB's scripting services instead of UI/Scene properties. Blender extension package prefixes are runtime-specific, so the script follows MPFB's official dynamic-import pattern and resolves `HumanService` and `TargetService` from loaded extension modules. Character creation then calls `HumanService.create_human(macro_detail_dict=...)` with numeric macro values such as female=0 and child age=0.

#### V5 operator-only MPFB automation

Blender 5.2 can register MPFB operators even when the extension's internal Python package path is not importable in background mode. V5 therefore treats `bpy.ops.mpfb.create_human()` as the only supported MPFB boundary. The generated continuous human mesh is then child-stylized directly through vertex proportion edits; no MPFB internal service module is required.

#### V5 extension repository discovery

Blender's `bpy.ops` proxy can exist even when the real operator class is not registered. V5 therefore discovers MPFB from Blender's own extension repository collection. For a repository that physically contains `mpfb/blender_manifest.toml`, the runtime module name is built as `bl_ext.<repo.module>.mpfb` and explicitly enabled with `bpy.ops.preferences.addon_enable`.

The environment check then performs a real temporary `mpfb.create_human()` call and verifies that a substantial Mesh was created before reporting PASS. The temporary human is deleted immediately afterwards.

#### V5 strict MPFB installation

A missing `mpfb/blender_manifest.toml` in all enabled Blender extension repositories means MPFB is not actually installed. The installer now performs repository sync, verifies that the official package list contains `mpfb`, installs/enables the package, and finally runs the real human-creation probe. A failed install is no longer treated as potentially acceptable.

The first-time command remains:

```bash
./install-mpfb.command
```

### Child LookDev v6 — native MPFB child phenotype

V5 validated the continuous MPFB basemesh route but still rendered an adult female silhouette. V6 therefore configures MPFB's own New Human scene properties before calling `mpfb.create_human`.

The MPFB source defines New Human settings with prefix `NH_`, and BlenderConfigSet adds the global `MPFB_` prefix. V6 therefore sets properties such as `MPFB_NH_phenotype_age="child"`, `MPFB_NH_phenotype_gender="female"`, `MPFB_NH_phenotype_race="asian"`, and `MPFB_NH_add_breast=False` before creation.

Run:

```bash
./render-child-lookdev-v6.command
```

Outputs:

```text
renders/lookdev/child-lookdev-v6.png
renders/lookdev/child-lookdev-v6.blend
```

The native MPFB child phenotype is the primary anatomy source. Only a small post-style push is applied afterwards for the target animation direction. Human visual review is still required.
