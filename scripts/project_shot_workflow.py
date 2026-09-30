"""Project-owned character/location definitions and immutable 3D control shots."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from PIL import Image
from adapters.video_generation.wavespeed_wan import write_json, probe_video
from scripts.graybox_manager import blender_executable

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.Lock()
_RUNNING = set()


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def inventory(project):
    from scripts.episode_workbench import characters as corrected_characters, saved_episodes, workflow_shots
    characters = corrected_characters(project)
    manifest = read(project / 'novel-anime-project.json', {})
    unit_map = read(project / 'storyboard/modern-shot-units.json', {}).get('shots', {})
    shots = []
    for scene in read(project / 'storyboard/shot-breakdown.json', {}).get('scene_breakdowns', []):
        for item in scene.get('shots', []):
            shot = {'id': item['id'], 'scene_id': scene['scene_id'],
                    'episode_id': scene.get('episode_id', ''),
                    'duration_seconds': float(item.get('duration_seconds', 5)),
                    'character_ids': item.get('start_state', {}).get('character_ids', []),
                    'excerpt': str(unit_map.get(item['id'], {}).get('text_excerpt', ''))}
            shots.append(shot)
    edited = saved_episodes(project)
    shots = [s for s in shots if s['episode_id'] not in edited]
    for episode in edited:shots.extend(workflow_shots(project,episode))
    shots.sort(key=lambda s:s['episode_id'])
    return {'project_id': project.name, 'title': manifest.get('title', project.name),
            'characters': [{'id':c['id'], 'name':c.get('name',''), 'description':c.get('description',''),
                            'review_status':c.get('human_review',{}).get('status','PENDING')} for c in characters],
            'shots':shots}


def state_path(project):
    return project / 'production/shot-workflow.json'


def status(project):
    data = read(state_path(project), {'selected_shot_id':'', 'bindings':{}})
    catalog = inventory(project)
    if not any(s['id']==data.get('selected_shot_id') for s in catalog['shots']) and catalog['shots']:
        first = next((s for s in catalog['shots'] if '手机' in s['excerpt']), catalog['shots'][0])
        data['selected_shot_id'] = first['id']
    selected = data.get('bindings', {}).get(data.get('selected_shot_id'), {})
    control = dict(selected.get('control', {}))
    identity = str(project.resolve())
    if control.get('status') == 'RUNNING' and identity not in _RUNNING:
        control['status'] = 'INTERRUPTED'
    output = control.get('output', '')
    control['ready'] = bool(control.get('status') == 'COMPLETED' and output and (project/output).is_file())
    source = next((s for s in catalog['shots'] if s['id'] == data.get('selected_shot_id')), None)
    source_changed = bool(selected and (not source or source['duration_seconds'] != selected.get('duration_seconds')
        or source['excerpt'] != selected.get('excerpt') or source['scene_id'] != selected.get('scene_id')
        or not any(c['id'] == selected.get('character_id') for c in catalog['characters'])
        or any(source.get(k) and selected.get(k)!=source[k] for k in ('action','environment'))))
    if source_changed:
        control.update(status='STALE', ready=False, error='分镜剧情、时长或角色资料已变化，请重新保存设定并制作控制镜头')
    return {**catalog, **data, 'selected':selected, 'control':control,
            'active':identity in _RUNNING, 'blender_installed':blender_executable() is not None}


def selected_id(project):
    return str(status(project).get('selected_shot_id',''))


def save(project, payload):
    with _LOCK:
        if str(project.resolve()) in _RUNNING:
            raise ValueError('控制镜头生成中，请等待完成后修改')
        catalog=inventory(project)
        shot_id=str(payload.get('shot_id',''))
        shot=next((s for s in catalog['shots'] if s['id']==shot_id),None)
        character_id=str(payload.get('character_id',''))
        character=next((c for c in catalog['characters'] if c['id']==character_id),None)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', shot_id):
            raise ValueError('无效的分镜编号')
        if not shot or not character:
            raise ValueError('请选择当前项目内的真实分镜和角色')
        if shot.get('action') and shot['action']!=payload.get('action'):
            raise ValueError('动作与当前台本不一致，请先在台本页修改动作，再准备控制镜头')
        for field in ('character_definition','scene_name','scene_definition'):
            if not isinstance(payload.get(field),str) or not 1 <= len(payload[field].strip()) <= 4000:
                raise ValueError('请填写角色外观、场景名称和场景设定')
        if payload.get('environment') not in ('modern_room','modern_corridor','ancient_courtyard'):
            raise ValueError('无效的场景简模')
        from scripts.episode_workbench import CONTROL_ACTIONS
        if payload.get('action') not in CONTROL_ACTIONS:
            raise ValueError('请选择支持的动作模板；其他动作需单独制作')
        if payload.get('definitions_confirmed') is not True:
            raise ValueError('请确认这份角色和场景设定；自动提取不等于已定妆')
        data=read(state_path(project),{'selected_shot_id':'','bindings':{}})
        prior=data['bindings'].get(shot_id,{})
        new={k:payload[k].strip() if isinstance(payload[k],str) else payload[k]
             for k in ('character_definition','scene_name','scene_definition','environment','action')}
        new.update(shot_id=shot_id,scene_id=shot['scene_id'],episode_id=shot['episode_id'],
                   character_id=character_id,character_name=character['name'],duration_seconds=shot['duration_seconds'],
                   excerpt=shot['excerpt'],definitions_confirmed=True)
        if 'framing' in shot:new.update(framing=shot['framing'],focus_id=shot.get('focus_id',''))
        signature=hashlib.sha256(json.dumps(new,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        new['definition_signature']=signature
        if prior.get('character_id')==character_id and prior.get('character_definition')==new['character_definition']:
            new['character_reference']=prior.get('character_reference','')
        if prior.get('scene_definition')==new['scene_definition'] and prior.get('scene_name')==new['scene_name']:
            new['scene_reference']=prior.get('scene_reference','')
        if signature==prior.get('definition_signature'):
            new['control']=prior.get('control',{})
        data['bindings'][shot_id]=new;data['selected_shot_id']=shot_id
        write_json(state_path(project),data)
        pack=project/'production/shot-packs'/shot_id;pack.mkdir(parents=True,exist_ok=True)
        (pack/'character-prompt.txt').write_text(character['name']+'：'+new['character_definition']+'\n保持正面、侧面和背面外观一致，现代服装或古装按上述设定。',encoding='utf-8')
        (pack/'scene-prompt.txt').write_text(new['scene_name']+'：'+new['scene_definition'],encoding='utf-8')
        write_json(pack/'scene.json',new)
    return status(project)


def select(project, shot_id):
    with _LOCK:
        data=read(state_path(project),{'selected_shot_id':'','bindings':{}})
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', shot_id) or not any(s['id']==shot_id for s in inventory(project)['shots']):
            raise ValueError('分镜不属于当前项目')
        data['selected_shot_id']=shot_id;write_json(state_path(project),data)
    return status(project)


def upload(project,payload):
    kind=payload.get('kind')
    if kind not in ('character','scene'):
        raise ValueError('无效的参考图类型')
    try:
        raw=base64.b64decode(payload.get('content_base64',''),validate=True)
        if not 0<len(raw)<=12*1024*1024:raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>30_000_000:raise ValueError()
            image.load();out=io.BytesIO();image.convert('RGB').save(out,format='PNG')
    except Exception:
        raise ValueError('请上传不超过12MB的有效参考图') from None
    with _LOCK:
        data=read(state_path(project),{})
        shot_id=data.get('selected_shot_id','');binding=data.get('bindings',{}).get(shot_id)
        if not binding:raise ValueError('先保存当前镜头的角色与场景设定')
        if payload.get('shot_id')!=shot_id:raise ValueError('项目镜头已切换，请重新选择图片')
        relative=f'production/references/{shot_id}/{kind}-{uuid.uuid4().hex}.png'
        path=project/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(out.getvalue())
        binding[kind+'_reference']=relative
        write_json(state_path(project),data)
    return status(project)


def context(project):
    data=status(project);binding=data['selected'];control=data['control']
    if not binding or not control.get('ready'):
        raise ValueError('请在当前项目保存角色与场景，再生成或导入本镜头的控制视频')
    path=(project/control['output']).resolve()
    if project.resolve() not in path.parents or not path.is_file():raise ValueError('控制视频路径无效')
    return control['output'],binding.get('character_reference','')


def prompt(binding):
    return f"人物：{binding.get('character_name','')}，{binding.get('character_definition','')}。场景：{binding.get('scene_name','')}，{binding.get('scene_definition','')}。遵循控制视频的动作、走位和相机时序，不增加镜头切换；保持人物、服装及背景稳定。"


def render(project):
    blender=blender_executable()
    if blender is None:raise ValueError('未安装 Blender，可以先导入自己的控制视频')
    project=project.resolve();identity=str(project)
    with _LOCK:
        if identity in _RUNNING:raise ValueError('当前项目控制镜头正在生成')
        data=read(state_path(project),{});shot_id=data.get('selected_shot_id','');binding=data.get('bindings',{}).get(shot_id)
        if not binding:raise ValueError('请先保存镜头设定')
        duration=float(binding['duration_seconds'])
        if not 0<duration<=15:raise ValueError('本地简模仅支持15秒以内单镜头，请先拆短镜头')
        relative=f'production/controls/{shot_id}/{uuid.uuid4().hex}'
        directory=project/relative;directory.mkdir(parents=True)
        spec={**binding,'project_id':project.name,'duration_seconds':duration,'fps':24,'width':480,'height':854}
        from scripts.episode_workbench import MODERN_EVENTS, characters, load_script
        if binding['action'] in MODERN_EVENTS:
            row=next((r for r in load_script(project,binding['episode_id'])['shots'] if r['id']==shot_id),None)
            if row is None:raise ValueError('此场景动作需要已保存的制作台本')
            spec.update(cast_ids=row.get('cast_ids',[]),characters=characters(project),visual=row['visual'],text=row['text'],framing=row.get('framing'),focus_id=row.get('focus_id',''))
        write_json(directory/'spec.json',spec)
        binding['control']={'status':'RUNNING','output':relative+'/control.mp4','blend':relative+'/control.blend','spec':relative+'/spec.json'}
        write_json(state_path(project),data);_RUNNING.add(identity)
    def worker():
        error=''
        try:
            with (directory/'render.log').open('wb') as log:
                from scripts.episode_workbench import STORY_EVENTS
                renderer='blender_story_preview.py' if binding['action'] in STORY_EVENTS else 'blender_project_control.py'
                result=subprocess.run([str(blender),'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'scripts'/renderer),'--',str(directory/'spec.json'),str(directory)],stdout=log,stderr=subprocess.STDOUT,timeout=1200)
            if result.returncode:raise ValueError('Blender 生成失败，详见本镜头 render.log')
            probe_video(directory/'control.mp4')
        except Exception as e:
            error=str(e) if isinstance(e,ValueError) else '控制渲染中断；可重新生成本地镜头，不产生云端费用'
        finally:
            with _LOCK:
                latest=read(state_path(project),{});current=latest['bindings'][shot_id]['control']
                current.update(status='ERROR' if error else 'COMPLETED',error=error)
                write_json(state_path(project),latest);_RUNNING.discard(identity)
    threading.Thread(target=worker,daemon=True).start()
    return status(project)


def import_control(project,payload):
    # A local user-supplied video can replace unsupported procedural actions.
    try:
        raw=base64.b64decode(payload.get('content_base64',''),validate=True)
        if not 1024<=len(raw)<=40*1024*1024:raise ValueError()
    except Exception:raise ValueError('请导入1KB～40MB的MP4控制视频') from None
    with _LOCK:
        if str(project.resolve()) in _RUNNING:raise ValueError('请等待本地生成完成')
        data=read(state_path(project),{});shot_id=data.get('selected_shot_id','');binding=data.get('bindings',{}).get(shot_id)
        if not binding or payload.get('shot_id')!=shot_id:raise ValueError('请先选择并保存当前镜头')
        relative=f'production/controls/{shot_id}/{uuid.uuid4().hex}/control.mp4'
        path=project/relative;path.parent.mkdir(parents=True);path.write_bytes(raw)
        try:info=probe_video(path)
        except Exception:path.unlink(missing_ok=True);raise
        if abs(info['duration_seconds']-binding['duration_seconds'])>max(.15,1/24):
            path.unlink(missing_ok=True);raise ValueError('控制视频时长须与所选分镜一致，避免字幕声音错位')
        binding['control']={'status':'COMPLETED','output':relative,'source':'USER_IMPORT'}
        write_json(state_path(project),data)
    return status(project)
