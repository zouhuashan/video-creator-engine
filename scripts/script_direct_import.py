"""Deterministic screenplay parsing into the existing scene/script contracts.

No novel selection, sentence scoring, LLM or dialogue rewriting runs here.
"""
from __future__ import annotations
import re
from pathlib import Path
from scripts.novel_anime_project import utc_timestamp
from scripts.novel_scene_backfill import _review, _source_provenance, save_scene_seed, apply_scene_seed

HEADER = re.compile(r'^【场景\s*(\d+)\s*[｜|]\s*([^｜|]+?)\s*[｜|]\s*([^】]+?)】$')
SCREEN = ('屏幕', '手机银行余额', '房贷提醒', '孩子学校群', '手机界面', '锅底刻')


def parse_script(text: str) -> dict:
    text = text.lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n')
    scenes=[]; current=None; before=[]
    for number,line in enumerate(text.splitlines(),1):
        match=HEADER.fullmatch(line.strip())
        if match:
            if int(match[1])<1:raise ValueError(f'第{number}行：场景编号须大于0')
            if any(s['number']==int(match[1]) for s in scenes):
                raise ValueError(f'第{number}行：场景编号重复')
            current={'number':int(match[1]),'location':match[2],'time':match[3],'lines':[]};scenes.append(current)
        elif current is not None:current['lines'].append(line)
        elif line.strip():before.append(line)
    if not scenes:raise ValueError('未找到场景块，请使用【场景1｜公司办公室｜白天】格式。')
    # Bare speaker labels are authoritative; object/interface labels are excluded.
    names=[]
    for scene in scenes:
        for block in re.split(r'\n\s*\n','\n'.join(scene['lines']).strip()):
            line=block.strip().splitlines()[0] if block.strip() else ''
            match=re.match(r'^([\u3400-\u9fff]{2,4})[：:]',line.strip())
            if match and not match[1].endswith('回复') and match[1] not in ('旁白','回复','屏幕出现') and not any(k in match[1] for k in SCREEN):
                if match[1] not in names:names.append(match[1])
            message=re.match(r'^(?:老婆|妻子|丈夫|老公)?([\u3400-\u9fff]{2,4}?)(?:发来微信|回复|手机界面)[：:]',line.strip())
            if message and message[1] not in names:names.append(message[1])
    all_units=[]
    for scene in scenes:
        focus=None;units=[];pending_screen=False
        for block in re.split(r'\n\s*\n','\n'.join(scene['lines']).strip()):
            lines=[line.strip() for line in block.splitlines() if line.strip()]
            if not lines:continue
            label=lines[0];kind='ACTION';speaker=None;body='\n'.join(lines)
            match=re.fullmatch(r'(.+?)[：:](.*)',label)
            if match:
                cue=match[1];body='\n'.join(([match[2]] if match[2] else [])+lines[1:])
                if cue=='旁白':kind='NARRATION'
                elif cue in names:kind='DIALOGUE';speaker=cue;focus=cue
                elif any(k in cue for k in SCREEN):kind='VISUAL';pending_screen=not body
                elif cue=='回复':
                    if not focus:raise ValueError(f'场景{scene["number"]}的“回复”没有明确说话人，请改为角色名：')
                    kind='DIALOGUE';speaker=focus
                elif any(k in cue for k in ('回复','发来微信','发消息')):
                    found=next((name for name in names if name in cue),None)
                    # “她给陈浩发消息” names the receiver, not the sender.
                    if cue.startswith(('她','他')):found=focus
                    if not found:raise ValueError(f'场景{scene["number"]}无法确定“{cue}”的发送者，请改为角色名：')
                    kind='DIALOGUE';speaker=found;focus=found
                else:
                    kind='VISUAL';body='\n'.join(lines)
            elif pending_screen or (label.startswith('【') and label.endswith('】')):
                kind='VISUAL';pending_screen=False
            else:
                # Only a named subject at the start changes scene focus.
                named=next((name for name in names if label.startswith(name)),None)
                if named:focus=named
            if not body:continue
            unit={'kind':kind,'text':body,'speaker':speaker,'cue':match[1] if match else ''}
            units.append(unit);all_units.append(unit)
        if not units:raise ValueError(f'场景{scene["number"]}没有内容')
        scene['units']=units
    title=next((re.split('[：:]',s,maxsplit=1)[1].strip() for s in before if re.match(r'第\d+集[：:]',s)), '第1集')
    duration=next((int(m[1]) for s in before if (m:=re.search(r'目标时长[：:]\s*(?:\d+\s*[-—～]\s*)?(\d+)\s*秒',s))),90)
    return {'scenes':scenes,'names':names,'episode_title':title,'duration':max(45,min(120,duration))}


def candidates(parsed:dict,ip_code:str)->list[dict]:
    return [{'id':f'CHR-{ip_code}-AUTO-{i:03d}','name':name,'aliases':[], 'mentions':[],
             'total_mentions':sum(u['speaker']==name for s in parsed['scenes'] for u in s['units'])}
            for i,name in enumerate(parsed['names'],1)]


def apply_direct_script(project:Path,parsed:dict,source_sha:str)->dict:
    from scripts.novel_story_bible import load_bible
    from scripts.novel_web_import import _chapter_refs_for_candidate
    names={c['name']:c['id'] for c in load_bible(project)['characters']}
    refs=_chapter_refs_for_candidate(project,{},source_sha)
    # The source catalog uses chapter IDs; imports supply a fallback below.
    if not refs:
        raise ValueError('剧本来源记录缺失')
    scenes=[];total=sum(max(.3,len(u['text'])/5) for s in parsed['scenes'] for u in s['units'])
    scale=parsed['duration']/total
    for i,source in enumerate(parsed['scenes'],1):
        sid=f'S01E001-SC{i:03d}';units=[]
        for j,u in enumerate(source['units'],1):
            units.append({'id':f'UNIT-{sid}-{j:03d}','sequence':j,'kind':u['kind'],'text':u['text'],
                'speaker_character_id':names.get(u['speaker']),
                'emotion':{'label':'原台本','intensity':.35,'performance_note':'保持原对白，不重写'} if u['kind'] in ('DIALOGUE','NARRATION') else None,
                'sound':None,'estimated_duration_seconds':round(max(.3,len(u['text'])/5)*scale,4),
                'beat_ref':None,'provenance':_source_provenance(refs)})
        cast=[c['id'] for c in load_bible(project)['characters'] if any(c['name'] in u['text'] or c['name']==u['speaker'] for u in source['units'])]
        scenes.append({'id':sid,'sequence':i,'title':source['location'],'purpose':'用户剧本直导，原对白与动作顺序保留',
            'location_id':None,'time_of_day':source['time'],'character_ids':cast,'units':units,
            'provenance':_source_provenance(refs),'human_review':_review()})
    seed={'schema_version':1,'project_id':project.name,'source_sha256':source_sha,'full_text_stored':False,
          'derivation':'SCRIPT_DIRECT_NO_REWRITE','created_at':utc_timestamp(),
          'episodes':[{'episode_id':'S01E001','target_duration_seconds':parsed['duration'],'scenes':scenes}]}
    save_scene_seed(project,seed);result=apply_scene_seed(project,seed)
    return {**result,'source_sha256':source_sha,'full_text_stored':False,'mode':'SCRIPT'}


def create_workbench(project:Path,parsed:dict,*,expected_revision=0)->None:
    """Use the current editor and renderer; unspoken directions remain visual."""
    from scripts import episode_workbench as w
    from scripts.novel_episode_script import load_script_package
    rows=[]
    for scene in load_script_package(project)['episode_scripts'][0]['scenes']:
        pending=[]
        for unit in scene['units']:
            if unit['kind'] not in ('DIALOGUE','NARRATION'):
                pending.append(unit);continue
            rows.append(_row(scene,unit,pending,len(rows)+1));pending=[]
        if pending:rows.append(_row(scene,None,pending,len(rows)+1))
    if not rows:raise ValueError('剧本没有可制作镜头')
    total=sum(row['duration_seconds'] for row in rows)
    if total>parsed['duration'] and len(rows)<parsed['duration']:
        scale=(parsed['duration']-len(rows))/(total-len(rows))
        for row in rows:row['duration_seconds']=1+(row['duration_seconds']-1)*scale
    from scripts.script_action_plan import plan_row
    rows=[plan_row(row,w.characters(project)) for row in rows]
    w.save_script(project,'S01E001',{'title':parsed['episode_title'],'shots':rows,'expected_revision':expected_revision})


def scene_groups(scene):
    groups=[];pending=[]
    for unit in scene['units']:
        pending.append(unit)
        if unit['kind'] in ('DIALOGUE','NARRATION'):
            groups.append(pending);pending=[]
    if pending:groups.append(pending)
    return groups


def _row(scene,spoken,visual,index):
    return {'id':f'SHOT-S01E001-WB{index:03d}','speaker_id':spoken['speaker_character_id'] or 'NARRATOR' if spoken else 'NARRATOR',
        'text':spoken['text'] if spoken else '', 'audio_kind':'speech' if spoken else 'silent',
        'visual':scene['title']+'｜'+scene['time_of_day']+'\n'+'\n'.join(u['text'] for u in visual),
        'duration_seconds':max(1,min(15,sum(u['estimated_duration_seconds'] for u in visual)+
                                    (spoken['estimated_duration_seconds'] if spoken else 0))),
        'render_kind':'screen','screen_title':scene['title'],'screen_lines':[line for u in visual if u['kind']=='VISUAL' for line in u['text'].splitlines()][:6],
        'cast_ids':scene['character_ids'][:4],'environment':'modern_room','action':'look_phone'}
