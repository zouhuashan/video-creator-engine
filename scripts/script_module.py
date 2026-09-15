"""Validate a WeChat Channels script draft and write project artifacts."""

from __future__ import annotations

import json
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


def _sentence_character_count(sentence: str) -> int:
    return sum(not character.isspace() and not unicodedata.category(character).startswith("P") for character in sentence)


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
    raw_sections = payload.get("sections")
    expected_ids = [section_id for section_id, _ in SECTION_DEFINITIONS]
    if not isinstance(raw_sections, dict) or set(raw_sections) != set(expected_ids):
        raise ScriptInputError(f"sections must contain exactly: {', '.join(expected_ids)}")

    normalized: list[dict[str, Any]] = []
    for section_id, title in SECTION_DEFINITIONS:
        raw_section = raw_sections[section_id]
        expected_fields = {"narration", "source_ids", "hook_type"} if section_id == "hook" else {"narration", "source_ids"}
        if not isinstance(raw_section, dict) or set(raw_section) != expected_fields:
            raise ScriptInputError(f"sections.{section_id} must contain {', '.join(sorted(expected_fields))} only")
        narration = raw_section.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise ScriptInputError(f"sections.{section_id}.narration must be a non-empty string")
        source_ids = raw_section.get("source_ids")
        if not isinstance(source_ids, list) or any(not isinstance(item, str) or not item for item in source_ids):
            raise ScriptInputError(f"sections.{section_id}.source_ids must be a list of source IDs")
        if len(source_ids) != len(set(source_ids)):
            raise ScriptInputError(f"sections.{section_id}.source_ids must not contain duplicates")
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
            }
        )
    _validate_script_style(normalized, _load_style_config())
    return normalized


def render_script_markdown(script: dict[str, Any]) -> str:
    lines = [
        f"# 视频号脚本：{script['topic']}",
        "",
        "脚本中的来源标注仅供核验，不作为口播内容。来源详情见同目录 `sources.md`。",
        "",
    ]
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
    sections = _normalize_sections(payload, sources_by_id)
    referenced_ids = {source_id for section in sections for source_id in section["source_ids"]}
    script = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "topic": research["topic"].strip(),
        "platform": "wechat_channels",
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
        "state": "SCRIPTED",
    }
