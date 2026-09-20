#!/usr/bin/env python3
"""Import authorized local novel text into chapter indexes and extraction candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.story_extraction import ChapterText, LocalLexiconExtractor, StoryExtractionError  # noqa: E402
from scripts.novel_anime_project import MANIFEST_NAME, NovelAnimeProjectError, load_project, replace_project, utc_timestamp, validate_project  # noqa: E402
from scripts.novel_anime_repository import NovelAnimeRepository  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, NovelSourceCatalogError, load_catalog, replace_catalog, validate_catalog  # noqa: E402


MAX_SOURCE_BYTES = 20 * 1024 * 1024
CHAPTER_HEADING = re.compile(r"^\s*(第[〇零一二两三四五六七八九十百千万\d]+[回章节卷](?:[　\s]+[^\r\n]+)?)\s*$")


class NovelSourceIngestError(RuntimeError):
    """Raised when source authorization, parsing, or persistence fails."""


GENERIC_CHARACTER_TERMS = {
    "男人", "女人", "男子", "女子", "少年", "少女", "青年", "老人", "老者", "孩子", "小孩",
    "父亲", "母亲", "父母", "师父", "师傅", "先生", "夫人", "姑娘", "公子", "小姐", "掌柜",
    "众人", "两人", "三人", "一人", "那人", "此人", "对方", "自己", "时候", "片刻",
}
SPEECH_SUFFIX = (
    "说道", "说", "问道", "问", "答道", "答", "喊道", "喊", "叫道", "叫",
    "笑道", "叹道", "喝道", "低声道", "轻声道", "沉声道", "冷声道",
)
SPEAKER_PATTERNS = (
    re.compile(r"(?:^|[。！？!?；;，,、“”‘’\s])([\u4e00-\u9fff]{2,4})(?=[：:][“\"‘'])"),
    re.compile(
        r"(?:^|[。！？!?；;，,、“”‘’\s])([\u4e00-\u9fff]{2,4})(?="
        + "|".join(re.escape(item) for item in sorted(SPEECH_SUFFIX, key=len, reverse=True))
        + r")"
    ),
)

ACTION_SUFFIX = (
    "抬头", "低头", "回头", "转身", "起身", "坐下", "站起", "站住",
    "走来", "走去", "走进", "走出", "上前", "退后", "停下", "离开", "来到",
    "看向", "望向", "盯着", "看着", "望着", "凝视", "打量",
    "点头", "摇头", "皱眉", "挑眉", "闭眼", "睁眼",
    "伸手", "抬手", "收手", "握住", "抓住", "接过", "推开", "拉住", "抱住", "扶住",
    "笑了", "笑道", "轻笑", "冷笑", "苦笑", "叹息", "沉默", "开口",
    "问道", "说道", "答道", "喊道", "叫道", "喝道",
)
ACTION_PATTERN = re.compile(
    r"(?:^|[。！？!?；;，,、“”‘’\s])"
    r"(?:只见|忽见|此时|这时|随后|片刻后|转眼间)?"
    r"([\u4e00-\u9fff]{2,4})"
    r"(?=(?:缓缓|忽然|突然|随即|便|却|又|正|仍|只是)?(?:"
    + "|".join(re.escape(item) for item in sorted(ACTION_SUFFIX, key=len, reverse=True))
    + r"))"
)
VOCATIVE_PATTERN = re.compile(r"[“\"‘]([\u4e00-\u9fff]{2,4})(?=[，,！!？?…])")
GENERIC_CHARACTER_SUFFIXES = ("男子", "女子", "少年", "少女", "老人", "老者", "孩子", "小孩", "众人")
GENERIC_NAME_FRAGMENTS = {
    "只见", "忽见", "此时", "这时", "随后", "片刻", "眼前", "身后", "门外", "屋内",
    "一个", "一名", "那名", "这名", "那位", "这位", "对面", "旁边", "终于", "忽然",
    "突然", "缓缓", "轻轻", "慢慢", "微微", "顿时", "立刻", "马上", "已经", "似乎",
}


def infer_character_lexicon(chapters: tuple[ChapterText, ...], ip_code: str, *, limit: int = 16) -> list[dict[str, Any]]:
    """Infer conservative Chinese character candidates without storing prose.

    Strong dialogue attribution remains the highest-confidence signal.  To
    support narration-heavy web novels, repeated 2–4 Han-character subjects
    before character actions and quoted vocatives are also scored.  A
    candidate must still recur in the source, keeping this deliberately more
    conservative than general-purpose Chinese NER.
    """

    def plausible(name: str) -> bool:
        name = str(name or "").strip()
        if not 2 <= len(name) <= 4:
            return False
        if name in GENERIC_CHARACTER_TERMS:
            return False
        if any(name.endswith(suffix) for suffix in GENERIC_CHARACTER_SUFFIXES):
            return False
        if any(fragment in name for fragment in GENERIC_NAME_FRAGMENTS):
            return False
        if any(token in name for token in ("这个", "那个", "什么", "怎么", "已经", "没有", "只是", "然后")):
            return False
        return bool(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name))

    scores: dict[str, dict[str, int]] = {}

    def hit(name: str, kind: str, position: int) -> None:
        if not plausible(name):
            return
        item = scores.setdefault(
            name,
            {"speaker_hits": 0, "action_hits": 0, "vocative_hits": 0, "first": position},
        )
        item[kind] += 1
        item["first"] = min(item["first"], position)

    for chapter_index, chapter in enumerate(chapters):
        text = chapter.text
        offset = chapter_index * 10_000_000
        for pattern in SPEAKER_PATTERNS:
            for match in pattern.finditer(text):
                hit(match.group(1), "speaker_hits", offset + match.start())
        for match in ACTION_PATTERN.finditer(text):
            hit(match.group(1), "action_hits", offset + match.start())
        for match in VOCATIVE_PATTERN.finditer(text):
            hit(match.group(1), "vocative_hits", offset + match.start())

    ranked: list[tuple[str, int, int, int, int, int]] = []
    for name, item in scores.items():
        total_mentions = sum(chapter.text.count(name) for chapter in chapters)
        speaker_hits = int(item["speaker_hits"])
        action_hits = int(item["action_hits"])
        vocative_hits = int(item["vocative_hits"])
        strong_contexts = speaker_hits + action_hits + vocative_hits
        if total_mentions < 2:
            continue
        if speaker_hits < 1 and vocative_hits < 1 and action_hits < 2:
            continue
        score = speaker_hits * 8 + vocative_hits * 6 + action_hits * 3 + min(total_mentions, 20)
        ranked.append((name, score, speaker_hits, action_hits, vocative_hits, int(item["first"])))

    ranked.sort(key=lambda item: (-item[1], -item[2], -item[3], -item[4], item[5], item[0]))

    return [
        {
            "id": f"CHR-{ip_code}-AUTO-{index:03d}",
            "name": name,
            "aliases": [],
        }
        for index, (name, _score, _speaker_hits, _action_hits, _vocative_hits, _first)
        in enumerate(ranked[: max(1, int(limit))], start=1)
    ]


def extract_character_candidates_from_text(source_text: str, ip_code: str) -> dict[str, Any]:
    raw_text = str(source_text or "")
    source_bytes = raw_text.encode("utf-8")
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise NovelSourceIngestError(f"source text exceeds {MAX_SOURCE_BYTES // (1024 * 1024)} MB")
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise NovelSourceIngestError("source text is empty")
    chapters = split_chapters(normalized, ip_code)
    lexicon = {
        "characters": infer_character_lexicon(chapters, ip_code),
        "locations": [],
        "props": [],
    }
    try:
        extraction = LocalLexiconExtractor().extract(chapters, lexicon)
    except StoryExtractionError as error:
        raise NovelSourceIngestError(str(error)) from error
    return {
        "source_sha256": _sha256_bytes(source_bytes),
        "chapter_count": len(chapters),
        "provider": extraction.provider,
        "characters": list(extraction.characters),
    }

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_source(path: Path) -> tuple[str, bytes]:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise NovelSourceIngestError(f"source file does not exist: {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_SOURCE_BYTES:
        raise NovelSourceIngestError(f"source file must be between 1 byte and {MAX_SOURCE_BYTES} bytes")
    data = path.read_bytes()
    if b"\x00" in data:
        raise NovelSourceIngestError("source file must be plain UTF-8 text")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NovelSourceIngestError("source file must use UTF-8") from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise NovelSourceIngestError("source text is empty")
    return normalized, data


def split_chapters(text: str, ip_code: str) -> tuple[ChapterText, ...]:
    lines = text.splitlines()
    headings = [(index, match.group(1).strip()) for index, line in enumerate(lines) if (match := CHAPTER_HEADING.fullmatch(line))]
    chapters: list[ChapterText] = []
    if not headings:
        chapters.append(ChapterText(f"CH-{ip_code}-0001", "全文", text.strip(), 1, len(lines)))
        return tuple(chapters)
    for position, (line_index, title) in enumerate(headings, start=1):
        next_index = headings[position][0] if position < len(headings) else len(lines)
        body = "\n".join(lines[line_index + 1:next_index]).strip()
        if not body:
            raise NovelSourceIngestError(f"chapter has no body text: {title}")
        # line_index is zero-based and the body begins on the line after the
        # heading, so its one-based source line is line_index + 2.
        chapters.append(ChapterText(f"CH-{ip_code}-{position:04d}", title, body, line_index + 2, next_index))
    return tuple(chapters)


def _assign_chapter_ids(chapters: tuple[ChapterText, ...], catalog: dict[str, Any], edition_id: str, ip_code: str) -> tuple[ChapterText, ...]:
    existing = {chapter["sequence"]: chapter["id"] for chapter in catalog["chapters"] if chapter["edition_id"] == edition_id}
    used_numbers = [int(str(chapter["id"]).rsplit("-", 1)[1]) for chapter in catalog["chapters"]]
    next_number = max(used_numbers, default=0) + 1
    assigned = []
    for sequence, chapter in enumerate(chapters, start=1):
        chapter_id = existing.get(sequence)
        if chapter_id is None:
            chapter_id = f"CH-{ip_code}-{next_number:04d}"
            next_number += 1
        assigned.append(ChapterText(chapter_id, chapter.title, chapter.text, chapter.line_start, chapter.line_end))
    return tuple(assigned)


def _load_lexicon(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"characters": [], "locations": [], "props": []}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelSourceIngestError(f"cannot read extraction lexicon: {error}") from error
    if not isinstance(payload, dict):
        raise NovelSourceIngestError("extraction lexicon must be a JSON object")
    return payload


def _atomic_json(path: Path, payload: dict[str, Any], *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise NovelSourceIngestError(f"refusing to overwrite source import: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=".source-import.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _authorize(catalog: dict[str, Any], edition: dict[str, Any], *, authorization_confirmed: bool, test_only: bool) -> None:
    if test_only:
        if catalog["adaptation_policy"]["local_technical_test_allowed"] is not True:
            raise NovelSourceIngestError("catalog does not allow local technical tests")
        return
    if authorization_confirmed is not True:
        raise NovelSourceIngestError("authorized source import requires authorization_confirmed=true")
    if edition["rights_status"] not in {"PUBLIC_DOMAIN_VERIFIED", "LICENSED"}:
        raise NovelSourceIngestError("source edition is not verified for import")
    if catalog["adaptation_policy"]["script_adaptation_allowed"] is not True:
        raise NovelSourceIngestError("source catalog does not allow script adaptation")
    if catalog["rights_assessment"]["human_review"]["status"] != "APPROVED":
        raise NovelSourceIngestError("source rights require approved human review")


def _sync_core_manifest(project_dir: Path, catalog: dict[str, Any], edition: dict[str, Any]) -> None:
    project = load_project(project_dir / MANIFEST_NAME)
    review = catalog["rights_assessment"]["human_review"]
    core_edition = {
        "id": edition["id"], "title": edition["title"], "revision": catalog["revision"],
        "status": "SOURCE_READY", "input_refs": [],
        "source_refs": [evidence["id"] for evidence in catalog["rights_assessment"]["evidence"]],
        "provider": None,
        "human_review": {"required": True, "status": review["status"], "reviewed_at": review["reviewed_at"], "reviewed_by": review["reviewed_by"]},
        "edition_label": edition["edition_label"], "source_url": edition["source_url"],
        "rights_status": edition["rights_status"], "chapter_ids": list(edition["chapter_ids"]),
    }
    project["source_editions"] = [item for item in project["source_editions"] if item["id"] != edition["id"]] + [core_edition]
    project["ip"]["source_edition_ids"] = sorted({*project["ip"]["source_edition_ids"], edition["id"]})
    project["revision"] += 1
    project["updated_at"] = utc_timestamp()
    replace_project(project_dir, validate_project(project))
    repository = NovelAnimeRepository(project_dir)
    if repository.db_path.is_file():
        repository.sync_manifest()


def ingest_source(project_dir: Path, edition_id: str, source_file: Path, *, lexicon_file: Path | None = None, authorization_confirmed: bool = False, test_only: bool = False) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    catalog = load_catalog(project_dir / CATALOG_RELATIVE_PATH)
    edition = next((item for item in catalog["editions"] if item["id"] == edition_id), None)
    if edition is None:
        raise NovelSourceIngestError(f"source edition is not registered: {edition_id}")
    _authorize(catalog, edition, authorization_confirmed=authorization_confirmed, test_only=test_only)
    source_text, source_bytes = _read_source(source_file)
    ip_code = catalog["ip_id"].removeprefix("IP-")
    chapters = _assign_chapter_ids(split_chapters(source_text, ip_code), catalog, edition_id, ip_code)
    lexicon = _load_lexicon(lexicon_file)
    if not lexicon.get("characters"):
        lexicon["characters"] = infer_character_lexicon(chapters, ip_code)
    try:
        extraction = LocalLexiconExtractor().extract(chapters, lexicon)
    except StoryExtractionError as error:
        raise NovelSourceIngestError(str(error)) from error
    import_id = f"IMP-{edition_id}-{_sha256_bytes(source_bytes)[:12].upper()}"
    import_payload = {
        "schema_version": 1,
        "import_id": import_id,
        "project_id": catalog["project_id"],
        "ip_id": catalog["ip_id"],
        "edition_id": edition_id,
        "source_file_name": Path(source_file).name,
        "source_sha256": _sha256_bytes(source_bytes),
        "source_bytes": len(source_bytes),
        "full_text_stored": False,
        "test_only": test_only,
        "authorization_confirmed": authorization_confirmed,
        "created_at": utc_timestamp(),
        "chapters": [{
            "chapter_id": chapter.chapter_id,
            "title": chapter.title,
            "sequence": index,
            "line_start": chapter.line_start,
            "line_end": chapter.line_end,
            "character_count": len(chapter.text),
            "text_sha256": hashlib.sha256(chapter.text.encode("utf-8")).hexdigest(),
        } for index, chapter in enumerate(chapters, start=1)],
        "extraction": {
            "provider": extraction.provider,
            "characters": list(extraction.characters),
            "locations": list(extraction.locations),
            "props": list(extraction.props),
            "events": list(extraction.events),
        },
        "human_review_required": True,
    }
    suffix = "-test" if test_only else ""
    output = project_dir / "sources" / "imports" / f"{import_id.lower()}{suffix}.json"
    _atomic_json(output, import_payload)
    if not test_only:
        old_chapters = [chapter for chapter in catalog["chapters"] if chapter["edition_id"] == edition_id]
        old_chapter_ids = {chapter["id"] for chapter in old_chapters}
        old_locator_by_sequence = {
            chapter["sequence"]: chapter["locator_ids"][0]
            for chapter in old_chapters
            if chapter.get("locator_ids")
        }
        used_locator_numbers = [int(str(locator["id"]).rsplit("-", 1)[1]) for locator in catalog["locators"]]
        next_locator_number = max(used_locator_numbers, default=0) + 1
        catalog["chapters"] = [chapter for chapter in catalog["chapters"] if chapter["edition_id"] != edition_id]
        catalog["locators"] = [locator for locator in catalog["locators"] if locator["chapter_id"] not in old_chapter_ids]
        edition["chapter_ids"] = [chapter.chapter_id for chapter in chapters]
        for index, chapter in enumerate(chapters, start=1):
            locator_id = old_locator_by_sequence.get(index)
            if locator_id is None:
                locator_id = f"LOC-{ip_code}-{next_locator_number:04d}"
                next_locator_number += 1
            catalog["chapters"].append({"id": chapter.chapter_id, "edition_id": edition_id, "sequence": index, "title": chapter.title, "volume": None, "locator_ids": [locator_id]})
            catalog["locators"].append({
                "id": locator_id, "chapter_id": chapter.chapter_id,
                "source_url": f"{edition['source_url']}#{chapter.chapter_id.lower()}",
                "location": {"page_start": None, "page_end": None, "paragraph_start": chapter.line_start, "paragraph_end": chapter.line_end, "label": chapter.title},
                "excerpt_sha256": None, "text_storage_allowed": False,
            })
        catalog["revision"] += 1
        catalog["updated_at"] = utc_timestamp()
        catalog = validate_catalog(catalog)
        replace_catalog(project_dir, catalog)
        _sync_core_manifest(project_dir, catalog, edition)
    return {
        "import_id": import_id,
        "output": output.relative_to(project_dir).as_posix(),
        "chapter_count": len(chapters),
        "character_candidates": len(extraction.characters),
        "location_candidates": len(extraction.locations),
        "prop_candidates": len(extraction.props),
        "event_candidates": len(extraction.events),
        "full_text_stored": False,
        "test_only": test_only,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--edition-id", required=True)
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--lexicon-file", type=Path)
    parser.add_argument("--authorization-confirmed", action="store_true")
    parser.add_argument("--test-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = ingest_source(args.project_dir, args.edition_id, args.source_file, lexicon_file=args.lexicon_file, authorization_confirmed=args.authorization_confirmed, test_only=args.test_only)
    except (NovelSourceIngestError, NovelSourceCatalogError, NovelAnimeProjectError, OSError) as error:
        print(f"novel_source_ingest: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
