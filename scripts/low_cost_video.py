"""Single-shot durable cloud workflow. Keys remain in server memory only."""
from __future__ import annotations
import json
import threading
import uuid
import time
from pathlib import Path
from adapters.video_generation.base import VideoGenerationRequest, VideoGenerationError
from adapters.video_generation.wavespeed_wan import WaveSpeedWanVideo, estimate, probe_video, write_json

_LOCK = threading.Lock()
_ACTIVE: set[str] = set()


def local_file(project: Path, relative: str) -> Path:
    path = (project / relative).resolve()
    if project.resolve() not in path.parents or not path.is_file():
        raise ValueError('项目素材不存在或路径越界')
    return path


def record_path(project: Path, shot_id: str = '') -> Path:
    import re
    if shot_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', shot_id):
        raise ValueError('无效的分镜编号')
    return project / 'graybox/low-cost' / ((shot_id or 'latest') + '.json')


def status(project: Path, shot_id: str = '') -> dict:
    path = record_path(project, shot_id)
    data = json.loads(path.read_text()) if path.is_file() else {'status': 'NOT_STARTED'}
    active = (str(project.resolve()) + ':' + shot_id) in _ACTIVE
    if data.get('status') == 'RUNNING' and not active:
        data['status'] = 'INTERRUPTED'
    data['active'] = active
    output = data.get('output', '')
    data['ready'] = bool(output and (project / output).is_file() and data.get('status') == 'COMPLETED')
    return data


def preview(project: Path, control: str, resolution: str) -> dict:
    info = probe_video(local_file(project, control))
    return {**info, **estimate(info['duration_seconds'], resolution), 'control': control}


def start(project: Path, payload: dict, control: str, character: str, key: str) -> dict:
    if payload.get('confirm_billable') is not True or payload.get('upload_authorized') is not True:
        raise ValueError('请确认素材上传和本次付费调用')
    if payload.get('control_reviewed') is not True:
        raise ValueError('请先观看并确认控制视频动作')
    if not key:
        raise ValueError('请先保存 WaveSpeed API Key')
    project = project.resolve()
    shot_id = str(payload.get('shot_id') or '')
    identity = str(project) + ':' + shot_id
    path = record_path(project, shot_id)
    with _LOCK:
        if identity in _ACTIVE:
            raise ValueError('当前镜头正在生成，请勿重复提交')
        previous = status(project, shot_id)
        if payload.get('resume') is True:
            if previous.get('status') == 'NOT_STARTED':
                raise ValueError('没有可恢复的任务')
            recipe = previous
        else:
            if previous.get('status') != 'NOT_STARTED' and payload.get('new_attempt') is not True:
                raise ValueError('已有测试记录；请恢复任务，或明确勾选新测试以重新付费')
            mode = str(payload.get('mode', 'replace'))
            resolution = str(payload.get('resolution', '480p'))
            quote = preview(project, control, resolution)
            budget = float(payload.get('max_cost_cny', 2))
            prompt = str(payload.get('prompt', '')).strip()
            if mode not in ('replace', 'animate', 'video_edit') or not prompt or len(prompt) > 8000:
                raise ValueError('请选择模式并填写有效提示词')
            import math
            if not math.isfinite(budget) or budget <= 0 or quote['estimated_cny'] > budget:
                raise ValueError('费用预估超过预算，未调用云端')
            if mode != 'video_edit':
                local_file(project, character)
            output = 'graybox/final/' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex + '-wavespeed-wan.mp4'
            recipe = {**quote, 'project_id': project.name, 'shot_id': shot_id, 'output': output, 'mode': mode, 'resolution': resolution,
                'character': character if mode != 'video_edit' else '', 'prompt': prompt,
                'max_cost_cny': budget, 'review_status': 'PENDING', 'provider': 'wavespeed_wan'}
        recipe = {**recipe, 'status': 'RUNNING', 'error': ''}
        write_json(path, recipe)
        _ACTIVE.add(identity)
        def worker():
            try:
                video = local_file(project, recipe['control'])
                images = (local_file(project, recipe['character']),) if recipe['character'] else ()
                output = project / recipe['output']
                output.parent.mkdir(parents=True, exist_ok=True)
                adapter = WaveSpeedWanVideo(api_key=key, mode=recipe['mode'],
                    resolution=recipe['resolution'], max_cost_cny=recipe['max_cost_cny'])
                result = adapter.generate(VideoGenerationRequest(image_paths=images,
                    reference_video_paths=(video,), output_path=output,
                    prompt_text=recipe['prompt'], shot_duration_seconds=recipe['duration_seconds']))
                ledger = json.loads(output.with_suffix('.job.json').read_text())
                recipe.update(quoted_usd=ledger.get('quoted_usd'), quoted_cny=ledger.get('quoted_cny'))
                recipe.update(status='COMPLETED', task_id=result.task_id,
                    duration_seconds=result.duration_seconds, remote_generation=True)
                metadata = {**recipe, 'shot_spec_id': recipe.get('shot_id') or 'PROJECT-CONTROL',
                    'qc_status': 'TECHNICAL_VIDEO_VALID_HUMAN_REVIEW_PENDING'}
                write_json(output.with_suffix('.json'), metadata)
            except Exception as error:
                recipe.update(status='ERROR', error=str(error) if isinstance(error, (ValueError, VideoGenerationError))
                              else '任务中断，可恢复查询；请核对云端任务状态')
            finally:
                write_json(path, recipe)
                with _LOCK:
                    _ACTIVE.discard(identity)
        threading.Thread(target=worker, daemon=True).start()
    return status(project, shot_id)


def review(project: Path, payload: dict) -> dict:
    shot_id = str(payload.get('shot_id') or '')
    path = record_path(project, shot_id)
    with _LOCK:
        data = status(project, shot_id)
        if not data.get('ready'):
            raise ValueError('请先完成测试视频，再记录验收')
        if payload.get('review_status') not in ('PASS', 'FAIL'):
            raise ValueError('请选择通过或返工')
        note = str(payload.get('note', '')).strip()
        if not note or len(note) > 2000:
            raise ValueError('请填写角色、背景和动作的验收意见')
        data.update(review_status=payload['review_status'], review_note=note)
        data.pop('active', None); data.pop('ready', None)
        write_json(path, data)
        metadata = (project / data['output']).with_suffix('.json')
        saved = json.loads(metadata.read_text())
        saved.update(review_status=data['review_status'], review_note=note)
        write_json(metadata, saved)
    return status(project, shot_id)
