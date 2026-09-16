#!/usr/bin/env python3
"""Normalize user-provided trend signals behind replaceable source adapters."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE_TYPES = (
    "wechat_ecosystem",
    "search_trend",
    "ai_digital_news",
    "community",
    "user_comment",
)
SIGNAL_FIELDS = {"signal_id", "topic", "title", "source_name", "observed_at", "strength"}
OPTIONAL_SIGNAL_FIELDS = {"summary", "url", "source_type"}
SIGNAL_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z")


class TrendDiscoveryError(ValueError):
    """Raised when source adapters or trend signals are invalid."""


class TrendSource(Protocol):
    """Replaceable boundary for one trend source; providers return normalized records."""

    source_type: str

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch source records without changing the output schema."""


class JsonFileTrendSource:
    """Local import adapter; API-backed providers can implement TrendSource instead."""

    def __init__(self, source_type: str, path: Path):
        if source_type not in SOURCE_TYPES:
            raise TrendDiscoveryError(f"unsupported source type: {source_type}")
        self.source_type = source_type
        self.path = Path(path)

    def fetch(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TrendDiscoveryError(f"cannot read {self.source_type} source {self.path}: {error}") from error
        if isinstance(payload, dict):
            if payload.get("schema_version") not in (None, 1):
                raise TrendDiscoveryError(f"unsupported source file schema: {self.path}")
            payload = payload.get("signals")
        if not isinstance(payload, list):
            raise TrendDiscoveryError(f"{self.source_type} source file must contain a signals list")
        if any(not isinstance(item, dict) for item in payload):
            raise TrendDiscoveryError(f"{self.source_type} source signals must be objects")
        return payload


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise TrendDiscoveryError("date must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise TrendDiscoveryError("date must use YYYY-MM-DD") from error


def _normalize_datetime(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrendDiscoveryError(f"{label} must be an ISO-8601 timestamp with a timezone")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise TrendDiscoveryError(f"{label} must be an ISO-8601 timestamp with a timezone") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrendDiscoveryError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_topic(value: str) -> str:
    """Create a stable grouping key while keeping the display topic untouched."""
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def normalize_signal(payload: Any, source_type: str) -> dict[str, Any]:
    if source_type not in SOURCE_TYPES:
        raise TrendDiscoveryError(f"unsupported source type: {source_type}")
    if not isinstance(payload, dict):
        raise TrendDiscoveryError("signal must be an object")
    unknown = set(payload) - SIGNAL_FIELDS - OPTIONAL_SIGNAL_FIELDS
    missing = SIGNAL_FIELDS - set(payload)
    if missing:
        raise TrendDiscoveryError(f"signal is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise TrendDiscoveryError(f"signal contains unsupported fields: {', '.join(sorted(unknown))}")
    supplied_type = payload.get("source_type")
    if supplied_type is not None and supplied_type != source_type:
        raise TrendDiscoveryError("signal source_type does not match its adapter")

    signal_id = payload["signal_id"]
    if not isinstance(signal_id, str) or not SIGNAL_ID_PATTERN.fullmatch(signal_id):
        raise TrendDiscoveryError("signal_id must be 1 to 100 safe identifier characters")
    normalized: dict[str, Any] = {"signal_id": signal_id, "source_type": source_type}
    for key in ("topic", "title", "source_name"):
        value = payload[key]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 300:
            raise TrendDiscoveryError(f"{key} must be 1 to 300 characters")
        normalized[key] = value.strip()
    strength = payload["strength"]
    if type(strength) is not int or not 0 <= strength <= 100:
        raise TrendDiscoveryError("strength must be an integer from 0 to 100")
    normalized["strength"] = strength
    normalized["observed_at"] = _normalize_datetime(payload["observed_at"], "observed_at")
    if "summary" in payload and payload["summary"] is not None:
        summary = payload["summary"]
        if not isinstance(summary, str) or len(summary.strip()) > 1000:
            raise TrendDiscoveryError("summary must be a string of 1000 characters or fewer")
        if summary.strip():
            normalized["summary"] = summary.strip()
    if "url" in payload and payload["url"] is not None:
        url = payload["url"]
        if not isinstance(url, str) or not url.strip():
            raise TrendDiscoveryError("url must be an absolute http(s) URL when supplied")
        try:
            parsed = urlsplit(url.strip())
        except ValueError as error:
            raise TrendDiscoveryError("url is invalid") from error
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise TrendDiscoveryError("url must be an absolute http(s) URL without embedded credentials")
        normalized["url"] = url.strip()
    return normalized


def validate_discovery_artifact(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise TrendDiscoveryError("trend artifact must use schema_version 1")
    try:
        run_date = _parse_date(payload.get("date"))
    except (TypeError, TrendDiscoveryError) as error:
        raise TrendDiscoveryError("trend artifact date must use YYYY-MM-DD") from error
    raw_signals = payload.get("signals")
    if not isinstance(raw_signals, list):
        raise TrendDiscoveryError("trend artifact signals must be a list")
    signals: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(raw_signals):
        source_type = raw.get("source_type") if isinstance(raw, dict) else None
        if source_type not in SOURCE_TYPES:
            raise TrendDiscoveryError(f"signals[{index}] has an unsupported source_type")
        signal = normalize_signal(raw, source_type)
        if date.fromisoformat(signal["observed_at"][:10]) > run_date:
            raise TrendDiscoveryError(f"signal {signal['signal_id']} is newer than the artifact date")
        if signal["signal_id"] in ids:
            raise TrendDiscoveryError(f"duplicate signal_id: {signal['signal_id']}")
        ids.add(signal["signal_id"])
        signals.append(signal)
    return {"date": run_date.isoformat(), "signals": signals}


def discover_trends(
    sources: list[TrendSource], *, run_date: str, collected_at: str | None = None
) -> dict[str, Any]:
    parsed_date = _parse_date(run_date)
    timestamp = _normalize_datetime(collected_at or utc_timestamp(), "collected_at")
    collected_datetime = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    signals: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    source_types: set[str] = set()
    for source in sources:
        if source.source_type not in SOURCE_TYPES:
            raise TrendDiscoveryError(f"unsupported source type: {source.source_type}")
        source_types.add(source.source_type)
        for raw in source.fetch():
            signal = normalize_signal(raw, source.source_type)
            observed_datetime = datetime.fromisoformat(signal["observed_at"].replace("Z", "+00:00"))
            if observed_datetime.date() > parsed_date or observed_datetime > collected_datetime:
                raise TrendDiscoveryError(f"signal {signal['signal_id']} is newer than the collection date/time")
            if signal["signal_id"] in seen_ids:
                raise TrendDiscoveryError(f"duplicate signal_id: {signal['signal_id']}")
            seen_ids.add(signal["signal_id"])
            signals.append(signal)

    received_count = len(signals)
    deduplicated: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for signal in signals:
        fingerprint = (
            signal["source_type"],
            normalize_topic(signal["topic"]),
            normalize_topic(signal["source_name"]),
            signal.get("url", "").casefold().rstrip("/"),
        )
        current = deduplicated.get(fingerprint)
        if current is None or (signal["observed_at"], signal["strength"], signal["signal_id"]) > (
            current["observed_at"], current["strength"], current["signal_id"]
        ):
            deduplicated[fingerprint] = signal
    normalized_signals = sorted(
        deduplicated.values(),
        key=lambda item: (normalize_topic(item["topic"]), item["source_type"], item["source_name"].casefold(), item["signal_id"]),
    )
    return {
        "schema_version": 1,
        "date": parsed_date.isoformat(),
        "collected_at": timestamp,
        "source_types": sorted(source_types),
        "stats": {
            "signals_received": received_count,
            "signals_accepted": len(normalized_signals),
            "duplicates_removed": received_count - len(normalized_signals),
        },
        "signals": normalized_signals,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise TrendDiscoveryError(f"refusing to overwrite existing output: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        try:
            os.link(temp_name, path)
        except FileExistsError as error:
            raise TrendDiscoveryError(f"refusing to overwrite existing output: {path}") from error
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def parse_source_spec(value: str) -> JsonFileTrendSource:
    source_type, separator, raw_path = value.partition("=")
    if not separator or not raw_path:
        raise TrendDiscoveryError("--source must use SOURCE_TYPE=PATH")
    return JsonFileTrendSource(source_type, Path(raw_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, metavar="TYPE=PATH", help="local JSON source adapter; repeat for each source")
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat(), help="artifact date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "topics" / "trends")
    args = parser.parse_args(argv)
    try:
        sources = [parse_source_spec(item) for item in args.source]
        result = discover_trends(sources, run_date=args.date)
        output = args.output_dir / f"{result['date']}.json"
        _atomic_write(output, result)
    except (OSError, TrendDiscoveryError) as error:
        print(f"trend-discovery: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(output), **result["stats"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
