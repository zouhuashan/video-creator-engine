// A single project follows six production steps. Existing adapters keep ownership
// of generation; retired experiments remain stored but have no navigation entry.
const PRODUCTION_STEPS = [
  {view:'anime', label:'项目与小说', hint:'选择小说项目，先制作第一集。'},
  {view:'story', label:'剧本与分镜', hint:'先核对剧情草稿；每个镜头都要有明确内容。'},
  {view:'characters', label:'角色与场景', hint:'固定人物外观和场景，准备可复用的参考图。'},
  {view:'studio', workspace:'audio', label:'配音与字幕', hint:'先试听配音并固定时长，再制作视频。'},
  {view:'shots', label:'镜头与视频', hint:'控制视频只用于动作预演；最终画面要单独验收。'},
  {view:'studio', workspace:'render', label:'成片与审片', hint:'检查画面、声音、字幕和剧情，人工确认后再发布。'},
];
let productionStory = null;
let productionStoryRequest = 0;

function initProductionLayout() {
  document.body.classList.add('production-mode');
  document.getElementById('productionCharactersHost').append(document.getElementById('shotWorkflowPanel'));
  document.getElementById('productionVideoHost').append(document.getElementById('lowCostVideoPanel'));
  document.getElementById('lowCostVideoPanel').classList.add('panel');
  document.getElementById('productionVideoKeyHost').append(document.getElementById('productionVideoKeyFields'));
  for (const id of ['workspaceView', 'modernView', 'imageStudioView', 'projectsView', 'providersView', 'outputPanel', 'logPanel']) {
    const retired = document.getElementById(id);
    retired.setAttribute('aria-hidden', 'true');
    retired.inert = true;
  }
  const status = document.getElementById('shotWorkflowStatus');
  document.querySelector('#shotWorkflowPanel .shot-workflow-form').append(status);
  // Plain-language error feedback remains visible when the old log panel is hidden.
  document.getElementById('productionPrevious').addEventListener('click', () => navigateProduction(-1));
  document.getElementById('productionNext').addEventListener('click', () => navigateProduction(1));
  document.getElementById('productionProjectSelect').addEventListener('change', event => {
    if (state.currentView==='story' && productionDirty) {
      event.target.value=resolveActiveNovelProject();
      document.getElementById('productionEditorStatus').textContent='请先保存台本修改，再切换项目。';
      return;
    }
    setActiveNovelProject(event.target.value);
    productionStory = null;
    shotWorkflowData = null;
    state.studio = null;
    state.voiceTimeline = null;
    state.finalAudio = null;
    state.grayboxProjectId = event.target.value;
    document.getElementById('workflowNotice').classList.add('hidden');
    document.getElementById('lowCostKey').value = '';
    renderProductionProjectSelector();
    setView(state.currentView, state.currentWorkspace);
  });
  document.getElementById('productionEpisodeSelect').addEventListener('change', event => {
    if(productionDirty){event.target.value=productionEpisode;document.getElementById('productionEditorStatus').textContent='请先保存台本修改，再切换集数。';return;}
    productionEpisodesByProject.set(resolveActiveNovelProject(),event.target.value);
    loadProductionStory();
  });
}

function productionStepIndex() {
  return PRODUCTION_STEPS.findIndex(step => step.view === state.currentView &&
    (step.view !== 'studio' || step.workspace === state.currentWorkspace));
}
function navigateProduction(offset) {
  const step = PRODUCTION_STEPS[productionStepIndex() + offset];
  if (step) setView(step.view, step.workspace);
}
function renderProductionProjectSelector() {
  const select = document.getElementById('productionProjectSelect');
  select.innerHTML = state.animeProjects.length
    ? state.animeProjects.map(project => `<option value="${escapeHtml(project.directory_id)}">${escapeHtml(novelProjectOptionLabel(project))}</option>`).join('')
    : '<option value="">请先导入小说</option>';
  select.value = resolveActiveNovelProject();
  const project = state.animeProjects.find(item => item.directory_id === select.value);
  document.getElementById('statProject').textContent = project?.title || '未选择';
  document.getElementById('statProjectHint').textContent = project ? `${project.episode_count || 0} 集 · 独立项目` : '导入小说后开始';
  document.getElementById('statAssets').textContent = '按镜头准备';
  document.getElementById('statProviders').textContent = '本地 + Wan';
}
function configureProductionView() {
  const isShots = state.currentView === 'shots';
  document.body.dataset.productionView = state.currentView;
  const host = document.getElementById(isShots ? 'productionShotsHost' : 'productionCharactersHost');
  host.append(document.getElementById('shotWorkflowPanel'));
  document.getElementById('shotWorkflowHeading').textContent = isShots ? '准备当前镜头的动作控制' : '确定角色与场景';
  const index = productionStepIndex();
  const step = PRODUCTION_STEPS[index];
  document.getElementById('productionFlowFooter').classList.toggle('hidden', index < 0);
  document.getElementById('productionPrevious').disabled = index <= 0;
  document.getElementById('productionNext').disabled = index < 0 || index === PRODUCTION_STEPS.length - 1;
  document.getElementById('productionFooterHint').textContent = step ? `${index + 1} / 6 · ${step.hint}` : '';
  document.getElementById('productionStepHint').textContent = step?.hint || (state.currentView === 'settings' ? '设置服务，不会自动付费生成' : '导入小说后核对剧情草稿');
  renderProductionProjectSelector();
}
function clearProductionShotDisplay() {
  clearTimeout(shotWorkflowPollTimer);
  clearTimeout(lowCostPollTimer);
  shotWorkflowData = null;
  for (const id of ['shotWorkflowEpisode', 'shotWorkflowShot', 'shotWorkflowCharacter']) document.getElementById(id).innerHTML = '';
  for (const id of ['shotWorkflowCharacterDefinition', 'shotWorkflowSceneName', 'shotWorkflowSceneDefinition']) document.getElementById(id).value = '';
  for (const id of ['shotWorkflowControlVideo', 'shotWorkflowCharacterImage', 'shotWorkflowSceneImage', 'lowCostResult']) {
    const media = document.getElementById(id);
    media.classList.add('hidden');
    media.removeAttribute('src');
  }
  for (const id of ['shotWorkflowSave', 'shotWorkflowRender', 'shotWorkflowCharacterFile', 'shotWorkflowSceneFile', 'shotWorkflowControlFile', 'lowCostStart', 'lowCostResume']) document.getElementById(id).disabled = true;
  for (const id of ['shotWorkflowConfirmed', 'lowCostReviewed', 'lowCostConsent']) document.getElementById(id).checked = false;
  document.getElementById('shotWorkflowPromptLinks').innerHTML = '';
  document.getElementById('shotWorkflowExcerpt').textContent = '';
  document.getElementById('shotWorkflowSavedSummary').textContent = '';
  document.getElementById('shotWorkflowBlendDownload').classList.add('hidden');
  document.getElementById('lowCostReviewPanel').classList.add('hidden');
  document.getElementById('lowCostPrompt').value = '';
  document.getElementById('lowCostQuoteText').textContent = '准备当前项目的镜头后，再查询费用。';
  document.getElementById('lowCostStatus').textContent = '正在载入当前项目…';
}
function renderProductionProjects() {
  const target = document.getElementById('animeProjects');
  target.innerHTML = state.animeProjects.length ? state.animeProjects.map(project => {
    const selected = project.directory_id === resolveActiveNovelProject();
    return `<article class="production-project-card${selected ? ' selected' : ''}">
      <div><span class="section-kicker">${selected ? '当前制作项目' : '已有项目'}</span><h3>${escapeHtml(project.title)}</h3>
      <p>${project.episode_count || 0} 集 · 剧本草稿 ${project.episode_scripts?.script_count || 0} 集 · 角色候选 ${project.story_bible?.character_count || 0} 个</p>
      <small>角色与分镜仍需核对。已有素材和结果保存在各自项目中。</small></div>
      <button class="primary-button" data-production-project="${escapeHtml(project.directory_id)}">${selected ? '继续制作' : '选择项目'}</button></article>`;
  }).join('') : '<div class="empty-state">还没有项目。点击“导入小说”开始。</div>';
  target.insertAdjacentHTML('beforeend','<p id="productionProjectStatus" role="status"></p>');
  target.querySelectorAll('[data-production-project]').forEach(button => {
    const remove=document.createElement('button');remove.className='project-delete-button';
    remove.textContent='删除项目';remove.dataset.productionDelete=button.dataset.productionProject;
    remove.addEventListener('click',()=>deleteProductionProject(remove.dataset.productionDelete,remove));
    const actions=document.createElement('div');actions.className='production-project-actions';
    button.replaceWith(actions);actions.append(button,remove);
  });
  target.querySelectorAll('[data-production-project]').forEach(button => button.addEventListener('click', () => {
    setActiveNovelProject(button.dataset.productionProject);
    state.studio = null;
    productionStory = null;
    shotWorkflowData = null;
    setView('story');
  }));
}
async function deleteProductionProject(projectId,button) {
  const project=state.animeProjects.find(item=>item.directory_id===projectId);
  if(!project)return;
  if(!await confirmProductionDelete(project))return;
  button.disabled=true;button.textContent='删除中…';
  const previous=resolveActiveNovelProject();
  try {
    const result=await api('/api/novel-anime/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:projectId,confirm_delete:true})});
    ++productionStoryRequest;++productionWorkbenchRequest;
    clearTimeout(productionWorkbenchTimer);productionWorkbench=null;productionStory=null;productionDirty=false;
    productionEpisodesByProject.delete(projectId);clearProductionShotDisplay();
    if(state.novelImportResult?.directory_id===projectId)state.novelImportResult=null;
    if(previous===projectId)clearActiveNovelProject();
    state.grayboxProjectId=null;state.studio=null;state.voiceTimeline=null;state.finalAudio=null;
    // Refresh only the project list: deletion stays on the management page.
    const fresh=await api('/api/novel-anime/projects');state.animeProjects=fresh.projects;
    const next=previous!==projectId&&fresh.projects.some(p=>p.directory_id===previous)?previous:result.default_project_id;
    if(next)setActiveNovelProject(next);else clearActiveNovelProject();
    setView('anime');
    document.getElementById('productionProjectStatus').textContent=`已删除《${project.title}》。${next?'可以选择其他项目继续制作。':'请导入新的小说。'}`;
  } catch(error) {
    document.getElementById('productionProjectStatus').textContent=error.message;
    button.disabled=false;button.textContent='删除项目';
  }
}
function confirmProductionDelete(project) {
  return new Promise(resolve=>{
    const dialog=document.createElement('dialog');dialog.className='production-delete-dialog';
    dialog.innerHTML=`<form method="dialog"><h2>删除《${escapeHtml(project.title)}》？</h2><p>将删除该项目的小说导入资料、台本、角色、素材及生成视频，无法撤销。其他项目不受影响。</p><div class="production-project-actions"><button class="secondary-button" value="cancel" autofocus>取消</button><button class="project-delete-button" value="delete">确认删除</button></div></form>`;
    dialog.addEventListener('close',()=>{const confirmed=dialog.returnValue==='delete';dialog.remove();resolve(confirmed);},{once:true});
    document.body.append(dialog);dialog.showModal();
  });
}
// The edited episode contract owns script, actual voice timing and assembly.
let productionEpisode = 'S01E001';
let productionWorkbench = null;
let productionWorkbenchRequest = 0;
let productionWorkbenchTimer = null;
let productionDirty = false;
const productionEpisodesByProject = new Map();
const episodeLabel = id => `第 ${Number(id.slice(-3))} 集`;
const workbenchEndpoint = (project, episode) => `/api/novel-anime/projects/${encodeURIComponent(project)}/episode-workbench/${episode}`;

async function loadProductionStory() {
  const project = resolveActiveNovelProject();
  const request = ++productionStoryRequest;
  const target = document.getElementById('productionScriptContent');
  if (!project) { target.innerHTML = '<div class="empty-state">请先选择小说。</div>'; return; }
  productionEpisode = productionEpisodesByProject.get(project) || 'S01E001';
  target.innerHTML = '<div class="empty-state">正在载入台本…</div>';
  try {
    const data = await api(workbenchEndpoint(project,productionEpisode));
    if (request !== productionStoryRequest || project !== resolveActiveNovelProject() || state.currentView !== 'story') return;
    productionStory = {project,data};
    productionDirty = false;
    const select = document.getElementById('productionEpisodeSelect');
    select.innerHTML = data.episodes.map(id => `<option value="${escapeHtml(id)}">${episodeLabel(id)}</option>`).join('');
    select.value = productionEpisode;
    renderProductionStory();
  } catch (error) { if (request === productionStoryRequest) target.innerHTML = `<p class="production-attention">${escapeHtml(error.message)}</p>`; }
}
function readProductionDraft() {
  const shots = [...document.querySelectorAll('#productionScriptContent [data-script-row]')].map(card => {
    const row = {...productionStory.data.script.shots.find(s => s.id === card.dataset.scriptRow)};
    card.querySelectorAll('[data-script-field]').forEach(input => {
      const key = input.dataset.scriptField;
      row[key] = key === 'duration_seconds' ? Number(input.value) : key === 'screen_lines' ? input.value.split('\n').filter(s => s.trim()) : input.value;
    });
    return row;
  });
  return {title:document.getElementById('productionScriptTitle').value,shots,
    expected_revision:productionStory.data.script.revision};
}
function renderVisualDirection(data) {
  const art=data.visual_direction;return art?.media_url?`<details class="production-art-direction"><summary>美术方向参考图（不是当前动画画面）</summary><figure><img src="${escapeHtml(art.media_url)}" alt="${escapeHtml(art.title)}" style="max-width:380px;width:100%;height:auto" loading="lazy"><figcaption>${escapeHtml(art.note)}</figcaption></figure></details>`:'';
}

function renderProductionStory() {
  if (!productionStory || productionStory.project !== resolveActiveNovelProject()) return;
  const data=productionStory.data, script=data.script, active=data.job.active;
  const target=document.getElementById('productionScriptContent');
  const speakers=[{id:'NARRATOR',name:'旁白'},...data.characters];
  const selectOptions=(options,value) => options.map(([id,label])=>`<option value="${escapeHtml(id)}" ${id===value?'selected':''}>${escapeHtml(label)}</option>`).join('');
  const field=(index,label,key,value,type='textarea')=>`<label class="production-field">${label}${type==='textarea'?`<textarea aria-label="镜头 ${index} ${label}" data-script-field="${key}" rows="2">${escapeHtml(value)}</textarea>`:`<input aria-label="镜头 ${index} ${label}" data-script-field="${key}" type="${type}" ${type==='number'?'min="1" max="15" step="0.1"':''} value="${escapeHtml(value)}">`}</label>`;
  target.innerHTML=`<div class="production-script-summary"><strong>${script.shots.length} 个镜头 · ${script.shots.filter(s=>s.render_kind==='control').length} 个人物 / 道具动态镜头 · 预计 ${script.shots.reduce((sum,s)=>sum+s.duration_seconds,0).toFixed(1)} 秒</strong><span>台本版本 ${script.revision} · ${script.revision?'已保存，等待你审读':'导入草稿，需要整理'}</span></div>
    ${data.import_mode==='SCRIPT'?`<p class="helper-text">剧本直导 · 导入原文可查看 · ${data.source_scenes.length} 个场景 · 未进行小说改写</p><details><summary>查看导入的原始场景与对白</summary>${data.source_scenes.map(scene=>`<article><h3>${escapeHtml(scene.title)} · ${escapeHtml(scene.time_of_day)}</h3>${scene.units.map(u=>`<p><small>${escapeHtml(u.kind==='DIALOGUE'?(data.characters.find(c=>c.id===u.speaker_character_id)?.name||'角色'):u.kind==='NARRATION'?'旁白':u.kind==='VISUAL'?'屏幕内容':'动作说明')}</small><br>${escapeHtml(u.text).replace(/\n/g,'<br>')}</p>`).join('')}</article>`).join('')}</details>`:''}
    ${renderVisualDirection(data)}
    ${data.director_draft_error?`<p role="alert">导演修改稿暂不可用：${escapeHtml(data.director_draft_error)}；当前台本仍可编辑。</p>`:''}
    ${data.director_draft?`<details class="production-director-draft"><summary>导演修改稿 · ${escapeHtml(data.director_draft.title)} · 约 ${data.director_draft.shots.reduce((sum,r)=>sum+r.duration_seconds,0).toFixed(0)} 秒</summary><p>${escapeHtml(data.director_draft.summary)}</p><p class="production-attention">${escapeHtml(data.director_draft.visual_limit)} 原稿和旧视频保留；采用后旧配音/成片会失效，需要重做。不会自动生成或付费。</p><ul>${data.director_draft.change_notes.map(n=>`<li>${escapeHtml(n)}</li>`).join('')}</ul>${data.director_draft.shots.map((r,i)=>`<article><h3>镜头 ${i+1} · ${escapeHtml(r.screen_title)} · ${r.duration_seconds.toFixed(1)} 秒</h3><p>${escapeHtml(data.director_draft.shot_notes[r.id]||'')}</p><p><strong>${escapeHtml(data.characters.find(c=>c.id===r.speaker_id)?.name||'旁白')}</strong>：${escapeHtml(r.text||'无配音，以画面讲述')}</p><p>${escapeHtml(r.visual).replace(/\n/g,'<br>')}</p>${r.screen_lines.length?`<p>画面字：${escapeHtml(r.screen_lines.join(' / '))}</p>`:''}</article>`).join('')}<button id="productionAdoptDirector" class="primary-button" ${active||data.director_draft.stale||data.director_draft.adopted?'disabled':''}>${data.director_draft.adopted?'已采用这版导演稿':'采用这版导演稿（保留原稿）'}</button><p>${data.director_draft.adopted?'当前已采用此稿，可到成片与审片查看新预演的进度；正式美术仍待落实。':data.director_draft.stale?'当前台本与提案的底稿不同，需要重新核对后再采用。':'这是剧情与镜头修改提案，尚未渲染新视频；美术与表演还需落实。'}</p></details>`:''}
    ${data.import_log?`<a href="/media/${encodeURIComponent(data.project_id)}/logs/import.log" target="_blank" rel="noopener">查看导入详细日志</a>`:''}
    <label class="production-field">本集标题<input id="productionScriptTitle" value="${escapeHtml(script.title)}" maxlength="120"></label>
    <p class="helper-text">“台词 / 旁白”会进入配音和字幕；“画面说明”和屏幕内容只用于画面。保存修改后，旧配音和成片会失效，未改动的素材可复用。</p>
    <fieldset class="production-editor" ${active?'disabled':''}>${script.shots.map((row,i)=>`<article class="production-script-row" data-script-row="${escapeHtml(row.id)}">
      <div class="production-row-heading"><strong>镜头 ${i+1}</strong><small>${escapeHtml(row.id)}</small><div><button type="button" data-row-move="${i}" data-offset="-1" ${i===0?'disabled':''}>上移</button><button type="button" data-row-move="${i}" data-offset="1" ${i===script.shots.length-1?'disabled':''}>下移</button><button type="button" data-row-delete="${i}" ${script.shots.length===1?'disabled':''}>删除</button></div></div>
      <div class="production-row-grid"><label class="production-field">说话人<select aria-label="镜头 ${i+1} 说话人" data-script-field="speaker_id">${selectOptions(speakers.map(s=>[s.id,s.name]),row.speaker_id)}</select></label>${field(i+1,'预计秒数','duration_seconds',row.duration_seconds,'number')}<label class="production-field">预演画面<select aria-label="镜头 ${i+1} 预演画面" data-script-field="render_kind">${selectOptions([['screen','屏幕 / 文字示意'],['control','人物动作简模']],row.render_kind)}</select></label></div>
      <p class="helper-text">${row.framing?`导演景别：${escapeHtml({wide:'全景',medium:'中景',closeup:'人物特写',insert:'物件特写'}[row.framing])} · `:''}出镜人物：${escapeHtml((row.cast_ids||[]).map(id=>data.characters.find(c=>c.id===id)?.name||id).join('、')||'屏幕或道具')}</p><label class="production-field">声音方式<select data-script-field="audio_kind">${selectOptions([['speech','台词 / 旁白配音'],['silent','无配音 · 只展示画面与屏幕字']],row.audio_kind||'speech')}</select></label>${field(i+1,'台词 / 旁白','text',row.text)}${field(i+1,'画面说明','visual',row.visual)}
      <details ${row.render_kind==='screen'?'open':''}><summary>屏幕内容与动作模板</summary><div class="production-row-grid"><label class="production-field">场景简模<select data-script-field="environment">${selectOptions([['modern_room','现代房间'],['modern_corridor','现代走廊'],['ancient_courtyard','古风庭院']],row.environment)}</select></label><label class="production-field">动作简模<select data-script-field="action">${selectOptions(Object.entries(data.control_actions),row.action)}</select></label></div>${row.action.startsWith('modern_')?`<div class="production-row-grid"><label class="production-field">导演景别<select data-script-field="framing">${selectOptions([['wide','场景全景'],['medium','人物中景'],['closeup','人物特写'],['insert','物件特写']],row.framing||'wide')}</select></label><label class="production-field">镜头焦点<select data-script-field="focus_id">${selectOptions([['','使用模板机位'],...data.characters.filter(c=>(row.cast_ids||[]).includes(c.id)).map(c=>[c.id,c.name]),...({modern_office:[['PROP_DOCUMENT','离职通知书'],['PROP_PHONE','手机']],modern_stairs:[['PROP_DOCUMENT','离职通知书'],['PROP_PHONE','手机']],modern_store:[['PROP_PHONE','手机']],modern_dinner:[['PROP_NOTICES','桌下通知书']],modern_system:[['PROP_PHONE','手机']],modern_kitchen:[['PROP_PHONE','手机'],['PROP_POT','旧铁锅']]}[row.action]||[])],row.focus_id||'')}</select></label></div>`:''}${field(i+1,'屏幕标题','screen_title',row.screen_title,'text')}${field(i+1,'屏幕文字（每行一条）','screen_lines',row.screen_lines.join('\n'))}</details>
      <button class="secondary-button small-button" data-production-shot="${escapeHtml(row.id)}" ${!script.revision?'disabled':''}>准备这个镜头的角色与场景</button></article>`).join('')}</fieldset>
    <div class="production-editor-actions">${data.import_mode==='SCRIPT'?`<button id="productionPlanActions" class="secondary-button" ${active?'disabled':''}>按场景补人物动作</button>`:''}<button id="productionAddShot" class="secondary-button" ${active?'disabled':''}>添加镜头</button><button id="productionSaveScript" class="primary-button" ${active?'disabled':''}>保存台本</button><button id="productionGoPreview" class="secondary-button" ${active?'disabled':''}>查看 / 制作免费预演</button></div><p id="productionEditorStatus" role="status" class="helper-text">${active?'本集正在生成，完成后可以修改。':productionDirty?'有未保存的修改。':'保存后可生成本地配音和字幕。'}</p>`;
  document.getElementById('productionScriptTitle').disabled=active;
  const dirty=()=>{productionDirty=true;document.getElementById('productionEditorStatus').textContent='有未保存的修改；请保存后再继续制作。';};
  target.querySelectorAll('input,select,textarea').forEach(el=>el.addEventListener('input',dirty));
  const changeRows=fn=>{const draft=readProductionDraft();fn(draft.shots);productionStory.data.script={...script,...draft};productionDirty=true;renderProductionStory();};
  target.querySelectorAll('[data-row-move]').forEach(b=>b.addEventListener('click',()=>changeRows(rows=>{const i=Number(b.dataset.rowMove),to=i+Number(b.dataset.offset);[rows[i],rows[to]]=[rows[to],rows[i]];})));
  target.querySelectorAll('[data-row-delete]').forEach(b=>b.addEventListener('click',()=>changeRows(rows=>rows.splice(Number(b.dataset.rowDelete),1))));
  document.getElementById('productionAddShot').addEventListener('click',()=>changeRows(rows=>rows.push({id:`SHOT-${productionEpisode}-WB${crypto.randomUUID().slice(0,8)}`,speaker_id:'NARRATOR',text:'',visual:'',duration_seconds:4,render_kind:'screen',screen_title:'剧情提示',screen_lines:[],environment:'modern_room',action:'look_phone'})));
  document.getElementById('productionSaveScript').addEventListener('click',async event=>{
    event.target.disabled=true;const project=productionStory.project,episode=productionEpisode;
    try {const saved=await api(workbenchEndpoint(project,episode)+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readProductionDraft())});
      if(project!==resolveActiveNovelProject()||episode!==productionEpisode)return;
      productionStory.data=saved;productionDirty=false;shotWorkflowData=null;renderProductionStory();document.getElementById('productionEditorStatus').textContent='台本已保存。请使用这一版本生成配音和预演。';
    } catch(error){document.getElementById('productionEditorStatus').textContent=error.message;event.target.disabled=false;}
  });
  document.getElementById('productionAdoptDirector')?.addEventListener('click',async event=>{
    if(productionDirty){document.getElementById('productionEditorStatus').textContent='请先保存修改；导演稿需要与当前底稿一致。';return;}
    event.target.disabled=true;const project=productionStory.project,episode=productionEpisode;
    try {const result=await api(workbenchEndpoint(project,episode)+'/adopt-director',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:script.revision,draft_signature:data.director_draft.draft_signature})});
      if(project!==resolveActiveNovelProject()||episode!==productionEpisode)return;
      productionStory.data=result;shotWorkflowData=null;renderProductionStory();document.getElementById('productionEditorStatus').textContent='已采用导演稿。原始剧本和旧版本保留，请按新稿准备表演与画面。';
    } catch(error){document.getElementById('productionEditorStatus').textContent=error.message;event.target.disabled=false;}
  });
  document.getElementById('productionPlanActions')?.addEventListener('click',async event=>{
    if(productionDirty){document.getElementById('productionEditorStatus').textContent='请先保存修改，再补人物动作。';return;}
    event.target.disabled=true;const project=productionStory.project,episode=productionEpisode;
    try {const data=await api(workbenchEndpoint(project,episode)+'/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:script.revision})});
      if(project!==resolveActiveNovelProject()||episode!==productionEpisode)return;
      productionStory.data=data;shotWorkflowData=null;renderProductionStory();document.getElementById('productionEditorStatus').textContent='已补充支持的场景动作，原对白保留。请重新制作免费预演；这是动作简模。';
    } catch(error){document.getElementById('productionEditorStatus').textContent=error.message;event.target.disabled=false;}
  });
  document.getElementById('productionGoPreview').addEventListener('click',()=>{if(productionDirty){document.getElementById('productionEditorStatus').textContent='请先保存修改，再制作预演。';return;}setView('studio','render');});
  target.querySelectorAll('[data-production-shot]').forEach(button=>button.addEventListener('click',async()=>{
    if(productionDirty){document.getElementById('productionEditorStatus').textContent='请先保存台本修改。';return;}
    button.disabled=true;
    try {await api(`/api/novel-anime/projects/${encodeURIComponent(productionStory.project)}/shot-workflow/select`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shot_id:button.dataset.productionShot})});setView('characters');}
    catch(error){document.getElementById('productionEditorStatus').textContent=error.message;button.disabled=false;}
  }));
}
function renderProductionStudio() {
  const audio=state.currentWorkspace==='audio';
  document.getElementById('studioTitle').textContent=audio?'配音与字幕':'成片与审片';
  document.getElementById('studioSubtitle').textContent=audio?'试听真实配音；字幕与镜头使用声音的实际时长。':'免费预演确认剧情和节奏。正式总装需要人物镜头通过视觉验收。';
  document.getElementById('studioTabs').innerHTML='';document.getElementById('studioReadiness').innerHTML='';document.getElementById('studioDetail').classList.add('hidden');
  loadProductionWorkbench();
}
async function loadProductionWorkbench(quiet=false) {
  clearTimeout(productionWorkbenchTimer);
  const project=resolveActiveNovelProject(),view=state.currentWorkspace;
  productionEpisode=productionEpisodesByProject.get(project)||'S01E001';
  const episode=productionEpisode,request=++productionWorkbenchRequest,target=document.getElementById('studioContent');
  if(!project){target.innerHTML='<div class="empty-state">请先选择小说。</div>';return;}
  if(!quiet)target.innerHTML='<div class="empty-state">正在载入本集声音和成片…</div>';
  try{
    const data=await api(workbenchEndpoint(project,episode));
    if(request!==productionWorkbenchRequest||project!==resolveActiveNovelProject()||episode!==productionEpisode||state.currentView!=='studio'||view!==state.currentWorkspace)return;
    productionWorkbench=data;
    if(!quiet || data.job.active || !target.querySelector('[data-workbench-ready]') || target.dataset.workbenchStatus!==data.job.status || target.dataset.workbenchActive!==String(data.job.active))renderProductionWorkbench(data);
    if(data.job.active)productionWorkbenchTimer=setTimeout(()=>loadProductionWorkbench(true),4000);
  }catch(error){if(request===productionWorkbenchRequest)target.innerHTML=`<p class="production-attention">${escapeHtml(error.message)}</p>`;}
}
function renderProductionWorkbench(data) {
  const audioView=state.currentWorkspace==='audio',job=data.job,script=data.script,target=document.getElementById('studioContent'),performance=data.character_performance||{};
  const performanceReview=performance.review||{checks:{},notes:''},performanceCheckLabels={character_proportion:'人物比例与站姿自然',facial_expression:'视线和面部反应符合情境',arm_trajectory:'肩臂轨迹连续且没有明显拉伸',hand_pose:'手指握持与手腕姿态可信',prop_contact:'手机与手掌接触位置可信',clothing_shape:'现代服装、鞋和头发轮廓可信'};
  target.dataset.workbenchStatus=job.status;target.dataset.workbenchActive=String(job.active);
  const failed=job.status==='ERROR'||job.interrupted;
  target.innerHTML=`<div data-workbench-ready class="production-script-summary"><strong>${escapeHtml(script.title)} · 台本 v${script.revision}</strong><label class="production-field">本集<select id="workbenchEpisode">${data.episodes.map(id=>`<option value="${id}" ${id===data.episode_id?'selected':''}>${episodeLabel(id)}</option>`).join('')}</select></label></div>
    <p class="production-attention">当前 ${script.shots.filter(s=>s.render_kind==='control').length}/${script.shots.length} 镜头使用人物或道具动作。${performance.ready?'6 秒自然人体单镜已生成；先审核这一镜，再决定是否恢复剧情制作。':'剧情制作保持锁定；请先制作自然人体单镜质量门。'} 费用 ¥0，无素材上传。配音默认为已安装的本地 Kokoro 中文音色，仍需你试听。</p>
    ${renderVisualDirection(data)}
    ${!audioView?`<section class="production-character-sample"><h3>${escapeHtml(performance.title||'自然人体单镜质量门')}</h3>${performance.ready?`<div class="production-preview"><video controls preload="metadata" poster="${escapeHtml(performance.poster_url)}" src="${escapeHtml(performance.media_url)}" aria-label="自然人体单镜质量门"></video><div><p>${escapeHtml(performance.summary)}</p><p>${escapeHtml(performance.technical_summary||'本地人物、动作和道具绑定已经完成。')} 骨骼与道具绑定检查：${performance.technical_contact_pass?'通过':'待修复'}；人工画面审核：${escapeHtml(performance.human_review||'PENDING')}。</p><p class="helper-text">资源：${escapeHtml(performance.license)}。只有这一镜人工通过后才恢复剧情制作，不会未经审核替换整集。</p><a class="secondary-button" href="${escapeHtml(performance.media_url)}" download>下载样片</a> <a href="${escapeHtml(performance.report_url)}" target="_blank" rel="noopener">查看动作检查</a> · <a href="${escapeHtml(performance.asset_manifest_url)}" target="_blank" rel="noopener">查看资源与许可</a></div></div><div class="production-review"><h3>逐项画面审核</h3><p class="helper-text">请完整播放样片后逐项勾选。全部通过才会开放剧情扩展；退回会保留样片和修改意见。</p>${Object.entries(performanceCheckLabels).map(([key,label])=>`<label><input type="checkbox" data-character-review="${key}" ${performanceReview.checks?.[key]?'checked':''}>${label}</label>`).join('')}<label class="production-field">修改意见<textarea id="characterReviewNotes" rows="3" placeholder="退回时请写明最需要修改的问题">${escapeHtml(performanceReview.notes||'')}</textarea></label><div class="production-editor-actions"><button id="characterReviewPass" class="primary-button">确认单镜通过</button><button id="characterReviewReject" class="secondary-button">退回继续修改</button></div><p id="characterReviewNotice" class="helper-text">${performance.can_expand?'已通过，可以恢复剧情制作。':performance.human_review==='REJECTED'?'已退回，剧情制作仍锁定。':'尚未人工确认，剧情制作保持锁定。'}</p></div>`:'<p>还没有自然人体单镜样片。先生成 6 秒质量门，确认人物、动作和表情，再决定是否恢复剧情制作。</p>'}<button id="workbenchCharacterSample" class="secondary-button" ${job.active?'disabled':''}>${performance.ready?'重做 6 秒人物单镜':'制作 6 秒人物单镜（本地免费）'}</button><p id="characterSampleNotice" class="helper-text">全程本地 Blender；不调用付费接口，不上传素材。</p></section>`:''}
    ${job.ready&&!audioView?`<div class="production-preview"><video controls preload="metadata" poster="${escapeHtml(job.poster_url||'')}" src="${escapeHtml(job.media_url)}" aria-label="${job.mode==='preview'?'本集剧情预演':'本集正式总装'}"></video><div><h3>${job.mode==='preview'?'剧情预演 · 待你审片':'正式镜头总装 · 待你审片'}</h3><p>技术检查通过；人工审片${job.human_review==='PASS'?'已确认剧情、配音和字幕':'待确认'}。不自动发布。</p><a class="secondary-button" href="${escapeHtml(job.media_url)}" download>下载视频</a> <a href="${escapeHtml(job.srt_url)}" download>下载字幕</a> · <a href="${escapeHtml(job.qc_url)}" target="_blank" rel="noopener">查看技术检查</a></div></div>`:''}
    <div class="production-editor-actions"><label class="production-field">本地配音<select id="workbenchProvider" ${job.active?'disabled':''}><option value="kokoro_local">Kokoro 中文（本地）</option><option value="macos_say" ${job.provider==='macos_say'?'selected':''}>系统语音（临时）</option></select></label><button id="workbenchPreview" class="primary-button" ${!data.can_generate||job.active?'disabled':''}>${audioView?'生成配音与剧情预演（免费）':'生成剧情预演（免费）'}</button>${failed?`<button id="workbenchResume" class="secondary-button">继续未完成的${job.mode==='final'?'总装':'预演'}</button>`:''}<button id="workbenchEdit" class="secondary-button">修改台本</button>${!audioView?`<button id="workbenchFinal" class="secondary-button" ${!data.can_assemble_final||job.active?'disabled':''}>总装已验收的正式镜头</button>`:''}</div>
    <p id="workbenchNotice" role="status" class="helper-text">${!data.can_generate?'先到“剧本与分镜”整理并保存台本。':escapeHtml(job.status==='STALE'?'台本已变化，请生成当前版本的预演。旧文件仍保留。':job.error||job.phase||'尚未生成')}</p>${!audioView&&data.final_block_reason?`<p class="helper-text">正式总装：${escapeHtml(data.final_block_reason)}</p>`:''}
    ${job.active?`<progress max="100" value="${job.progress||0}" aria-label="生成进度"></progress><p>${escapeHtml(job.phase||'生成中')} · ${job.progress||0}%</p>`:''}
    ${data.audio_ready?`<details class="production-audio-details" ${audioView?'open':''}><summary>声音与字幕时间轴 · ${Number(data.audio.duration).toFixed(2)} 秒 · 逐镜试听</summary><div class="production-voice-list">${data.audio.lines.map((line,i)=>`<article><div><strong>镜头 ${i+1} · ${escapeHtml(data.characters.find(c=>c.id===line.speaker_id)?.name||'旁白')}</strong><small>${Number(line.start).toFixed(2)}–${Number(line.end).toFixed(2)} 秒 · 镜头 ${Number(line.clip_duration).toFixed(2)} 秒</small><p>${escapeHtml(line.text)}</p></div><audio controls preload="none" src="${escapeHtml(line.media_url)}" aria-label="镜头 ${i+1} 配音"></audio></article>`).join('')}</div></details>`:'<div class="empty-state">还没有当前台本的配音。保存台本后，点击免费预演生成。</div>'}
    ${job.ready&&job.mode==='preview'&&!audioView?`<div class="production-review"><h3>观看后确认</h3><p class="helper-text">这里只确认剧情、声音和字幕；人物与场景画质另行验收。</p><label><input type="checkbox" id="workbenchStoryChecked">剧情与节奏可以</label><label><input type="checkbox" id="workbenchVoiceChecked">配音内容与音色可以</label><label><input type="checkbox" id="workbenchSubtitlesChecked">字幕内容与时间可以</label><button id="workbenchReview" class="secondary-button">保存我的审片确认</button></div>`:''}`;
  document.getElementById('workbenchEpisode').addEventListener('change',event=>{productionEpisodesByProject.set(data.project_id,event.target.value);productionEpisode=event.target.value;loadProductionWorkbench();});
  document.getElementById('workbenchEdit').addEventListener('click',()=>setView('story'));
  document.getElementById('workbenchCharacterSample')?.addEventListener('click',async event=>{
    event.target.disabled=true;document.getElementById('characterSampleNotice').textContent='正在本地渲染 6 秒人物单镜，通常需要约 2 分钟…';
    try{await api(workbenchEndpoint(data.project_id,data.episode_id)+'/character-sample',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});loadProductionWorkbench();}
    catch(error){document.getElementById('characterSampleNotice').textContent=error.message;event.target.disabled=false;}
  });
  const submitCharacterReview=async decision=>{
    const notice=document.getElementById('characterReviewNotice');
    const checks={};target.querySelectorAll('[data-character-review]').forEach(input=>checks[input.dataset.characterReview]=input.checked);
    try{await api(workbenchEndpoint(data.project_id,data.episode_id)+'/character-review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision,checks,notes:document.getElementById('characterReviewNotes').value})});loadProductionWorkbench();}
    catch(error){notice.textContent=error.message;}
  };
  document.getElementById('characterReviewPass')?.addEventListener('click',()=>submitCharacterReview('PASS'));
  document.getElementById('characterReviewReject')?.addEventListener('click',()=>submitCharacterReview('REJECTED'));
  const run=async(mode,resume=false)=>{
    const episode=data.episode_id,project=data.project_id;
    try {await api(workbenchEndpoint(project,episode)+'/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,resume,provider:resume?job.provider:document.getElementById('workbenchProvider').value,expected_revision:script.revision})});
      if(project===resolveActiveNovelProject()&&episode===productionEpisode)loadProductionWorkbench();
    }catch(error){document.getElementById('workbenchNotice').textContent=error.message;}
  };
  document.getElementById('workbenchPreview').addEventListener('click',()=>run('preview'));
  document.getElementById('workbenchResume')?.addEventListener('click',()=>run(job.mode||'preview',true));
  document.getElementById('workbenchFinal')?.addEventListener('click',()=>run('final'));
  document.getElementById('workbenchReview')?.addEventListener('click',async()=>{
    try{await api(workbenchEndpoint(data.project_id,data.episode_id)+'/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:job.id,story_checked:document.getElementById('workbenchStoryChecked').checked,voice_checked:document.getElementById('workbenchVoiceChecked').checked,subtitles_checked:document.getElementById('workbenchSubtitlesChecked').checked})});loadProductionWorkbench();}
    catch(error){document.getElementById('workbenchNotice').textContent=error.message;}
  });
}

async function loadProductionSettings() {
  try {
    const health = await api('/api/health');
    const provider = (health.providers || []).find(item => item.id === 'wavespeed_wan');
    document.getElementById('productionKeyStatus').textContent = provider?.configured ? 'Wan 视频服务：已配置密钥' : 'Wan 视频服务：尚未配置密钥';
  } catch (error) { document.getElementById('productionKeyStatus').textContent = error.message; }
}
initProductionLayout();
