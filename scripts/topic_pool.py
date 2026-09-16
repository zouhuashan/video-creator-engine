#!/usr/bin/env python3
"""Rank normalized trend signals into a review-only topic pool."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .trend_discovery import ROOT, SOURCE_TYPES, TrendDiscoveryError, normalize_topic, validate_discovery_artifact
except ImportError:
    from trend_discovery import ROOT, SOURCE_TYPES, TrendDiscoveryError, normalize_topic, validate_discovery_artifact


CONFIG_PATH = ROOT / "config" / "topic-pool.json"


class TopicPoolError(ValueError):
    """Raised when trend signals cannot safely form a topic pool."""


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TopicPoolError(f"cannot read {label} {path}: {error}") from error


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return validate_config(_read_json(Path(path), "topic pool config"))


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise TopicPoolError("topic pool config must be an object")
    weights = config.get("discovery_score_weights_percent")
    if config.get("schema_version") != 1 or not isinstance(weights, dict):
        raise TopicPoolError("unsupported topic pool config schema")
    if set(weights) != {"source_diversity", "signal_strength", "freshness"}:
        raise TopicPoolError("topic pool config must define all discovery score dimensions")
    if any(type(value) is not int or value < 0 for value in weights.values()) or sum(weights.values()) != 100:
        raise TopicPoolError("discovery score weights must be non-negative integers summing to 100")
    half_life = config.get("freshness_half_life_days")
    if type(half_life) not in {int, float} or half_life <= 0:
        raise TopicPoolError("freshness_half_life_days must be positive")
    return config


def _freshness_score(signals: list[dict[str, Any]], as_of: date, half_life_days: float) -> int:
    scores: list[float] = []
    for signal in signals:
        observed = datetime.fromisoformat(signal["observed_at"].replace("Z", "+00:00"))
        age_days = max(0.0, (datetime.combine(as_of, datetime.min.time(), timezone.utc) - observed).total_seconds() / 86400)
        scores.append(100 * (0.5 ** (age_days / half_life_days)))
    return round(sum(scores) / len(scores)) if scores else 0


def build_topic_pool(
    trend_artifact: Any,
    *,
    as_of: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        artifact = validate_discovery_artifact(trend_artifact)
    except TrendDiscoveryError as error:
        raise TopicPoolError(str(error)) from error
    try:
        run_date = date.fromisoformat(as_of) if as_of else date.fromisoformat(artifact["date"])
    except (TypeError, ValueError) as error:
        raise TopicPoolError("as_of must use YYYY-MM-DD") from error
    if run_date < date.fromisoformat(artifact["date"]):
        raise TopicPoolError("as_of cannot precede the trend artifact date")
    active = validate_config(config) if config is not None else load_config()
    weights = active["discovery_score_weights_percent"]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for signal in artifact["signals"]:
        key = normalize_topic(signal["topic"])
        if not key:
            raise TopicPoolError("trend signal topic cannot normalize to an empty value")
        grouped.setdefault(key, []).append(signal)

    candidates: list[dict[str, Any]] = []
    for key, signals in grouped.items():
        representative = max(signals, key=lambda item: (item["strength"], item["observed_at"], item["signal_id"]))
        source_types = sorted({signal["source_type"] for signal in signals})
        source_diversity = round(100 * len(source_types) / len(SOURCE_TYPES))
        signal_strength = round(sum(signal["strength"] for signal in signals) / len(signals))
        freshness = _freshness_score(signals, run_date, active["freshness_half_life_days"])
        contributions = {
            dimension: round(score * weights[dimension] / 100, 1)
            for dimension, score in {
                "source_diversity": source_diversity,
                "signal_strength": signal_strength,
                "freshness": freshness,
            }.items()
        }
        discovery_score = round(sum(contributions.values()))
        references = [
            {
                "signal_id": signal["signal_id"],
                "source_type": signal["source_type"],
                "source_name": signal["source_name"],
                "title": signal["title"],
                "observed_at": signal["observed_at"],
                "strength": signal["strength"],
                **({"url": signal["url"]} if "url" in signal else {}),
                **({"summary": signal["summary"]} if "summary" in signal else {}),
            }
            for signal in sorted(signals, key=lambda item: (item["source_type"], item["observed_at"], item["signal_id"]))
        ]
        candidates.append({
            "topic": representative["topic"],
            "discovery_score": discovery_score,
            "score_breakdown": {
                "source_diversity": source_diversity,
                "signal_strength": signal_strength,
                "freshness": freshness,
                "weighted_contributions": contributions,
                "source_types": source_types,
            },
            "ranking_reason": (
                f"{len(source_types)} of {len(SOURCE_TYPES)} source categories; "
                f"average signal strength {signal_strength}/100; freshness {freshness}/100"
            ),
            "supporting_signals": references,
            "review_status": "needs_human_review",
            "next_step": "verify_sources_and_complete_research",
            "production_eligible": False,
        })
    candidates.sort(key=lambda item: (-item["discovery_score"], normalize_topic(item["topic"])))
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return {
        "schema_version": 1,
        "date": run_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_artifact_date": artifact["date"],
        "score_policy": {
            "type": "discovery_priority_only",
            "weights_percent": dict(weights),
            "freshness_half_life_days": active["freshness_half_life_days"],
            "production_decision": "requires_verified_research_and_topic_scoring",
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise TopicPoolError(f"refusing to overwrite existing output: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        try:
            os.link(temp_name, path)
        except FileExistsError as error:
            raise TopicPoolError(f"refusing to overwrite existing output: {path}") from error
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trend_artifact", type=Path)
    parser.add_argument("--as-of", help="pool date (YYYY-MM-DD); defaults to the trend artifact date")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "topics")
    args = parser.parse_args(argv)
    try:
        trend = _read_json(args.trend_artifact, "trend artifact")
        result = build_topic_pool(trend, as_of=args.as_of)
        output = args.output_dir / f"{result['date']}.json"
        _atomic_write(output, result)
    except (OSError, TopicPoolError) as error:
        print(f"topic-pool: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(output), "candidate_count": result["candidate_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
