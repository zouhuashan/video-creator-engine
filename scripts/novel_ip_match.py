#!/usr/bin/env python3
"""Match public-domain literary works to reviewed novel-market topic signals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "validation" / "classic-ip-catalog.json"
DEFAULT_SNAPSHOTS = ROOT / "validation" / "rank-snapshot-coverage.json"
RIGHTS_SHORTLIST_STATUS = "pass_for_human_decision"
PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")


class NovelIpMatchError(ValueError):
    """Raised when market or literary-rights evidence is incomplete or invalid."""


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelIpMatchError(f"cannot read {label} {path}: {error}") from error


def _period_index(value: str, unit: str) -> int | None:
    match = PERIOD_RE.fullmatch(value)
    if not match:
        return None
    year, month, day = (int(group) if group else None for group in match.groups())
    if month is None or month < 1 or month > 12:
        return None
    if unit == "calendar_month" and day is None:
        return year * 12 + month
    if unit == "day" and day is not None:
        try:
            return date(year, month, day).toordinal()
        except ValueError:
            return None
    return None


def longest_consecutive_snapshot_run(platform: dict[str, Any]) -> int:
    """Count only adjacent periods in the same documented chart scope."""
    unit = platform.get("period_unit")
    by_scope: dict[str, list[int]] = {}
    for snapshot in platform.get("snapshots", []):
        period = snapshot.get("period")
        scope = snapshot.get("scope_id")
        index = _period_index(period, unit) if isinstance(period, str) else None
        if isinstance(scope, str) and index is not None:
            by_scope.setdefault(scope, []).append(index)
    longest = 0
    for indexes in by_scope.values():
        run = 0
        previous: int | None = None
        for index in sorted(set(indexes)):
            run = run + 1 if previous is not None and index == previous + 1 else 1
            longest = max(longest, run)
            previous = index
    return longest


def analyze_snapshot_coverage(snapshot_artifact: Any) -> dict[str, Any]:
    if not isinstance(snapshot_artifact, dict) or snapshot_artifact.get("schema_version") != 1:
        raise NovelIpMatchError("unsupported rank snapshot coverage schema")
    required = snapshot_artifact.get("required_consecutive_periods_per_platform")
    platforms = snapshot_artifact.get("platforms")
    if type(required) is not int or required < 1 or not isinstance(platforms, list) or not platforms:
        raise NovelIpMatchError("rank snapshot coverage must define platforms and a positive period requirement")
    results = []
    for platform in platforms:
        if not isinstance(platform, dict) or not isinstance(platform.get("snapshots"), list):
            raise NovelIpMatchError("each platform must contain a snapshots list")
        run = longest_consecutive_snapshot_run(platform)
        results.append({
            "platform": platform.get("platform", "unknown"),
            "longest_consecutive_periods": run,
            "required_consecutive_periods": required,
            "complete": run >= required,
            "chart_family": platform.get("chart_family"),
            "limitation": platform.get("limitation"),
        })
    return {
        "complete": all(item["complete"] for item in results),
        "platforms": results,
        "note": "Only identical chart-scope IDs count as a longitudinal series.",
    }


def _validate_work(work: Any, territory: str, research_date: date) -> dict[str, Any]:
    if not isinstance(work, dict):
        raise NovelIpMatchError("classic IP records must be objects")
    required_fields = ("work_id", "title", "author")
    if any(not work.get(field) for field in required_fields):
        raise NovelIpMatchError(f"classic IP {work.get('work_id', 'unknown')} is missing source or rights evidence")
    year = work.get("author_death_year")
    if type(year) is not int and year is not None:
        raise NovelIpMatchError(f"classic IP {work['work_id']} author_death_year must be an integer or null")
    if work.get("territory") != territory:
        raise NovelIpMatchError(f"classic IP {work['work_id']} rights territory does not match catalog target")
    rights_pass = (
        year is not None
        and year + 50 < research_date.year
        and work.get("rights_gate") == RIGHTS_SHORTLIST_STATUS
        and work.get("shortlist_eligible") is True
        and bool(work.get("rights_evidence_urls"))
    )
    if work.get("shortlist_eligible") and not rights_pass:
        raise NovelIpMatchError(f"classic IP {work['work_id']} claims shortlist eligibility without passing the rights gate")
    if not isinstance(work.get("rights_evidence_urls", []), list):
        raise NovelIpMatchError(f"classic IP {work['work_id']} rights_evidence_urls must be a list")
    if work.get("shortlist_eligible") and (not work.get("source_edition") or not work.get("edition_source_url")):
        raise NovelIpMatchError(f"classic IP {work['work_id']} lacks its specific source edition")
    fit = work.get("format_fit")
    if not isinstance(fit, dict) or any(type(fit.get(key)) is not int or not 1 <= fit[key] <= 5 for key in (
        "continuous_arc", "episode_hooks", "visual_worldbuilding", "adaptation_crowding_risk"
    )):
        raise NovelIpMatchError(f"classic IP {work['work_id']} format_fit must use 1-5 integer ratings")
    alignments = work.get("topic_alignments", {})
    if not isinstance(alignments, dict) or any(value not in {"direct", "adjacent", "none"} for value in alignments.values()):
        raise NovelIpMatchError(f"classic IP {work['work_id']} has invalid topic alignment")
    return {**work, "rights_pass_for_shortlist": rights_pass}


def build_match_report(topic_pool: Any, catalog: Any, snapshot_artifact: Any) -> dict[str, Any]:
    if not isinstance(topic_pool, dict) or topic_pool.get("schema_version") != 1 or not isinstance(topic_pool.get("candidates"), list):
        raise NovelIpMatchError("topic pool must be a schema version 1 artifact")
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1 or not isinstance(catalog.get("works"), list):
        raise NovelIpMatchError("classic IP catalog must be a schema version 1 artifact")
    try:
        as_of = date.fromisoformat(catalog["research_date"])
    except (KeyError, TypeError, ValueError) as error:
        raise NovelIpMatchError("classic IP catalog research_date must use YYYY-MM-DD") from error
    territory = catalog.get("target_territory")
    if not isinstance(territory, str) or not territory:
        raise NovelIpMatchError("classic IP catalog must set target_territory")

    snapshot_coverage = analyze_snapshot_coverage(snapshot_artifact)
    signal_tags = sorted({
        tag
        for signal in catalog.get("market_signals", [])
        if isinstance(signal, dict)
        for tag in signal.get("trend_tags", [])
        if isinstance(tag, str)
    })
    if not signal_tags:
        raise NovelIpMatchError("catalog must contain at least one normalized market trend tag")
    market_evidence = [
        {
            "platform": signal.get("platform"),
            "period": signal.get("period"),
            "genre_signal": signal.get("genre_signal"),
            "evidence_level": signal.get("evidence_level"),
            "source_url": signal.get("source_url"),
            **({"genre_source_url": signal["genre_source_url"]} if signal.get("genre_source_url") else {}),
        }
        for signal in catalog.get("market_signals", [])
        if isinstance(signal, dict)
    ]
    source_topics = [item.get("topic") for item in topic_pool["candidates"] if isinstance(item, dict) and isinstance(item.get("topic"), str)]
    if not source_topics:
        raise NovelIpMatchError("topic pool contains no reviewable topics")

    ranked = []
    excluded = []
    for raw_work in catalog["works"]:
        work = _validate_work(raw_work, territory, as_of)
        alignments = work.get("topic_alignments", {})
        direct = sum(1 for tag in signal_tags if alignments.get(tag) == "direct")
        adjacent = sum(1 for tag in signal_tags if alignments.get(tag) == "adjacent")
        topic_fit = min(5, direct * 2 + adjacent)
        fit = work["format_fit"]
        score = (
            topic_fit * 2
            + fit["continuous_arc"]
            + fit["episode_hooks"]
            + fit["visual_worldbuilding"]
            - fit["adaptation_crowding_risk"]
        )
        entry = {
            "work_id": work["work_id"],
            "title": work["title"],
            "rights_pass_for_shortlist": work["rights_pass_for_shortlist"],
            "shortlist_eligible": work["shortlist_eligible"],
            "topic_fit_score": topic_fit,
            "direct_signal_matches": direct,
            "adjacent_signal_matches": adjacent,
            "format_fit": fit,
            "review_priority_score": score,
            "match_inference": work.get("match_inference", ""),
            "source_edition": work.get("source_edition", "底本未核验"),
            "edition_source_url": work.get("edition_source_url"),
            "rights_evidence_urls": work["rights_evidence_urls"],
            "known_expression_risks": work.get("known_expression_risks", []),
            "adaptation_risk_evidence_urls": work.get("adaptation_risk_evidence_urls", []),
            "preproduction_scan_match_required": work.get("preproduction_scan_match_required", True),
            "production_allowed": False,
        }
        (ranked if work["rights_pass_for_shortlist"] else excluded).append(entry)
    ranked.sort(key=lambda item: (-item["review_priority_score"], item["work_id"]))
    excluded.sort(key=lambda item: item["work_id"])
    return {
        "schema_version": 1,
        "research_date": as_of.isoformat(),
        "target_territory": territory,
        "market_source_artifact_date": topic_pool.get("date"),
        "market_topic_sample": source_topics[:10],
        "normalized_market_tags": signal_tags,
        "market_signal_evidence": market_evidence,
        "matching_policy": {
            "type": "human_review_priority_only",
            "formula": "2*topic_fit_score + continuous_arc + episode_hooks + visual_worldbuilding - adaptation_crowding_risk",
            "score_range_note": "The score is a transparent editorial heuristic, not market prediction, legal advice, or automatic IP selection.",
            "topic_alignment_note": "Direct/adjacent tags are editorial inferences from chart genres and abstract topic patterns; no current novel's characters, plot sequence, or prose are reused.",
            "human_main_ip_decision_required": True,
            "production_allowed": False,
        },
        "snapshot_coverage": snapshot_coverage,
        "shortlist": ranked,
        "excluded_pending_rights_or_source_review": excluded,
        "recommended_for_human_discussion": ranked[0]["work_id"] if ranked else None,
        "main_ip_selected": None,
        "publication_allowed": False,
        "readiness": "ready_for_human_ip_decision" if snapshot_coverage["complete"] and ranked else "partial_snapshot_history_required",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# P17-03 公版原作与题材匹配（{report['research_date']}）",
        "",
        f"- 榜单连续快照验收：{'PASS' if report['snapshot_coverage']['complete'] else '未完成'}",
        f"- 主 IP 人工讨论建议：{report['recommended_for_human_discussion'] or '暂无'}",
        "- 主 IP 已定稿：否；制作与发布许可：否。",
        "- 匹配分仅用于人工排序；题材结构匹配是推断，不是热度对改编效果的直接证明。",
        "",
        "## 榜单快照",
        "",
        "| 平台 | 同口径连续期数 | 要求 | 状态 |",
        "|---|---:|---:|---|",
    ]
    for item in report["snapshot_coverage"]["platforms"]:
        lines.append(f"| {item['platform']}（{item.get('chart_family') or ''}） | {item['longest_consecutive_periods']} | {item['required_consecutive_periods']} | {'达标' if item['complete'] else '待补'} |")
    lines.extend(["", "## 热度信号与来源", "", "| 平台 | 期数 | 抽象题材信号 | 来源 |", "|---|---|---|---|"])
    for signal in report["market_signal_evidence"]:
        links = [f"[榜单]({signal['source_url']})"] if signal.get("source_url") else []
        if signal.get("genre_source_url"):
            links.append(f"[类型页]({signal['genre_source_url']})")
        lines.append(f"| {signal.get('platform', '')} | {signal.get('period', '')} | {signal.get('genre_signal', '')} | {' · '.join(links)} |")
    lines.extend(["", "## 人工决策短名单", "", "| 顺位 | 原作 | 题材匹配 | 连续剧情 | 分集钩子 | 视觉世界 | 后世表达拥挤风险 | 审阅分 |", "|---:|---|---:|---:|---:|---:|---:|---:|"])
    for rank, item in enumerate(report["shortlist"], 1):
        fit = item["format_fit"]
        lines.append(f"| {rank} | {item['title']} | {item['topic_fit_score']}/5 | {fit['continuous_arc']}/5 | {fit['episode_hooks']}/5 | {fit['visual_worldbuilding']}/5 | {fit['adaptation_crowding_risk']}/5 | {item['review_priority_score']} |")
    for item in report["shortlist"]:
        lines.extend(["", f"### {item['title']}", "", item["match_inference"], "", f"底本：{item['source_edition']} [来源]({item['edition_source_url']})。", "", "表达风险：" + "；".join(item["known_expression_risks"]), ""])
        risk_urls = item.get("adaptation_risk_evidence_urls", [])
        if risk_urls:
            lines.append("既有改编参考：" + "；".join(f"[来源 {number}]({url})" for number, url in enumerate(risk_urls, 1)) + "。")
            lines.append("")
    lines.extend([
        "## 下一步",
        "",
        "补齐番茄同一路由的第三个连续日榜快照，并在晋江取得连续三个同口径月榜快照；同时对入围作品的古籍扫描逐卷确认版本、注释层和后世表达边界。完成后再请人选定主 IP。",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic_pool", type=Path, help="P16 topic-pool JSON artifact")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "projects" / "p17-03")
    args = parser.parse_args(argv)
    try:
        report = build_match_report(
            _read_json(args.topic_pool, "topic pool"),
            _read_json(args.catalog, "classic IP catalog"),
            _read_json(args.snapshots, "rank snapshot coverage"),
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / "classic-ip-match.json"
        md_path = args.output_dir / "classic-ip-match.md"
        if json_path.exists() or md_path.exists():
            raise NovelIpMatchError(f"refusing to overwrite existing output in {args.output_dir}")
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
    except (OSError, NovelIpMatchError) as error:
        print(f"novel-ip-match: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "shortlist_count": len(report["shortlist"]),
        "recommended_for_human_discussion": report["recommended_for_human_discussion"],
        "snapshot_coverage_complete": report["snapshot_coverage"]["complete"],
        "readiness": report["readiness"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
