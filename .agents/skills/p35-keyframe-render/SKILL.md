---
name: p35-keyframe-render
description: Generate exactly one VideoCreator P35 final keyframe from canonical character/scene references plus the current Blender control frame. Use only when a P35 Codex batch prompt asks for one frame and an exact PNG output path.
---

# P35 keyframe render

Use this skill only for one-frame P35 rendering jobs.

1. Respect the reference roles exactly:
   - Reference 1: canonical character identity, face, hair, costume, proportions.
   - Reference 2: canonical scene architecture, materials, palette, lanterns and lighting language.
   - Reference 3: current Blender control frame; it is the sole authority for camera, framing, screen position, pose, gaze, occlusion and spatial layout.
   - Reference 4, when present: previous accepted final frame for temporal continuity only.
2. Invoke the built-in `$imagegen` capability. Do not answer with a textual description instead of creating the image.
3. Do not redesign camera, actor position, pose, architecture or props.
4. Do not create a collage, text, UI, watermark, contact sheet or alternate versions.
5. Generate exactly one final image.
6. Save/copy the selected final PNG to the exact output path supplied in the task.
7. Verify that exact path exists before finishing.
8. Do not edit source code, task files, manifests, references or unrelated files.
9. If image generation fails, report failure. Never create a placeholder image.
