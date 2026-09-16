"""Deterministic local entity mention and event-candidate extractor."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .base import ChapterText, ExtractionResult, StoryExtractionError, StoryExtractionProvider


ENTITY_GROUPS = ("characters", "locations", "props")
ACTION_MARKERS = ("去", "来", "走", "看", "说", "问", "答", "取", "放", "发现", "决定", "离开", "进入", "抵达", "寻找", "遇见")


class LocalLexiconExtractor(StoryExtractionProvider):
    name = "local_lexicon"
    remote_generation = False

    def extract(self, chapters: tuple[ChapterText, ...], lexicon: dict[str, Any]) -> ExtractionResult:
        if not chapters:
            raise StoryExtractionError("at least one chapter is required")
        normalized = self._validate_lexicon(lexicon)
        groups: dict[str, list[dict[str, Any]]] = {group: [] for group in ENTITY_GROUPS}
        events: list[dict[str, Any]] = []
        for group in ENTITY_GROUPS:
            for entity in normalized[group]:
                mentions = []
                terms = tuple(dict.fromkeys((entity["name"], *entity["aliases"])))
                for chapter in chapters:
                    count = sum(chapter.text.count(term) for term in terms)
                    if count:
                        mentions.append({"chapter_id": chapter.chapter_id, "count": count})
                groups[group].append({**entity, "mentions": mentions, "total_mentions": sum(item["count"] for item in mentions), "needs_review": True})
        entity_terms = {
            term: entity["id"]
            for group in ENTITY_GROUPS
            for entity in normalized[group]
            for term in tuple(dict.fromkeys((entity["name"], *entity["aliases"])))
        }
        for chapter in chapters:
            sentences = [sentence.strip() for sentence in re.split(r"[。！？!?\n]+", chapter.text) if sentence.strip()]
            for sentence_index, sentence in enumerate(sentences, start=1):
                involved = sorted({entity_id for term, entity_id in entity_terms.items() if term in sentence})
                markers = [marker for marker in ACTION_MARKERS if marker in sentence]
                if not involved or not markers:
                    continue
                events.append({
                    "event_id": f"EVT-{chapter.chapter_id}-{sentence_index:04d}",
                    "chapter_id": chapter.chapter_id,
                    "sentence_index": sentence_index,
                    "sentence_sha256": hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
                    "entity_refs": involved,
                    "action_markers": markers,
                    "confidence": "candidate",
                    "needs_review": True,
                })
        return ExtractionResult(self.name, tuple(groups["characters"]), tuple(groups["locations"]), tuple(groups["props"]), tuple(events))

    @staticmethod
    def _validate_lexicon(payload: Any) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(payload, dict):
            raise StoryExtractionError("lexicon must be an object")
        normalized: dict[str, list[dict[str, Any]]] = {}
        all_ids: set[str] = set()
        for group in ENTITY_GROUPS:
            items = payload.get(group, [])
            if not isinstance(items, list):
                raise StoryExtractionError(f"lexicon.{group} must be a list")
            normalized[group] = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    raise StoryExtractionError(f"lexicon.{group}[{index}] must be an object")
                entity_id = str(item.get("id") or "")
                name = str(item.get("name") or "").strip()
                aliases = item.get("aliases", [])
                prefix = {"characters": "CHR", "locations": "LOCN", "props": "PROP"}[group]
                if not re.fullmatch(rf"{prefix}-[A-Z0-9][A-Z0-9-]{{1,60}}", entity_id) or entity_id in all_ids:
                    raise StoryExtractionError(f"lexicon.{group}[{index}].id is invalid or duplicated")
                if not name or not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias.strip() for alias in aliases):
                    raise StoryExtractionError(f"lexicon.{group}[{index}] name or aliases are invalid")
                all_ids.add(entity_id)
                normalized[group].append({"id": entity_id, "name": name, "aliases": [alias.strip() for alias in aliases]})
        return normalized
