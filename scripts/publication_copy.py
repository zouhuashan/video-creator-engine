#!/usr/bin/env python3
"""Validate publication copy, score title candidates, and write Markdown artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "publication-copy.json"
TYPE_LABELS = {"search": "A · 搜索型", "conflict": "B · 冲突型", "result": "C · 结果型"}


class PublicationCopyError(ValueError):
    """Raised when publication copy cannot meet platform rules."""


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationCopyError(f"invalid publication copy config: {error}") from error
    if config.get("schema_version") != 1 or set(config.get("required_types", [])) != set(TYPE_LABELS):
        raise PublicationCopyError("unsupported publication copy config")
    return config


def _visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def validate_and_score(payload: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    active = config or load_config()
    if payload.get("schema_version") != 1 or not isinstance(payload.get("project_id"), str) or not payload["project_id"].strip():
        raise PublicationCopyError("publication copy requires schema_version 1 and project_id")
    keyword = payload.get("topic_keyword")
    if not isinstance(keyword, str) or not keyword.strip() or "\n" in keyword:
        raise PublicationCopyError("topic_keyword must be one non-empty line")
    keyword = keyword.strip()
    candidates = payload.get("candidates")
    count = active["candidate_count"]
    if not isinstance(candidates, list) or not count["min"] <= len(candidates) <= count["max"]:
        raise PublicationCopyError("publication copy requires 3-6 title candidates")
    required_fields = {"candidate_id", "type", "text"}
    ids, texts, types, scored = set(), set(), set(), []
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != required_fields:
            raise PublicationCopyError("each title candidate must contain exactly candidate_id, type, and text")
        candidate_id, kind, text = candidate["candidate_id"], candidate["type"], candidate["text"]
        if not isinstance(candidate_id, str) or not re.fullmatch(r"TITLE_[A-F]", candidate_id) or candidate_id in ids:
            raise PublicationCopyError("title IDs must be unique TITLE_A through TITLE_F")
        if kind not in TYPE_LABELS:
            raise PublicationCopyError(f"unknown title type: {kind}")
        if not isinstance(text, str) or "\n" in text:
            raise PublicationCopyError(f"title {candidate_id} must be one line")
        text = text.strip()
        length = _visible_length(text)
        if not active["title_characters"]["min"] <= length <= active["title_characters"]["max"]:
            raise PublicationCopyError(f"title {candidate_id} must contain 6-30 visible characters")
        if text.casefold() in texts:
            raise PublicationCopyError("title candidate text must be unique")
        if kind == "search" and keyword.casefold() not in text.casefold():
            raise PublicationCopyError("search title must contain the topic keyword")
        if kind == "conflict" and not any(pattern in text for pattern in active["conflict_patterns"]):
            raise PublicationCopyError("conflict title must express a clear tension or question")
        if kind == "result" and not any(pattern in text for pattern in active["result_patterns"]):
            raise PublicationCopyError("result title must signal a conclusion or outcome")
        hype = [term for term in active["forbidden_hype"] if term.casefold() in text.casefold()]
        if hype:
            raise PublicationCopyError(f"title {candidate_id} contains unsupported hype: {', '.join(hype)}")
        score_reasons = []
        score = 0
        if keyword.casefold() in text.casefold():
            score += 4
            score_reasons.append("包含主题关键词")
        if active["title_characters"]["preferred_min"] <= length <= active["title_characters"]["preferred_max"]:
            score += 3
            score_reasons.append("长度适合移动端")
        if kind == "conflict":
            score += 2
            score_reasons.append("问题冲突明确")
        elif kind == "result":
            score += 2
            score_reasons.append("结果承诺清晰")
        else:
            score += 2
            score_reasons.append("搜索意图清晰")
        if text.endswith(("？", "?")):
            score += 1
            score_reasons.append("疑问表达完整")
        scored.append({"candidate_id": candidate_id, "type": kind, "text": text, "score": score,
                       "score_reasons": score_reasons, "visible_characters": length})
        ids.add(candidate_id)
        texts.add(text.casefold())
        types.add(kind)
    missing_types = set(active["required_types"]) - types
    if missing_types:
        raise PublicationCopyError(f"title candidates are missing types: {', '.join(sorted(missing_types))}")
    caption = payload.get("caption")
    if not isinstance(caption, str) or "\n\n\n" in caption:
        raise PublicationCopyError("caption must be plain readable text")
    caption = caption.strip()
    caption_length = _visible_length(caption)
    if not active["caption_characters"]["min"] <= caption_length <= active["caption_characters"]["max"]:
        raise PublicationCopyError("caption must contain 20-500 visible characters")
    hashtags = payload.get("hashtags")
    tag_count = active["hashtag_count"]
    if not isinstance(hashtags, list) or not tag_count["min"] <= len(hashtags) <= tag_count["max"] or len(set(hashtags)) != len(hashtags):
        raise PublicationCopyError("hashtags must contain 3-8 unique values")
    for tag in hashtags:
        if not isinstance(tag, str) or not re.fullmatch(r"#[^#\s]+", tag):
            raise PublicationCopyError("each hashtag must begin with # and contain no spaces")
        length = _visible_length(tag[1:])
        if not active["hashtag_characters"]["min"] <= length <= active["hashtag_characters"]["max"]:
            raise PublicationCopyError("hashtag text must contain 2-15 visible characters")
    recommended = max(scored, key=lambda item: (item["score"], -scored.index(item)))
    return {"schema_version": 1, "project_id": payload["project_id"], "topic_keyword": keyword,
            "candidates": scored, "recommended": recommended["candidate_id"],
            "recommendation_reason": "；".join(recommended["score_reasons"]),
            "caption": caption, "hashtags": hashtags}


def _render_titles(result: dict[str, Any]) -> str:
    lines = ["# 标题候选", ""]
    for candidate in result["candidates"]:
        lines.extend([f"## {TYPE_LABELS[candidate['type']]}", "", candidate["text"], "",
                      f"- ID: `{candidate['candidate_id']}`", f"- 评分: {candidate['score']}",
                      f"- 依据: {'；'.join(candidate['score_reasons'])}", ""])
    selected = next(item for item in result["candidates"] if item["candidate_id"] == result["recommended"])
    lines.extend(["## 最终推荐", "", f"**{selected['text']}**", "", f"推荐理由：{result['recommendation_reason']}", ""])
    return "\n".join(lines)


def _write_all(directory: Path, files: dict[str, str]) -> None:
    if any((directory / name).exists() for name in files):
        raise PublicationCopyError("refusing to overwrite existing publication copy")
    temporaries: list[tuple[str, str]] = []
    try:
        for name, content in files.items():
            descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=directory)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(content)
            temporaries.append((temporary, str(directory / name)))
        for temporary, destination in temporaries:
            os.replace(temporary, destination)
    except Exception:
        for temporary, _ in temporaries:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        raise


def write_publication_copy(project_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    directory = Path(project_dir).resolve()
    result = validate_and_score(payload)
    if directory.name != result["project_id"]:
        raise PublicationCopyError("publication copy project_id must match the project directory")
    files = {
        "title.md": _render_titles(result),
        "caption.md": f"# 发布文案\n\n{result['caption']}\n",
        "hashtags.md": "# 标签\n\n" + " ".join(result["hashtags"]) + "\n",
        "publication-copy.json": json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    }
    _write_all(directory, files)
    return {"status": "PASS", "recommended": result["recommended"],
            "recommendation_reason": result["recommendation_reason"], "outputs": list(files)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--input-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input_file.read_text(encoding="utf-8"))
        result = write_publication_copy(args.project_dir, payload)
    except (OSError, json.JSONDecodeError, PublicationCopyError) as error:
        print(f"publication_copy: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
