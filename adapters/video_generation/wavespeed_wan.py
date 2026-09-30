"""Budget-first Wan video-to-video adapter; no paid submission is retried."""
from __future__ import annotations
import json
import hashlib
import io
import math
import mimetypes
import os
import re
import subprocess
import shutil
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult

API = 'https://api.wavespeed.ai/api/v3'
USD_CNY = 6.714  # Estimate only; provider billing and FX can change.


def probe_video(path: Path) -> dict:
    try:
        if shutil.which('ffprobe'):
            result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                'format=duration:stream=codec_type,width,height', '-of', 'json', str(path)],
                capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
            if not streams:
                raise ValueError()
            width, height = streams[0]['width'], streams[0]['height']
        else:
            # Existing installations ship FFmpeg without ffprobe. Decode one frame
            # to reject invalid media; use container duration for the local preview.
            result = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(path),
                '-map', '0:v:0', '-frames:v', '1', '-f', 'null', '-'],
                capture_output=True, text=True, check=True, timeout=30)
            timing = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', result.stderr)
            size = re.search(r'Video:.*? (\d{2,5})x(\d{2,5})(?:[ ,])', result.stderr)
            if not timing or not size:
                raise ValueError()
            duration = int(timing[1]) * 3600 + int(timing[2]) * 60 + float(timing[3])
            width, height = int(size[1]), int(size[2])
        if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
            raise ValueError()
        return {'duration_seconds': duration, 'width': width, 'height': height}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        raise VideoGenerationError('无法读取有效视频的时长和画面') from error


def estimate(duration: float, resolution: str = '480p') -> dict:
    if resolution not in ('480p', '720p') or not math.isfinite(duration) or not 0 < duration <= 120:
        raise VideoGenerationError('仅支持 480p/720p、最长 120 秒输入视频')
    seconds = max(3, math.ceil(duration))
    usd = round(seconds * (0.04 if resolution == '480p' else 0.08), 4)
    return {'billable_seconds': seconds, 'estimated_usd': usd,
            'estimated_cny': math.ceil(usd * USD_CNY * 100) / 100,
            'usd_cny': USD_CNY, 'resolution': resolution, 'estimate_only': True}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class WaveSpeedWanVideo(VideoGenerationProvider):
    name = 'wavespeed_wan'
    remote_generation = True

    def __init__(self, api_key=None, mode='replace', resolution='480p', max_cost_cny=2.0,
                 opener=None, sleeper=time.sleep, probe=probe_video, timeout_polls=180):
        self.key = api_key or os.environ.get('WAVESPEED_API_KEY', '')
        self.mode, self.resolution, self.budget = mode, resolution, float(max_cost_cny)
        self.open = opener or (lambda request: urlopen(request, timeout=90))
        self.sleep, self.probe, self.polls = sleeper, probe, timeout_polls

    def _json(self, route, payload=None, raw=None, headers=None):
        body = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        request = Request(API + route, data=body, headers={
            'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json', **(headers or {})})
        try:
            with self.open(request) as response:
                data = json.loads(response.read())
            if data.get('code', 200) != 200 or not isinstance(data.get('data'), dict):
                raise ValueError()
            return data['data']
        except Exception as error:
            # Do not expose keys, signed URLs, or provider response bodies.
            raise VideoGenerationError('WaveSpeed 请求失败；请检查密钥、余额或服务状态') from None

    def _upload(self, path):
        if path.stat().st_size > 200 * 1024 * 1024:
            raise VideoGenerationError('上传素材超过 200MB')
        raw = path.read_bytes()
        suffix = path.suffix.lower()
        if suffix == '.webp':
            from PIL import Image
            try:
                buffer = io.BytesIO()
                with Image.open(io.BytesIO(raw)) as image:
                    image.convert('RGBA').save(buffer, format='PNG')
                raw, suffix = buffer.getvalue(), '.png'
            except (OSError, ValueError):
                raise VideoGenerationError('人物参考图无法转换为 PNG') from None
        if len(raw) > 200 * 1024 * 1024:
            raise VideoGenerationError('转换后的上传素材超过 200MB')
        data = self._json('/media/upload/binary', raw=raw, headers={
            'Content-Type': mimetypes.guess_type('input' + suffix)[0] or 'application/octet-stream',
            'file': 'input' + suffix})
        url = str(data.get('download_url', ''))
        if urlparse(url).scheme != 'https':
            raise VideoGenerationError('上传服务没有返回 HTTPS 素材地址')
        return url

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        request.validate()
        if not self.key:
            raise VideoGenerationError('请先配置 WaveSpeed API Key')
        if self.mode not in ('animate', 'replace', 'video_edit'):
            raise VideoGenerationError('无效的 Wan 模式')
        if len(request.reference_video_paths) != 1 or request.reference_audio_paths:
            raise VideoGenerationError('Wan 需要一个控制视频，不支持音频参考')
        if len(request.image_paths) != (0 if self.mode == 'video_edit' else 1):
            raise VideoGenerationError('人物模式需要一张人物参考图；改画风模式不接收参考图')
        if not request.prompt_text.strip():
            raise VideoGenerationError('请填写提示词')
        video = request.reference_video_paths[0]
        info = self.probe(video)
        quote = estimate(info['duration_seconds'], self.resolution)
        if not math.isfinite(self.budget) or self.budget <= 0 or quote['estimated_cny'] > self.budget:
            raise VideoGenerationError('预估费用超过本次预算上限，未上传或提交')
        for path in (*request.reference_video_paths, *request.image_paths):
            if path.stat().st_size > 200 * 1024 * 1024:
                raise VideoGenerationError('上传素材超过 200MB')
        ledger = request.output_path.with_suffix('.job.json')
        state = json.loads(ledger.read_text()) if ledger.exists() else {}
        fingerprint = hashlib.sha256(json.dumps({
            'files': [hashlib.sha256(p.read_bytes()).hexdigest() for p in (*request.reference_video_paths, *request.image_paths)],
            'prompt': request.prompt_text, 'mode': self.mode, 'resolution': self.resolution
        }, sort_keys=True).encode()).hexdigest()
        if state and state.get('fingerprint') != fingerprint:
            raise VideoGenerationError('任务素材或参数已变化，不能恢复成另一请求')
        task_id = state.get('task_id')
        if state.get('submission_started') and not task_id:
            raise VideoGenerationError('提交结果未知，禁止自动重扣；先到 WaveSpeed 控制台核对任务')
        if not task_id:
            payload = {'video': self._upload(video), 'prompt': request.prompt_text,
                       'resolution': self.resolution, 'seed': -1}
            if self.mode != 'video_edit':
                payload.update(image=self._upload(request.image_paths[0]), mode=self.mode)
            model = 'wavespeed-ai/wan-2.2/' + ('video-edit' if self.mode == 'video_edit' else 'animate')
            live = self._json('/model/price', {'model_id': model, 'inputs': payload})
            try:
                live_usd = float(live.get('discounted_price', live['price']))
                if live.get('currency') != 'USD' or not math.isfinite(live_usd) or live_usd < 0:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise VideoGenerationError('无法确认当前接口报价，未提交付费任务') from None
            live_cny = math.ceil(live_usd * USD_CNY * 100) / 100
            if live_cny > self.budget:
                raise VideoGenerationError('云端实时报价超过预算，未提交付费任务')
            state = {**quote, 'submission_started': True, 'model': model, 'mode': self.mode,
                'quoted_usd': live_usd, 'quoted_cny': live_cny, 'fingerprint': fingerprint}
            write_json(ledger, state)  # A network timeout must never cause a second POST.
            data = self._json('/' + model, payload)
            task_id = str(data.get('id') or '')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', task_id):
                raise VideoGenerationError('提交结果未知，请到服务控制台核对')
            state['task_id'] = task_id
            write_json(ledger, state)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(task_id)):
            raise VideoGenerationError('无效的任务编号')
        for _ in range(self.polls):
            data = self._json('/predictions/' + task_id + '/result')
            status = str(data.get('status', '')).lower()
            if status in ('failed', 'cancelled', 'timeout', 'deleted'):
                raise VideoGenerationError('远程任务未成功；恢复只查询，不重新扣费提交')
            if status == 'completed':
                outputs = data.get('outputs') or []
                url = outputs[0] if outputs else ''
                if isinstance(url, dict):
                    url = url.get('url', '')
                if not isinstance(url, str) or urlparse(url).scheme != 'https':
                    raise VideoGenerationError('远程结果地址无效')
                temporary = request.output_path.with_suffix('.download.mp4')
                try:
                    # No API credentials are sent to output storage.
                    with self.open(Request(url)) as response, temporary.open('wb') as handle:
                        total = 0
                        while chunk := response.read(1024 * 1024):
                            total += len(chunk)
                            if total > 512 * 1024 * 1024:
                                raise ValueError()
                            handle.write(chunk)
                    output_info = self.probe(temporary)
                    temporary.replace(request.output_path)
                except Exception:
                    temporary.unlink(missing_ok=True)
                    raise VideoGenerationError('结果下载或视频校验失败；可恢复同一任务') from None
                state['completed'] = True
                write_json(ledger, state)
                return VideoGenerationResult(request.output_path, self.name,
                    output_info['duration_seconds'], len(request.image_paths), True, task_id)
            self.sleep(10)
        raise VideoGenerationError('等待超时；可恢复同一任务，无需重新提交')
