"""Validate sourced research input and write project research artifacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from .project_state import StateError, load_run_state, transition_project
except ImportError:
    from project_state import StateError, load_run_state, transition_project


SCHEMA_VERSION = 1
SOURCE_ID_PATTERN = re.compile(r"S\d{3,}\Z")
SOURCE_MODES = {
    "automatic_research",
    "user_materials_first",
    "provided_sources_only",
    "no_external_research",
}
SOURCE_POLICY = {
    "official": {"rank": 1, "label": "官方来源"},
    "primary_document": {"rank": 2, "label": "原始文档"},
    "authoritative_media": {"rank": 3, "label": "权威媒体"},
    "high_quality_community": {"rank": 4, "label": "高质量社区"},
    "search_summary": {"rank": 5, "label": "搜索摘要"},
}
OUTPUT_NAMES = ("research.json", "research.md", "sources.md")
RISK_SEVERITIES = {"low", "medium", "high", "critical"}


class ResearchInputError(ValueError):
    """Raised when research input is incomplete or lacks traceable evidence."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchInputError(f"{field} must be a non-empty string")
    return value.strip()


def _list_field(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ResearchInputError(f"{field} must be a list")
    return value


def _source_ids(value: Any, field: str, sources_by_id: dict[str, dict[str, Any]]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ResearchInputError(f"{field} must contain at least one source ID")
    result: list[str] = []
    for source_id in value:
        if not isinstance(source_id, str) or source_id not in sources_by_id:
            raise ResearchInputError(f"{field} refers to unknown source ID: {source_id}")
        if source_id not in result:
            result.append(source_id)
    search_leads = [
        source_id for source_id in result
        if sources_by_id[source_id]["source_type"] == "search_summary"
    ]
    if search_leads:
        raise ResearchInputError(
            f"{field} cites search summary {', '.join(search_leads)}; open a source page before using it as evidence"
        )
    return sorted(
        result,
        key=lambda source_id: (SOURCE_POLICY[sources_by_id[source_id]["source_type"]]["rank"], source_id),
    )


def _evidence_item(
    item: Any,
    *,
    label: str,
    claim_key: str,
    sources_by_id: dict[str, dict[str, Any]],
    extra_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ResearchInputError(f"{label} must be an object")
    normalized: dict[str, Any] = {}
    for key in extra_keys:
        normalized[key] = _text(item.get(key), f"{label}.{key}")
        if key == "severity" and normalized[key] not in RISK_SEVERITIES:
            raise ResearchInputError(f"{label}.severity must be one of: {', '.join(sorted(RISK_SEVERITIES))}")
    normalized[claim_key] = _text(item.get(claim_key), f"{label}.{claim_key}")
    evidence = _text(item.get("evidence"), f"{label}.evidence")
    if len(evidence) > 500:
        raise ResearchInputError(f"{label}.evidence must be 500 characters or fewer")
    normalized["evidence"] = evidence
    normalized["source_ids"] = _source_ids(item.get("source_ids"), f"{label}.source_ids", sources_by_id)
    for key in ("id", "checked_at", "severity"):
        if key in item and item[key] is not None:
            normalized[key] = _text(item[key], f"{label}.{key}")
    return normalized


def normalize_research_input(payload: Any, *, now: str | None = None) -> dict[str, Any]:
    """Validate all factual claims and produce a normalized research record."""
    if not isinstance(payload, dict):
        raise ResearchInputError("research input must be a JSON object")
    topic = _text(payload.get("topic"), "topic")
    source_mode = payload.get("source_mode", "automatic_research")
    if not isinstance(source_mode, str) or source_mode not in SOURCE_MODES:
        raise ResearchInputError(f"source_mode must be one of: {', '.join(sorted(SOURCE_MODES))}")

    source_items = _list_field(payload.get("sources", []), "sources")
    if not source_items:
        raise ResearchInputError("sources must contain at least one verifiable source")
    sources: list[dict[str, Any]] = []
    sources_by_id: dict[str, dict[str, Any]] = {}
    timestamp = now or utc_timestamp()
    for index, item in enumerate(source_items, start=1):
        label = f"sources[{index - 1}]"
        if not isinstance(item, dict):
            raise ResearchInputError(f"{label} must be an object")
        source_id = _text(item.get("source_id"), f"{label}.source_id")
        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            raise ResearchInputError(f"{label}.source_id must match S001")
        if source_id in sources_by_id:
            raise ResearchInputError(f"duplicate source ID: {source_id}")
        url = _text(item.get("url"), f"{label}.url")
        try:
            parsed_url = urlsplit(url)
        except ValueError as error:
            raise ResearchInputError(f"{label}.url is invalid") from error
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ResearchInputError(f"{label}.url must be an absolute http or https URL")
        if parsed_url.username or parsed_url.password:
            raise ResearchInputError(f"{label}.url must not contain embedded credentials")
        source = {
            "source_id": source_id,
            "title": _text(item.get("title"), f"{label}.title"),
            "publisher": _text(item.get("publisher"), f"{label}.publisher"),
            "url": url,
            "source_type": _text(item.get("source_type"), f"{label}.source_type"),
            "published_at": item.get("published_at"),
            "accessed_at": item.get("accessed_at") or timestamp,
        }
        if source["source_type"] not in SOURCE_POLICY:
            raise ResearchInputError(
                f"{label}.source_type must be one of: {', '.join(SOURCE_POLICY)}"
            )
        source["priority_rank"] = SOURCE_POLICY[source["source_type"]]["rank"]
        source["priority_label"] = SOURCE_POLICY[source["source_type"]]["label"]
        for date_key in ("published_at", "accessed_at"):
            date_value = source[date_key]
            if date_value is not None and (not isinstance(date_value, str) or not date_value.strip()):
                raise ResearchInputError(f"{label}.{date_key} must be a non-empty string or null")
        sources.append(source)
        sources_by_id[source_id] = source

    raw_facts = _list_field(payload.get("core_facts", []), "core_facts")
    if not raw_facts:
        raise ResearchInputError("at least one source-backed core_fact is required")
    raw_faqs = _list_field(payload.get("user_faqs", []), "user_faqs")
    raw_specs = _list_field(payload.get("price_spec_versions", []), "price_spec_versions")
    raw_risks = _list_field(payload.get("risks", []), "risks")
    facts = [
        _evidence_item(item, label=f"core_facts[{index}]", claim_key="claim", sources_by_id=sources_by_id)
        for index, item in enumerate(raw_facts)
    ]

    faqs = [
        _evidence_item(item, label=f"user_faqs[{index}]", claim_key="answer", extra_keys=("question",), sources_by_id=sources_by_id)
        for index, item in enumerate(raw_faqs)
    ]
    raw_viewpoints = payload.get("viewpoints", {})
    if not isinstance(raw_viewpoints, dict):
        raise ResearchInputError("viewpoints must be an object with positive and negative lists")
    raw_positive = _list_field(raw_viewpoints.get("positive", []), "viewpoints.positive")
    raw_negative = _list_field(raw_viewpoints.get("negative", []), "viewpoints.negative")
    viewpoints = {
        side: [
            _evidence_item(item, label=f"viewpoints.{side}[{index}]", claim_key="claim", sources_by_id=sources_by_id)
            for index, item in enumerate(raw_positive if side == "positive" else raw_negative)
        ]
        for side in ("positive", "negative")
    }
    specs = [
        _evidence_item(
            item,
            label=f"price_spec_versions[{index}]",
            claim_key="value",
            extra_keys=("item",),
            sources_by_id=sources_by_id,
        )
        for index, item in enumerate(raw_specs)
    ]
    risks = [
        _evidence_item(
            item,
            label=f"risks[{index}]",
            claim_key="risk",
            extra_keys=("severity",),
            sources_by_id=sources_by_id,
        )
        for index, item in enumerate(raw_risks)
    ]
    directions = _list_field(payload.get("asset_directions", []), "asset_directions")
    normalized_directions = [_text(direction, f"asset_directions[{index}]") for index, direction in enumerate(directions)]
    sources.sort(key=lambda source: (source["priority_rank"], source["source_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "topic": topic,
        "source_mode": source_mode,
        "source_policy": [
            {"rank": details["rank"], "source_type": source_type, "label": details["label"]}
            for source_type, details in SOURCE_POLICY.items()
        ],
        "research_status": "complete",
        "created_at": timestamp,
        "core_facts": facts,
        "user_faqs": faqs,
        "viewpoints": viewpoints,
        "price_spec_versions": specs,
        "asset_directions": normalized_directions,
        "risks": risks,
        "sources": sources,
    }


def _citations(item: dict[str, Any]) -> str:
    return " ".join(f"[{source_id}]" for source_id in item["source_ids"])


def _render_evidence_section(title: str, items: list[dict[str, Any]], render_claim: Any) -> list[str]:
    lines = [f"## {title}", ""]
    if not items:
        lines.extend(["暂无已记录的来源支持内容。", ""])
        return lines
    for item in items:
        lines.extend([f"- {render_claim(item)} {_citations(item)}", f"  - 证据摘要：{item['evidence']}"])
        if item.get("checked_at"):
            lines.append(f"  - 核验时间：{item['checked_at']}")
    lines.append("")
    return lines


def render_research_markdown(research: dict[str, Any]) -> str:
    lines = [
        f"# 研究报告：{research['topic']}",
        "",
        f"- 研究状态：{research['research_status']}",
        f"- 来源模式：`{research['source_mode']}`",
        f"- 生成时间：{research['created_at']}",
        "",
        "## 来源优先级",
        "",
        "官方来源 > 原始文档 > 权威媒体 > 高质量社区 > 搜索摘要。引用按优先级排序；搜索摘要只作检索线索，不能单独支撑事实。",
        "",
    ]
    lines.extend(_render_evidence_section("核心事实", research["core_facts"], lambda item: item["claim"]))
    lines.extend(
        _render_evidence_section(
            "用户常见问题",
            research["user_faqs"],
            lambda item: f"**{item['question']}** {item['answer']}",
        )
    )
    lines.extend(_render_evidence_section("正面观点", research["viewpoints"]["positive"], lambda item: item["claim"]))
    lines.extend(_render_evidence_section("反面观点", research["viewpoints"]["negative"], lambda item: item["claim"]))
    lines.extend(
        _render_evidence_section(
            "价格、规格与版本",
            research["price_spec_versions"],
            lambda item: f"{item['item']}：{item['value']}",
        )
    )
    lines.extend(["## 可用素材方向", ""])
    if research["asset_directions"]:
        lines.extend(f"- {direction}" for direction in research["asset_directions"])
    else:
        lines.append("暂无已记录的素材方向。")
    lines.append("")
    lines.extend(
        _render_evidence_section(
            "风险信息",
            research["risks"],
            lambda item: f"{item['risk']}（级别：{item['severity']}）",
        )
    )
    lines.extend(["## 参考来源", "", "来源编号对应 `sources.md`。", ""])
    return "\n".join(lines)


def render_sources_markdown(research: dict[str, Any]) -> str:
    lines = [f"# 来源清单：{research['topic']}", ""]
    for source in research["sources"]:
        lines.extend(
            [
                f"## [{source['source_id']}] {source['title']}",
                "",
                f"- 发布方：{source['publisher']}",
                f"- 类型：{source['priority_label']}（优先级 {source['priority_rank']}）",
                f"- 链接：<{source['url']}>",
                f"- 发布/更新日期：{source['published_at'] or '未提供'}",
                f"- 查阅时间：{source['accessed_at']}",
                *(
                    ["- 用途：仅作检索线索，不能单独支撑事实"]
                    if source["source_type"] == "search_summary"
                    else ["- 用途：可用于事实引用"]
                ),
                "",
            ]
        )
    return "\n".join(lines)


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


def write_research_artifacts(directory: Path, project_id: str, payload: Any) -> dict[str, Any]:
    """Validate, write the three research artifacts, and advance CREATED to RESEARCHED."""
    directory = Path(directory)
    state = load_run_state(directory, project_id)
    if state["status"] != "CREATED":
        raise StateError(f"research requires status CREATED; current status is {state['status']}")
    existing = [name for name in OUTPUT_NAMES if (directory / name).exists()]
    if existing:
        raise StateError(f"refusing to overwrite existing research artifacts: {', '.join(existing)}")

    research = normalize_research_input(payload)
    rendered = {
        "research.json": json.dumps(research, ensure_ascii=False, indent=2) + "\n",
        "research.md": render_research_markdown(research),
        "sources.md": render_sources_markdown(research),
    }
    created_paths: list[Path] = []
    try:
        for name, content in rendered.items():
            path = directory / name
            _atomic_write(path, content)
            created_paths.append(path)
        transition_project(directory, project_id, "RESEARCHED", note="Research artifacts validated and written")
    except Exception:
        for path in created_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    return {
        "project_id": project_id,
        "status": "RESEARCHED",
        "topic": research["topic"],
        "outputs": list(OUTPUT_NAMES),
        "core_fact_count": len(research["core_facts"]),
        "source_count": len(research["sources"]),
    }
