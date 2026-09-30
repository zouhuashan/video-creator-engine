"""Reviewable editorial proposals, separate from canonical imports/current script."""
from pathlib import Path

def load_draft(project:Path,episode:str,current:dict)->dict|None:
    from scripts import episode_workbench as w
    path=w.directory(project,episode)/'director-draft.json'
    if not path.is_file():return None
    data=w.read(path,{})
    if data.get('episode_id')!=episode or data.get('project_id')!=project.name:
        raise ValueError('导演修改稿不属于当前项目/集数')
    w.validate_script(project,episode,{'title':data.get('title'),'shots':data.get('shots')})
    audit=w.read(w.directory(project,episode)/'director-adoptions.json',{}).get('adoptions',[])
    adopted=bool(audit and audit[-1].get('after_signature')==current.get('signature') and audit[-1].get('draft_signature')==w.digest(data))
    notes=data.get('change_notes',[]);notes=notes if isinstance(notes,list) and all(isinstance(n,str) for n in notes) else []
    shot_notes=data.get('shot_notes',{});shot_notes=shot_notes if isinstance(shot_notes,dict) else {}
    return {**data,'summary':str(data.get('summary','')),'visual_limit':str(data.get('visual_limit','正式美术未完成')),'change_notes':notes,'shot_notes':shot_notes,'draft_signature':w.digest(data),'adopted':adopted,'stale':not adopted and data.get('base_signature')!=current.get('signature')}

def adopt_draft(project:Path,episode:str,payload:dict)->dict:
    from scripts import episode_workbench as w
    with w._LOCK:
        current=w.load_script(project,episode)
        draft=load_draft(project,episode,current)
        if not draft:raise ValueError('本集没有导演修改稿')
        if draft.get('adopted'):raise ValueError('这版导演稿已采用，无需重复覆盖')
        if draft['stale'] or payload.get('expected_revision')!=current['revision']:
            raise ValueError('当前台本已变化，请重新核对导演修改稿，避免覆盖编辑')
        if payload.get('draft_signature')!=draft['draft_signature']:
            raise ValueError('导演修改稿已变化，请刷新后再采用')
        # Existing save supplies busy checks, immutable revisions and downstream
        # invalidation. Canonical source scripts and media are never overwritten.
        result=w.save_script(project,episode,{'title':draft['title'],'shots':draft['shots'],'expected_revision':current['revision']})
        audit_path=w.directory(project,episode)/'director-adoptions.json'
        history=w.read(audit_path,{'adoptions':[]})
        history['adoptions'].append({'draft_signature':draft['draft_signature'],'before_signature':current['signature'],
            'after_signature':result['script']['signature'],'timestamp':w.time.time()})
        w.write_json(audit_path,history)
        return w.inventory(project,episode)
