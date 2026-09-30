"""Versioned episode scripts, reusable local voices, and reviewed episode assembly.

The six-step Web workflow reads this production contract when present. Legacy
writing-room drafts and historical media stay intact; the workbench never makes
an external generation request or promotes a control render to a final master.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import wave
from pathlib import Path
from copy import deepcopy

from adapters.tts import KokoroSherpaTTS, MacOSSayTTS
from adapters.tts.kokoro_sherpa import prepare_kokoro_text
from adapters.video_generation.wavespeed_wan import probe_video, write_json
from scripts.graybox_manager import blender_executable

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.RLock()
_RUNNING = set()
_ID = re.compile(r'S\d{2}E\d{3}')

STORY_EVENTS={'wake_up':'惊醒、坐起','child_question':'女儿揉眼问话','father_reassure':'父亲俯身安抚',
    'father_realize':'父亲反应特写','whistle_drop':'哨子落桌','room_blackout':'震动、停电',
    'leave_room':'父女离开房间','door_leak':'消防门缝红液特写'}
from scripts.script_action_plan import MODERN_EVENTS
STORY_EVENTS.update(MODERN_EVENTS)
CONTROL_ACTIONS={'look_phone':'抬手查看手机','walk_stop_look':'走近、停步、抬头',**STORY_EVENTS}



def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else deepcopy(default)


def digest(data):
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def directory(project, episode):
    if not isinstance(episode,str) or not _ID.fullmatch(episode):
        raise ValueError('无效的集数编号')
    manifest=read(project/'novel-anime-project.json',{})
    ids={item.get('id') for item in manifest.get('episodes',[])}
    if episode not in ids:
        raise ValueError('该集不属于当前项目')
    return project/'production/episodes'/episode


def characters(project):
    corrections=read(project/'production/character-corrections.json',{})
    archived=set(corrections.get('archived_ids',[]))
    overrides=corrections.get('characters',{})
    result=[]
    for item in read(project/'story-bible/characters/index.json',{}).get('characters',[]):
        if item['id'] in archived: continue
        result.append({**item,**overrides.get(item['id'],{})})
    return result


def saved_episodes(project):
    return [item.name for item in (project/'production/episodes').iterdir()
            if item.is_dir() and _ID.fullmatch(item.name) and (item/'script.json').is_file()] if (project/'production/episodes').is_dir() else []


def load_script(project,episode):
    path=directory(project,episode)/'script.json'
    if path.is_file(): return read(path)
    legacy=read(project/'writing-room/episodes'/episode/'script.json',{}).get('episode_script',{})
    rows=[]
    for scene in legacy.get('scenes',[]):
        for unit in scene.get('units',[]):
            if unit.get('kind') not in ('NARRATION','DIALOGUE'):continue
            rows.append({'id':f"SHOT-{episode}-WB{len(rows)+1:03d}", 'visual':scene.get('title') or '填写画面说明',
                'text':unit.get('text',''),'speaker_id':unit.get('speaker_character_id') or 'NARRATOR',
                'duration_seconds':max(1,float(unit.get('estimated_duration_seconds') or 3)),
                'render_kind':'screen','screen_title':'剧情提示','screen_lines':[], 'environment':'modern_room', 'action':'look_phone'})
    return {'schema_version':1,'project_id':project.name,'episode_id':episode,'title':'待整理的导入草稿',
        'revision':0,'signature':'','review_status':'PENDING','shots':rows,'source':'LEGACY_IMPORT_DRAFT'}


def validate_script(project,episode,payload):
    directory(project,episode)
    if not isinstance(payload,dict) or not isinstance(payload.get('title'),str) or not 1<=len(payload['title'].strip())<=120:
        raise ValueError('请填写本集标题（最多120字）')
    rows=payload.get('shots')
    if not isinstance(rows,list) or not 1<=len(rows)<=40:raise ValueError('本集需要1到40个镜头')
    known={c['id'] for c in characters(project)}|{'NARRATOR'}
    unique=set();clean=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict):raise ValueError('镜头必须是结构化记录')
        sid=row.get('id') or f'SHOT-{episode}-WB{uuid.uuid4().hex[:10]}'
        if not isinstance(sid,str) or not re.fullmatch(r'SHOT-'+episode+r'-WB[A-Za-z0-9_-]{1,40}',sid) or sid in unique:
            raise ValueError('镜头编号重复或不属于当前集')
        unique.add(sid)
        audio_kind=row.get('audio_kind','speech')
        if audio_kind not in ('speech','silent'):raise ValueError('请选择配音或无配音画面')
        for key in ('text','visual'):
            minimum=0 if key=='text' and audio_kind=='silent' else 1
            if not isinstance(row.get(key),str) or not minimum<=len(row[key].strip())<=1000:
                raise ValueError(f'镜头{i+1}需要完整台词和画面说明（最多1000字）')
        if row.get('speaker_id') not in known:raise ValueError(f'镜头{i+1}说话角色不属于当前项目，请选旁白或已核对角色')
        duration=row.get('duration_seconds',4)
        if isinstance(duration,bool) or not isinstance(duration,(float,int)) or not math.isfinite(duration) or not 1<=duration<=15:
            raise ValueError('每个镜头预计时长须为1到15秒')
        if row.get('render_kind') not in ('screen','control'):raise ValueError('请选择屏幕镜头或人物动作预演')
        if row.get('environment') not in ('modern_room','modern_corridor','ancient_courtyard') or row.get('action') not in CONTROL_ACTIONS:
            raise ValueError('无效的本地动作模板')
        lines=row.get('screen_lines',[])
        if not isinstance(lines,list) or len(lines)>6 or any(not isinstance(s,str) or len(s)>80 for s in lines):raise ValueError('屏幕内容最多6行，每行80字')
        title=row.get('screen_title','剧情提示')
        if not isinstance(title,str) or len(title)>80:raise ValueError('屏幕标题过长')
        cast=row.get('cast_ids',[row['speaker_id']] if row['speaker_id']!='NARRATOR' else [])
        if not isinstance(cast,list) or len(cast)>4 or any(c not in known or c=='NARRATOR' for c in cast) or len(set(cast))!=len(cast):raise ValueError('出镜人物需要是当前项目的已核对角色')
        clean.append({key:row[key].strip() for key in ('text','visual','speaker_id','render_kind','environment','action')}|
                     {'id':sid,'duration_seconds':round(duration,3),'screen_title':title,'screen_lines':lines,'cast_ids':cast})
        if 'audio_kind' in row:clean[-1]['audio_kind']=audio_kind
        if 'framing' in row:
            if row['framing'] not in ('wide','medium','closeup','insert'):raise ValueError('无效的导演镜头景别')
            focus=row.get('focus_id','')
            if focus not in known|{'PROP_DOCUMENT','PROP_PHONE','PROP_POT','PROP_NOTICES',''}:raise ValueError('导演镜头焦点不属于当前项目')
            if row['framing'] in ('medium','closeup') and focus not in cast:raise ValueError('特写焦点角色没有在当前镜头出镜')
            if row['framing']=='insert':
                props={'modern_office':{'PROP_DOCUMENT','PROP_PHONE'},'modern_stairs':{'PROP_DOCUMENT','PROP_PHONE'},
                       'modern_store':{'PROP_PHONE'},'modern_dinner':{'PROP_NOTICES'},'modern_system':{'PROP_PHONE'},'modern_kitchen':{'PROP_PHONE','PROP_POT'}}
                if focus not in props.get(row['action'],set()):raise ValueError('当前场景不支持这个物件特写')
            clean[-1].update(framing=row['framing'],focus_id=focus)
    if sum(s['duration_seconds'] for s in clean)>120:raise ValueError('首集短视频预计总时长超过120秒，请缩短台本')
    return {'title':payload['title'].strip(),'shots':clean}


def _active(project,episode):
    if (str(project.resolve()),episode) in _RUNNING:return True
    job=read(directory(project,episode)/'job.json',{})
    if job.get('status')!='RUNNING' or not job.get('owner_pid'):return False
    try:os.kill(job['owner_pid'],0);return True
    except (OSError,TypeError):return False


def save_script(project,episode,payload):
    with _LOCK:
        if _active(project,episode):raise ValueError('本集正在生成，请等待完成后修改台本')
        prior=load_script(project,episode)
        expected=payload.get('expected_revision')
        if isinstance(expected,bool) or not isinstance(expected,int) or expected!=prior['revision']:
            raise ValueError('台本已被修改，请刷新后重新保存，避免覆盖另一份修改')
        clean=validate_script(project,episode,payload)
        signature=digest(clean)
        if signature==prior.get('signature'):return inventory(project,episode)
        revision=prior['revision']+1
        data={'schema_version':1,'project_id':project.name,'episode_id':episode,'revision':revision,
              'signature':signature,'review_status':'PENDING','source':'PRODUCTION_SCRIPT','updated_at':time.time(),**clean}
        folder=directory(project,episode)
        write_json(folder/'revisions'/f'{revision:03d}-{signature[:12]}.json',data)
        write_json(folder/'script.json',data)
        # Media is immutable and retained. Status depends on the script hash;
        # audio and motion caches independently reuse only unchanged inputs.
        return inventory(project,episode)


def effective_duration(project,episode,row,script):
    audio=read(directory(project,episode)/'audio.json',{})
    if audio.get('script_signature')!=script['signature']:return row['duration_seconds']
    return next((line['clip_duration'] for line in audio.get('lines',[]) if line['shot_id']==row['id']),row['duration_seconds'])


def workflow_shots(project,episode):
    script=load_script(project,episode)
    return [{'id':row['id'],'episode_id':episode,'scene_id':f"{episode}-WB-{i+1:03d}",
        'duration_seconds':effective_duration(project,episode,row,script),
        'character_ids':row.get('cast_ids',[row['speaker_id']] if row['speaker_id']!='NARRATOR' else []),
        'action':row['action'],'environment':row['environment'],
        'excerpt':row['text']+'；画面：'+row['visual'],**({k:row[k] for k in ('framing','focus_id')} if 'framing' in row else {})} for i,row in enumerate(script['shots'])]


def inventory(project,episode):
    script=load_script(project,episode);folder=directory(project,episode)
    from scripts.humanoid_performance import status as humanoid_performance_status
    audio=read(folder/'audio.json',{});job=read(folder/'job.json',{})
    audio_ready=bool(script['signature']) and audio.get('script_signature')==script['signature'] and all(
        (project/l['path']).is_file() for l in audio.get('lines',[])) and len(audio.get('lines',[]))==len(script['shots'])
    stale=bool(job.get('script_signature')) and job['script_signature']!=script['signature']
    active=_active(project,episode)
    review=read(folder/'preview-review.json',{})
    final_reason='先生成并人工确认剧情、配音和字幕。'
    if audio_ready and review.get('status')=='PASS' and review.get('script_signature')==script['signature']:
        try:
            for row,line in zip(script['shots'],audio['lines']):
                if row['render_kind']=='control':_final_source(project,row,line['clip_duration'])
            final_reason=''
        except (ValueError,StopIteration):final_reason='人物镜头缺少当前台本对应的正式画面，或尚未通过视觉验收。'
    mode=read(project/'sources/import-mode.json',{}).get('mode','NOVEL')
    source_scenes=[]
    if mode=='SCRIPT':
        source_scenes=read(project/'writing-room/episodes'/episode/'script.json',{}).get('episode_script',{}).get('scenes',[])
    visual_direction=read(folder/'visual-direction.json',None)
    if visual_direction:
        try:_inside(project,visual_direction['image'])
        except (ValueError,OSError,KeyError,TypeError):visual_direction=None
    from scripts.episode_director_draft import load_draft
    director_draft_error=''
    try:director_draft=load_draft(project,episode,script)
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError) as error:
        director_draft=None;director_draft_error=str(error)
    return {'project_id':project.name,'episode_id':episode,'script':script,'import_mode':mode,'director_draft':director_draft,'director_draft_error':director_draft_error,'visual_direction':visual_direction,
        'character_performance':humanoid_performance_status(project),
        'source_scenes':source_scenes,'import_log':'logs/import.log' if (project/'logs/import.log').is_file() else '',
        'can_assemble_final':not final_reason,'final_block_reason':final_reason,
        'preview_review':review if review.get('script_signature')==script['signature'] else {'status':'PENDING'},
        'characters':[{'id':c['id'],'name':c['name']} for c in characters(project)],'control_actions':CONTROL_ACTIONS,
        'episodes':[e['id'] for e in read(project/'novel-anime-project.json',{}).get('episodes',[])],
        'audio':audio if audio_ready else {'status':'STALE' if audio else 'NOT_RUN','lines':[]},
        'job':{**job,'status':'STALE' if stale else job.get('status','NOT_RUN'),'active':active,
               'interrupted':bool(job and job.get('status')=='RUNNING' and not active),
               'ready':bool(job.get('output')) and (project/job['output']).is_file() and not stale and job.get('status')=='COMPLETED'},
        'can_generate':bool(script['signature']),'audio_ready':audio_ready}


def _duration(path):
    with wave.open(str(path),'rb') as audio:
        return audio.getnframes()/audio.getframerate()


def _inside(project,relative):
    path=(project/relative).resolve()
    if not path.is_relative_to(project.resolve()) or not path.is_file():raise ValueError('素材必须存在于当前项目目录中')
    return path


def _synthesize(project,script,provider='kokoro_local'):
    if provider not in ('kokoro_local','macos_say'):raise ValueError('预演只使用已安装的本地配音，无付费调用')
    adapter=KokoroSherpaTTS() if provider=='kokoro_local' else MacOSSayTTS()
    names={c['id']:c['name'] for c in characters(project)};lines=[];offset=0
    for row in script['shots']:
        silent=row.get('audio_kind')=='silent'
        female=names.get(row['speaker_id']) in ('陈念','沈岚','林秋','林晓')
        voice=('zf_001' if female else 'zm_010') if provider=='kokoro_local' else ('Tingting' if female else 'Reed (中文（中国大陆）)')
        synthesis_text=prepare_kokoro_text(row['text']) if provider=='kokoro_local' else row['text']
        short_local=provider=='kokoro_local' and bool(re.match(r'^[\u3400-\u9fff]{1,2}(?:[。？！……]+|$)',synthesis_text))
        actual_provider='macos_say' if short_local else provider
        actual_voice=('Tingting' if female else 'Reed (中文（中国大陆）)') if short_local else voice
        identity_data={'text':row['text'],'voice':voice,'provider':provider,'speed':1,'adapter':'v1'}
        if short_local or synthesis_text!=row['text']:
            identity_data.update(adapter='short-speech-v2',synthesis_text=synthesis_text,
                                 actual_provider=actual_provider,actual_voice=actual_voice)
        identity=digest(identity_data)
        if silent:identity=digest({'audio_kind':'silent','duration':row['duration_seconds'],'adapter':'v1'})
        path=directory(project,script['episode_id'])/'cache/audio'/f'{identity}.wav'
        if not path.is_file():
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_name(path.stem+'.pending.wav')
            if silent:
                with wave.open(str(temp),'wb') as audio:
                    audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(48000)
                    audio.writeframes(b'\0\0'*round(row['duration_seconds']*48000))
            else:
                result=(MacOSSayTTS() if short_local else adapter).synthesize(synthesis_text,voice=actual_voice,speed=1)
                source=path.with_suffix('.source'+('.aiff' if actual_provider=='macos_say' else '.wav'))
                source.write_bytes(result.audio)
                _command(['ffmpeg','-y','-i',str(source),'-ar','48000','-ac','1',str(temp)])
                source.unlink(missing_ok=True)
            temp.replace(path)
        spoken=0 if silent else _duration(path)
        clip=math.ceil(max(row['duration_seconds'],spoken+.65)*24)/24
        if clip>15:raise ValueError('单镜头真实配音超过15秒，请拆短台词')
        lines.append({'shot_id':row['id'],'text':'' if silent else row['text'],'speaker_id':row['speaker_id'],'voice':actual_voice,
            'actual_provider':'local_silence' if silent else actual_provider,'synthesis_text':'' if silent else synthesis_text,
            'path':path.relative_to(project).as_posix(),'audio_signature':identity,'spoken_duration':spoken,
            'clip_duration':clip,'start':round(offset+.2,3),'end':round(offset+.2+spoken,3),'clip_start':round(offset,3)})
        offset+=clip
    if offset>120:raise ValueError('真实配音使整集超过120秒，请拆集或缩短台词')
    data={'schema_version':1,'script_signature':script['signature'],'provider':provider,'status':'READY','duration':round(offset,3),'lines':lines}
    write_json(directory(project,script['episode_id'])/'audio.json',data)
    return data


def _command(args,timeout=300):
    completed=subprocess.run(args[:1]+(['-hide_banner','-loglevel','error'] if args[0]=='ffmpeg' else [])+args[1:],capture_output=True,text=True,timeout=timeout)
    if completed.returncode:raise ValueError((completed.stderr or completed.stdout)[-1800:])


def _screen_clip(project,row,duration,path):
    from scripts.episode_screen_renderer import render_screen
    render_screen({**row,'_series_title':read(project/'novel-anime-project.json',{}).get('title','剧情预演'),
                   '_episode_id':row['id'].split('-')[1]},duration,path)


def mouth_envelope(path,offset=.2):
    # Audio caches are 48 kHz mono signed 16-bit WAV. Energy drives opening only;
    # this is not phoneme alignment or a claim of production lip-sync.
    import array
    with wave.open(str(path),'rb') as audio:
        rate=audio.getframerate();samples=array.array('h',audio.readframes(audio.getnframes()))
    step=round(rate*.1);levels=[math.sqrt(sum(s*s for s in samples[i:i+step])/max(1,len(samples[i:i+step]))) for i in range(0,len(samples),step)]
    top=max(levels or [1]) or 1
    return [[0,0],[offset,0]]+[[round(offset+i*.1,3),round(min(1,e/top),3)] for i,e in enumerate(levels)]+[[round(offset+len(samples)/rate,3),0]]


def _control_clip(project,row,duration,path):
    blender=blender_executable()
    if not blender:raise ValueError('本地动作预演需要已安装的Blender；可改为屏幕镜头')
    folder=path.parent;folder.mkdir(parents=True,exist_ok=True)
    spec={'project_id':project.name,'shot_id':row['id'],'character_id':row['speaker_id'],
        'duration_seconds':duration,'width':480,'height':854,'fps':24,'environment':row['environment'],'action':row['action'],'cast_ids':row.get('cast_ids',[]),'characters':characters(project),
        'visual':row.get('visual',''),'text':row.get('text',''),'framing':row.get('framing'),'focus_id':row.get('focus_id',''),
        'project_path':str(project.resolve())}
    if row['speaker_id']!='NARRATOR' and (row['action'] in ('child_question','father_reassure') or row['action'] in MODERN_EVENTS):
        audio=read(directory(project,row['id'].split('-')[1])/'audio.json',{})
        line=next((l for l in audio.get('lines',[]) if l['shot_id']==row['id']),None)
        if line:
            name=next((c['name'] for c in characters(project) if c['id']==row['speaker_id']), '')
            modern_actor={'陈浩':'ChenHao','林晓':'LinXiao','主管':'Supervisor'}.get(name) if row['speaker_id'] in row.get('cast_ids',[]) else None
            spec.update(voice_actor=modern_actor if row['action'] in MODERN_EVENTS else 'Child' if row['action']=='child_question' else 'Dad',mouth_envelope=mouth_envelope(_inside(project,line['path'])))
    write_json(folder/'spec.json',spec)
    renderer='blender_story_preview.py' if row['action'] in STORY_EVENTS else 'blender_project_control.py'
    _command([str(blender),'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'scripts'/renderer),'--',str(folder/'spec.json'),str(folder)],timeout=1200)
    if not (folder/'control.mp4').is_file():raise ValueError('Blender没有生成控制视频，请检查本镜头的道具与角色焦点')
    shutil.copyfile(folder/'control.mp4',path)


def _ass_time(seconds):
    centis=round(seconds*100);return f'{centis//360000}:{centis//6000%60:02d}:{centis//100%60:02d}.{centis%100:02d}'


def _subtitle_text(text):
    text=text.replace('\\','＼').replace('{','｛').replace('}','｝').replace('\r','').replace('\n',' ')
    return r'\N'.join(text[i:i+17] for i in range(0,len(text),17))


def _subtitles(audio,path,preview,script=None):
    events=[]
    duration=audio['duration']
    if preview:events.append(f'Dialogue: 0,0:00:00.00,{_ass_time(duration)},Watermark,,0,0,0,,剧情预演 · 动作简模 · 待画面验收')
    rows={r['id']:r for r in (script or {}).get('shots',[])}
    for line in audio['lines']:
        row=rows.get(line['shot_id'],{})
        if row.get('render_kind')=='control' and row.get('screen_lines'):
            screen_text=_subtitle_text(' '.join(row['screen_lines']))
            events.append(f"Dialogue: 0,{_ass_time(line['clip_start'])},{_ass_time(line['clip_start']+line['clip_duration'])},Screen,,0,0,0,,{screen_text}")
        if not line['text']:continue
        events.append(f"Dialogue: 1,{_ass_time(line['start'])},{_ass_time(line['end'])},Default,,0,0,0,,{_subtitle_text(line['text'])}")
    path.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 480\nPlayResY: 854\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,PingFang SC,23,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,1,2,0,2,24,24,84,1\nStyle: Watermark,PingFang SC,14,&H00ECECEC,&H000000FF,&H00202020,&H80000000,0,0,0,0,100,100,0,0,1,1,0,8,20,20,35,1\nStyle: Screen,PingFang SC,19,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,1,2,0,8,35,35,75,1\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'+'\n'.join(events)+'\n',encoding='utf-8')
    srt=path.with_suffix('.srt')
    def stamp(s):
        ms=round(s*1000);return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'
    srt.write_text('\n\n'.join(f"{i}\n{stamp(line['start'])} --> {stamp(line['end'])}\n{line['text']}" for i,line in enumerate((l for l in audio['lines'] if l['text']),1))+'\n',encoding='utf-8')


def _mix(audio,project,directory):
    inputs=[];filters=[];labels=[]
    for i,line in enumerate(audio['lines']):
        inputs+=['-i',str(_inside(project,line['path']))]
        filters.append(f'[{i}:a]adelay={round(line["start"]*1000)}:all=1[a{i}]');labels.append(f'[a{i}]')
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0,apad,atrim=duration={audio["duration"]},loudnorm=I=-16:TP=-1:LRA=9[out]')
    output=directory/'mix.wav'
    _command(['ffmpeg','-y',*inputs,'-filter_complex',';'.join(filters),'-map','[out]','-ar','48000','-ac','2',str(output)])
    return output


def _final_source(project,row,duration):
    from scripts.low_cost_video import status as remote_status
    from scripts.project_shot_workflow import read as read_workflow, state_path
    result=remote_status(project,row['id'])
    binding=read_workflow(state_path(project),{}).get('bindings',{}).get(row['id'],{})
    if not result.get('ready') or result.get('review_status')!='PASS':raise ValueError('正式镜头缺失或尚未验收：'+row['id'])
    candidate=next(s for s in workflow_shots(project,row['id'].split('-')[1]) if s['id']==row['id'])
    control=binding.get('control',{})
    if (control.get('status')!='COMPLETED' or not control.get('output')
        or not (project/control['output']).is_file()
        or any(binding.get(k)!=candidate.get(k) for k in ('excerpt','scene_id','duration_seconds','action','environment','framing','focus_id'))):
        raise ValueError('镜头动作控制已失效，请按新台本重做：'+row['id'])
    if result.get('control')!=control['output']:raise ValueError('正式镜头来自旧动作控制，请重新验收：'+row['id'])
    path=_inside(project,result['output']);actual=probe_video(path)['duration_seconds']
    if abs(actual-duration)>.2:raise ValueError('正式镜头时长与配音不符，请重新生成或剪辑：'+row['id'])
    return path


def _update_job(project,episode,**values):
    path=directory(project,episode)/'job.json';data=read(path,{})|values;write_json(path,data)
    if data.get('id'):write_json(path.parent/'jobs'/data['id']/'job.json',data)


def _worker(project,episode,script,mode,provider,job_id):
    folder=directory(project,episode)/'jobs'/job_id;folder.mkdir(parents=True,exist_ok=True)
    try:
        _update_job(project,episode,status='RUNNING',phase='配音与字幕',progress=5,error='')
        audio=_synthesize(project,script,provider)
        clips=[]
        for i,(row,line) in enumerate(zip(script['shots'],audio['lines'])):
            _update_job(project,episode,phase=f'镜头 {i+1}/{len(script["shots"])}',progress=10+int(i/len(script['shots'])*65))
            renderer_file=ROOT/'scripts'/('episode_screen_renderer.py' if row['render_kind']=='screen' else 'blender_story_preview.py' if row['action'] in STORY_EVENTS else 'blender_project_control.py')
            renderer_hash=hashlib.sha256(renderer_file.read_bytes()+(ROOT/'scripts/blender_fixed_modern_story.py').read_bytes() if row['action'] in MODERN_EVENTS and row['render_kind']=='control' else renderer_file.read_bytes()).hexdigest()
            key=digest({'row':row,'duration':line['clip_duration'],'renderer':renderer_hash,'audio':line['audio_signature'] if row['speaker_id']!='NARRATOR' else '',
                        **({'characters':[{'id':c['id'],'name':c['name']} for c in characters(project)]} if row['action'] in MODERN_EVENTS and row['render_kind']=='control' else {})})
            output=directory(project,episode)/'cache/clips'/key/'preview.mp4'
            if mode=='final' and row['render_kind']=='control':source=_final_source(project,row,line['clip_duration'])
            else:
                if not output.is_file():
                    output.parent.mkdir(parents=True,exist_ok=True)
                    (_control_clip if row['render_kind']=='control' else _screen_clip)(project,row,line['clip_duration'],output)
                source=output
            normalized=folder/f'clip-{i:03d}.mp4'
            filters='scale=480:854:force_original_aspect_ratio=decrease,pad=480:854:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24'
            if row['render_kind']=='control' and '黑屏' in row['visual']:
                filters+=f",fade=t=out:st={max(0,line['clip_duration']-.7)}:d=0.7"
            _command(['ffmpeg','-y','-i',str(source),'-an','-vf',filters,
                '-t',str(line['clip_duration']),'-c:v','libx264','-pix_fmt','yuv420p',str(normalized)])
            clips.append(normalized)
        _update_job(project,episode,phase='声音、字幕与镜头总装',progress=80)
        concat=folder/'concat.txt';concat.write_text('\n'.join(f"file '{p.name}'" for p in clips))
        video=folder/'picture.mp4';_command(['ffmpeg','-y','-f','concat','-safe','1','-i',str(concat),'-c','copy',str(video)])
        mix=_mix(audio,project,folder);sub=folder/'subtitles.ass';_subtitles(audio,sub,mode=='preview',script)
        output=folder/('story-preview.mp4' if mode=='preview' else 'episode-master.mp4')
        # Subtitles live next to the job; avoid quoting user-controlled filesystem
        # paths into FFmpeg's filter grammar.
        completed=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i','picture.mp4','-i','mix.wav','-vf','ass=subtitles.ass','-map','0:v','-map','1:a','-c:v','libx264','-c:a','aac','-b:a','160k','-pix_fmt','yuv420p','-t',str(audio['duration']),'-movflags','+faststart',output.name],cwd=folder,capture_output=True,text=True,timeout=300)
        if completed.returncode:raise ValueError(completed.stderr[-1800:])
        media=probe_video(output)
        _command(['ffmpeg','-i',str(output),'-map','0:a:0','-f','null','-'])
        _command(['ffmpeg','-i',str(output),'-f','null','-'])
        if (media['width'],media['height'])!=(480,854):raise ValueError('总装尺寸与预演规格不符')
        if abs(media['duration_seconds']-audio['duration'])>.25:raise ValueError('总装时长与声音时间轴不符')
        qc={'status':'PASS','duration':media['duration_seconds'],'expected_duration':audio['duration'],'subtitle_count':sum(bool(l['text']) for l in audio['lines']),
            'shot_count':len(clips),'frame_size':[480,854],'fps':24,'decode':'PASS','human_review':'PENDING','mode':mode,'script_signature':script['signature']}
        write_json(folder/'qc.json',qc)
        poster_time=next((l['clip_start']+l['clip_duration']*.65 for r,l in zip(script['shots'],audio['lines']) if r['action']=='father_reassure'),min(.5,audio['duration']/2))
        _command(['ffmpeg','-y','-ss',str(poster_time),'-i',str(output),'-frames:v','1',str(folder/'poster.png')])
        _update_job(project,episode,status='COMPLETED',phase='等待人工审片',progress=100,output=output.relative_to(project).as_posix(),
                    subtitles=sub.relative_to(project).as_posix(),qc=(folder/'qc.json').relative_to(project).as_posix(),poster=(folder/'poster.png').relative_to(project).as_posix(),human_review='PENDING')
    except Exception as error:_update_job(project,episode,status='ERROR',phase='需要处理',error=str(error),progress=0)
    finally:
        with _LOCK:_RUNNING.discard((str(project.resolve()),episode))


def start(project,episode,payload):
    with _LOCK:
        script=load_script(project,episode)
        if not script['signature']:raise ValueError('请先保存整理后的台本')
        if payload.get('expected_revision')!=script['revision']:raise ValueError('台本已变化，请刷新后再生成')
        mode=payload.get('mode','preview');provider=payload.get('provider','kokoro_local')
        if mode not in ('preview','final') or provider not in ('kokoro_local','macos_say'):raise ValueError('无效的总装方式或本地配音服务')
        identity=(str(project.resolve()),episode)
        if _active(project,episode):raise ValueError('本集已在生成中')
        prior=read(directory(project,episode)/'job.json',{})
        resume=payload.get('resume',False)
        if resume and (prior.get('script_signature')!=script['signature'] or prior.get('mode')!=mode or prior.get('provider')!=provider):
            raise ValueError('台本或生成方式已变化，请重新创建任务，原结果保留')
        if mode=='final':
            audio=read(directory(project,episode)/'audio.json',{})
            if audio.get('script_signature')!=script['signature']:raise ValueError('先生成并检查当前台本的真实声音时间轴')
            review=read(directory(project,episode)/'preview-review.json',{})
            if review.get('script_signature')!=script['signature'] or review.get('status')!='PASS' or review.get('provider')!=provider:
                raise ValueError('先人工确认当前台本的剧情、配音和字幕')
            for row,line in zip(script['shots'],audio.get('lines',[])):
                if row['render_kind']=='control':_final_source(project,row,line['clip_duration'])
            if len(audio.get('lines',[]))!=len(script['shots']):raise ValueError('正式声音时间轴不完整')
        job_id=prior.get('id') if resume and prior.get('id') else uuid.uuid4().hex
        _update_job(project,episode,id=job_id,owner_pid=os.getpid(),script_signature=script['signature'],mode=mode,provider=provider,status='RUNNING',phase='排队',progress=0,error='',output='',subtitles='',qc='')
        _RUNNING.add(identity)
        threading.Thread(target=_worker,args=(project,episode,deepcopy(script),mode,provider,job_id),daemon=True).start()
        return inventory(project,episode)


def review_preview(project,episode,payload):
    with _LOCK:
        current=inventory(project,episode);job=current['job']
        if not job.get('ready') or job.get('active') or job.get('mode')!='preview' or payload.get('job_id')!=job.get('id'):
            raise ValueError('请先观看当前版本的剧情预演再确认')
        if any(payload.get(k) is not True for k in ('story_checked','voice_checked','subtitles_checked')):
            raise ValueError('请分别确认剧情、配音和字幕')
        data={'status':'PASS','script_signature':current['script']['signature'],'provider':job['provider'],
              'job_id':job['id'],'note':str(payload.get('note',''))[:1000],'reviewed_at':time.time()}
        write_json(directory(project,episode)/'preview-review.json',data)
        _update_job(project,episode,human_review='PASS')
        return inventory(project,episode)
