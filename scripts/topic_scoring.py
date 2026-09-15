"""Calculate explainable topic scores from research artifacts and an assessment."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

try:
    from .project_state import DEFAULT_PROJECTS_DIR, ROOT, StateError, load_run_state, project_dir
except ImportError:
    from project_state import DEFAULT_PROJECTS_DIR, ROOT, StateError, load_run_state, project_dir


CONFIG_PATH = ROOT / "config" / "topic-scoring.json"
RATING_FIELDS = (
    "traffic_value",
    "commercial_value",
    "evergreen_score",
    "production_cost",
    "originality",
)
EVIDENCE_SCORES = {
    "official": 100,
    "primary_document": 90,
    "authoritative_media": 80,
    "high_quality_community": 60,
    "search_summary": 0,
}


class TopicScoringError(ValueError):
    """Raised when research, score config, or assessment cannot be scored safely."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_integer(value: Any, label: str) -> int:
    if type(value) is not int or not 0 <= value <= 100:
        raise TopicScoringError(f"{label} must be an integer from 0 to 100")
    return value


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise TopicScoringError(f"{label} not found: {path}") from error
    except json.JSONDecodeError as error:
        raise TopicScoringError(f"invalid {label}: {error}") from error


def _load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = _read_json(path, "topic scoring config")
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config.get("schema_version") != 1:
        raise TopicScoringError("unsupported topic scoring config schema")
    if config.get("score_scale") != {"minimum": 0, "maximum": 100}:
        raise TopicScoringError("topic scoring currently requires a 0-100 score scale")
    weights = config.get("weights_percent")
    expected_fields = set(RATING_FIELDS) | {"evidence_strength"}
    if not isinstance(weights, dict) or set(weights) != expected_fields:
        raise TopicScoringError("topic scoring weights must define all six weighted dimensions")
    if any(type(weight) is not int or weight < 0 for weight in weights.values()) or sum(weights.values()) != 100:
        raise TopicScoringError("topic scoring weights must be non-negative integers summing to 100")
    for key in ("minimum_total_score", "risk_filter_threshold", "independent_source_bonus", "risk_count_increment"):
        value = config.get(key)
        if type(value) is not int or not 0 <= value <= 100:
            raise TopicScoringError(f"topic scoring config {key} must be an integer from 0 to 100")
    if not isinstance(config.get("action_below_threshold"), str) or not config["action_below_threshold"].strip():
        raise TopicScoringError("action_below_threshold must be a non-empty decision label")
    if config.get("production_cost_transform") != "100 - production_cost":
        raise TopicScoringError("unsupported production_cost_transform")
    source_scores = config.get("evidence_source_scores")
    if not isinstance(source_scores, dict) or set(source_scores) != set(EVIDENCE_SCORES):
        raise TopicScoringError("evidence_source_scores must define all factual source tiers")
    for source_type, score in source_scores.items():
        _bounded_integer(score, f"evidence_source_scores.{source_type}")
    risk_scores = config.get("risk_severity_scores")
    if not isinstance(risk_scores, dict) or set(risk_scores) != {"low", "medium", "high", "critical"}:
        raise TopicScoringError("risk_severity_scores must define low, medium, high, and critical")
    for severity, score in risk_scores.items():
        if not isinstance(severity, str) or not severity:
            raise TopicScoringError("risk severity names must be non-empty strings")
        _bounded_integer(score, f"risk_severity_scores.{severity}")
    return config


def _normalize_ratings(assessment: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(assessment, dict) or type(assessment.get("schema_version")) is not int or assessment.get("schema_version") != 1:
        raise TopicScoringError("topic assessment must use schema_version 1")
    raw_ratings = assessment.get("ratings")
    if not isinstance(raw_ratings, dict) or set(raw_ratings) != set(RATING_FIELDS):
        raise TopicScoringError(f"ratings must contain exactly: {', '.join(RATING_FIELDS)}")
    ratings: dict[str, dict[str, Any]] = {}
    for field in RATING_FIELDS:
        item = raw_ratings[field]
        if not isinstance(item, dict):
            raise TopicScoringError(f"ratings.{field} must contain score and rationale")
        score = _bounded_integer(item.get("score"), f"ratings.{field}.score")
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale.strip()) > 500:
            raise TopicScoringError(f"ratings.{field}.rationale must be 1 to 500 characters")
        ratings[field] = {"score": score, "rationale": rationale.strip()}
    return ratings


def _evidence_strength(research: dict[str, Any], config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    sources = research.get("sources")
    facts = research.get("core_facts")
    if not isinstance(sources, list) or not isinstance(facts, list) or not facts:
        raise TopicScoringError("research.json must contain sources and at least one core fact")
    sources_by_id: dict[str, dict[str, Any]] = {}
    source_scores = config["evidence_source_scores"]
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise TopicScoringError(f"research.sources[{index}] must be an object")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in sources_by_id:
            raise TopicScoringError(f"research.sources[{index}] has an invalid or duplicate source_id")
        source_type = source.get("source_type")
        if source_type not in source_scores:
            raise TopicScoringError(f"source {source_id} has unsupported evidence tier: {source_type}")
        publisher = source.get("publisher")
        if not isinstance(publisher, str) or not publisher.strip():
            raise TopicScoringError(f"source {source_id} has no publisher for independent-source checks")
        sources_by_id[source_id] = source

    fact_scores: list[int] = []
    source_type_counts: dict[str, int] = {source_type: 0 for source_type in source_scores}
    corroborated_fact_count = 0
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict):
            raise TopicScoringError(f"research.core_facts[{index}] must be an object")
        source_ids = fact.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise TopicScoringError(f"research.core_facts[{index}] has no source references")
        cited: list[dict[str, Any]] = []
        for source_id in source_ids:
            source = sources_by_id.get(source_id)
            if source is None:
                raise TopicScoringError(f"research.core_facts[{index}] refers to unknown source {source_id}")
            if source["source_type"] == "search_summary":
                raise TopicScoringError(f"research.core_facts[{index}] uses a search summary as factual evidence")
            cited.append(source)
        tiers = {source["source_type"] for source in cited}
        for source_type in tiers:
            source_type_counts[source_type] += 1
        best_source_score = max(source_scores[source["source_type"]] for source in cited)
        publishers = {source["publisher"].strip().casefold() for source in cited}
        if len(publishers) >= 2:
            best_source_score = min(100, best_source_score + config["independent_source_bonus"])
            corroborated_fact_count += 1
        fact_scores.append(best_source_score)

    mean = sum(fact_scores) / len(fact_scores)
    score = int(Decimal(str(mean)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return score, {
        "core_fact_count": len(facts),
        "fact_scores": fact_scores,
        "corroborated_fact_count": corroborated_fact_count,
        "source_type_coverage": source_type_counts,
    }


def _risk_score(research: dict[str, Any], config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    risks = research.get("risks")
    if not isinstance(risks, list):
        raise TopicScoringError("research.risks must be present as a list, empty when no risks were found")
    severity_scores = config["risk_severity_scores"]
    risk_values: list[int] = []
    normalized_severities: list[str] = []
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            raise TopicScoringError(f"research.risks[{index}] must be an object")
        severity = risk.get("severity")
        if not isinstance(severity, str) or severity not in severity_scores:
            raise TopicScoringError(
                f"research.risks[{index}].severity must be one of: {', '.join(severity_scores)}"
            )
        risk_values.append(severity_scores[severity])
        normalized_severities.append(severity)
    if not risk_values:
        return 0, {"risk_count": 0, "severities": [], "interpretation": "no risks recorded in research.json"}
    score = min(100, max(risk_values) + config["risk_count_increment"] * (len(risk_values) - 1))
    return score, {"risk_count": len(risk_values), "severities": normalized_severities}


def calculate_topic_score(
    research: Any,
    assessment: Any,
    config: dict[str, Any] | None = None,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Calculate weighted topic score; evidence and risk dimensions come from research."""
    if not isinstance(research, dict) or research.get("research_status") != "complete":
        raise TopicScoringError("topic scoring requires a complete research.json")
    topic = research.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        raise TopicScoringError("research.json has no topic")
    active_config = config or _load_config()
    ratings = _normalize_ratings(assessment)
    evidence_score, evidence_details = _evidence_strength(research, active_config)
    risk_score, risk_details = _risk_score(research, active_config)

    scores = {field: ratings[field]["score"] for field in RATING_FIELDS}
    scores["evidence_strength"] = evidence_score
    scores["risk_score"] = risk_score
    weighted_values = dict(scores)
    weighted_values["production_cost"] = 100 - scores["production_cost"]
    weights = active_config["weights_percent"]
    raw_contributions = {
        field: Decimal(weighted_values[field] * weights[field]) / Decimal(100)
        for field in weights
    }
    contributions = {
        field: float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        for field, value in raw_contributions.items()
    }
    unrounded_total = sum(raw_contributions.values())
    total_score = int(unrounded_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    minimum_score = active_config["minimum_total_score"]
    risk_threshold = active_config["risk_filter_threshold"]
    if risk_score >= risk_threshold:
        decision = "blocked_by_risk_filter"
        decision_reason = f"risk_score {risk_score} meets or exceeds filter threshold {risk_threshold}"
    elif total_score < minimum_score:
        decision = active_config["action_below_threshold"]
        decision_reason = f"total_score {total_score} is below minimum {minimum_score}"
    else:
        decision = "eligible_for_production"
        decision_reason = "score and risk gates passed"

    return {
        "schema_version": 1,
        "topic": topic.strip(),
        "created_at": created_at or utc_timestamp(),
        **scores,
        "total_score": total_score,
        "weighted_contributions": contributions,
        "weights_percent": dict(weights),
        "production_cost_weighted_value": weighted_values["production_cost"],
        "evidence_details": evidence_details,
        "risk_details": risk_details,
        "risk_filter": {
            "threshold": risk_threshold,
            "passed": risk_score < risk_threshold,
        },
        "minimum_total_score": minimum_score,
        "decision": decision,
        "decision_reason": decision_reason,
        "assessment_rationales": {field: ratings[field]["rationale"] for field in RATING_FIELDS},
    }


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
            file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def write_topic_score(directory: Path, project_id: str, assessment: Any) -> dict[str, Any]:
    """Score a researched topic and save topic.json without advancing lifecycle state."""
    directory = Path(directory)
    state = load_run_state(directory, project_id)
    if state["status"] != "RESEARCHED":
        raise StateError(f"topic scoring requires status RESEARCHED; current status is {state['status']}")
    output_path = directory / "topic.json"
    if output_path.exists():
        raise StateError(f"refusing to overwrite existing topic score: {output_path}")
    research = _read_json(directory / "research.json", "research.json")
    result = calculate_topic_score(research, assessment, _load_config())
    result["project_id"] = project_id
    _atomic_write(output_path, json.dumps(result, ensure_ascii=False, indent=2))
    return {
        "project_id": project_id,
        "topic": result["topic"],
        "scores": {field: result[field] for field in (*RATING_FIELDS, "evidence_strength", "risk_score", "total_score")},
        "decision": result["decision"],
        "decision_reason": result["decision_reason"],
        "risk_filter": result["risk_filter"],
        "outputs": ["topic.json"],
        "state": state["status"],
    }


def score_project(project_id: str, assessment_file: Path, projects_dir: Path = DEFAULT_PROJECTS_DIR) -> dict[str, Any]:
    directory = project_dir(project_id, projects_dir)
    assessment = _read_json(Path(assessment_file), "topic assessment")
    return write_topic_score(directory, project_id, assessment)
