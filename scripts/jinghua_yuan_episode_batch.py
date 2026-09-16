#!/usr/bin/env python3
"""Build the first five local 《镜花缘》 pilot episodes.

The pilot deliberately uses original narration inspired by the novel's travel
motif.  It does not copy source text, call a remote video provider, or publish
anything.  Each episode is rendered from local keyframes, local macOS speech,
and burned-in SRT captions so the whole chain can be reviewed before adding
image-to-video motion providers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.tts import MacOSSayTTS  # noqa: E402
from adapters.video.video_use import _media_tool, video_use_environment  # noqa: E402
from adapters.video_generation import (  # noqa: E402
    LocalKenBurnsVideo,
    VideoGenerationError,
    VideoGenerationRequest,
    normalize_image_paths,
)
from scripts.local_storyboard_pipeline import build_mux_command  # noqa: E402


class EpisodeBatchError(RuntimeError):
    """Raised when a local episode cannot be built safely."""


SHOT_DURATION = 3.1
TRANSITION = 0.4
VOICE = "Tingting"

# These are original pilot beats.  They use the broad premise and names only
# as a temporary creative test; no sentence is copied from a source edition.
EPISODES: tuple[dict[str, Any], ...] = (
    {
        "episode_id": "episode-01",
        "title": "残图",
        "logline": "唐小山在旧书页里发现一张缺角海图，决定追查它指向的航线。",
        "scenes": (
            ("chart-discovery", "父亲留下的海图只剩半页，缺口像一扇没有打开的门。", "shot-01-chart-discovery.png", (35, 72, 112)),
            ("ink-mark", "她在墨痕背面找到一个陌生印记，和海风的方向完全相反。", "shot-02-compass-clue.png", (74, 54, 98)),
            ("first-decision", "天亮前，她把残图收进衣襟，决定独自出海寻找另一半。", "shot-03-departure.png", (115, 62, 48)),
        ),
    },
    {
        "episode_id": "episode-02",
        "title": "云隙罗盘",
        "logline": "罗盘在夜航中偏离北方，指向云层深处一条不存在的路。",
        "scenes": (
            ("night-watch", "夜色压低了海面，罗盘的指针却忽然离开北方。", "shot-02-compass-clue.png", (28, 53, 102)),
            ("cloud-opening", "云隙里露出一线青光，残图上的墨线随之慢慢发亮。", "shot-01-chart-discovery.png", (42, 92, 116)),
            ("follow-signal", "唐小山没有调回船头，她相信这道光就是失页留下的讯号。", "shot-03-departure.png", (78, 63, 103)),
        ),
    },
    {
        "episode_id": "episode-03",
        "title": "雾海灯塔",
        "logline": "浓雾中出现一座漂浮灯塔，灯光用三次闪烁回应她的残图。",
        "scenes": (
            ("fog-sea", "清晨的雾把海面折成两层，远处有灯光在雾里呼吸。", "shot-03-departure.png", (83, 83, 96)),
            ("lighthouse", "灯塔连续闪了三次，正好对应残图边缘的三个缺口。", "shot-02-compass-clue.png", (112, 73, 56)),
            ("narrow-channel", "她收起风帆驶入窄水道，身后的灯塔转眼又被白雾吞没。", "shot-01-chart-discovery.png", (55, 78, 92)),
        ),
    },
    {
        "episode_id": "episode-04",
        "title": "无字港",
        "logline": "船抵达一座没有招牌的港口，只有潮声能让海图显出新字。",
        "scenes": (
            ("silent-harbor", "港口没有旗帜，也没有人迎接，石阶上只留着一串潮湿脚印。", "shot-01-chart-discovery.png", (89, 68, 53)),
            ("tide-writing", "潮水拍过残图，空白处浮出一行短短的字：向风的背面走。", "shot-02-compass-clue.png", (43, 99, 91)),
            ("fragment", "唐小山在旧灯台下找到失页一角，纸边还带着未干的海盐。", "shot-03-departure.png", (98, 61, 70)),
        ),
    },
    {
        "episode_id": "episode-05",
        "title": "向风的背面",
        "logline": "两片海图终于拼合，新的航线把唐小山带向故事真正的起点。",
        "scenes": (
            ("join-the-map", "两片纸页在晨光里合拢，缺失的海岸线终于完整出现。", "shot-01-chart-discovery.png", (54, 89, 89)),
            ("open-water", "罗盘重新指向远方，海面像一条被展开的青色绸带。", "shot-02-compass-clue.png", (45, 76, 113)),
            ("new-horizon", "她回头看了一眼渐远的港口，然后驶向地图之外的第一座岛。", "shot-03-departure.png", (126, 71, 43)),
        ),
    },
)


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_scene_variant(source: Path, output: Path, episode_number: int, scene_number: int, caption: str, tint: tuple[int, int, int]) -> None:
    """Create a deterministic, locally tinted keyframe while retaining the character design."""
    image = Image.open(source).convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
    image = ImageEnhance.Color(image).enhance(0.78)
    image = ImageEnhance.Contrast(image).enhance(1.05)
    tint_layer = Image.new("RGB", image.size, tint)
    image = Image.blend(image, tint_layer, 0.14).filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=3))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1080, 150), fill=(9, 13, 24, 145))
    draw.text((54, 48), f"镜花缘 · EP{episode_number:02d} · {scene_number:02d}", font=_font(34), fill=(245, 226, 183, 235))
    draw.rectangle((42, 1690, 1038, 1868), fill=(5, 9, 18, 148))
    draw.text((70, 1740), caption, font=_font(32), fill=(255, 255, 255, 245), spacing=8)
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


def _timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds - hours * 3600 - minutes * 60
    whole = int(remaining)
    millis = int(round((remaining - whole) * 1000))
    if millis == 1000:
        whole += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{whole:02d},{millis:03d}"


def write_subtitles(path: Path, lines: list[str], shot_duration: float = SHOT_DURATION, transition: float = TRANSITION) -> None:
    total = len(lines) * shot_duration - (len(lines) - 1) * transition
    chunks: list[str] = []
    for index, line in enumerate(lines):
        start = index * (shot_duration - transition)
        end = total if index == len(lines) - 1 else (index + 1) * (shot_duration - transition)
        chunks.append(f"{index + 1}\n{_timestamp(start)} --> {_timestamp(end)}\n{line}\n")
    path.write_text("\n".join(chunks), encoding="utf-8")


def _convert_audio(aiff: Path, wav: Path) -> None:
    ffmpeg = _media_tool("ffmpeg") or "ffmpeg"
    completed = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(aiff), "-ar", "48000", "-ac", "1", str(wav)], check=False, capture_output=True, text=True, env=video_use_environment())
    if completed.returncode != 0 or not wav.is_file() or wav.stat().st_size == 0:
        raise EpisodeBatchError(completed.stderr[-1200:] or "local voice conversion failed")


def build_episode(project_dir: Path, episode: dict[str, Any], *, shot_duration: float = SHOT_DURATION, transition: float = TRANSITION) -> dict[str, Any]:
    episode_dir = project_dir / "episodes" / episode["episode_id"]
    if episode_dir.exists():
        raise EpisodeBatchError(f"refusing to overwrite existing episode directory: {episode_dir}")
    source_dir = project_dir / "assets" / "scenes"
    for _, _, source_name, _ in episode["scenes"]:
        if not (source_dir / source_name).is_file():
            raise EpisodeBatchError(f"missing scene source: {source_dir / source_name}")
    episode_dir.mkdir(parents=True)
    scenes_dir = episode_dir / "assets" / "scenes"
    image_paths: list[Path] = []
    for index, (_, caption, source_name, tint) in enumerate(episode["scenes"], start=1):
        target = scenes_dir / f"shot-{index:02d}.png"
        build_scene_variant(source_dir / source_name, target, int(episode["episode_id"][-2:]), index, caption, tint)
        image_paths.append(target)
    lines = [scene[1] for scene in episode["scenes"]]
    subtitles = episode_dir / "subtitles.srt"
    write_subtitles(subtitles, lines, shot_duration, transition)
    script = episode_dir / "script.md"
    script.write_text(f"# {episode['episode_id']}｜{episode['title']}\n\n**梗概**：{episode['logline']}\n\n" + "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1)) + "\n\n> 本集为原创试制旁白，仅借用《镜花缘》的世界意象，不复制原文；发布前仍需完成人工版权审核。\n", encoding="utf-8")
    storyboard = episode_dir / "storyboard.md"
    storyboard.write_text("# 本地动态分镜\n\n" + "\n".join(f"- 镜头 {i}: {scene[0]}｜{scene[1]}｜本地关键帧 `assets/scenes/shot-{i:02d}.png`" for i, scene in enumerate(episode["scenes"], 1)) + "\n", encoding="utf-8")
    voice_dir = episode_dir / "voice"
    voice_dir.mkdir()
    raw = voice_dir / "narration.aiff"
    wav = voice_dir / "narration.wav"
    raw.write_bytes(MacOSSayTTS().synthesize("。".join(lines), VOICE, speed=0.96).audio)
    _convert_audio(raw, wav)
    silent = episode_dir / ".silent.mp4"
    output = episode_dir / "final.mp4"
    request = VideoGenerationRequest(image_paths=normalize_image_paths(image_paths), output_path=silent, shot_duration_seconds=shot_duration, transition_seconds=transition, width=1080, height=1920, prompt_text="国风动漫连续分镜，保持唐小山角色与服饰一致")
    try:
        LocalKenBurnsVideo().generate(request)
        completed = subprocess.run(build_mux_command(silent, wav, subtitles, output), check=False, capture_output=True, text=True, env=video_use_environment())
        if completed.returncode != 0:
            raise EpisodeBatchError(completed.stderr[-1200:] or "episode narration merge failed")
    except VideoGenerationError as error:
        raise EpisodeBatchError(str(error)) from error
    finally:
        silent.unlink(missing_ok=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise EpisodeBatchError(f"episode output is empty: {output}")
    metadata = {"schema_version": 1, "episode_id": episode["episode_id"], "title": episode["title"], "logline": episode["logline"], "status": "LOCAL_REVIEW", "provider": "local_ken_burns", "character_asset": "../assets/characters/tang-xiaoshan-portrait.png", "source_note": "原创试制旁白；临时使用《镜花缘》意象，未复制原文。", "scenes": [{"id": scene[0], "caption": scene[1]} for scene in episode["scenes"]], "output": "final.mp4", "voice": "voice/narration.wav", "subtitles": "subtitles.srt"}
    (episode_dir / "episode.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"episode_id": episode["episode_id"], "title": episode["title"], "output": str(output), "duration_seconds": len(image_paths) * shot_duration - (len(image_paths) - 1) * transition, "provider": "local_ken_burns"}


def build_batch(project_dir: Path, *, episode_count: int = 5) -> list[dict[str, Any]]:
    project_dir = Path(project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        raise EpisodeBatchError(f"project does not exist: {project_dir}")
    if episode_count < 1 or episode_count > len(EPISODES):
        raise EpisodeBatchError(f"episode_count must be between 1 and {len(EPISODES)}")
    results = []
    for episode in EPISODES[:episode_count]:
        results.append(build_episode(project_dir, episode))
    index = project_dir / "episodes" / "README.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("# 《镜花缘》前五集本地试播\n\n" + "\n".join(f"- [{item['episode_id']}｜{item['title']}]({item['episode_id']}/final.mp4) — {item['provider']}，配音与字幕已合成" for item in results) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--episode-count", type=int, default=5)
    args = parser.parse_args()
    try:
        print(json.dumps(build_batch(args.project_dir, episode_count=args.episode_count), ensure_ascii=False, indent=2))
    except (EpisodeBatchError, OSError, ValueError) as error:
        print(f"jinghua_yuan_episode_batch: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
