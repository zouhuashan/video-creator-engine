"""Deterministic blocking for supported scenes; no dialogue rewrite or paid call."""
MODERN_EVENTS={'modern_office':'办公室递通知、问答', 'modern_stairs':'楼梯坐下、低头反应',
    'modern_store':'便利店隔架而坐', 'modern_door':'家门相遇、停步',
    'modern_dinner':'餐桌夹菜、夫妻问答', 'modern_system':'手机震动、锁屏反应',
    'modern_kitchen':'旧锅推进、神情变化'}

def plan_row(row,characters):
    result=dict(row)
    # These first templates require the script's explicit roles; unfamiliar casts
    # remain unassigned instead of being replaced with another story's actors.
    names={c['name']:c['id'] for c in characters}
    if not all(n in names for n in ('陈浩','林晓')):return result
    location=row.get('screen_title','') or row.get('visual','').split('｜')[0]
    event=next((v for k,v in [('办公室','modern_office'),('楼梯','modern_stairs'),('便利店','modern_store'),
        ('家门','modern_door'),('餐桌','modern_dinner'),('系统出现','modern_system'),('厨房','modern_kitchen')] if k in location),None)
    if not event:return result
    cast={'modern_office':['陈浩','主管'],'modern_stairs':['林晓'],'modern_store':['陈浩','林晓'],
        'modern_door':['陈浩','林晓'],'modern_dinner':['陈浩','林晓'],'modern_system':['陈浩','林晓'],'modern_kitchen':['陈浩']}[event]
    result['screen_lines']=[line for line in row.get('screen_lines',[]) if line!='陈浩愣住。']
    result.update(render_kind='control',action=event,environment='modern_corridor' if event in ('modern_door','modern_stairs') else 'modern_room',
                  cast_ids=[names[n] for n in cast if n in names])
    return result

def apply_plan(project,episode,payload):
    from scripts import episode_workbench as w
    with w._LOCK:
        script=w.load_script(project,episode)
        if payload.get('expected_revision')!=script['revision']:raise ValueError('台本已变化，请刷新后再补动作')
        if w._active(project,episode):raise ValueError('本集正在生成，请完成后再补动作')
        rows=[plan_row(r,w.characters(project)) for r in script['shots']]
        if rows==script['shots']:raise ValueError('当前镜头已接入动作，或尚无匹配的人物/场景模板，请逐镜选择动作')
        w.save_script(project,episode,{'title':script['title'],'shots':rows,'expected_revision':script['revision']})
        return w.inventory(project,episode)
