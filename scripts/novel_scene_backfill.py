#!/usr/bin/env python3
"""Build privacy-preserving episode scene seeds from an uploaded novel TXT.

The full source text is never persisted by this module.  It keeps only a small
deterministic selection of source sentences needed to bootstrap DRAFT episode
scenes, so older projects can be repaired by re-selecting the same TXT once and
new projects can create routable shots immediately after import.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_episode_script import load_script_package, validate_script_package, write_script_package
from scripts.novel_source_ingest import split_chapters
from scripts.novel_story_bible import load_bible


OUTPUT = Path("writing-room/scene-seeds.json")
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])\s*|\n+")
_QUOTE = re.compile(r"[“「『\"]([^”」』\"]{1,500})[”」』\"]")
_ACTION_MARKERS = ("去", "来", "走", "看", "说", "问", "答", "取", "放", "发现", "决定", "离开", "进入", "抵达", "寻找", "遇见", "推", "抬", "站", "跑", "转", "起身", "开门", "挥", "追", "打", "跃")
_DIALOGUE_MARKERS = ("说道", "说", "问道", "问", "答道", "答", "喊道", "喊", "叫道", "叫", "笑道", "叹道", "低声道", "轻声道", "沉声道", "冷声道")


class NovelSceneBackfillError(RuntimeError):
    pass


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def _source_provenance(chapter_ids: list[str]) -> dict[str, Any]:
    return {
        "kind": "SOURCE",
        "source_refs": list(dict.fromkeys(chapter_ids)),
        "story_refs": [],
        "note": "本地 Scene Seed 从用户本次提供的原 TXT 确定性抽取；未持久化完整原文。",
    }


def _safe_excerpt(text: str, limit: int = 220) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(1, limit - 1)].rstrip() + "…"


def _matching_import_chapters(project: Path, source_sha256: str) -> dict[int, str]:
    root = project / "sources" / "imports"
    if not root.is_dir():
        return {}
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("source_sha256") or "") != source_sha256:
            continue
        result: dict[int, str] = {}
        for item in payload.get("chapters", []):
            try:
                sequence = int(item.get("sequence") or 0)
            except (TypeError, ValueError):
                continue
            chapter_id = str(item.get("chapter_id") or "").strip()
            if sequence > 0 and chapter_id:
                result[sequence] = chapter_id
        if result:
            return result
    return {}


def _term_index(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    for item in items:
        entity_id = str(item.get("id") or "")
        for term in [str(item.get("name") or ""), *(str(value) for value in item.get("aliases", []))]:
            term = term.strip()
            if entity_id and term:
                terms.append((term, entity_id))
    return sorted(set(terms), key=lambda pair: (-len(pair[0]), pair[0], pair[1]))


def _matched_ids(text: str, index: list[tuple[str, str]]) -> list[str]:
    return list(dict.fromkeys(entity_id for term, entity_id in index if term in text))


def _speaker_id(sentence: str, character_terms: list[tuple[str, str]]) -> str | None:
    quote = _QUOTE.search(sentence)
    if not quote:
        return None
    prefix = sentence[: quote.start()]
    best: tuple[int, str] | None = None
    for term, entity_id in character_terms:
        position = prefix.rfind(term)
        if position < 0:
            continue
        tail = prefix[position + len(term):]
        if not any(marker in tail for marker in _DIALOGUE_MARKERS):
            continue
        if best is None or position > best[0]:
            best = (position, entity_id)
    return best[1] if best else None


def _sentence_score(text: str, character_terms: list[tuple[str, str]]) -> float:
    score = 0.0
    if _QUOTE.search(text):
        score += 3.0
    score += min(4.0, sum(1 for marker in _ACTION_MARKERS if marker in text) * 0.8)
    score += min(3.0, len(_matched_ids(text, character_terms)) * 0.8)
    if len(text) >= 12:
        score += 0.5
    return score


def _select_episode_sentences(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(records) <= limit:
        return records
    selected: set[int] = {0, len(records) - 1}
    ranked = sorted(
        range(len(records)),
        key=lambda index: (-float(records[index]["score"]), index),
    )
    for index in ranked:
        selected.add(index)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        step = (len(records) - 1) / max(1, limit - 1)
        for slot in range(limit):
            selected.add(round(slot * step))
            if len(selected) >= limit:
                break
    return [records[index] for index in sorted(selected)[:limit]]


def _duration(kind: str, text: str, unit_budget: float) -> float:
    if kind == "ACTION":
        estimate = max(1.5, min(5.0, len(text) / 8.0))
    else:
        estimate = max(1.5, min(8.0, len(text) / 5.0))
    return round(min(estimate, max(0.8, unit_budget)), 2)


def build_scene_seed(project_dir: Path, source_text: str, *, source_sha256: str | None = None) -> dict[str, Any]:
    project = Path(project_dir).expanduser().resolve()
    source_text = str(source_text or "")
    if not source_text.strip():
        raise NovelSceneBackfillError("source text is required for scene backfill")
    source_bytes = source_text.encode("utf-8")
    digest = source_sha256 or hashlib.sha256(source_bytes).hexdigest()
    manifest = load_project(project / MANIFEST_NAME)
    ip_code = str(manifest["ip"]["id"]).removeprefix("IP-")
    chapters = list(split_chapters(source_text.replace("\r\n", "\n").replace("\r", "\n").strip(), ip_code))
    persisted_ids = _matching_import_chapters(project, digest)
    bible = load_bible(project)
    character_terms = _term_index(list(bible.get("characters") or []))
    location_terms = _term_index(list(bible.get("locations") or []))

    records: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(chapters, start=1):
        chapter_id = persisted_ids.get(chapter_index, chapter.chapter_id)
        sentences = [item.strip() for item in _SENTENCE_SPLIT.split(chapter.text) if item and item.strip()]
        for sentence_index, sentence in enumerate(sentences, start=1):
            excerpt = _safe_excerpt(sentence)
            records.append({
                "chapter_id": chapter_id,
                "chapter_title": chapter.title,
                "chapter_sequence": chapter_index,
                "sentence_index": sentence_index,
                "text": excerpt,
                "score": _sentence_score(excerpt, character_terms),
            })

    if not records:
        raise NovelSceneBackfillError("source text produced no scene-ready sentences")

    episodes = sorted(manifest["episodes"], key=lambda item: (item["season_id"], item["episode_number"]))
    if not episodes:
        raise NovelSceneBackfillError("project has no episodes")

    episode_payloads: list[dict[str, Any]] = []
    total = len(records)
    for episode_index, episode in enumerate(episodes):
        start = (episode_index * total) // len(episodes)
        end = ((episode_index + 1) * total) // len(episodes)
        bucket = records[start:end]
        if not bucket:
            nearest = min(total - 1, start)
            bucket = [records[nearest]]
        target = float(episode.get("target_duration_seconds") or 60.0)
        max_units = max(2, min(12, int(max(2.0, target * 0.55) // 3)))
        selected = _select_episode_sentences(bucket, max_units)
        scene_size = 4
        scenes: list[dict[str, Any]] = []
        for scene_index, offset in enumerate(range(0, len(selected), scene_size), start=1):
            chunk = selected[offset:offset + scene_size]
            scene_id = f"{episode['id']}-SC{scene_index:03d}"
            chapter_ids = list(dict.fromkeys(str(item["chapter_id"]) for item in chunk))
            chapter_titles = list(dict.fromkeys(str(item["chapter_title"]) for item in chunk))
            scene_text = " ".join(str(item["text"]) for item in chunk)
            character_ids = _matched_ids(scene_text, character_terms)
            location_ids = _matched_ids(scene_text, location_terms)
            unit_budget = max(0.8, min(8.0, (target * 0.80) / max(1, len(selected))))
            units: list[dict[str, Any]] = []
            for unit_index, item in enumerate(chunk, start=1):
                raw = str(item["text"])
                speaker = _speaker_id(raw, character_terms)
                quote = _QUOTE.search(raw)
                if speaker and quote:
                    kind = "DIALOGUE"
                    text = _safe_excerpt(quote.group(1))
                    emotion = {"label": "中性", "intensity": 0.45, "performance_note": "按原文语气自然表达"}
                elif any(marker in raw for marker in _ACTION_MARKERS):
                    kind = "ACTION"
                    text = raw
                    speaker = None
                    emotion = None
                else:
                    kind = "NARRATION"
                    text = raw
                    speaker = None
                    emotion = {"label": "叙事", "intensity": 0.35, "performance_note": "平稳、清晰，不额外演绎"}
                units.append({
                    "id": f"UNIT-{scene_id}-{unit_index:03d}",
                    "sequence": unit_index,
                    "kind": kind,
                    "text": text,
                    "speaker_character_id": speaker,
                    "emotion": emotion,
                    "sound": None,
                    "estimated_duration_seconds": _duration(kind, text, unit_budget),
                    "beat_ref": None,
                    "provenance": _source_provenance([str(item["chapter_id"])]),
                })
                if speaker and speaker not in character_ids:
                    character_ids.append(speaker)
            scenes.append({
                "id": scene_id,
                "sequence": scene_index,
                "title": " / ".join(chapter_titles[:2]) or f"场景 {scene_index}",
                "purpose": "从用户提供原文中提取可进入镜头规划的动作、对白或叙事种子。",
                "location_id": location_ids[0] if location_ids else None,
                "time_of_day": "未指定",
                "character_ids": character_ids,
                "units": units,
                "provenance": _source_provenance(chapter_ids),
                "human_review": _review(),
            })
        episode_payloads.append({
            "episode_id": episode["id"],
            "target_duration_seconds": target,
            "source_sentence_count": len(bucket),
            "selected_sentence_count": len(selected),
            "scenes": scenes,
        })

    return {
        "schema_version": 1,
        "project_id": manifest["project_id"],
        "source_sha256": digest,
        "full_text_stored": False,
        "derivation": "LOCAL_DETERMINISTIC_SOURCE_SCENE_SEED",
        "created_at": utc_timestamp(),
        "episodes": episode_payloads,
    }


def save_scene_seed(project_dir: Path, seed: dict[str, Any]) -> Path:
    project = Path(project_dir).expanduser().resolve()
    path = project / OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def load_scene_seed(project_dir: Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve() / OUTPUT
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelSceneBackfillError(f"cannot read scene seed: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise NovelSceneBackfillError("scene seed is invalid")
    return payload


def apply_scene_seed(project_dir: Path, seed: dict[str, Any] | None = None) -> dict[str, Any]:
    project = Path(project_dir).expanduser().resolve()
    seed = seed or load_scene_seed(project)
    package = load_script_package(project)
    scenes_by_episode = {
        str(item["episode_id"]): list(item.get("scenes") or [])
        for item in seed.get("episodes", [])
        if isinstance(item, dict)
    }
    changed = 0
    scene_count = 0
    unit_count = 0
    for script in package["episode_scripts"]:
        scenes = scenes_by_episode.get(str(script["episode_id"]), [])
        if not scenes:
            continue
        script["scenes"] = scenes
        script["status"] = "DRAFT"
        script["human_review"] = _review()
        changed += 1
        scene_count += len(scenes)
        unit_count += sum(len(scene.get("units") or []) for scene in scenes)
    if changed <= 0:
        raise NovelSceneBackfillError("scene seed does not match project episodes")
    package["revision"] = int(package.get("revision") or 1) + 1
    package["updated_at"] = utc_timestamp()
    package = validate_script_package(project, package)
    write_script_package(project, package, overwrite=True)
    return {
        "status": "READY",
        "episode_count": changed,
        "scene_count": scene_count,
        "unit_count": unit_count,
        "script_revision": package["revision"],
        "seed_path": OUTPUT.as_posix(),
    }


def backfill_episode_scenes(
    project_dir: Path,
    source_text: str,
    *,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    seed = build_scene_seed(project_dir, source_text, source_sha256=source_sha256)
    save_scene_seed(project_dir, seed)
    result = apply_scene_seed(project_dir, seed)
    return {**result, "source_sha256": seed["source_sha256"], "full_text_stored": False}


__all__ = [
    "NovelSceneBackfillError",
    "OUTPUT",
    "apply_scene_seed",
    "backfill_episode_scenes",
    "build_scene_seed",
    "load_scene_seed",
    "save_scene_seed",
]
