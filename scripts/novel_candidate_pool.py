#!/usr/bin/env python3
"""Join researched novel records to the review-only automatic topic pool."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from .topic_pool import build_topic_pool
    from .trend_discovery import discover_trends, normalize_topic
except ImportError:
    from topic_pool import build_topic_pool
    from trend_discovery import discover_trends, normalize_topic


RIGHTS_STATUSES = {"public_domain_source_verified", "licensed", "unknown", "not_available"}
RIGHTS_CAN_PASS = {"public_domain_source_verified", "licensed"}
POOL_SOURCE_TYPE = "community"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z")


class NovelCandidatePoolError(ValueError):
    """Raised when candidate records or topic-pool joins are invalid."""


class _RankSnapshotSource:
    source_type = POOL_SOURCE_TYPE

    def __init__(self, signals: list[dict[str, Any]]):
        self._signals = signals

    def fetch(self) -> list[dict[str, Any]]:
        return self._signals


def _text(value: Any, label: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise NovelCandidatePoolError(f"{label} must be 1 to {limit} characters")
    return value.strip()


def _url(value: Any, label: str) -> str:
    text = _text(value, label, 2000)
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise NovelCandidatePoolError(f"{label} must be an absolute http(s) URL without embedded credentials")
    return text


def _date(value: Any, label: str) -> date:
    text = _text(value, label, 10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise NovelCandidatePoolError(f"{label} must use YYYY-MM-DD") from error
    if parsed.isoformat() != text:
        raise NovelCandidatePoolError(f"{label} must use YYYY-MM-DD")
    return parsed


def validate_catalog(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise NovelCandidatePoolError("novel catalog must use schema_version 1")
    snapshot_date = _date(payload.get("snapshot_date"), "snapshot_date")
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise NovelCandidatePoolError("candidates must be a list")
    candidates = []
    ids: set[str] = set()
    titles: set[str] = set()
    for index, raw in enumerate(raw_candidates):
        label = f"candidates[{index}]"
        if not isinstance(raw, dict):
            raise NovelCandidatePoolError(f"{label} must be an object")
        candidate_id = _text(raw.get("candidate_id"), f"{label}.candidate_id", 100)
        if not SAFE_ID.fullmatch(candidate_id):
            raise NovelCandidatePoolError(f"{label}.candidate_id must use safe ASCII identifier characters")
        title = _text(raw.get("title"), f"{label}.title", 200)
        key = normalize_topic(title)
        if candidate_id in ids or key in titles:
            raise NovelCandidatePoolError(f"duplicate candidate ID or normalized title: {candidate_id}")
        ids.add(candidate_id)
        titles.add(key)
        status = raw.get("work_status")
        if status not in ("ongoing", "completed", "unknown"):
            raise NovelCandidatePoolError(f"{label}.work_status must be ongoing, completed, or unknown")
        rights = raw.get("rights")
        if not isinstance(rights, dict) or rights.get("status") not in tuple(RIGHTS_STATUSES):
            raise NovelCandidatePoolError(f"{label}.rights.status is invalid")
        evidence = rights.get("evidence_urls", [])
        if not isinstance(evidence, list):
            raise NovelCandidatePoolError(f"{label}.rights.evidence_urls must be a list")
        normalized_evidence = [_url(item, f"{label}.rights.evidence_urls[{n}]") for n, item in enumerate(evidence)]
        rights_status = rights["status"]
        if rights_status in RIGHTS_CAN_PASS and not normalized_evidence:
            raise NovelCandidatePoolError(f"{label}.rights needs evidence URLs before metadata gate can pass")
        adaptation_source = raw.get("adaptation_source")
        if not isinstance(adaptation_source, dict):
            raise NovelCandidatePoolError(f"{label}.adaptation_source must be an object")
        source_url = adaptation_source.get("source_url")
        normalized_source = {
            "source_url": _url(source_url, f"{label}.adaptation_source.source_url"),
            "edition_note": _text(adaptation_source.get("edition_note"), f"{label}.adaptation_source.edition_note", 500),
        }
        signals = raw.get("platform_signals")
        if not isinstance(signals, list):
            raise NovelCandidatePoolError(f"{label}.platform_signals must be a list")
        normalized_signals = []
        snapshot_keys: set[tuple[str, str, str, str]] = set()
        for signal_index, signal in enumerate(signals):
            signal_label = f"{label}.platform_signals[{signal_index}]"
            if not isinstance(signal, dict):
                raise NovelCandidatePoolError(f"{signal_label} must be an object")
            observed = _date(signal.get("observed_at"), f"{signal_label}.observed_at")
            if observed > snapshot_date:
                raise NovelCandidatePoolError(f"{signal_label}.observed_at cannot be after snapshot_date")
            rank = signal.get("rank")
            if rank is not None and (type(rank) is not int or rank < 1):
                raise NovelCandidatePoolError(f"{signal_label}.rank must be a positive integer or null")
            chart_size = signal.get("chart_size")
            if chart_size is not None and (type(chart_size) is not int or chart_size < 1):
                raise NovelCandidatePoolError(f"{signal_label}.chart_size must be a positive integer or null")
            if rank is not None and (chart_size is None or rank > chart_size):
                raise NovelCandidatePoolError(f"{signal_label}.rank requires chart_size at least as large as rank")
            metric_value = signal.get("metric_value")
            if metric_value is not None and (type(metric_value) not in {int, float, str} or isinstance(metric_value, str) and not metric_value.strip()):
                raise NovelCandidatePoolError(f"{signal_label}.metric_value must be a non-empty string or number")
            if rank is None and metric_value is None:
                raise NovelCandidatePoolError(f"{signal_label} must preserve a rank or raw metric value")
            platform = _text(signal.get("platform"), f"{signal_label}.platform", 100)
            chart_name = _text(signal.get("chart_name"), f"{signal_label}.chart_name", 200)
            chart_period = _text(signal.get("chart_period"), f"{signal_label}.chart_period", 100)
            snapshot_key = (platform.casefold(), chart_name.casefold(), chart_period.casefold(), observed.isoformat())
            if snapshot_key in snapshot_keys:
                raise NovelCandidatePoolError(f"{signal_label} duplicates a platform/chart snapshot")
            snapshot_keys.add(snapshot_key)
            normalized_signals.append({
                "platform": platform,
                "chart_name": chart_name,
                "chart_period": chart_period,
                "observed_at": observed.isoformat(),
                "rank": rank,
                "chart_size": chart_size,
                "rank_note": _text(signal["rank_note"], f"{signal_label}.rank_note", 500) if signal.get("rank_note") else None,
                "evidence_note": _text(signal["evidence_note"], f"{signal_label}.evidence_note", 500) if signal.get("evidence_note") else None,
                "metric_name": _text(signal["metric_name"], f"{signal_label}.metric_name", 100) if signal.get("metric_name") else None,
                "metric_value": metric_value,
                "metric_unit": _text(signal["metric_unit"], f"{signal_label}.metric_unit", 100) if signal.get("metric_unit") else None,
                "source_url": _url(signal.get("source_url"), f"{signal_label}.source_url"),
            })
        pool_topic = _text(raw.get("pool_topic", title), f"{label}.pool_topic", 200)
        candidates.append({
            "candidate_id": candidate_id,
            "title": title,
            "author": _text(raw.get("author"), f"{label}.author", 200),
            "genre": _text(raw.get("genre"), f"{label}.genre", 200),
            "work_status": status,
            "platform_signals": normalized_signals,
            "adaptation_source": normalized_source,
            "rights": {
                "status": rights_status,
                "basis": _text(rights.get("basis"), f"{label}.rights.basis", 1000),
                "evidence_urls": normalized_evidence,
            },
            "pool_topic": pool_topic,
        })
    return {"schema_version": 1, "snapshot_date": snapshot_date.isoformat(), "candidates": candidates}


def build_novel_candidate_pool(catalog: Any) -> dict[str, Any]:
    normalized_catalog = validate_catalog(catalog)
    pool_date = date.fromisoformat(normalized_catalog["snapshot_date"])
    raw_signals: list[dict[str, Any]] = []
    for candidate in normalized_catalog["candidates"]:
        for index, signal in enumerate(candidate["platform_signals"]):
            rank, chart_size = signal["rank"], signal["chart_size"]
            # Counts and ambiguous page records remain in the catalog but are
            # not converted into a score with a different unit.
            if rank is None or chart_size is None:
                continue
            raw_signals.append({
                "signal_id": f"{candidate['candidate_id']}-PS{index:02d}",
                "topic": candidate["pool_topic"],
                "title": f"{candidate['title']} ranked {rank}/{chart_size}",
                "source_name": f"{signal['platform']} · {signal['chart_name']} · {signal['chart_period']}",
                "observed_at": f"{signal['observed_at']}T00:00:00Z",
                "strength": round(100 * (chart_size - rank + 1) / chart_size),
                "summary": f"Rank percentile within this chart: {rank}/{chart_size}",
                "url": signal["source_url"],
            })
    trend_artifact = discover_trends(
        [_RankSnapshotSource(raw_signals)],
        run_date=pool_date.isoformat(),
    )
    topic_pool = build_topic_pool(trend_artifact, as_of=pool_date.isoformat())
    pool_rows = topic_pool["candidates"]
    by_topic: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(pool_rows):
        if not isinstance(row, dict):
            raise NovelCandidatePoolError(f"topic_pool.candidates[{index}] must be an object")
        topic = _text(row.get("topic"), f"topic_pool.candidates[{index}].topic", 300)
        score, rank = row.get("discovery_score"), row.get("rank")
        if type(score) is not int or not 0 <= score <= 100 or type(rank) is not int or rank < 1:
            raise NovelCandidatePoolError(f"topic_pool.candidates[{index}] has invalid score or rank")
        key = normalize_topic(topic)
        if key in by_topic:
            raise NovelCandidatePoolError(f"topic pool contains duplicate normalized topic: {topic}")
        by_topic[key] = row

    candidates = []
    for candidate in normalized_catalog["candidates"]:
        topic_row = by_topic.get(normalize_topic(candidate["pool_topic"]))
        rights_status = candidate["rights"]["status"]
        if rights_status in RIGHTS_CAN_PASS:
            rights_gate = "PASS_METADATA_ONLY"
        elif rights_status == "not_available":
            rights_gate = "BLOCKED_NOT_AVAILABLE"
        else:
            rights_gate = "BLOCKED_UNVERIFIED_RIGHTS"
        candidates.append({
            **candidate,
            "topic_pool_match": topic_row is not None,
            "topic_pool_rank": topic_row["rank"] if topic_row else None,
            "topic_discovery_score": topic_row["discovery_score"] if topic_row else None,
            "trend_signal_refs": [item["signal_id"] for item in topic_row["supporting_signals"]] if topic_row else [],
            "topic_pool_review_status": topic_row.get("review_status") if topic_row else "not_in_auto_topic_pool",
            "rights_gate": rights_gate,
            "eligible_for_human_adaptation_review": topic_row is not None and rights_gate == "PASS_METADATA_ONLY",
            "main_ip_selected": False,
            "production_eligible": False,
            "publication_allowed": False,
        })
    candidates.sort(key=lambda item: (item["topic_pool_rank"] is None, item["topic_pool_rank"] or 0, item["candidate_id"]))
    review_ids = [item["candidate_id"] for item in candidates if item["eligible_for_human_adaptation_review"]]
    platforms = sorted({signal["platform"] for candidate in candidates for signal in candidate["platform_signals"]})
    return {
        "schema_version": 1,
        "date": pool_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "candidate_count": len(candidates),
        "platform_count": len(platforms),
        "platforms": platforms,
        "topic_pool_match_count": sum(item["topic_pool_match"] for item in candidates),
        "rights_blocked_count": sum(item["rights_gate"].startswith("BLOCKED") for item in candidates),
        "human_adaptation_review_candidates": review_ids,
        "main_ip_selected": False,
        "production_eligible": False,
        "publication_allowed": False,
        "scoring_policy": "Uses the P16 discovery pool on rank percentiles only. Raw counts and ambiguous ranks remain visible but do not enter its numeric score; original platform, chart, rank, period, and URL stay attached for review.",
        "candidates": candidates,
        "trend_discovery": trend_artifact,
        "topic_pool": topic_pool,
    }


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelCandidatePoolError(f"cannot read {label} {path}: {error}") from error


def _markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# 小说候选池（{payload['date']}）",
        "",
        f"共 {payload['candidate_count']} 部；覆盖 {payload['platform_count']} 个平台；其中 {payload['topic_pool_match_count']} 部进入 P16 自动选题池，{payload['rights_blocked_count']} 部因权利未知或不可用被拦截。",
        "",
        "| P16 排名 | 作品 | 榜单信号 | 权利状态 | 改编门 |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for item in payload["candidates"]:
        signals = []
        for signal in item["platform_signals"]:
            if signal["rank"] is not None:
                measure = f"第 {signal['rank']}/{signal['chart_size']} 名"
            elif signal["metric_value"] is not None:
                measure = f"{signal['metric_name'] or '指标'} {signal['metric_value']} {signal['metric_unit'] or ''}".strip()
            else:
                measure = "无"
            signals.append(f"{signal['platform']} {signal['chart_name']} {signal['chart_period']}：{measure}")
        rank = str(item["topic_pool_rank"]) if item["topic_pool_rank"] is not None else "—"
        lines.append(
            f"| {rank} | {item['title']} | {'；'.join(signals) or '无热度快照'} | "
            f"{item['rights']['status']} | {item['rights_gate']} |"
        )
    lines.extend([
        "",
        "P16 分数综合榜单内名次百分位、更新时间和信号类别；阅读人数等原始值不参与跨榜单数值合并。权利状态未知的作品不能进入改编流程。此池不自动选择主 IP、制作或发布。",
        "",
    ])
    return "\n".join(lines)


def write_pool(output_dir: Path, payload: dict[str, Any]) -> Path:
    target = Path(output_dir).expanduser().resolve()
    if target.exists():
        raise NovelCandidatePoolError(f"refusing to overwrite existing output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        artifacts = {
            "trend-discovery.json": payload["trend_discovery"],
            "topic-pool.json": payload["topic_pool"],
            "novel-candidate-pool.json": {key: value for key, value in payload.items() if key not in {"trend_discovery", "topic_pool"}},
        }
        for name, artifact in artifacts.items():
            (staging / name).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / "novel-candidate-pool.md").write_text(_markdown_report(payload), encoding="utf-8")
        os.rename(staging, target)
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target / "novel-candidate-pool.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_catalog", type=Path, help="reviewed novel candidate catalog JSON")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_novel_candidate_pool(_read_json(args.candidate_catalog, "novel candidate catalog"))
        output = write_pool(args.output_dir, result)
    except (OSError, NovelCandidatePoolError) as error:
        print(f"novel-candidate-pool: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "READY_FOR_HUMAN_REVIEW", "output": str(output), **{key: result[key] for key in ("candidate_count", "platform_count", "topic_pool_match_count", "rights_blocked_count", "human_adaptation_review_candidates")}}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
