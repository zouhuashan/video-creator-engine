"""Chinese narration normalization before TTS and cache lookup."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import TTSProviderError


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "zh-voice.json"
DIGITS = "零一二三四五六七八九"
PAUSE_PATTERN = re.compile(r"\{pause:(short|long)\}")
EMPHASIS_PATTERN = re.compile(r"\*\*([^*\n]+)\*\*")
HAN_TO_LATIN = re.compile(r"([\u3400-\u9fff])([A-Za-z])")
LATIN_TO_HAN = re.compile(r"([A-Za-z])([\u3400-\u9fff])")


class ChineseSpeechError(TTSProviderError):
    """Raised when narration markup or normalization config is invalid."""


@dataclass(frozen=True)
class SpeechPlan:
    text: str
    emotion: str | None
    provider: str
    locale: str = "zh-CN"


def load_zh_voice_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ChineseSpeechError(f"invalid Chinese voice config: {error}") from error
    required = {"schema_version", "locale", "acronyms", "products", "pause_markers", "emphasis_markers"}
    if not isinstance(config, dict) or not required.issubset(config):
        raise ChineseSpeechError("Chinese voice config is incomplete")
    if config["schema_version"] != 1 or config["locale"] != "zh-CN":
        raise ChineseSpeechError("unsupported Chinese voice config")
    if not all(isinstance(config[field], dict) and config[field] for field in required - {"schema_version", "locale"}):
        raise ChineseSpeechError("Chinese voice mappings must be non-empty objects")
    return config


def _four_digit_number(number: int) -> str:
    if number == 0:
        return DIGITS[0]
    units = ((1000, "千"), (100, "百"), (10, "十"), (1, ""))
    parts: list[str] = []
    pending_zero = False
    remainder = number
    for value, unit in units:
        digit, remainder = divmod(remainder, value)
        if digit:
            if pending_zero:
                parts.append("零")
                pending_zero = False
            parts.append(DIGITS[digit] + unit)
        elif parts and remainder:
            pending_zero = True
    result = "".join(parts)
    return result[1:] if 10 <= number < 20 and result.startswith("一十") else result


def integer_to_chinese(number: int) -> str:
    if number < 0:
        return "负" + integer_to_chinese(-number)
    if number == 0:
        return "零"
    if number >= 1_000_000_000_000:
        raise ChineseSpeechError("numbers at or above one trillion require an explicit pronunciation")

    groups: list[tuple[int, str]] = []
    remainder = number
    for divisor, unit in ((100_000_000, "亿"), (10_000, "万"), (1, "")):
        value, remainder = divmod(remainder, divisor)
        if value:
            groups.append((value, unit))

    parts: list[str] = []
    previous_unit = ""
    for value, unit in groups:
        if parts and value < 1000 and previous_unit:
            parts.append("零")
        parts.append(_four_digit_number(value) + unit)
        previous_unit = unit
    return "".join(parts)


def decimal_to_chinese(value: str) -> str:
    negative = value.startswith("-")
    unsigned = value[1:] if negative else value
    if "." not in unsigned:
        result = integer_to_chinese(int(unsigned))
    else:
        integer, fraction = unsigned.split(".", 1)
        result = integer_to_chinese(int(integer)) + "点" + "".join(DIGITS[int(digit)] for digit in fraction)
    return "负" + result if negative else result


def _replace_named_terms(text: str, mapping: dict[str, str]) -> str:
    for source in sorted(mapping, key=len, reverse=True):
        text = re.sub(re.escape(source), mapping[source], text, flags=re.IGNORECASE)
    return text


def _normalize_numbers(text: str) -> str:
    text = re.sub(
        r"(-?\d+(?:\.\d+)?)\s*%",
        lambda match: "百分之" + decimal_to_chinese(match.group(1)),
        text,
    )
    text = re.sub(
        r"[¥￥]\s*(-?\d+(?:\.\d+)?)",
        lambda match: decimal_to_chinese(match.group(1)) + "元",
        text,
    )
    text = re.sub(
        r"(?<!\d)(\d{4})年",
        lambda match: "".join(DIGITS[int(digit)] for digit in match.group(1)) + "年",
        text,
    )
    text = re.sub(
        r"(?<![A-Za-z0-9])(-?\d+)G\b",
        lambda match: decimal_to_chinese(match.group(1)) + " G",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?<![A-Za-z0-9])(-?\d+\.\d+)(?![A-Za-z0-9])",
        lambda match: decimal_to_chinese(match.group(1)),
        text,
    )
    return re.sub(
        r"(?<![A-Za-z0-9.])(-?\d+)(?![A-Za-z0-9.])",
        lambda match: decimal_to_chinese(match.group(1)),
        text,
    )


def optimize_chinese_speech(
    text: str,
    *,
    provider: str = "fish_audio",
    emotion: str | None = None,
    config: dict[str, Any] | None = None,
) -> SpeechPlan:
    if not isinstance(text, str) or not text.strip():
        raise ChineseSpeechError("Chinese narration text must be non-empty")
    if text.count("**") % 2:
        raise ChineseSpeechError("unclosed emphasis marker")
    active = config or load_zh_voice_config()
    marker_family = provider if provider in active["pause_markers"] else "generic"
    if emotion is not None:
        if not isinstance(emotion, str) or not emotion.strip():
            emotion = None
        elif any(character in emotion for character in "[]\n\r"):
            raise ChineseSpeechError("emotion must be plain text without brackets or line breaks")
        else:
            emotion = emotion.strip()

    optimized = re.sub(r"\s+", " ", text.strip())
    optimized = PAUSE_PATTERN.sub(
        lambda match: active["pause_markers"][marker_family][match.group(1)], optimized
    )
    if "{pause:" in optimized:
        raise ChineseSpeechError("unsupported pause marker; use short or long")
    emphasis_template = active["emphasis_markers"].get(provider, active["emphasis_markers"]["generic"])
    optimized = EMPHASIS_PATTERN.sub(
        lambda match: emphasis_template.format(text=match.group(1).strip()), optimized
    )
    optimized = _replace_named_terms(optimized, active["products"])
    optimized = _replace_named_terms(optimized, active["acronyms"])
    optimized = re.sub(
        r"\b[A-Z]{2,6}\b",
        lambda match: " ".join(match.group(0)),
        optimized,
    )
    optimized = _normalize_numbers(optimized)
    optimized = HAN_TO_LATIN.sub(r"\1 \2", optimized)
    optimized = LATIN_TO_HAN.sub(r"\1 \2", optimized)
    optimized = re.sub(r"[ \t]+", " ", optimized)
    optimized = re.sub(r"\s+([，。！？；：、])", r"\1", optimized).strip()
    return SpeechPlan(text=optimized, emotion=emotion, provider=provider, locale=active["locale"])
