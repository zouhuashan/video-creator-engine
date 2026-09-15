"""Validate a WeChat Channels script draft and write project artifacts."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .project_state import ROOT, StateError, load_run_state, transition_project
except ImportError:
    from project_state import ROOT, StateError, load_run_state, transition_project


SCHEMA_VERSION = 1
SECTION_DEFINITIONS = (
    ("hook", "Hook"),
    ("problem", "Problem"),
    ("evidence", "Evidence"),
    ("comparison", "Comparison"),
    ("conclusion", "Conclusion"),
    ("cta", "CTA"),
)
OUTPUT_NAMES = ("script.json", "script.md")
SOURCE_TYPES = {
    "official",
    "primary_document",
    "authoritative_media",
    "high_quality_community",
    "search_summary",
}
STYLE_CONFIG_PATH = ROOT / "config" / "script-style.json"
DURATION_CONFIG_PATH = ROOT / "config" / "script-duration.json"
HOOK_TYPES = {"conclusion", "counterintuitive", "conflict"}
HOOK_TYPE_LABELS = {
    "conclusion": "先给结论",
    "counterintuitive": "反常识",
    "conflict": "明确冲突",
}
SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])|\n+")


class ScriptInputError(ValueError):
    """Raised when a script draft or its evidence references are invalid."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ScriptInputError(f"{label} not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ScriptInputError(f"invalid {label}: {error}") from error


def _load_style_config() -> dict[str, Any]:
    config = _read_json(STYLE_CONFIG_PATH, "script style config")
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config.get("schema_version") != 1:
        raise ScriptInputError("unsupported script style config schema")
    max_sentence_characters = config.get("max_sentence_characters")
    max_commas = config.get("max_commas_per_sentence")
    if type(max_sentence_characters) is not int or max_sentence_characters < 1:
        raise ScriptInputError("script style config max_sentence_characters must be a positive integer")
    if type(max_commas) is not int or max_commas < 0:
        raise ScriptInputError("script style config max_commas_per_sentence must be a non-negative integer")
    for field in ("academic_phrases", "mechanical_transitions"):
        phrases = config.get(field)
        if not isinstance(phrases, list) or not phrases or any(not isinstance(item, str) or not item for item in phrases):
            raise ScriptInputError(f"script style config {field} must be a non-empty list of phrases")
    hook_markers = config.get("hook_markers")
    if not isinstance(hook_markers, dict) or set(hook_markers) != HOOK_TYPES:
        raise ScriptInputError("script style config must define markers for all hook types")
    for hook_type, markers in hook_markers.items():
        if not isinstance(markers, list) or not markers or any(not isinstance(item, str) or not item for item in markers):
            raise ScriptInputError(f"script style config hook_markers.{hook_type} must be a non-empty list")
    return config


def _load_duration_config() -> dict[str, Any]:
    config = _read_json(DURATION_CONFIG_PATH, "script duration config")
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config.get("schema_version") != 1:
        raise ScriptInputError("unsupported script duration config schema")
    for field in (
        "minimum_target_duration_seconds",
        "default_target_duration_seconds",
        "maximum_target_duration_seconds",
        "hook_duration_seconds",
        "speech_rate_units_per_minute",
    ):
        if type(config.get(field)) is not int or config[field] < 1:
            raise ScriptInputError(f"script duration config {field} must be a positive integer")
    if not (
        config["minimum_target_duration_seconds"]
        <= config["default_target_duration_seconds"]
        <= config["maximum_target_duration_seconds"]
    ):
        raise ScriptInputError("script duration config target must fall within its platform duration range")
    compression_order = config.get("compression_section_priority")
    if (
        not isinstance(compression_order, list)
        or any(not isinstance(section, str) for section in compression_order)
        or len(compression_order) != len(set(compression_order))
        or any(section not in {"problem", "comparison", "conclusion"} for section in compression_order)
    ):
        raise ScriptInputError("script duration config has an invalid compression section priority")
    return config


def _target_duration(payload: Any, config: dict[str, Any]) -> int:
    if not isinstance(payload, dict):
        raise ScriptInputError("script input must contain an object")
    target = payload.get("target_duration_seconds", config["default_target_duration_seconds"])
    if (
        type(target) is not int
        or not config["minimum_target_duration_seconds"] <= target <= config["maximum_target_duration_seconds"]
    ):
        raise ScriptInputError(
            "target_duration_seconds must be an integer from "
            f"{config['minimum_target_duration_seconds']} to {config['maximum_target_duration_seconds']}"
        )
    return target


def _sentence_character_count(sentence: str) -> int:
    return sum(not character.isspace() and not unicodedata.category(character).startswith("P") for character in sentence)


def _is_han(character: str) -> bool:
    name = unicodedata.name(character, "")
    return name.startswith(("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH"))


def _script_unit_count(sections: list[dict[str, Any]]) -> int:
    """Count each Han character and each contiguous non-Han alphanumeric token once."""
    count = 0
    for section in sections:
        text = section["narration"]
        index = 0
        while index < len(text):
            character = text[index]
            if _is_han(character):
                count += 1
                index += 1
            elif character.isalnum():
                count += 1
                index += 1
                while index < len(text) and text[index].isalnum() and not _is_han(text[index]):
                    index += 1
            else:
                index += 1
    return count


def _estimate_duration(sections: list[dict[str, Any]], speech_rate: int) -> dict[str, Any]:
    word_count = _script_unit_count(sections)
    if word_count < 1:
        raise ScriptInputError("script must contain at least one spoken character or word")
    # Round up to tenths so an estimate just above the target cannot be rounded down to a pass.
    estimated_duration = math.ceil(word_count * 600 / speech_rate) / 10
    return {
        "estimated_duration": estimated_duration,
        "word_count": word_count,
        "speech_rate": speech_rate,
    }


def _compress_to_target(
    sections: list[dict[str, Any]], target_seconds: int, duration_config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    speech_rate = duration_config["speech_rate_units_per_minute"]
    original_metrics = _estimate_duration(sections, speech_rate)
    current_metrics = original_metrics
    removed_sentences: list[dict[str, str]] = []

    hook = next(section for section in sections if section["section"] == "hook")
    hook_duration = math.ceil(_script_unit_count([hook]) * 600 / speech_rate) / 10
    if hook_duration > duration_config["hook_duration_seconds"]:
        raise ScriptInputError(
            f"Hook estimated_duration {hook_duration:.1f}s exceeds its "
            f"{duration_config['hook_duration_seconds']}s opening window; shorten the opening and retry"
        )

    if current_metrics["estimated_duration"] > target_seconds:
        sections_by_id = {section["section"]: section for section in sections}
        for section_id in duration_config["compression_section_priority"]:
            section = sections_by_id[section_id]
            for candidate in list(section.get("optional_sentences", [])):
                if current_metrics["estimated_duration"] <= target_seconds:
                    break
                section["narration"] = section["narration"].replace(candidate, "", 1)
                section["optional_sentences"].remove(candidate)
                removed_sentences.append({"section": section_id, "text": candidate})
                current_metrics = _estimate_duration(sections, speech_rate)
            if current_metrics["estimated_duration"] <= target_seconds:
                break

    if current_metrics["estimated_duration"] > target_seconds:
        compressed_count = len(removed_sentences)
        raise ScriptInputError(
            f"estimated_duration {current_metrics['estimated_duration']:.1f}s exceeds target "
            f"{target_seconds}s after removing {compressed_count} marked optional sentence(s); "
            "rewrite the remaining narration more concisely and retry"
        )
    return original_metrics, current_metrics, removed_sentences


def _validate_script_style(sections: list[dict[str, Any]], config: dict[str, Any]) -> None:
    issues: list[str] = []
    speech = "\n".join(section["narration"] for section in sections)
    for phrase in config["academic_phrases"]:
        if phrase in speech:
            issues.append(f"论文式表达：{phrase}")
    for phrase in config["mechanical_transitions"]:
        if phrase in speech:
            issues.append(f"机械连接词：{phrase}")

    for section in sections:
        for sentence_number, sentence in enumerate(SENTENCE_BOUNDARY.split(section["narration"]), start=1):
            if not sentence.strip():
                continue
            character_count = _sentence_character_count(sentence)
            if character_count > config["max_sentence_characters"]:
                issues.append(
                    f"{section['title']} 第 {sentence_number} 句有 {character_count} 个字符，"
                    f"超过上限 {config['max_sentence_characters']}"
                )
            comma_count = sentence.count("，") + sentence.count(",")
            if comma_count > config["max_commas_per_sentence"]:
                issues.append(
                    f"{section['title']} 第 {sentence_number} 句包含 {comma_count} 个逗号，"
                    "请拆成更短、单一信息点的句子"
                )

    hook = next(section for section in sections if section["section"] == "hook")
    hook_type = hook.get("hook_type")
    if not isinstance(hook_type, str) or hook_type not in HOOK_TYPES:
        issues.append("Hook 必须标记为 conclusion、counterintuitive 或 conflict")
    else:
        first_sentence = SENTENCE_BOUNDARY.split(hook["narration"], maxsplit=1)[0]
        markers = config["hook_markers"][hook_type]
        if not any(marker in first_sentence for marker in markers):
            issues.append(f"Hook 标记为 {hook_type}，但开场句没有对应的结论、反常识或冲突表达")

    if issues:
        raise ScriptInputError("脚本口语化检查未通过：" + "；".join(issues))


def _load_research_and_topic(directory: Path, project_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    research = _read_json(directory / "research.json", "research.json")
    if not isinstance(research, dict) or research.get("research_status") != "complete":
        raise ScriptInputError("script generation requires a complete research.json")
    topic = research.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        raise ScriptInputError("research.json has no topic")

    score = _read_json(directory / "topic.json", "topic.json")
    if not isinstance(score, dict):
        raise ScriptInputError("topic.json must contain an object")
    if score.get("project_id") not in (None, project_id):
        raise ScriptInputError("topic.json project_id does not match this project")
    if score.get("topic") != topic.strip():
        raise ScriptInputError("topic.json topic does not match research.json")
    risk_filter = score.get("risk_filter")
    if (
        score.get("decision") != "eligible_for_production"
        or not isinstance(risk_filter, dict)
        or risk_filter.get("passed") is not True
    ):
        raise ScriptInputError("topic is not eligible for production; script generation is blocked")
    total_score = score.get("total_score")
    minimum_score = score.get("minimum_total_score")
    if (
        type(total_score) is not int
        or type(minimum_score) is not int
        or total_score < minimum_score
    ):
        raise ScriptInputError("topic score does not meet its production threshold")

    raw_sources = research.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ScriptInputError("research.json must contain at least one source")
    sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(raw_sources):
        if not isinstance(source, dict):
            raise ScriptInputError(f"research.sources[{index}] must be an object")
        source_id = source.get("source_id")
        source_type = source.get("source_type")
        if not isinstance(source_id, str) or not source_id:
            raise ScriptInputError(f"research.sources[{index}] has no valid source_id")
        if source_id in sources:
            raise ScriptInputError(f"duplicate research source_id: {source_id}")
        if source_type not in SOURCE_TYPES:
            raise ScriptInputError(f"source {source_id} has an unsupported source_type")
        if not isinstance(source.get("title"), str) or not source["title"].strip():
            raise ScriptInputError(f"source {source_id} has no title")
        if not isinstance(source.get("url"), str) or not source["url"].strip():
            raise ScriptInputError(f"source {source_id} has no URL")
        sources[source_id] = source
    return research, sources


def _normalize_sections(payload: Any, sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload.get("schema_version") != SCHEMA_VERSION:
        raise ScriptInputError("script input must use schema_version 1")
    if not {"schema_version", "sections"} <= set(payload) or not set(payload) <= {
        "schema_version", "sections", "target_duration_seconds"
    }:
        raise ScriptInputError("script input contains missing or unsupported fields")
    raw_sections = payload.get("sections")
    expected_ids = [section_id for section_id, _ in SECTION_DEFINITIONS]
    if not isinstance(raw_sections, dict) or set(raw_sections) != set(expected_ids):
        raise ScriptInputError(f"sections must contain exactly: {', '.join(expected_ids)}")

    normalized: list[dict[str, Any]] = []
    for section_id, title in SECTION_DEFINITIONS:
        raw_section = raw_sections[section_id]
        required_fields = {"narration", "source_ids", "hook_type"} if section_id == "hook" else {"narration", "source_ids"}
        allowed_fields = required_fields | ({"optional_sentences"} if section_id in {"problem", "comparison", "conclusion"} else set())
        if not isinstance(raw_section, dict) or not required_fields <= set(raw_section) or not set(raw_section) <= allowed_fields:
            raise ScriptInputError(f"sections.{section_id} must contain required fields and only supported optional fields")
        narration = raw_section.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise ScriptInputError(f"sections.{section_id}.narration must be a non-empty string")
        source_ids = raw_section.get("source_ids")
        if not isinstance(source_ids, list) or any(not isinstance(item, str) or not item for item in source_ids):
            raise ScriptInputError(f"sections.{section_id}.source_ids must be a list of source IDs")
        if len(source_ids) != len(set(source_ids)):
            raise ScriptInputError(f"sections.{section_id}.source_ids must not contain duplicates")
        optional_sentences = raw_section.get("optional_sentences", [])
        if not isinstance(optional_sentences, list) or any(not isinstance(item, str) or not item.strip() for item in optional_sentences):
            raise ScriptInputError(f"sections.{section_id}.optional_sentences must be a list of complete sentences")
        if len(optional_sentences) != len(set(optional_sentences)):
            raise ScriptInputError(f"sections.{section_id}.optional_sentences must not contain duplicates")
        if optional_sentences:
            sentence_parts = [part.strip() for part in SENTENCE_BOUNDARY.split(narration) if part.strip()]
            if len(optional_sentences) >= len(sentence_parts):
                raise ScriptInputError(f"sections.{section_id} must retain at least one required sentence")
            for optional_sentence in optional_sentences:
                if sentence_parts.count(optional_sentence) != 1 or not re.search(r"[。！？!?；;]$", optional_sentence):
                    raise ScriptInputError(
                        f"sections.{section_id}.optional_sentences entries must match one complete, punctuated sentence in narration"
                    )
        if section_id == "evidence" and not source_ids:
            raise ScriptInputError("sections.evidence must cite at least one research source")
        for source_id in source_ids:
            source = sources.get(source_id)
            if source is None:
                raise ScriptInputError(f"sections.{section_id} references unknown source: {source_id}")
            if source.get("source_type") == "search_summary":
                raise ScriptInputError(f"search summary {source_id} cannot support a script claim")
        normalized.append(
            {
                "section": section_id,
                "title": title,
                "narration": narration.strip(),
                "source_ids": list(source_ids),
                **({"hook_type": raw_section.get("hook_type")} if section_id == "hook" else {}),
                **({"optional_sentences": list(optional_sentences)} if section_id in {"problem", "comparison", "conclusion"} else {}),
            }
        )
    return normalized


def render_script_markdown(script: dict[str, Any]) -> str:
    lines = [
        f"# 视频号脚本：{script['topic']}",
        "",
        (
            f"- 目标时长：{script['target_duration_seconds']} 秒；预计时长：{script['estimated_duration']} 秒；"
            f"字数：{script['word_count']}；预计语速：{script['speech_rate']} 个口播单位/分钟"
        ),
        "",
        "脚本中的来源标注仅供核验，不作为口播内容。来源详情见同目录 `sources.md`。",
        "",
    ]
    if script["compression"]["applied"]:
        lines.extend([f"- 已自动压缩 {len(script['compression']['removed_sentences'])} 句可删补充内容。", ""])
    for section in script["sections"]:
        lines.extend([f"## {section['title']}", ""])
        if section.get("hook_type"):
            lines.extend([f"> 开场方向（非口播）：{HOOK_TYPE_LABELS[section['hook_type']]}", ""])
        lines.extend([section["narration"], ""])
        if section["source_ids"]:
            citations = "、".join(f"[{source_id}]" for source_id in section["source_ids"])
            lines.extend([f"> 依据（非口播）：{citations}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
            if not content.endswith("\n"):
                file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def write_script_artifacts(directory: Path, project_id: str, payload: Any) -> dict[str, Any]:
    """Validate, write the script JSON/Markdown, and advance RESEARCHED to SCRIPTED."""
    directory = Path(directory)
    state = load_run_state(directory, project_id)
    if state["status"] != "RESEARCHED":
        raise StateError(f"script generation requires status RESEARCHED; current status is {state['status']}")
    output_paths = [directory / name for name in OUTPUT_NAMES]
    for output_path in output_paths:
        if output_path.exists():
            raise StateError(f"refusing to overwrite existing script artifact: {output_path}")

    research, sources_by_id = _load_research_and_topic(directory, project_id)
    duration_config = _load_duration_config()
    target_duration_seconds = _target_duration(payload, duration_config)
    sections = _normalize_sections(payload, sources_by_id)
    original_metrics, metrics, removed_sentences = _compress_to_target(
        sections, target_duration_seconds, duration_config
    )
    _validate_script_style(sections, _load_style_config())
    referenced_ids = {source_id for section in sections for source_id in section["source_ids"]}
    script = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "topic": research["topic"].strip(),
        "platform": "wechat_channels",
        "target_duration_seconds": target_duration_seconds,
        "estimated_duration": metrics["estimated_duration"],
        "word_count": metrics["word_count"],
        "word_count_basis": "CJK characters plus contiguous non-Han alphanumeric tokens",
        "speech_rate": metrics["speech_rate"],
        "speech_rate_unit": "script_units_per_minute",
        "compression": {
            "applied": bool(removed_sentences),
            "original_estimated_duration": original_metrics["estimated_duration"],
            "removed_sentences": removed_sentences,
        },
        "created_at": utc_timestamp(),
        "sections": sections,
        "sources": [
            {
                "source_id": source_id,
                "title": source["title"],
                "url": source["url"],
                "source_type": source["source_type"],
            }
            for source_id, source in sources_by_id.items()
            if source_id in referenced_ids
        ],
    }

    written: list[Path] = []
    try:
        _atomic_write(output_paths[0], json.dumps(script, ensure_ascii=False, indent=2))
        written.append(output_paths[0])
        _atomic_write(output_paths[1], render_script_markdown(script))
        written.append(output_paths[1])
        transition_project(
            directory,
            project_id,
            "SCRIPTED",
            note="Validated six-section WeChat Channels script and source references",
        )
    except Exception:
        for path in written:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise

    return {
        "project_id": project_id,
        "topic": script["topic"],
        "sections": [section["section"] for section in sections],
        "outputs": list(OUTPUT_NAMES),
        "target_duration_seconds": target_duration_seconds,
        "estimated_duration": metrics["estimated_duration"],
        "word_count": metrics["word_count"],
        "speech_rate": metrics["speech_rate"],
        "compression": script["compression"],
        "state": "SCRIPTED",
    }
