"""Build and execute a deterministic FFmpeg final merge."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from .video_use import _media_tool, video_use_environment


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "ffmpeg-finalizer.json"
BITRATE = re.compile(r"^[1-9]\d*(?:[kKmM])?$")


class FinalizerError(ValueError):
    """Raised when a final merge specification or render fails."""


@dataclass(frozen=True)
class AudioTrack:
    path: Path
    volume: float = 1.0
    delay_ms: int = 0


@dataclass(frozen=True)
class FinalMergeSpec:
    video_inputs: tuple[Path, ...]
    audio_inputs: tuple[AudioTrack, ...]
    output: Path
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    video_bitrate: str
    audio_bitrate: str
    container: str
    transition: str = "none"
    transition_duration: float = 0.0


def load_finalizer_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalizerError(f"invalid FFmpeg finalizer config: {error}") from error
    if config.get("schema_version") != 1 or config.get("engine") != "ffmpeg":
        raise FinalizerError("unsupported FFmpeg finalizer config")
    normalization = config.get("audio_normalization")
    if not isinstance(normalization, dict) or set(normalization) != {
        "integrated_lufs", "true_peak_db", "loudness_range_lu"
    }:
        raise FinalizerError("FFmpeg audio normalization config is incomplete")
    default_output = config.get("default_output")
    required_output = {
        "width", "height", "fps", "video_codec", "expected_video_codec",
        "audio_codec", "video_bitrate", "audio_bitrate", "container",
    }
    if not isinstance(default_output, dict) or set(default_output) != required_output:
        raise FinalizerError("FFmpeg default output config is incomplete")
    return config


def probe_duration(path: Path) -> float:
    ffprobe = _media_tool("ffprobe")
    if ffprobe is None:
        raise FinalizerError("ffprobe is required for final merge")
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=video_use_environment(),
        )
        duration = float(completed.stdout.strip())
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        raise FinalizerError(f"cannot probe duration: {path.name}") from error
    if duration <= 0:
        raise FinalizerError(f"media duration must be positive: {path.name}")
    return duration


def _validate_spec(spec: FinalMergeSpec, config: dict[str, Any]) -> None:
    if not spec.video_inputs:
        raise FinalizerError("final merge requires at least one video input")
    for path in spec.video_inputs:
        if not Path(path).is_file():
            raise FinalizerError(f"video input does not exist: {path}")
    for track in spec.audio_inputs:
        if not Path(track.path).is_file():
            raise FinalizerError(f"audio input does not exist: {track.path}")
        if not 0 <= track.volume <= 4 or track.delay_ms < 0:
            raise FinalizerError("audio volume must be 0-4 and delay_ms must be non-negative")
    if spec.width <= 0 or spec.height <= 0 or spec.width % 2 or spec.height % 2:
        raise FinalizerError("output width and height must be positive even integers")
    if not 1 <= spec.fps <= 120:
        raise FinalizerError("output fps must be between 1 and 120")
    if spec.video_codec not in config["allowed_video_codecs"]:
        raise FinalizerError(f"unsupported video codec: {spec.video_codec}")
    if spec.audio_codec not in config["allowed_audio_codecs"]:
        raise FinalizerError(f"unsupported audio codec: {spec.audio_codec}")
    if spec.container not in config["allowed_containers"] or Path(spec.output).suffix.lower() != f".{spec.container}":
        raise FinalizerError("output extension must match an allowed container")
    if not BITRATE.fullmatch(spec.video_bitrate) or not BITRATE.fullmatch(spec.audio_bitrate):
        raise FinalizerError("video and audio bitrates must be positive FFmpeg bitrate values")
    if spec.transition not in config["allowed_transitions"]:
        raise FinalizerError(f"unsupported transition: {spec.transition}")
    if spec.transition == "none" and spec.transition_duration != 0:
        raise FinalizerError("transition_duration must be zero when transition is none")
    if spec.transition != "none" and not 0 < spec.transition_duration <= 2:
        raise FinalizerError("transition_duration must be between 0 and 2 seconds")


def build_final_merge_command(
    spec: FinalMergeSpec,
    *,
    config: dict[str, Any] | None = None,
    duration_probe: Callable[[Path], float] = probe_duration,
) -> list[str]:
    active = config or load_finalizer_config()
    _validate_spec(spec, active)
    ffmpeg = _media_tool("ffmpeg")
    if ffmpeg is None:
        raise FinalizerError("ffmpeg is required for final merge")

    command = [ffmpeg, "-y"]
    for path in spec.video_inputs:
        command.extend(["-i", str(Path(path).resolve())])
    for track in spec.audio_inputs:
        command.extend(["-i", str(Path(track.path).resolve())])

    filters: list[str] = []
    for index in range(len(spec.video_inputs)):
        filters.append(
            f"[{index}:v:0]scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,"
            f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={spec.fps:g},setsar=1,format={active['pixel_format']},settb=AVTB,setpts=PTS-STARTPTS[v{index}]"
        )

    if len(spec.video_inputs) == 1:
        video_label = "v0"
    elif spec.transition == "none":
        inputs = "".join(f"[v{index}]" for index in range(len(spec.video_inputs)))
        filters.append(f"{inputs}concat=n={len(spec.video_inputs)}:v=1:a=0[vout]")
        video_label = "vout"
    else:
        durations = [duration_probe(Path(path).resolve()) for path in spec.video_inputs]
        if any(duration <= spec.transition_duration for duration in durations):
            raise FinalizerError("each video must be longer than the transition duration")
        previous = "v0"
        for boundary in range(len(spec.video_inputs) - 1):
            output = f"vx{boundary + 1}"
            offset = sum(durations[: boundary + 1]) - spec.transition_duration * (boundary + 1)
            filters.append(
                f"[{previous}][v{boundary + 1}]xfade=transition={spec.transition}:"
                f"duration={spec.transition_duration:g}:offset={offset:.6f}[{output}]"
            )
            previous = output
        video_label = previous

    audio_label: str | None = None
    if spec.audio_inputs:
        first_audio_index = len(spec.video_inputs)
        for index, track in enumerate(spec.audio_inputs):
            filters.append(
                f"[{first_audio_index + index}:a:0]aresample={active['audio_sample_rate']},"
                f"adelay={track.delay_ms}:all=1,volume={track.volume:g}[a{index}]"
            )
        audio_inputs = "".join(f"[a{index}]" for index in range(len(spec.audio_inputs)))
        normalization = active["audio_normalization"]
        filters.append(
            f"{audio_inputs}amix=inputs={len(spec.audio_inputs)}:duration=longest:dropout_transition=0,"
            f"loudnorm=I={normalization['integrated_lufs']}:TP={normalization['true_peak_db']}:"
            f"LRA={normalization['loudness_range_lu']},aresample={active['audio_sample_rate']}[aout]"
        )
        audio_label = "aout"

    command.extend(["-filter_complex", ";".join(filters), "-map", f"[{video_label}]"])
    if audio_label:
        command.extend(["-map", f"[{audio_label}]", "-c:a", spec.audio_codec, "-b:a", spec.audio_bitrate])
    else:
        command.append("-an")
    command.extend(
        [
            "-c:v",
            spec.video_codec,
            "-b:v",
            spec.video_bitrate,
            "-pix_fmt",
            active["pixel_format"],
            "-r",
            f"{spec.fps:g}",
            "-shortest",
        ]
    )
    if active.get("faststart"):
        command.extend(["-movflags", "+faststart"])
    command.extend(["-f", spec.container, str(Path(spec.output).resolve())])
    return command


def run_final_merge(spec: FinalMergeSpec) -> dict[str, Any]:
    command = build_final_merge_command(spec)
    output = Path(spec.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=video_use_environment(),
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise FinalizerError("FFmpeg final merge failed") from error
    if not output.is_file() or output.stat().st_size == 0:
        raise FinalizerError("FFmpeg final merge produced no output")
    digest_builder = hashlib.sha256()
    with output.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest_builder.update(chunk)
    digest = digest_builder.hexdigest()
    return {
        "status": "PASS",
        "output": str(output),
        "size_bytes": output.stat().st_size,
        "sha256": digest,
    }


def default_final_merge_spec(
    video_inputs: tuple[Path, ...],
    audio_inputs: tuple[AudioTrack, ...],
    output: Path,
    *,
    transition: str = "none",
    transition_duration: float = 0.0,
    config: dict[str, Any] | None = None,
) -> FinalMergeSpec:
    active = config or load_finalizer_config()
    defaults = active["default_output"]
    if not audio_inputs:
        raise FinalizerError("standard output requires at least one audio track")
    return FinalMergeSpec(
        video_inputs=video_inputs,
        audio_inputs=audio_inputs,
        output=Path(output),
        width=defaults["width"],
        height=defaults["height"],
        fps=defaults["fps"],
        video_codec=defaults["video_codec"],
        audio_codec=defaults["audio_codec"],
        video_bitrate=defaults["video_bitrate"],
        audio_bitrate=defaults["audio_bitrate"],
        container=defaults["container"],
        transition=transition,
        transition_duration=transition_duration,
    )


def inspect_final_output(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise FinalizerError(f"final output does not exist or is empty: {path}")
    ffprobe = _media_tool("ffprobe")
    if ffprobe is None:
        raise FinalizerError("ffprobe is required to validate final output")
    try:
        completed = subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
            env=video_use_environment(),
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise FinalizerError("cannot inspect final output") from error
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        raise FinalizerError("standard output requires one video stream and one audio stream")
    try:
        frame_rate = float(Fraction(video.get("avg_frame_rate") or video["r_frame_rate"]))
        duration = float(payload["format"]["duration"])
        metadata = {
            "width": int(video["width"]),
            "height": int(video["height"]),
            "fps": frame_rate,
            "video_codec": video["codec_name"],
            "audio_codec": audio["codec_name"],
            "sample_rate": int(audio["sample_rate"]),
            "container": payload["format"]["format_name"],
            "duration_seconds": duration,
            "size_bytes": path.stat().st_size,
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise FinalizerError("final output metadata is incomplete") from error
    return metadata


def validate_standard_metadata(
    metadata: dict[str, Any], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    active = config or load_finalizer_config()
    expected = active["default_output"]
    try:
        checks = {
            "resolution": (
                int(metadata.get("width", 0)) == expected["width"]
                and int(metadata.get("height", 0)) == expected["height"]
            ),
            "fps": abs(float(metadata.get("fps", 0)) - expected["fps"]) < 0.001,
            "video_codec": metadata.get("video_codec") == expected["expected_video_codec"],
            "audio_codec": metadata.get("audio_codec") == expected["audio_codec"],
            "audio_sample_rate": int(metadata.get("sample_rate", 0)) == active["audio_sample_rate"],
            "container": expected["container"] in str(metadata.get("container", "")).split(","),
            "duration": float(metadata.get("duration_seconds", 0)) > 0,
            "file_size": int(metadata.get("size_bytes", 0)) > 0,
        }
    except (TypeError, ValueError) as error:
        raise FinalizerError("final output metadata values are invalid") from error
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise FinalizerError(f"final output standard failed: {', '.join(failed)}")
    return {"status": "PASS", "checks": checks, "metadata": metadata}


def validate_standard_output(
    path: Path, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    return validate_standard_metadata(inspect_final_output(path), config)


def run_standard_final_merge(spec: FinalMergeSpec) -> dict[str, Any]:
    active = load_finalizer_config()
    if not spec.audio_inputs:
        raise FinalizerError("standard merge requires at least one audio track")
    expected = active["default_output"]
    expected_fields = {
        "width": expected["width"],
        "height": expected["height"],
        "fps": expected["fps"],
        "video_codec": expected["video_codec"],
        "audio_codec": expected["audio_codec"],
        "video_bitrate": expected["video_bitrate"],
        "audio_bitrate": expected["audio_bitrate"],
        "container": expected["container"],
    }
    mismatched = [field for field, value in expected_fields.items() if getattr(spec, field) != value]
    if mismatched:
        raise FinalizerError(f"standard merge spec mismatch: {', '.join(mismatched)}")
    render = run_final_merge(spec)
    validation = validate_standard_output(Path(render["output"]), active)
    return {**render, "output_standard": validation}
