# Open-Source Fusion for Modern Drama

VideoCreator Engine keeps one orchestrator, one project state and one Web workspace. The goal is not to install every popular repository. The goal is to absorb the strongest production idea from each project without creating a second source of truth.

## Rule: one capability, one primary owner

```text
Story / Brief
  -> Writing Room
  -> Character + Scene assets
  -> Director Intent
  -> Technical Shot Contract
  -> Voice-first timing
  -> 2-5 second editorial Shots
  -> Cost Router
  -> Local renderer / optional Wan / premium H3
  -> Editable Timeline
  -> Subtitle + BGM + SFX
  -> QC
  -> Human approval
  -> Final render
```

No external project may silently replace the VideoCreator project model, approval gates or publish boundary.

## What we absorb

### 0xsline/short-drama
Use its short-drama writing discipline as reference rules: hook, episode rhythm, conflict escalation, payoff, self-check and compliance. Keep VideoCreator Writing Room as the owner of scripts.

### Seedance2-Storyboard-Generator
Use stable Character / Scene / Prop identifiers and structured shot descriptions. Generalize those ideas into a provider-neutral production contract, so the same storyboard can drive local renderers, Wan, H3 or a future provider.

Canonical references are:

```text
C:<character-id>
S:<scene-or-location-id>
P:<registered-project-asset-path>
```

### short-drama-production
Use three ideas: Director Intent is separate from Technical Execution; upstream revisions invalidate stale downstream plans; human approval belongs at explicit stage boundaries. Keep VideoCreator's existing repository/runtime as the only state machine.

### Wan2.2
Treat Wan as an optional Video Provider for continuous motion. It is never the default renderer for the whole episode. The Cost Router must first try reuse, static, local motion, screen MG, stock and layered 2.5D.

### GPT-SoVITS
Treat voice cloning as optional for recurring characters. Timing remains owned by the existing Voice Timeline. A provider change must not silently change approved Shot durations.

### VideoCaptioner
Use only when imported external media has unknown speech/subtitles. For VideoCreator-generated dialogue, create SRT/ASS directly from the known TTS timeline and avoid an ASR round-trip.

### moyin-creator
Borrow product ideas: editable project, visible provider state, queue, retry, per-shot regeneration and batch operations. Do not replace the existing VideoCreator Web application.

## Production contract

The contract has three independent layers:

```text
Narrative
  source text / story purpose / beat

Director Intent
  shot size / angle / movement / blocking / action / expression
  continuity_from / must_keep / must_not

Technical Execution
  duration / motion strategy / renderer / assets / tracks / cost
```

This split prevents a provider-specific prompt from becoming the storyboard.

Every Shot has separate Storyboard, Keyframe and Video approval states. A paid video provider is not allowed merely because a Shot exists.

## Integration order

1. Freeze character and scene identities.
2. Build and approve the storyboard/production contract.
3. Lock voice timing.
4. Route each 2-5 second Shot to the cheapest acceptable renderer.
5. Generate only approved keyframes/assets.
6. Escalate only irreducible continuous motion to an optional video provider.
7. Edit, mix, QC and review in the existing timeline.
8. Keep final publishing manual.

The first acceptance target is one 2-3 minute modern drama episode with roughly 30-40 Shots. Do not add another model unless that pilot exposes a concrete capability gap.
