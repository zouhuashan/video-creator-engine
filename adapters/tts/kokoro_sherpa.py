"""Local Kokoro TTS adapter backed by sherpa-onnx.

The checked-in application Python can differ from the Python ABI used by the
optional sherpa-onnx wheel.  This adapter therefore runs the small worker in a
compatible interpreter instead of importing sherpa-onnx in the web process.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Mapping

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_DIR = ROOT / ".dependencies" / "kokoro-runtime"
DEFAULT_MODEL_DIR = ROOT / ".dependencies" / "models" / "kokoro-int8-multi-lang-v1_1"
DEFAULT_PYTHON = ROOT / ".dependencies" / "python-bin" / "python3.13"
WORKER_PATH = Path(__file__).with_name("_kokoro_worker.py")

# Official kokoro-multi-lang-v1_1 voices.bin order from sherpa-onnx.
KOKORO_VOICE_IDS = (
    "af_maple", "af_sol", "bf_vale",
    "zf_001", "zf_002", "zf_003", "zf_004", "zf_005", "zf_006", "zf_007", "zf_008",
    "zf_017", "zf_018", "zf_019", "zf_021", "zf_022", "zf_023", "zf_024", "zf_026",
    "zf_027", "zf_028", "zf_032", "zf_036", "zf_038", "zf_039", "zf_040", "zf_042",
    "zf_043", "zf_044", "zf_046", "zf_047", "zf_048", "zf_049", "zf_051", "zf_059",
    "zf_060", "zf_067", "zf_070", "zf_071", "zf_072", "zf_073", "zf_074", "zf_075",
    "zf_076", "zf_077", "zf_078", "zf_079", "zf_083", "zf_084", "zf_085", "zf_086",
    "zf_087", "zf_088", "zf_090", "zf_092", "zf_093", "zf_094", "zf_099",
    "zm_009", "zm_010", "zm_011", "zm_012", "zm_013", "zm_014", "zm_015", "zm_016",
    "zm_020", "zm_025", "zm_029", "zm_030", "zm_031", "zm_033", "zm_034", "zm_035",
    "zm_037", "zm_041", "zm_045", "zm_050", "zm_052", "zm_053", "zm_054", "zm_055",
    "zm_056", "zm_057", "zm_058", "zm_061", "zm_062", "zm_063", "zm_064", "zm_065",
    "zm_066", "zm_068", "zm_069", "zm_080", "zm_081", "zm_082", "zm_089", "zm_091",
    "zm_095", "zm_096", "zm_097", "zm_098", "zm_100",
)
KOKORO_VOICE_TO_SID = {voice_id: sid for sid, voice_id in enumerate(KOKORO_VOICE_IDS)}
KOKORO_VOICE_ALIASES = {
    "default": "zm_010",
    "male": "zm_010",
    "male_narrator": "zm_010",
    "narrator_male": "zm_010",
    "男声": "zm_010",
    "男旁白": "zm_010",
    "female": "zf_001",
    "female_narrator": "zf_001",
    "narrator_female": "zf_001",
    "女声": "zf_001",
    "女旁白": "zf_001",
}

_PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "﹐": "，",
        "､": "，",
        "﹒": "。",
        "｡": "。",
        "﹖": "？",
        "﹗": "！",
        "﹔": "；",
        "﹕": "：",
        "“": "“",
        "”": "”",
        "‘": "‘",
        "’": "’",
    }
)


def normalize_chinese_punctuation(text: str) -> str:
    """Normalize pauses without altering Latin words or decimal numbers."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").translate(
        _PUNCTUATION_TRANSLATION
    )
    normalized = re.sub(r"\.{3,}|…{2,}", "……", normalized)
    normalized = re.sub(r"-{2,}|—{2,}", "——", normalized)
    normalized = normalized.replace("?", "？").replace("!", "！")
    normalized = re.sub(r"(?<=[\u3400-\u9fff])[ \t]*,[ \t]*", "，", normalized)
    normalized = re.sub(r"(?<=[\u3400-\u9fff])[ \t]*;[ \t]*", "；", normalized)
    normalized = re.sub(r"(?<=[\u3400-\u9fff])[ \t]*\.(?!\d)", "。", normalized)
    normalized = re.sub(r"[ \t]*([，。？！；：])[ \t]*", r"\1", normalized)
    normalized = re.sub(r"([，。；：])\1+", r"\1", normalized)
    normalized = re.sub(r"([？！])\1+", r"\1", normalized)
    normalized = re.sub(r"[ \t]*\n+[ \t]*", "。", normalized)
    normalized = re.sub(r"([。？！])。+", r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def resolve_kokoro_voice(
    voice: str, aliases: Mapping[str, str] = KOKORO_VOICE_ALIASES
) -> tuple[str, int]:
    normalized = voice.strip().lower()
    canonical = aliases.get(normalized, normalized)
    try:
        return canonical, KOKORO_VOICE_TO_SID[canonical]
    except KeyError as error:
        examples = "zm_010, zm_012, zf_001, zf_002"
        raise TTSProviderError(
            f"unsupported Kokoro voice_id {voice!r}; use an installed voice such as {examples}"
        ) from error


class KokoroSherpaTTS(TTSProvider):
    """Non-billable local Kokoro v1.1 Chinese speech synthesis."""

    name = "kokoro_local"

    def __init__(
        self,
        *,
        runtime_dir: Path | str = DEFAULT_RUNTIME_DIR,
        model_dir: Path | str = DEFAULT_MODEL_DIR,
        python_executable: Path | str = DEFAULT_PYTHON,
        num_threads: int = 2,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir).expanduser().resolve()
        self.model_dir = Path(model_dir).expanduser().resolve()
        self.python_executable = Path(python_executable).expanduser().resolve()
        self.num_threads = num_threads
        self.runner = runner
        self.environment = dict(environment or os.environ)

    def _validate_dependencies(self) -> None:
        if not self.python_executable.is_file():
            raise TTSProviderError(
                "Kokoro local runtime is unavailable: compatible Python was not found at "
                f"{self.python_executable}. Set python_executable or install the local runtime."
            )
        package = self.runtime_dir / "sherpa_onnx" / "__init__.py"
        if not package.is_file():
            raise TTSProviderError(
                "Kokoro local runtime is unavailable: sherpa-onnx was not found at "
                f"{self.runtime_dir}. Set runtime_dir or install sherpa-onnx locally."
            )
        required = (
            "model.int8.onnx",
            "voices.bin",
            "tokens.txt",
            "lexicon-us-en.txt",
            "lexicon-zh.txt",
            "phone-zh.fst",
            "date-zh.fst",
            "number-zh.fst",
        )
        missing = [name for name in required if not (self.model_dir / name).is_file()]
        if missing:
            raise TTSProviderError(
                "Kokoro local model is incomplete at "
                f"{self.model_dir}; missing: {', '.join(missing)}"
            )
        if not WORKER_PATH.is_file():
            raise TTSProviderError("Kokoro local worker is missing from the application")
        if (
            isinstance(self.num_threads, bool)
            or not isinstance(self.num_threads, int)
            or self.num_threads < 1
        ):
            raise TTSProviderError("Kokoro num_threads must be a positive integer")

    def synthesize(
        self, text: str, voice: str, speed: float = 1.0, emotion: str | None = None
    ) -> SynthesisResult:
        text, voice, speed, emotion = validate_synthesis_request(text, voice, speed, emotion)
        if emotion is not None:
            raise TTSProviderError("Kokoro local TTS does not support emotion controls")
        normalized_text = normalize_chinese_punctuation(text)
        if not normalized_text:
            raise TTSProviderError("text became empty after Chinese punctuation normalization")
        canonical_voice, sid = resolve_kokoro_voice(voice)
        self._validate_dependencies()

        with tempfile.TemporaryDirectory(prefix="video-creator-kokoro-") as temporary:
            output = Path(temporary) / "voice.wav"
            command = [
                str(self.python_executable),
                str(WORKER_PATH),
                "--model-dir",
                str(self.model_dir),
                "--output",
                str(output),
                "--sid",
                str(sid),
                "--speed",
                str(speed),
                "--num-threads",
                str(self.num_threads),
            ]
            environment = dict(self.environment)
            previous_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(self.runtime_dir), previous_pythonpath))
            )
            try:
                completed = self.runner(
                    command,
                    input=normalized_text.encode("utf-8"),
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                )
            except OSError as error:
                raise TTSProviderError(
                    "Kokoro local synthesis could not start its compatible Python runtime"
                ) from error
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
                suffix = f": {detail[-1]}" if detail else ""
                raise TTSProviderError(f"Kokoro local synthesis failed{suffix}")
            try:
                audio = output.read_bytes()
            except OSError as error:
                raise TTSProviderError("Kokoro local synthesis produced no readable WAV file") from error

        if not audio:
            raise TTSProviderError("Kokoro local synthesis returned empty audio")
        return SynthesisResult(
            audio=audio,
            provider=self.name,
            voice=canonical_voice,
            speed=speed,
            emotion=None,
            audio_format="wav",
            billable_generation=False,
        )
