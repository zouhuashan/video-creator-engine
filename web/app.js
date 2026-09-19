const state = { projects: [], animeProjects: [], project: null, providers: [], integrations: [], studio: null, readiness: null, backups: null, studioProjectId: null, imageStudio: null, imageStudioProjectId: null, imageStudioSelected: null, imageStudioProviderPreference: 'AUTO', pipeline: null, pipelineProjectId: null, selectedProvider: 'local_ken_burns', selectedImage: null, currentView: 'workspace', currentWorkspace: 'overview' };

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const now = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

function log(message, isError = false) {
  const row = document.createElement('div');
  row.className = `log-entry${isError ? ' error' : ''}`;
  row.innerHTML = `<span class="log-time">${now()}</span><span>${escapeHtml(message)}</span>`;
  $('#logList').prepend(row);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  return data;
}

function pipelineStageLabel(id) {
  return ({ story:'故事', character:'角色', shot:'分镜', scene_control:'空间控制', prompt:'自动 Prompt', image:'关键帧', video:'动态镜头', tts:'配音', subtitles:'字幕', assembly:'FFmpeg 总装', qc:'自动 QC', review:'人工审核' })[id] || id;
}

function renderPipeline() {
  const data = state.pipeline || { status: 'NOT_STARTED', progress: 0, stages: [], review: { ready: false, status: 'PENDING' }, next: 'RUN_PIPELINE' };
  const select = $('#pipelineProjectSelect');
  if (select) {
    select.innerHTML = state.animeProjects.map((item) => `<option value="${escapeHtml(item.directory_id)}">${escapeHtml(item.title)}</option>`).join('');
    if (state.pipelineProjectId) select.value = state.pipelineProjectId;
  }
  $('#pipelineStatus').textContent = data.status || 'NOT_STARTED';
  $('#pipelineProgressText').textContent = `${Number(data.progress || 0)}%`;
  $('#pipelineProgressBar').style.width = `${Math.max(0, Math.min(100, Number(data.progress || 0)))}%`;
  $('#pipelineNext').textContent = data.next || '等待启动';

  const stages = data.stages || [];
  $('#pipelineStages').innerHTML = stages.length ? stages.map((stage) => `
    <div class="pipeline-stage">
      <span class="pipeline-stage-status ${escapeHtml(String(stage.status || '').toLowerCase())}">${escapeHtml(stage.status || 'PENDING')}</span>
      <strong>${escapeHtml(pipelineStageLabel(stage.id))}</strong>
      <small>${escapeHtml(stage.detail || '')}</small>
    </div>
  `).join('') : '<div class="empty-state">点击“创建整集（自动规划）”，软件会生成完整机器执行图。P30-01 不会自动触发远程计费。</div>';

  const preview = String(data.preview || '');
  const previewWrap = $('#pipelinePreviewWrap');
  if (preview) {
    previewWrap.classList.remove('hidden');
    $('#pipelinePreview').src = `/media/${encodeURIComponent(data.project_id)}/${preview.split('/').map(encodeURIComponent).join('/')}`;
  } else {
    previewWrap.classList.add('hidden');
    $('#pipelinePreview').removeAttribute('src');
  }
  const approve = $('#pipelineApproveButton');
  approve.disabled = !Boolean(data.review?.ready);
  approve.textContent = data.review?.status === 'APPROVED' ? '已人工确认' : '人工确认成片';
}

async function loadPipeline(projectId = state.pipelineProjectId || state.animeProjects[0]?.directory_id) {
  if (!projectId) return;
  state.pipelineProjectId = projectId;
  state.pipeline = await api(`/api/pipeline/status?project_id=${encodeURIComponent(projectId)}`);
  renderPipeline();
}

async function runAutoPipeline() {
  const projectId = state.pipelineProjectId || state.animeProjects[0]?.directory_id;
  if (!projectId) { log('没有可用国漫项目', true); return; }
  const button = $('#pipelineRunButton');
  button.disabled = true;
  button.textContent = '自动规划中…';
  log(`启动整集软件流水线：${projectId}`);
  try {
    state.pipeline = await api('/api/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, dry_run: true }),
    });
    renderPipeline();
    log(`流水线完成：${state.pipeline.status} · ${state.pipeline.progress}%`);
  } catch (error) {
    log(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>▶</span>创建整集（自动规划）';
  }
}

async function approvePipeline() {
  const projectId = state.pipelineProjectId;
  if (!projectId || !state.pipeline?.review?.ready) return;
  try {
    state.pipeline = await api('/api/pipeline/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, status: 'APPROVED', note: 'Web final review approved' }),
    });
    renderPipeline();
    log('成片已人工确认；系统仍不会自动发布平台。');
  } catch (error) {
    log(error.message, true);
  }
}

function renderStats() {
  $('#statProject').textContent = state.project?.name || state.project?.id || '—';
  $('#statProjectHint').textContent = state.project ? '本地试制项目' : '等待载入';
  $('#statAssets').textContent = state.project ? state.project.files.filter((file) => file.kind === 'image').length : '—';
  $('#statProviders').textContent = state.providers.filter((provider) => provider.configured).length + ' / ' + state.providers.length;
}

function renderProviders() {
  $('#providerGrid').innerHTML = state.providers.map((provider) => {
    const selected = provider.id === state.selectedProvider ? ' selected' : '';
    const status = provider.remote ? (provider.configured ? '已配置密钥' : `待配置 ${provider.env}`) : '无需密钥';
    return `<button class="provider-card${selected}" data-provider="${escapeHtml(provider.id)}"><strong>${escapeHtml(provider.label)}</strong><small>${provider.remote ? '远程图生视频' : '本地推镜与转场'}</small><span class="provider-status${provider.configured ? '' : ' off'}">● ${escapeHtml(status)}</span></button>`;
  }).join('');
  document.querySelectorAll('.provider-card').forEach((button) => button.addEventListener('click', () => {
    state.selectedProvider = button.dataset.provider;
    const provider = state.providers.find((item) => item.id === state.selectedProvider);
    $('#modelInput').value = state.selectedProvider === 'openai_sora' ? 'sora-2' : state.selectedProvider === 'runway' ? 'gen4.5' : $('#modelInput').value;
    $('#billableConfirm').checked = false;
    $('#generateHint').textContent = provider?.remote ? `已选择 ${provider.label}，点击生成前需要确认一次远程调用。` : '本地路线无需密钥，不会上传素材。';
    renderProviders();
    updateGenerateButton();
  }));
}

function renderProviderSettings() {
  const remoteProviders = state.providers.filter((provider) => provider.remote);
  const providerCards = remoteProviders.map((provider) => {
    const ready = provider.configured;
    const status = ready ? (provider.source === 'session' ? '本次服务已配置' : '环境变量已配置') : '尚未配置';
    return `<div class="provider-setting"><div class="provider-setting-head"><div><strong>${escapeHtml(provider.label)}</strong><small>环境变量：${escapeHtml(provider.env)} · 输入后只保存在当前服务进程内</small></div><span class="key-status${ready ? ' ready' : ''}">● ${escapeHtml(status)}</span></div><div class="key-form"><input type="password" autocomplete="off" data-key-input="${escapeHtml(provider.id)}" placeholder="粘贴 ${escapeHtml(provider.label)} API Key"><button data-save-key="${escapeHtml(provider.id)}">保存密钥</button></div></div>`;
  });
  const integrationCards = state.integrations.map((integration) => {
    const ready = integration.connected;
    const status = integration.paused ? '已暂停' : (ready ? '独立服务已连接' : (integration.configured ? '已配置，连接失败' : '尚未配置'));
    const defaultUrl = integration.base_url || 'http://127.0.0.1:1241';
    const openLink = ready ? ` · <a href="${escapeHtml(integration.base_url)}" target="_blank" rel="noopener noreferrer">打开 ArcReel</a>` : '';
    const projects = integration.projects?.length ? ` · 镜像：${escapeHtml(integration.projects.join('、'))}` : '';
    return `<div class="provider-setting integration-setting"><div class="provider-setting-head"><div><strong>${escapeHtml(integration.label)}</strong><small>可选的任务队列、模型调度、成本统计与剪映导出工作台 · ${escapeHtml(integration.license)}</small><small><a href="https://github.com/ArcReel/ArcReel" target="_blank" rel="noopener noreferrer">Powered by ArcReel</a>${openLink} · 独立服务接入，不改变本项目主数据</small></div><span class="key-status${ready ? ' ready' : ''}">● ${escapeHtml(status)}</span></div><div class="integration-form"><input type="url" data-integration-url="${escapeHtml(integration.id)}" value="${escapeHtml(defaultUrl)}" placeholder="ArcReel 服务地址"><input type="password" autocomplete="off" data-integration-key="${escapeHtml(integration.id)}" placeholder="访问令牌（未启用认证可留空）"><button data-save-integration="${escapeHtml(integration.id)}">保存并检测</button></div><small class="integration-detail">${escapeHtml(integration.detail || '')}${projects}</small></div>`;
  });
  $('#providerSettings').innerHTML = [...providerCards, ...integrationCards].join('');
  document.querySelectorAll('[data-save-key]').forEach((button) => button.addEventListener('click', async () => {
    const providerId = button.dataset.saveKey;
    const input = document.querySelector(`[data-key-input="${providerId}"]`);
    button.disabled = true;
    try {
      const result = await api('/api/settings/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: providerId, key: input.value }) });
      const provider = state.providers.find((item) => item.id === providerId);
      if (provider) { provider.configured = result.configured; provider.source = result.source; }
      input.value = '';
      renderProviderSettings();
      renderProviders();
      renderStats();
      log(`${provider?.label || providerId} 密钥已更新（仅当前服务进程）`);
    } catch (error) { log(error.message, true); }
    finally { button.disabled = false; }
  }));
  document.querySelectorAll('[data-save-integration]').forEach((button) => button.addEventListener('click', async () => {
    const integrationId = button.dataset.saveIntegration;
    const urlInput = document.querySelector(`[data-integration-url="${integrationId}"]`);
    const keyInput = document.querySelector(`[data-integration-key="${integrationId}"]`);
    button.disabled = true;
    try {
      const result = await api('/api/settings/integrations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ integration: integrationId, base_url: urlInput.value, api_key: keyInput.value }) });
      const index = state.integrations.findIndex((item) => item.id === integrationId);
      if (index >= 0) state.integrations[index] = result;
      keyInput.value = '';
      renderProviderSettings();
      log(`${result.label || integrationId}：${result.detail}`);
    } catch (error) { log(error.message, true); }
    finally { button.disabled = false; }
  }));
}

function renderProjectTable() {
  $('#projectLibraryCount').textContent = `${state.projects.length} 个项目`;
  $('#projectTable').innerHTML = state.projects.map((project) => `<div class="project-row"><strong>${escapeHtml(project.name)}</strong><small>${project.media_count} 个媒体文件</small><small>${project.id === state.project?.id ? '当前打开' : '可切换'}</small><button data-open-project="${escapeHtml(project.id)}">打开项目</button></div>`).join('');
  document.querySelectorAll('[data-open-project]').forEach((button) => button.addEventListener('click', async () => {
    const projectId = button.dataset.openProject;
    $('#projectSelect').value = projectId;
    try { await loadProject(projectId); setView('workspace'); log(`已打开项目：${projectId}`); } catch (error) { log(error.message, true); }
  }));
}

function renderAnimeProjects() {
  if (!state.animeProjects.length) {
    $('#animeProjects').innerHTML = '<div class="empty-state">还没有 P18 小说国漫项目。</div>';
    return;
  }
  $('#animeProjects').innerHTML = state.animeProjects.map((project) => {
    const repository = project.repository;
    const repositoryText = repository ? `${repository.entities} 实体 · ${repository.dependencies} 依赖 · ${repository.asset_versions} 资产版本 · ${repository.snapshots} 快照` : '数据仓库待初始化';
    const runtime = project.runtime;
    const runtimeText = runtime ? `任务：${runtime.succeeded} 成功 / ${runtime.queued} 排队 / ${runtime.running} 运行 · ${runtime.locks} 锁 · ${runtime.migrations} 迁移` : '运行时待初始化';
    const sources = project.source_catalog;
    const bible = project.story_bible;
    const sourceText = sources ? `底本 ${sources.edition_count} · 章节 ${sources.chapter_count} · 导入 ${sources.import_count} · 事件候选 ${sources.event_candidates} · ${sources.status}` : '来源与权利目录待创建';
    const bibleText = bible ? `故事圣经 ${bible.world_status} · 角色 ${bible.character_count} · 地点 ${bible.location_count} · 时间线 ${bible.timeline_event_count} · 连续性快照 ${bible.continuity_snapshot_count}` : '故事圣经待创建';
    const plan = project.series_plan;
    const planText = plan ? `全剧规划 ${plan.status} · 季计划 ${plan.season_plan_count} · 角色弧 ${plan.character_arc_count} · 转折 ${plan.major_turn_count}` : '全剧与季度规划待创建';
    const episodePlan = project.episode_planning;
    const episodePlanText = episodePlan ? `故事弧 ${episodePlan.story_arc_count} · 单集卡 ${episodePlan.episode_card_count} · 已就绪 ${episodePlan.ready_card_count} · 节拍 ${episodePlan.beat_count}` : '故事弧与单集卡待创建';
    const scripts = project.episode_scripts;
    const scriptText = scripts ? `剧本 ${scripts.script_count} · 场 ${scripts.scene_count} · 表演单元 ${scripts.unit_count} · 连续性输入 ${scripts.available_input_count}/${scripts.script_count}` : '场景剧本待创建';
    const review = project.story_review;
    const reviewText = review ? `剧情审核 ${review.overall_status} · 阻断 ${review.blocker_count} · 警告 ${review.warning_count} · 人工审核 ${review.human_review_status}` : '剧情审核待执行';
    const visual = project.visual_bible;
    const visualText = visual ? `视觉圣经 ${visual.status} · 色板 ${visual.swatch_count} · 五集配色 ${visual.episode_palette_count} · 构图规则 ${visual.composition_rule_count} · 负面约束 ${visual.negative_constraint_count}` : '视觉圣经待创建';
    const characters = project.character_designs;
    const characterText = characters ? `角色设定 ${characters.ready_character_count}/${characters.character_count} · 已选转面 ${characters.selected_turnaround_count} · 表情 ${characters.selected_expression_count} · 服装 ${characters.costume_count}` : '角色设定待创建';
    const environment = project.environment_assets;
    const environmentText = environment ? `场景 ${environment.ready_location_count}/${environment.location_count} · 变体 ${environment.location_variant_count} · 道具 ${environment.ready_prop_count}/${environment.prop_count} · 状态 ${environment.prop_state_count} · 绑定 ${environment.scene_assignment_count}` : '场景与道具资产待创建';
    const assetReview = project.asset_review;
    const assetReviewText = assetReview ? `参考包 ${assetReview.reference_package_count} · 参考 ${assetReview.reference_count} · 已选 ${assetReview.selected_reference_count} · 美术审核 ${assetReview.approved_review_count} · ${assetReview.ready ? '可用' : `阻断 ${assetReview.blocker_count}`}` : '参考包与美术审核待创建';
    const shotBreakdown = project.shot_breakdown;
    const shotText = shotBreakdown ? `分镜 ${shotBreakdown.scene_count} 场 / ${shotBreakdown.shot_count} 镜 · 已审 ${shotBreakdown.reviewed_shot_count}` : 'Scene/Shot 分镜待创建';
    const storyboard = project.storyboard;
    const storyboardText = storyboard ? `首尾帧 ${storyboard.frame_count} · 已选 ${storyboard.selected_frame_count} · 已审镜头 ${storyboard.approved_shot_count}` : '静态 storyboard 待创建';
    const animatic = project.animatic;
    const animaticText = animatic ? `Animatic ${animatic.ready_episode_count}/${animatic.episode_count} 集 · 镜头 ${animatic.shot_count} · 临时音频 ${animatic.audio_ready_count} · 字幕 ${animatic.subtitle_ready_count}` : '本地 Animatic 待创建';
    const animaticReview = project.animatic_review;
    const animaticReviewText = animaticReview ? `Animatic 审核 ${animaticReview.overall_status} · 发现 ${animaticReview.finding_count} · 阻断 ${animaticReview.blocker_count}` : 'Animatic 审核待执行';
    const voices = project.voice_profiles;
    const voiceText = voices ? `配音角色 ${voices.ready_profile_count}/${voices.profile_count} · 台词 ${voices.ready_line_count}/${voices.line_count}` : '配音角色与逐句台词待创建';
    const audio = project.audio_assets;
    const audioText = audio ? `音频轨 ${audio.ready_track_count}/${audio.track_count} · Cue ${audio.cue_count} · 已清权 ${audio.cleared_track_count} · ${audio.target_lufs} LUFS` : '音乐/环境声/音效待创建';
    const audioMix = project.audio_mix;
    const audioMixText = audioMix ? `混音 ${audioMix.ready_episode_count}/${audioMix.episode_count} 集 · 输出 ${audioMix.mix_output_count} · 最大同步偏移 ${audioMix.max_sync_offset_ms} ms` : '混音与声画同步待创建';
    const dynamic = project.dynamic_shots;
    const dynamicText = dynamic ? `动态镜头 ${dynamic.ready_route_count}/${dynamic.shot_count} · 队列 ${dynamic.queued_job_count}/${dynamic.job_count} · 已审 ${dynamic.approved_review_count} · 预算 ${dynamic.budget_spent}/${dynamic.budget_limit} USD` : '动态镜头路由待创建';
    const edit = project.edit_timelines;
    const editText = edit ? `剪辑 ${edit.ready_episode_count}/${edit.episode_count} 集 · Clip ${edit.clip_count} · 局部重渲染 ${edit.rerender_job_count}` : '集级时间线待创建';
    const qc = project.qc;
    const qcText = qc ? `QC ${qc.overall_status} · 阻断 ${qc.open_blocker_count} · 问题单 ${qc.open_issue_count} · 批注 ${qc.annotation_count}` : '六类 QC 待执行';
    const acceptance = project.acceptance;
    const acceptanceText = acceptance ? `正式验收 ${acceptance.decision} · 五集 ${acceptance.ready_episode_count}/${acceptance.episode_count} · 动作测试 ${acceptance.motion_tests_run}/${acceptance.motion_test_count}` : '正式五集验收待执行';
    const readiness = project.readiness;
    const readinessText = readiness ? `阶段门 ${readiness.ready_count}/${readiness.gate_count} · ${readiness.decision}` : '阶段门待计算';
    return `<article class="anime-project-card"><div class="anime-project-head"><div><span class="section-kicker">${escapeHtml(project.ip_id)} · ${escapeHtml(project.series_id)}</span><h3>${escapeHtml(project.title)}</h3></div><span class="result-chip">${escapeHtml(project.status)}</span></div><div class="hierarchy-row"><span>剧集 1</span><span>${project.season_count} 季</span><span>${project.episode_count} 集</span></div><div class="episode-token-row">${project.episode_ids.map((id) => `<span>${escapeHtml(id)}</span>`).join('')}</div><div class="source-row"><span>${escapeHtml(sourceText)}</span><strong class="${sources?.publication_allowed ? 'allowed' : 'blocked'}">${sources?.publication_allowed ? '可发布' : '禁止发布'}</strong></div><div class="runtime-row readiness-summary">${escapeHtml(readinessText)}</div><div class="runtime-row">${escapeHtml(bibleText)}</div><div class="runtime-row">${escapeHtml(planText)}</div><div class="runtime-row">${escapeHtml(episodePlanText)}</div><div class="runtime-row">${escapeHtml(scriptText)}</div><div class="runtime-row">${escapeHtml(reviewText)}</div><div class="runtime-row">${escapeHtml(visualText)}</div><div class="runtime-row">${escapeHtml(characterText)}</div><div class="runtime-row">${escapeHtml(environmentText)}</div><div class="runtime-row">${escapeHtml(assetReviewText)}</div><div class="runtime-row">${escapeHtml(shotText)}</div><div class="runtime-row">${escapeHtml(storyboardText)}</div><div class="runtime-row">${escapeHtml(animaticText)}</div><div class="runtime-row">${escapeHtml(animaticReviewText)}</div><div class="runtime-row">${escapeHtml(voiceText)}</div><div class="runtime-row">${escapeHtml(audioText)}</div><div class="runtime-row">${escapeHtml(audioMixText)}</div><div class="runtime-row">${escapeHtml(dynamicText)}</div><div class="runtime-row">${escapeHtml(editText)}</div><div class="runtime-row">${escapeHtml(qcText)}</div><div class="runtime-row">${escapeHtml(acceptanceText)}</div><div class="repository-row"><small>${escapeHtml(repositoryText)}</small><button data-open-anime-project="${escapeHtml(project.directory_id)}">进入制作台</button><button data-impact-project="${escapeHtml(project.directory_id)}" data-impact-root="${escapeHtml(project.ip_id)}" ${repository ? '' : 'disabled'}>分析 IP 影响</button></div><div class="runtime-row">${escapeHtml(runtimeText)}</div><div class="impact-result" data-impact-result="${escapeHtml(project.directory_id)}"></div><small class="manifest-note">${escapeHtml(project.project_id)} · novel-anime-project.json</small></article>`;
  }).join('');
  document.querySelectorAll('[data-open-anime-project]').forEach((button) => button.addEventListener('click', async () => {
    try { await loadStudio(button.dataset.openAnimeProject); setView('studio', 'overview'); log(`已打开国漫制作台：${button.dataset.openAnimeProject}`); } catch (error) { log(error.message, true); }
  }));
  document.querySelectorAll('[data-impact-project]').forEach((button) => button.addEventListener('click', async () => {
    const target = document.querySelector(`[data-impact-result="${button.dataset.impactProject}"]`);
    button.disabled = true;
    try {
      const result = await api(`/api/novel-anime/projects/${encodeURIComponent(button.dataset.impactProject)}/impact/${encodeURIComponent(button.dataset.impactRoot)}`);
      target.textContent = `影响范围：${result.impact.map((item) => item.entity_id).join(' → ')}`;
    } catch (error) { target.textContent = error.message; }
    finally { button.disabled = false; }
  }));
}

const RESOURCE_ENDPOINTS = {
  ip: { source_catalog: 'sources' },
  story: { story_bible: 'story-bible' },
  script: { series_plan: 'series-plan', episode_planning: 'episode-planning', episode_scripts: 'episode-scripts', story_review: 'story-review' },
  assets: { visual_bible: 'visual-bible', character_designs: 'character-designs', environment_assets: 'environment-assets', asset_review: 'asset-review' },
  storyboard: { shot_breakdown: 'shot-breakdown', storyboard: 'storyboard', animatic: 'animatic', animatic_review: 'animatic-review' },
  audio: { voice_profiles: 'voice-profiles', audio_assets: 'audio-assets', audio_mix: 'audio-mix' },
  render: { dynamic_shots: 'dynamic-shots', edit_timelines: 'edit-timelines', episode_masters: 'episode-masters', provider_motion_tests: 'provider-motion-tests', runtime: 'runtime' },
  review: { qc: 'qc', acceptance: 'acceptance' },
  publish: { source_catalog: 'sources', qc: 'qc', acceptance: 'acceptance', repository: 'repository', backups: 'backups' },
};

function compactValue(value) {
  if (value === null || value === undefined) return '尚未创建';
  if (typeof value !== 'object') return String(value);
  const entries = Object.entries(value).filter(([name]) => !['category_status', 'gates', 'next_actions'].includes(name));
  return entries.slice(0, 8).map(([name, item]) => `${name}: ${typeof item === 'object' ? JSON.stringify(item) : item}`).join(' · ') || '已连接';
}

function renderReadiness() {
  const readiness = state.readiness;
  if (!readiness) { $('#studioReadiness').innerHTML = ''; return; }
  const percent = Math.round((readiness.ready_count / Math.max(readiness.gate_count, 1)) * 100);
  const gates = readiness.gates.map((item) => `<button class="readiness-gate ${item.status === 'READY' ? 'ready' : 'blocked'}" data-gate-detail="${escapeHtml(item.id)}"><span class="gate-icon">${item.status === 'READY' ? '✓' : '!'}</span><span><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.detail)}</small></span></button>`).join('');
  $('#studioReadiness').innerHTML = `<div class="readiness-head"><div><span class="section-kicker">READINESS GATES</span><strong>${escapeHtml(readiness.decision)} · ${readiness.ready_count}/${readiness.gate_count} 阶段通过</strong><small>${readiness.next_actions?.length ? `下一步：${escapeHtml(readiness.next_actions[0])}` : '当前没有阻断项'}</small></div><div class="readiness-meter"><span style="width:${percent}%"></span></div></div><div class="readiness-grid">${gates}</div>`;
  document.querySelectorAll('[data-gate-detail]').forEach((button) => button.addEventListener('click', () => {
    const gate = readiness.gates.find((item) => item.id === button.dataset.gateDetail);
    if (gate) showStudioDetail(`${gate.label} · ${gate.status}`, gate);
  }));
}

function showStudioDetail(title, payload, endpoint = '') {
  const detail = $('#studioDetail');
  detail.classList.remove('hidden');
  detail.innerHTML = `<div class="detail-head"><div><span class="section-kicker">DETAIL</span><h3>${escapeHtml(title)}</h3></div><button class="text-button" id="closeStudioDetail">关闭</button></div><pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>${endpoint ? `<small class="studio-api">数据接口：${escapeHtml(endpoint)}</small>` : ''}`;
  $('#closeStudioDetail').addEventListener('click', () => detail.classList.add('hidden'));
}

const RIG_V2_LAYER_LABELS = {
  head: '头部',
  torso: '躯干',
  upper_arm_l: '左上臂',
  forearm_l: '左前臂',
  hand_l: '左手',
  upper_arm_r: '右上臂',
  forearm_r: '右前臂',
  hand_r: '右手',
};

const RIG_V2_GUIDE = {
  head: { title: '头部', instruction: '检查自动框是否覆盖主要头发和脸部。Pivot 应在脖子与头部连接处。' },
  torso: { title: '躯干', instruction: '检查胸腹主体是否完整。宽袖与手臂层轻微重叠是正常的。Pivot 放在胸腹中心。' },
  upper_arm_l: { title: '左上臂', instruction: '人物自己的左臂在画面右侧。检查肩到肘这一段，Pivot 放肩关节。' },
  forearm_l: { title: '左前臂', instruction: '人物自己的左前臂在画面右侧。检查肘到手腕，Pivot 放肘关节。' },
  hand_l: { title: '左手', instruction: '人物自己的左手在画面右侧。自动识别最容易偏，重点检查手掌/袖口，Pivot 放手腕。' },
  upper_arm_r: { title: '右上臂', instruction: '人物自己的右臂在画面左侧。检查肩到肘这一段，Pivot 放肩关节。' },
  forearm_r: { title: '右前臂', instruction: '人物自己的右前臂在画面左侧。检查肘到手腕，Pivot 放肘关节。' },
  hand_r: { title: '右手', instruction: '人物自己的右手在画面左侧。自动识别最容易偏，重点检查手掌/袖口，Pivot 放手腕。' },
};

async function openRigV2Editor(projectId, characterId) {
  const target = $('#rigV2Editor');
  if (!target) return;
  target.classList.remove('hidden');
  document.body.classList.add('rig-v2-open');
  target.innerHTML = '<div class="empty-state">正在载入 Rig V2 分层工作区…</div>';
  try {
    const workspace = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/rig-v2-workspace/${encodeURIComponent(characterId)}`);
    const required = workspace.required_layers || [];
    const saved = workspace.existing?.segmentation || {};
    const layers = Object.fromEntries(required.map((name, index) => {
      const item = saved[name] || {};
      return [name, {
        polygon: Array.isArray(item.polygon) ? item.polygon.map((point) => [Number(point[0]), Number(point[1])]) : [],
        pivot: item.pivot && Number.isFinite(Number(item.pivot.x)) && Number.isFinite(Number(item.pivot.y))
          ? { x: Number(item.pivot.x), y: Number(item.pivot.y) }
          : null,
        z_index: Number.isFinite(Number(item.z_index)) ? Number(item.z_index) : index,
        confidence: item.confidence || '',
        note: item.note || '',
      }];
    }));
    let activeLayer = required[0];
    let mode = 'polygon';
    let zoom = 1;
    let guideMode = true;
    let guideIndex = 0;
    let autoDraftLoaded = false;

    const readiness = workspace.readiness?.profiles || {};
    const upperReady = readiness.GODOT_UPPER_BODY_IK?.ready ? 'READY' : 'NOT READY';
    target.innerHTML = `
      <div class="rig-v2-editor-head">
        <div>
          <div class="section-kicker">GODOT RIG V2</div>
          <strong>${escapeHtml(workspace.character_name)} · 上半身 IK 分层</strong>
          <small>当前：${escapeHtml(upperReady)} · 在原图上逐层勾轮廓，再切换到 Pivot 模式点肩/肘/腕等关节点。不会上传图片。</small>
        </div>
        <button class="text-button" data-close-rig-v2>关闭</button>
      </div>
      <div class="rig-v2-layout">
        <div class="rig-v2-canvas-wrap"><canvas id="rigV2Canvas"></canvas></div>
        <div class="rig-v2-controls">
          <div class="rig-v2-guide-card">
            <div class="section-kicker">新手引导</div>
            <strong id="rigV2GuideTitle">正在准备自动草稿…</strong>
            <small id="rigV2GuideText">系统会先自动生成 8 层和 Pivot，你只需要逐层看是否明显偏了。</small>
            <div class="rig-v2-guide-actions">
              <button class="secondary-button small-button active" data-rig-v2-guide-toggle>新手模式：开</button>
              <button class="secondary-button small-button" data-rig-v2-auto-draft>重新自动草稿</button>
            </div>
            <div class="rig-v2-guide-nav">
              <button class="secondary-button small-button" data-rig-v2-prev>上一层</button>
              <span id="rigV2GuideStep">1 / 8</span>
              <button class="secondary-button small-button" data-rig-v2-next>下一层</button>
            </div>
            <button class="primary-button small-button" data-rig-v2-auto-generate>一键自动生成 Rig V2</button>
          </div>
          <label>当前层<select class="compact-select" id="rigV2LayerSelect">${required.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(RIG_V2_LAYER_LABELS[name] || name)}</option>`).join('')}</select></label>
          <div class="rig-v2-mode-row">
            <button class="secondary-button small-button active" data-rig-v2-mode="polygon">勾轮廓</button>
            <button class="secondary-button small-button" data-rig-v2-mode="pivot">点 Pivot</button>
          </div>
          <div class="rig-v2-view-row">
            <button class="secondary-button small-button" data-rig-v2-fit>适配画布</button>
            <button class="secondary-button small-button" data-rig-v2-zoom-out>缩小</button>
            <button class="secondary-button small-button" data-rig-v2-zoom-in>放大</button>
          </div>
          <div class="rig-v2-actions">
            <button class="secondary-button small-button" data-rig-v2-undo>撤销一点</button>
            <button class="secondary-button small-button" data-rig-v2-clear>清空当前层</button>
            <button class="secondary-button small-button" data-rig-v2-save>生成 Rig V2</button>
            <button class="primary-button small-button" data-rig-v2-preview>生成 2.5D 动作预览</button>
          </div>
          <div class="rig-v2-preview hidden" id="rigV2PreviewBox">
            <video id="rigV2PreviewVideo" controls playsinline></video>
            <small id="rigV2PreviewText">本地 Godot 2.5D 预览</small>
          </div>
          <div class="rig-v2-status" id="rigV2Status"></div>
          <small>提示：轮廓至少 3 个点；Pivot 必须点在原画布内。关节区域可以适度重叠，避免转动时出现断缝。</small>
        </div>
      </div>`;

    const canvas = $('#rigV2Canvas');
    const ctx = canvas.getContext('2d');
    const image = new Image();
    const layerSelect = $('#rigV2LayerSelect');
    const status = $('#rigV2Status');
    const guideTitle = $('#rigV2GuideTitle');
    const guideText = $('#rigV2GuideText');
    const guideStep = $('#rigV2GuideStep');

    function setActiveLayer(name) {
      if (!required.includes(name)) return;
      activeLayer = name;
      guideIndex = Math.max(0, required.indexOf(name));
      layerSelect.value = name;
      draw();
      renderStatus();
    }

    function applyAutoDraft(draft, overwrite = false) {
      const proposed = draft?.layers || {};
      required.forEach((name) => {
        const item = proposed[name];
        if (!item) return;
        const current = layers[name];
        const empty = current.polygon.length < 3 || !current.pivot;
        if (!overwrite && !empty) return;
        layers[name] = {
          polygon: Array.isArray(item.polygon) ? item.polygon.map((point) => [Number(point[0]), Number(point[1])]) : [],
          pivot: item.pivot ? { x: Number(item.pivot.x), y: Number(item.pivot.y) } : null,
          z_index: Number.isFinite(Number(item.z_index)) ? Number(item.z_index) : required.indexOf(name),
          confidence: item.confidence || '',
          note: item.note || '',
        };
      });
      autoDraftLoaded = true;
      draw();
      renderStatus();
    }

    async function loadAutoDraft(overwrite = false) {
      const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/rig-v2-auto-draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: characterId }),
      });
      applyAutoDraft(result.draft, overwrite);
      log(`Rig V2 自动草稿已生成：${characterId}`);
      return result;
    }

    function renderGuide() {
      if (!guideTitle || !guideText || !guideStep) return;
      const item = layers[activeLayer] || {};
      const guide = RIG_V2_GUIDE[activeLayer] || { title: activeLayer, instruction: '' };
      const confidence = item.confidence ? ` · 自动置信度 ${item.confidence}` : '';
      guideTitle.textContent = guideMode
        ? `第 ${guideIndex + 1} 步：${guide.title}${confidence}`
        : `手动模式：${guide.title}`;
      guideText.textContent = guideMode
        ? `${guide.instruction}${item.note ? ' ' + item.note : ''}`
        : '可以自由选择任意层、勾轮廓或修改 Pivot。';
      guideStep.textContent = `${guideIndex + 1} / ${required.length}`;
    }

    function layerStatus(name) {
      const item = layers[name];
      const polygonOk = item.polygon.length >= 3;
      const pivotOk = !!item.pivot;
      return `${RIG_V2_LAYER_LABELS[name] || name}: ${polygonOk ? item.polygon.length + ' 点' : '未完成轮廓'} · ${pivotOk ? `Pivot(${Math.round(item.pivot.x)}, ${Math.round(item.pivot.y)})` : '未设 Pivot'}`;
    }

    function renderStatus() {
      status.innerHTML = required.map((name) => `<span class="${layers[name].polygon.length >= 3 && layers[name].pivot ? 'ready' : ''}">${escapeHtml(layerStatus(name))}</span>`).join('');
      renderGuide();
    }

    function applyCanvasZoom() {
      canvas.style.width = `${Math.max(30, Math.round(zoom * 100))}%`;
    }

    function fitCanvas() {
      zoom = 1;
      applyCanvasZoom();
      const wrap = canvas.closest('.rig-v2-canvas-wrap');
      if (wrap) {
        wrap.scrollTop = 0;
        wrap.scrollLeft = Math.max(0, (canvas.clientWidth - wrap.clientWidth) / 2);
      }
    }

    function draw() {
      if (!image.complete || !image.naturalWidth) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      required.forEach((name) => {
        const item = layers[name];
        if (!item.polygon.length) return;
        ctx.save();
        ctx.lineWidth = Math.max(2, canvas.width / 500);
        ctx.globalAlpha = name === activeLayer ? 1 : 0.35;
        ctx.beginPath();
        item.polygon.forEach((point, index) => {
          if (index === 0) ctx.moveTo(point[0], point[1]);
          else ctx.lineTo(point[0], point[1]);
        });
        if (item.polygon.length >= 3) ctx.closePath();
        ctx.strokeStyle = name === activeLayer ? '#ffffff' : '#bfc7d5';
        ctx.stroke();
        item.polygon.forEach((point) => {
          ctx.beginPath();
          ctx.arc(point[0], point[1], Math.max(3, canvas.width / 250), 0, Math.PI * 2);
          ctx.fillStyle = name === activeLayer ? '#ffffff' : '#aab3c2';
          ctx.fill();
        });
        if (item.pivot) {
          ctx.beginPath();
          ctx.arc(item.pivot.x, item.pivot.y, Math.max(5, canvas.width / 180), 0, Math.PI * 2);
          ctx.strokeStyle = '#ffb86b';
          ctx.lineWidth = Math.max(2, canvas.width / 500);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(item.pivot.x - 10, item.pivot.y);
          ctx.lineTo(item.pivot.x + 10, item.pivot.y);
          ctx.moveTo(item.pivot.x, item.pivot.y - 10);
          ctx.lineTo(item.pivot.x, item.pivot.y + 10);
          ctx.stroke();
        }
        ctx.restore();
      });
    }

    image.onload = () => {
      canvas.width = Number(workspace.canvas?.width) || image.naturalWidth;
      canvas.height = Number(workspace.canvas?.height) || image.naturalHeight;
      draw();
      renderStatus();
      fitCanvas();
      if (!workspace.existing?.segmentation && !autoDraftLoaded) {
        loadAutoDraft(false).catch((error) => log(`自动草稿失败：${error.message}`, true));
      }
    };
    image.src = workspace.source_url;

    canvas.addEventListener('click', (event) => {
      const rect = canvas.getBoundingClientRect();
      const x = (event.clientX - rect.left) * canvas.width / rect.width;
      const y = (event.clientY - rect.top) * canvas.height / rect.height;
      if (mode === 'pivot') layers[activeLayer].pivot = { x, y };
      else layers[activeLayer].polygon.push([x, y]);
      draw();
      renderStatus();
    });

    layerSelect.addEventListener('change', () => {
      setActiveLayer(layerSelect.value);
    });

    target.querySelector('[data-rig-v2-guide-toggle]').addEventListener('click', (event) => {
      guideMode = !guideMode;
      event.currentTarget.textContent = `新手模式：${guideMode ? '开' : '关'}`;
      event.currentTarget.classList.toggle('active', guideMode);
      renderGuide();
    });
    target.querySelector('[data-rig-v2-prev]').addEventListener('click', () => {
      setActiveLayer(required[Math.max(0, guideIndex - 1)]);
    });
    target.querySelector('[data-rig-v2-next]').addEventListener('click', () => {
      setActiveLayer(required[Math.min(required.length - 1, guideIndex + 1)]);
    });
    target.querySelector('[data-rig-v2-auto-draft]').addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = '正在生成草稿…';
      try {
        await loadAutoDraft(true);
      } catch (error) {
        log(error.message, true);
      } finally {
        button.disabled = false;
        button.textContent = '重新自动草稿';
      }
    });
    target.querySelector('[data-rig-v2-auto-generate]').addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = '正在自动生成…';
      try {
        const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/rig-v2-auto-generate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: characterId }),
        });
        const rig = result.readiness?.rigs?.find((item) => item.character_id === characterId);
        const upper = rig?.profiles?.GODOT_UPPER_BODY_IK?.ready;
        log(`自动 Rig V2 已生成：${characterId} · 上半身 IK ${upper ? 'READY' : 'NOT READY'} · 人工审核 PENDING`);
        showStudioDetail('自动 Rig V2 生成结果', result, `/api/novel-anime/projects/${encodeURIComponent(projectId)}/godot-rig-readiness`);
      } catch (error) {
        log(error.message, true);
      } finally {
        button.disabled = false;
        button.textContent = '一键自动生成 Rig V2';
      }
    });

    target.querySelectorAll('[data-rig-v2-mode]').forEach((button) => button.addEventListener('click', () => {
      mode = button.dataset.rigV2Mode;
      target.querySelectorAll('[data-rig-v2-mode]').forEach((item) => item.classList.toggle('active', item === button));
    }));

    target.querySelector('[data-rig-v2-fit]').addEventListener('click', fitCanvas);
    target.querySelector('[data-rig-v2-zoom-in]').addEventListener('click', () => {
      zoom = Math.min(3, zoom + 0.25);
      applyCanvasZoom();
    });
    target.querySelector('[data-rig-v2-zoom-out]').addEventListener('click', () => {
      zoom = Math.max(0.3, zoom - 0.25);
      applyCanvasZoom();
    });

    target.querySelector('[data-rig-v2-undo]').addEventListener('click', () => {
      if (mode === 'pivot') layers[activeLayer].pivot = null;
      else layers[activeLayer].polygon.pop();
      draw();
      renderStatus();
    });

    target.querySelector('[data-rig-v2-clear]').addEventListener('click', () => {
      layers[activeLayer] = { ...layers[activeLayer], polygon: [], pivot: null };
      draw();
      renderStatus();
    });

    const closeRigV2Editor = () => {
      target.classList.add('hidden');
      document.body.classList.remove('rig-v2-open');
    };
    target.querySelector('[data-close-rig-v2]').addEventListener('click', closeRigV2Editor);
    target.addEventListener('click', (event) => {
      if (event.target === target) closeRigV2Editor();
    });

    target.querySelector('[data-rig-v2-preview]').addEventListener('click', async (event) => {
      const button = event.currentTarget;
      const incomplete = required.filter((name) => layers[name].polygon.length < 3 || !layers[name].pivot);
      if (incomplete.length) {
        log('请先生成 Rig V2，或先点“一键自动生成 Rig V2”。', true);
        return;
      }
      button.disabled = true;
      button.textContent = '正在渲染 2.5D…';
      try {
        const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/godot-25d-preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: characterId, seconds: 4 }),
        });
        const box = $('#rigV2PreviewBox');
        const video = $('#rigV2PreviewVideo');
        const text = $('#rigV2PreviewText');
        if (box && video) {
          video.src = `${result.media_url}?t=${Date.now()}`;
          box.classList.remove('hidden');
          video.load();
          video.play().catch(() => {});
        }
        if (text) text.textContent = `Godot 2.5D · ${result.duration_seconds}s · ${result.features.join(' · ')} · 人工审核 ${result.human_review}`;
        log(`Godot 2.5D 预览已生成：${characterId}`);
      } catch (error) {
        log(error.message, true);
      } finally {
        button.disabled = false;
        button.textContent = '生成 2.5D 动作预览';
      }
    });

    target.querySelector('[data-rig-v2-save]').addEventListener('click', async (event) => {
      const button = event.currentTarget;
      const incomplete = required.filter((name) => layers[name].polygon.length < 3 || !layers[name].pivot);
      if (incomplete.length) {
        log(`Rig V2 未完成：${incomplete.map((name) => RIG_V2_LAYER_LABELS[name] || name).join('、')}`, true);
        return;
      }
      button.disabled = true;
      button.textContent = '正在生成…';
      try {
        const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/rig-v2-segment`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: characterId, layers }),
        });
        const rig = result.readiness?.rigs?.find((item) => item.character_id === characterId);
        const upper = rig?.profiles?.GODOT_UPPER_BODY_IK?.ready;
        log(`Rig V2 已生成：${characterId} · 上半身 IK ${upper ? 'READY' : 'NOT READY'}`);
        showStudioDetail('Rig V2 生成结果', result, `/api/novel-anime/projects/${encodeURIComponent(projectId)}/godot-rig-readiness`);
      } catch (error) {
        log(error.message, true);
      } finally {
        button.disabled = false;
        button.textContent = '生成 Rig V2';
      }
    });
  } catch (error) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

async function loadCharacterAssetGallery() {
  const target = $('#characterAssetGallery');
  if (!target || !state.studio?.directory_id) return;
  try {
    const projectId = state.studio.directory_id;
    const [result, rigResult, coverageResult, batchResult] = await Promise.all([
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/character-assets`),
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/character-rigs`),
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/rig-coverage`),
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/final-batch`),
    ]);
    let reviewResult = null;
    try { reviewResult = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/final-shot-review`); } catch (error) { log(`审片状态读取失败：${error.message}`, true); }
    const rigSummary = (rigResult.rigs || []).map((rig) => `<div class="character-rig-summary"><div><strong>${escapeHtml(rig.id)}</strong><small>来源：${escapeHtml(rig.source_asset_id || '本地角色图')} · ${rig.layers?.length || 0} 层 · ${escapeHtml((rig.human_review || {}).status || 'PENDING')} · 校验 ${rig.validation?.valid ? '通过' : '需检查'}</small></div><span>${escapeHtml((rig.motion_channels || []).join(' · '))}</span><select class="compact-select rig-expression-select" data-rig-expression><option value="neutral">平静</option><option value="soft_smile">浅笑</option><option value="concerned">担忧</option><option value="surprised">惊讶</option></select><button class="secondary-button small-button" data-rig-v2-editor="${escapeHtml(rig.character_id || '')}">Rig V2 / Godot IK</button><button class="secondary-button small-button" data-rig-preview="${escapeHtml(rig.id)}">生成 Rig 动作预览</button><button class="secondary-button small-button" data-shot-rig-preview="${escapeHtml(rig.id)}">按分镜预览</button><button class="secondary-button small-button" data-final-rig-preview="${escapeHtml(rig.id)}">生成最终镜头</button></div>`).join('');
    const cards = result.assets.length ? result.assets.map((asset) => `<article class="character-asset-card"><img src="${escapeHtml(asset.media_url)}" alt="${escapeHtml(asset.name)}"><div><strong>${escapeHtml(asset.view)} · ${escapeHtml(asset.name)}</strong><small>${escapeHtml(asset.asset_id || asset.character_id)}</small><button class="secondary-button small-button" data-character-preview="${escapeHtml(asset.path)}">生成本地动作预览</button></div></article>`).join('') : '<div class="empty-state">尚无本地角色图片。</div>';
    const checkOptions = (value) => ['PENDING', 'PASS', 'CHANGES_REQUESTED'].map((item) => `<option value="${item}" ${item === value ? 'selected' : ''}>${item}</option>`).join('');
    const reviewCard = reviewResult ? `<div class="final-shot-review"><div class="final-review-copy"><div class="section-kicker">FINAL SHOT REVIEW</div><strong>${escapeHtml(reviewResult.video_path || '尚未生成最终镜头')}</strong><small>三项均为 PASS 后才可批准；批量范围按已审核的角色 Rig 计算。</small></div><label>声音<select class="compact-select" data-final-check="sound">${checkOptions(reviewResult.checks?.sound || 'PENDING')}</select></label><label>字幕<select class="compact-select" data-final-check="subtitles">${checkOptions(reviewResult.checks?.subtitles || 'PENDING')}</select></label><label>嘴型<select class="compact-select" data-final-check="mouth">${checkOptions(reviewResult.checks?.mouth || 'PENDING')}</select></label><input class="text-field" data-final-reviewer placeholder="审核人" value="${escapeHtml(reviewResult.reviewer || '')}"><input class="text-field" data-final-note placeholder="修改意见或备注" value="${escapeHtml(reviewResult.note || '')}"><button class="secondary-button small-button" data-save-final-review>保存审片</button><button class="secondary-button small-button" data-run-final-batch ${reviewResult.status === 'APPROVED' ? '' : 'disabled'}>批量生成已审核角色镜头</button></div>` : '';
    const coverageCard = `<div class="rig-coverage-card"><div><div class="section-kicker">RIG COVERAGE</div><strong>${coverageResult.covered_shot_count}/${coverageResult.total_shot_count} 个对白镜头可生成 · ${coverageResult.coverage_percent}%</strong><small>当前批次：${escapeHtml(batchResult.status || 'NOT_RUN')} · 已生成 ${batchResult.count || 0} 镜｜待补角色：${escapeHtml((coverageResult.missing_character_ids || []).join('、') || '无')}</small></div><div class="readiness-meter"><span style="width:${coverageResult.coverage_percent}%"></span></div></div>`;
    target.innerHTML = `${reviewCard}${coverageCard}${rigSummary ? `<div class="character-rig-list"><div class="section-kicker">NATIVE CHARACTER RIG</div>${rigSummary}</div>` : ''}<div id="rigV2Editor" class="rig-v2-editor hidden"></div><div class="character-asset-grid">${cards}</div>`;
    document.querySelectorAll('[data-rig-v2-editor]').forEach((button) => button.addEventListener('click', () => {
      const characterId = button.dataset.rigV2Editor;
      if (characterId) openRigV2Editor(projectId, characterId);
    }));
    document.querySelectorAll('[data-character-preview]').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true;
      button.textContent = '正在渲染…';
      try {
        const preview = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/character-motion-test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset_path: button.dataset.characterPreview, seconds: 4 }) });
        showOutput(preview.media_url, preview.provider, preview.output, preview.duration_seconds);
        setView('workspace');
        log(`本地角色动作预览已生成：${preview.output}`);
      } catch (error) { log(error.message, true); }
      finally { button.disabled = false; button.textContent = '生成本地动作预览'; }
    }));
    document.querySelectorAll('[data-rig-preview]').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true; button.textContent = '正在渲染…';
      try {
        const expression = button.parentElement.querySelector('[data-rig-expression]')?.value || 'neutral';
        const preview = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/character-rig-motion-test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rig_id: button.dataset.rigPreview, expression, seconds: 4 }) });
        showOutput(preview.media_url, preview.provider, preview.output, preview.duration_seconds); setView('workspace'); log(`Rig 分层动作预览已生成：${preview.output}`);
      } catch (error) { log(error.message, true); }
      finally { button.disabled = false; button.textContent = '生成 Rig 动作预览'; }
    }));
    document.querySelectorAll('[data-shot-rig-preview]').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true; button.textContent = '正在渲染…';
      try {
        const expression = button.parentElement.querySelector('[data-rig-expression]')?.value || 'neutral';
        const preview = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/storyboard-rig-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rig_id: button.dataset.shotRigPreview, shot_id: 'SHOT-S01E002-SC002-001', expression, seconds: 4 }) });
        showOutput(preview.media_url, preview.provider, preview.output, preview.duration_seconds); setView('workspace'); log(`分镜 Rig 预览已生成：${preview.output}`);
      } catch (error) { log(error.message, true); }
      finally { button.disabled = false; button.textContent = '按分镜预览'; }
    }));
    document.querySelectorAll('[data-final-rig-preview]').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true; button.textContent = '正在合成…';
      try {
        const expression = button.parentElement.querySelector('[data-rig-expression]')?.value || 'neutral';
        const preview = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/storyboard-final-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rig_id: button.dataset.finalRigPreview, shot_id: 'SHOT-S01E002-SC002-001', expression, seconds: 4 }) });
        showOutput(preview.media_url, preview.provider, preview.output, 4); setView('workspace'); log(`最终镜头已合成：${preview.output}`);
      } catch (error) { log(error.message, true); }
      finally { button.disabled = false; button.textContent = '生成最终镜头'; }
    }));
    document.querySelectorAll('[data-save-final-review]').forEach((button) => button.addEventListener('click', async () => {
      const checks = Object.fromEntries([...target.querySelectorAll('[data-final-check]')].map((select) => [select.dataset.finalCheck, select.value]));
      const status = Object.values(checks).every((value) => value === 'PASS') ? 'APPROVED' : (Object.values(checks).includes('CHANGES_REQUESTED') ? 'CHANGES_REQUESTED' : 'PENDING');
      button.disabled = true; button.textContent = '正在保存…';
      try {
        await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/final-shot-review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ checks, status, reviewer: target.querySelector('[data-final-reviewer]').value, note: target.querySelector('[data-final-note]').value }) });
        log(`最终镜头审片状态已保存：${status}`); await loadCharacterAssetGallery();
      } catch (error) { log(error.message, true); button.disabled = false; button.textContent = '保存审片'; }
    }));
    document.querySelectorAll('[data-run-final-batch]').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true; button.textContent = '正在建立批量任务…';
      try {
        const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/storyboard-final-batch-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        showStudioDetail('批量最终镜头任务', result, `/api/novel-anime/projects/${encodeURIComponent(projectId)}/storyboard-final-batch-preview`); log(`已建立 ${result.shot_count} 个镜头任务`);
      } catch (error) { log(error.message, true); button.disabled = false; button.textContent = '批量生成当前角色镜头'; }
    }));
  } catch (error) { target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`; }
}

async function loadEpisodeMasterGallery() {
  const target = $('#episodeMasterGallery');
  if (!target || !state.studio?.directory_id) return;
  const projectId = state.studio.directory_id;
  const options = (value) => [
    ['PENDING', '待审核'], ['PASS', '通过'], ['CHANGES_REQUESTED', '需修改'],
  ].map(([status, label]) => `<option value="${status}" ${status === value ? 'selected' : ''}>${label}</option>`).join('');
  try {
    const [result, providerTests] = await Promise.all([
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/episode-masters`),
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/provider-motion-tests`),
    ]);
    if (!result.episodes?.length) { target.innerHTML = '<div class="empty-state">尚未生成集级母版。</div>'; return; }
    const providerSection = providerTests.tests?.length ? `<div class="provider-test-section"><div class="provider-test-heading"><div><span class="section-kicker">MOTION PROVIDER TESTS</span><strong>第一集 3 个动作模型对比输入包已准备</strong><small>${escapeHtml(providerTests.remote_execution)} · 尚未上传素材或产生费用</small></div></div><div class="provider-test-grid">${providerTests.tests.map((test) => `<article class="provider-test-card"><img src="${escapeHtml(test.start_frame_url || '')}" alt="${escapeHtml(test.label)}"><div><span>${escapeHtml(test.provider)}</span><strong>${escapeHtml(test.label)}</strong><small>${escapeHtml(test.motion_goal)} · ${test.target_duration_seconds} 秒</small><p>${escapeHtml(test.prompt)}</p><em>${escapeHtml(test.status)}</em></div></article>`).join('')}</div></div>` : '';
    target.innerHTML = `<div class="episode-master-summary"><div><span class="section-kicker">FIVE EPISODE MASTERS</span><strong>${result.episode_count} 集已生成 · ${escapeHtml(result.status)} · 技术 QC ${escapeHtml(result.technical_qc?.status || 'NOT_RUN')}</strong><small>技术检查 ${result.technical_qc?.passed_episode_count || 0}/${result.technical_qc?.episode_count || result.episode_count} 集通过；整体人审：${escapeHtml(result.human_review?.status || 'PENDING')}。每集四项检查全部通过后，系统才会标记该集已批准。</small></div><button class="secondary-button small-button" data-open-episode-qc>查看技术报告</button></div>${providerSection}<div class="episode-master-grid">${result.episodes.map((episode) => {
      const review = episode.human_review || {};
      const checks = review.checks || {};
      return `<article class="episode-master-card" data-episode-card="${escapeHtml(episode.episode_id)}"><video controls playsinline preload="metadata" poster="${escapeHtml(episode.qc_frame_url || '')}" src="${escapeHtml(episode.media_url || '')}"></video><div class="episode-master-copy"><div class="episode-master-head"><strong>${escapeHtml(episode.episode_id)}</strong><span class="review-status ${review.status === 'APPROVED' ? 'approved' : review.status === 'CHANGES_REQUESTED' ? 'changes' : ''}">${escapeHtml(review.status || 'PENDING')}</span></div><small>${Number(episode.duration_seconds || 0).toFixed(1)} 秒 · ${episode.segment_count || 0} 个镜头单元 · 已烧录字幕</small><div class="episode-check-grid"><label>剧情连贯<select class="compact-select" data-episode-check="story">${options(checks.story || 'PENDING')}</select></label><label>画面<select class="compact-select" data-episode-check="picture">${options(checks.picture || 'PENDING')}</select></label><label>声音<select class="compact-select" data-episode-check="audio">${options(checks.audio || 'PENDING')}</select></label><label>字幕<select class="compact-select" data-episode-check="subtitles">${options(checks.subtitles || 'PENDING')}</select></label></div><input class="text-field" data-episode-reviewer placeholder="审核人（记录结果时必填）" value="${escapeHtml(review.reviewed_by || '')}"><input class="text-field" data-episode-note placeholder="修改意见或备注" value="${escapeHtml(review.note || '')}"><div class="episode-master-actions"><button class="secondary-button small-button" data-save-episode-review="${escapeHtml(episode.episode_id)}">保存本集审片</button><a href="${escapeHtml(episode.subtitle_url || '#')}" target="_blank" rel="noopener noreferrer">查看字幕文件</a></div></div></article>`;
    }).join('')}</div>`;
    target.querySelector('[data-open-episode-qc]')?.addEventListener('click', async () => {
      try {
        const qc = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/episode-masters/qc`);
        showStudioDetail('五集母版技术 QC', qc, `/api/novel-anime/projects/${encodeURIComponent(projectId)}/episode-masters/qc`);
      } catch (error) { log(error.message, true); }
    });
    target.querySelectorAll('[data-save-episode-review]').forEach((button) => button.addEventListener('click', async () => {
      const card = button.closest('[data-episode-card]');
      const checks = Object.fromEntries([...card.querySelectorAll('[data-episode-check]')].map((select) => [select.dataset.episodeCheck, select.value]));
      button.disabled = true; button.textContent = '正在保存…';
      try {
        const saved = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/episode-masters/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ episode_id: button.dataset.saveEpisodeReview, checks, reviewer: card.querySelector('[data-episode-reviewer]').value, note: card.querySelector('[data-episode-note]').value }) });
        log(`${saved.episode_id} 审片状态已保存：${saved.human_review.status}`);
        await loadEpisodeMasterGallery();
      } catch (error) { log(error.message, true); button.disabled = false; button.textContent = '保存本集审片'; }
    }));
  } catch (error) { target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`; }
}

async function openStudioResource(workspaceId, key, value) {
  const projectId = state.studio?.directory_id;
  const endpointName = RESOURCE_ENDPOINTS[workspaceId]?.[key];
  if (!projectId || !endpointName) { showStudioDetail(key, value); return; }
  try {
    const endpoint = `/api/novel-anime/projects/${encodeURIComponent(projectId)}/${endpointName}`;
    const payload = await api(endpoint);
    showStudioDetail(key, payload, endpoint);
  } catch (error) { showStudioDetail(`${key}（摘要）`, { error: error.message, summary: value }); }
}

function renderStudio() {
  if (!state.studio) {
    $('#studioContent').innerHTML = '<div class="empty-state">请选择一个国漫项目后再进入制作台。</div>';
    $('#studioReadiness').innerHTML = '';
    return;
  }
  const workspaces = state.studio.workspaces || [];
  const active = workspaces.find((item) => item.id === state.currentWorkspace) || workspaces[0];
  state.currentWorkspace = active.id;
  $('#studioTitle').textContent = active.title;
  $('#studioSubtitle').textContent = active.description;
  const select = $('#studioProjectSelect');
  select.innerHTML = state.animeProjects.map((item) => `<option value="${escapeHtml(item.directory_id)}">${escapeHtml(item.title)}</option>`).join('');
  select.value = state.studio.directory_id;
  $('#studioTabs').innerHTML = workspaces.map((item) => `<button class="studio-tab${item.id === active.id ? ' active' : ''}" data-studio-workspace="${escapeHtml(item.id)}">${escapeHtml(item.title)}</button>`).join('');
  document.querySelectorAll('[data-studio-workspace]').forEach((button) => button.addEventListener('click', () => { state.currentWorkspace = button.dataset.studioWorkspace; $('#studioDetail').classList.add('hidden'); renderStudio(); }));
  renderReadiness();
  const entries = Object.entries(active.data || {}).filter(([key]) => key !== 'project' && key !== 'readiness');
  const cards = entries.map(([key, value]) => `<button class="studio-data-card" data-studio-resource="${escapeHtml(key)}"><strong>${escapeHtml(key)}</strong><small>${escapeHtml(compactValue(value))}</small><span class="card-link">查看详情 →</span></button>`).join('');
  const action = active.id === 'review' ? `<div class="review-action"><strong>记录审片问题</strong><div class="form-row"><input id="issueTitle" class="text-field" placeholder="问题标题"><input id="issueRefs" class="text-field" placeholder="关联 ID（逗号分隔）"><button class="secondary-button small-button" id="issueButton">创建问题单</button></div><small>问题会写入项目 QC，仍需人工处理后才能通过发布门。</small></div>` : '';
  const characterGallery = active.id === 'assets' ? '<div class="native-asset-section"><div class="panel-heading"><div><span class="section-kicker">LOCAL CHARACTER ASSETS</span><h3>角色转面与零成本动作预览</h3><p class="panel-subtitle">直接使用本地透明角色图和程序化镜头，不上传素材，不调用外部模型。</p></div></div><div class="character-asset-gallery" id="characterAssetGallery"><div class="empty-state">正在载入角色资产…</div></div></div>' : '';
  const episodeMasterGallery = active.id === 'render' ? '<div class="native-asset-section"><div class="panel-heading"><div><span class="section-kicker">LOCAL EPISODE REVIEW</span><h3>《镜花缘》前五集本地母版</h3><p class="panel-subtitle">在线播放、检查剧情/画面/声音/字幕，并逐集保存人工审核。这里不会自动发布。</p></div></div><div id="episodeMasterGallery"><div class="empty-state">正在载入五集母版…</div></div></div>' : '';
  $('#studioContent').innerHTML = `<div class="studio-hero"><div><span class="section-kicker">${escapeHtml(state.studio.project_id)}</span><h3>${escapeHtml(state.studio.title)} · ${escapeHtml(active.title)}</h3><p>${escapeHtml(active.description)}。页面直接读取项目 Schema、状态机和 QC 结果，不维护 Web 独立数据。</p></div><span class="studio-status">${escapeHtml(active.status)}</span></div><div class="studio-data-grid">${cards || '<div class="empty-state">当前工作区暂无数据。</div>'}</div>${characterGallery}${episodeMasterGallery}${action}<div class="studio-api">工作区 API：/api/novel-anime/projects/${encodeURIComponent(state.studio.directory_id)}/workspaces</div>`;
  if (active.id === 'assets') loadCharacterAssetGallery();
  if (active.id === 'render') loadEpisodeMasterGallery();
  document.querySelectorAll('[data-studio-resource]').forEach((button) => button.addEventListener('click', () => {
    const key = button.dataset.studioResource;
    openStudioResource(active.id, key, active.data[key]);
  }));
  $('#issueButton')?.addEventListener('click', submitIssue);
}

function setView(view, workspace = state.currentWorkspace) {
  state.currentView = view;
  if (view === 'studio') state.currentWorkspace = workspace;
  document.querySelectorAll('.nav-item').forEach((nav) => nav.classList.toggle('active', nav.dataset.view === view && (view !== 'studio' || nav.dataset.workspace === state.currentWorkspace)));
  ['workspace', 'anime', 'studio', 'imageStudio', 'projects', 'providers'].forEach((name) => $(`#${name}View`).classList.toggle('hidden', name !== view));
  $('#outputPanel').classList.toggle('hidden', view !== 'workspace');
  $('#logPanel')?.classList.toggle('hidden', view !== 'workspace');
  if (view === 'projects') renderProjectTable();
  if (view === 'anime') renderAnimeProjects();
  if (view === 'studio') renderStudio();
  if (view === 'imageStudio') {
    const target = state.imageStudioProjectId || state.animeProjects[0]?.directory_id;
    if (target) loadImageStudio(target).catch((error) => log(error.message, true));
  }
  if (view === 'providers') renderProviderSettings();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderImageStudio() {
  const data = state.imageStudio;
  const select = $('#imageStudioProject');
  const projects = state.animeProjects || [];
  select.innerHTML = projects.map((item) => `<option value="${escapeHtml(item.directory_id)}">${escapeHtml(item.title)}</option>`).join('');
  if (data?.project_id) select.value = data.project_id;

  const providers = data?.providers || [];
  const openai = providers.find((item) => item.provider_id === 'OPENAI_IMAGE' || item.id === 'openai_image') || data?.provider || {};
  const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image') || {};
  const routing = data?.routing || {};
  const providerSelect = $('#imageStudioProviderSelect');
  if (providerSelect) providerSelect.value = state.imageStudioProviderPreference || data?.default_provider || 'AUTO';
  const localReady = Boolean(comfyui.connected && comfyui.workflow_ready);
  const remoteReady = Boolean(openai.configured);
  const preference = state.imageStudioProviderPreference || 'AUTO';
  $('#imageStudioProvider').textContent = preference === 'COMFYUI_IMAGE' ? 'ComfyUI Local' : preference === 'OPENAI_IMAGE' ? (openai.label || 'OpenAI Image') : (localReady ? 'AUTO → ComfyUI' : 'AUTO → OpenAI fallback');
  $('#imageStudioModel').textContent = localReady ? (comfyui.checkpoint || 'Local checkpoint') : (openai.model || '—');
  $('#imageStudioStatus').textContent = (localReady || remoteReady) ? 'READY' : 'NO PROVIDER';
  $('#imageStudioStatus').classList.toggle('off', !(localReady || remoteReady));
  $('#imageStudioRoute').textContent = routing.final_visual_route || 'IMAGE_PROVIDER_ROUTER';
  $('#imageStudioBlenderRole').textContent = \`Blender · \${routing.blender_role || 'AUXILIARY_3D_CONTROL'}\`;
  $('#imageStudioComfyUrl').value = comfyui.base_url || 'http://127.0.0.1:8188';
  $('#imageStudioComfyHint').textContent = localReady
    ? \`本地 ComfyUI 已连接 · \${comfyui.checkpoint_count || 0} 个 checkpoint · 不产生远程 API 费用。\`
    : \`本地 ComfyUI 未就绪：\${comfyui.detail || '请启动 ComfyUI 或修改地址'}\`;
  $('#imageStudioKeyHint').textContent = openai.configured
    ? \`OpenAI fallback 已配置（\${openai.source === 'environment' ? '环境变量' : '当前 Web 会话'}），密钥不会显示或写入文件。\`
    : 'OpenAI 仅作为远程 fallback；未配置时 AUTO 不会产生远程调用。';

  const character = data?.character || {};
  const lock = character.visual_lock || {};
  $('#imageStudioCharacterLock').innerHTML = `<strong>${escapeHtml(character.character_id || 'CHAR-CHILD-001')} · ${escapeHtml(character.name || '营地小女孩')}</strong><small>${escapeHtml(lock.face || '')}</small><small>${escapeHtml(lock.hair || '')}</small><small>${escapeHtml(lock.costume || '')}</small>`;

  const items = data?.items || [];
  $('#imageStudioCount').textContent = `${items.length} 张`;
  if (!items.length) {
    $('#imageStudioGallery').innerHTML = '<div class="empty-state">还没有 AI 生图资产。</div>';
    return;
  }
  $('#imageStudioGallery').innerHTML = items.map((item, index) => `
    <button class="image-studio-thumb" data-image-studio-index="${index}">
      <img src="${escapeHtml(item.media_url)}" alt="${escapeHtml(item.artifact_type || 'image')}" loading="lazy">
      <span><strong>${escapeHtml(item.artifact_type === 'character_bible' ? '角色定妆板' : '镜头关键帧')}</strong><small>${escapeHtml(item.model || '')} · ${escapeHtml(item.review_status || 'PENDING')}</small></span>
    </button>
  `).join('');
  document.querySelectorAll('[data-image-studio-index]').forEach((button) => button.addEventListener('click', () => {
    const item = items[Number(button.dataset.imageStudioIndex)];
    showImageStudioResult(item);
  }));
  if ($('#imageStudioResult').classList.contains('hidden')) showImageStudioResult(items[0]);
}

function showImageStudioResult(item) {
  if (!item) return;
  state.imageStudioSelected = item;
  $('#imageStudioEmpty').classList.add('hidden');
  $('#imageStudioResult').classList.remove('hidden');
  $('#imageStudioPreview').src = item.media_url;
  $('#imageStudioResultType').textContent = item.artifact_type === 'character_bible' ? '角色定妆板' : '镜头关键帧';
  $('#imageStudioResultPath').textContent = item.output || '—';
  $('#imageStudioResultInfo').textContent = `${item.provider || 'Image Provider'} · ${item.model || ''} · ${item.size || ''} · 人工审核 ${item.review_status || 'PENDING'}`;
  $('#imageStudioReview').textContent = item.review_status || 'PENDING';
}

async function loadImageStudio(projectId = state.imageStudioProjectId || state.animeProjects[0]?.directory_id) {
  if (!projectId) return;
  state.imageStudioProjectId = projectId;
  state.imageStudio = await api(`/api/image-studio/status?project_id=${encodeURIComponent(projectId)}`);
  renderImageStudio();
}

async function saveImageStudioKey() {
  const button = $('#imageStudioSaveKey');
  const input = $('#imageStudioKey');
  const key = input.value.trim();
  if (!key) { log('请输入 OpenAI API Key', true); return; }
  button.disabled = true;
  button.textContent = '保存中…';
  try {
    await api('/api/settings/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'openai_image', key }),
    });
    input.value = '';
    await loadImageStudio(state.imageStudioProjectId);
    log('OpenAI Image Key 已保存到当前 Web 服务进程');
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; button.textContent = '保存 Key'; }
}

async function saveComfyUIEndpoint() {
  const button = $('#imageStudioSaveComfy');
  const baseUrl = $('#imageStudioComfyUrl').value.trim();
  if (!baseUrl) { log('请输入 ComfyUI 地址', true); return; }
  button.disabled = true;
  button.textContent = '检测中…';
  try {
    const result = await api('/api/settings/integrations', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ integration: 'comfyui', base_url: baseUrl }),
    });
    await loadImageStudio(state.imageStudioProjectId);
    log(\`ComfyUI：\${result.detail || (result.connected ? '连接正常' : '未连接')}\`);
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; button.textContent = '保存并检测'; }
}

async function reviewImageStudio(status) {
  const item = state.imageStudioSelected;
  const projectId = state.imageStudioProjectId;
  if (!item?.metadata || !projectId) { log('请先选择一张 AI 生图结果', true); return; }
  const label = status === 'APPROVED' ? '通过' : '需要修改';
  let note = '';
  if (status === 'CHANGES_REQUESTED') {
    note = window.prompt('请输入需要修改的内容（可留空）：', '') ?? '';
  }
  try {
    const result = await api('/api/image-studio/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        metadata: item.metadata,
        status,
        note,
      }),
    });
    showImageStudioResult(result);
    await loadImageStudio(projectId);
    showImageStudioResult(result);
    log(`AI 生图人工审核：${label}`);
  } catch (error) { log(error.message, true); }
}

async function generateImageStudio(kind) {
  const projectId = state.imageStudioProjectId || state.animeProjects[0]?.directory_id;
  if (!projectId) { log('没有可用的国漫项目', true); return; }
  const providers = state.imageStudio?.providers || [];
  const openai = providers.find((item) => item.provider_id === 'OPENAI_IMAGE' || item.id === 'openai_image') || state.imageStudio?.provider || {};
  const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image') || {};
  const preference = state.imageStudioProviderPreference || 'AUTO';
  const localReady = Boolean(comfyui.connected && comfyui.workflow_ready);
  const usesRemote = preference === 'OPENAI_IMAGE' || (preference === 'AUTO' && !localReady);
  const label = kind === 'character-bible' ? '角色定妆板' : '镜头关键帧';
  if (preference === 'COMFYUI_IMAGE' && !localReady) { log('ComfyUI 本地 Provider 尚未就绪', true); return; }
  if (usesRemote) {
    if (!openai.configured) { log('本地 ComfyUI 不可用，OpenAI fallback 也未配置', true); return; }
    if (!window.confirm(\`将使用 OpenAI fallback 生成\${label}，可能产生 API 费用。确认继续？\`)) return;
  }

  const button = kind === 'character-bible' ? $('#generateCharacterBibleButton') : $('#generateKeyframeButton');
  const original = button.innerHTML;
  button.disabled = true;
  button.textContent = '生成中…';
  log(`开始生成${label} · ${usesRemote ? 'OpenAI fallback' : 'ComfyUI local'}…`);
  try {
    const result = await api(`/api/image-studio/${kind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        custom_prompt: $('#imageStudioPrompt').value.trim(),
        confirm_billable: usesRemote,
        provider_preference: preference,
      }),
    });
    showImageStudioResult(result);
    await loadImageStudio(projectId);
    showImageStudioResult(result);
    log(`${label}生成完成：${result.output}`);
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; button.innerHTML = original; }
}

async function loadStudio(projectId = state.studioProjectId || state.animeProjects[0]?.directory_id) {
  if (!projectId) return;
  state.studioProjectId = projectId;
  const [studio, readiness, backups] = await Promise.all([
    api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/workspaces`),
    api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/readiness`),
    api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/backups`),
  ]);
  state.studio = studio;
  state.readiness = readiness;
  state.backups = backups;
  renderStudio();
}

async function createSnapshot() {
  if (!state.studio?.directory_id) return;
  const button = $('#snapshotButton');
  button.disabled = true;
  try {
    const label = `Web 工作台快照 ${new Date().toLocaleString('zh-CN', { hour12: false })}`;
    await api(`/api/novel-anime/projects/${encodeURIComponent(state.studio.directory_id)}/backups`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label }) });
    await loadStudio(state.studio.directory_id);
    log(`已创建项目快照：${label}`);
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; }
}

async function submitIssue() {
  const title = $('#issueTitle')?.value.trim();
  const refs = ($('#issueRefs')?.value || '').split(',').map((item) => item.trim()).filter(Boolean);
  if (!title) { log('请先填写问题标题', true); return; }
  try {
    await api(`/api/novel-anime/projects/${encodeURIComponent(state.studio.directory_id)}/qc/issues`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, target_refs: refs }) });
    log(`已创建 QC 问题单：${title}`);
    await loadStudio(state.studio.directory_id);
    state.currentWorkspace = 'review';
    renderStudio();
  } catch (error) { log(error.message, true); }
}

function renderAssets() {
  const images = (state.project?.files || []).filter((file) => file.kind === 'image');
  $('#imageCount').textContent = `${images.length} 张图片`;
  if (!images.length) {
    $('#assetGrid').innerHTML = '<div class="empty-state">项目中还没有可用图片。</div>';
    state.selectedImage = null;
    return;
  }
  if (!state.selectedImage || !images.some((image) => image.path === state.selectedImage)) state.selectedImage = images[0].path;
  $('#assetGrid').innerHTML = images.map((image) => `<button class="asset-card${image.path === state.selectedImage ? ' selected' : ''}" data-image="${escapeHtml(image.path)}"><img src="/media/${encodeURIComponent(state.project.id)}/${image.path.split('/').map(encodeURIComponent).join('/')}" alt="${escapeHtml(image.name)}" loading="lazy"><span class="asset-name">${escapeHtml(image.name)}</span></button>`).join('');
  document.querySelectorAll('.asset-card').forEach((button) => button.addEventListener('click', () => { state.selectedImage = button.dataset.image; renderAssets(); updateGenerateButton(); }));
}

function renderEpisodes() {
  const episodes = state.project?.episodes || [];
  $('#episodeCount').textContent = `${episodes.length} 集`;
  if (!episodes.length) {
    $('#episodeList').innerHTML = '<div class="empty-state">还没有本地试播集。</div>';
    return;
  }
  $('#episodeList').innerHTML = episodes.map((episode) => `<button class="episode-card" data-episode-media="${escapeHtml(episode.media_url)}" data-episode-title="${escapeHtml(episode.episode_id + '｜' + episode.title)}"><span class="episode-index">${escapeHtml(episode.episode_id.replace('episode-', 'EP'))}</span><span><strong>${escapeHtml(episode.title)}</strong><small>本地分镜 · 配音 · 字幕</small></span><span class="episode-arrow">▶</span></button>`).join('');
  document.querySelectorAll('[data-episode-media]').forEach((button) => button.addEventListener('click', () => {
    showOutput(button.dataset.episodeMedia, 'local_ken_burns', button.dataset.episodeTitle, 8.5);
    log(`已载入试播集：${button.dataset.episodeTitle}`);
  }));
}

function updateGenerateButton() {
  const remote = state.providers.find((provider) => provider.id === state.selectedProvider)?.remote;
  $('#generateButton').disabled = !state.project || !state.selectedImage || (remote && !$('#billableConfirm').checked);
}

async function loadProject(projectId) {
  state.project = await api(`/api/projects/${encodeURIComponent(projectId)}`);
  const animeProject = state.animeProjects.find((item) => item.directory_id === state.project.id);
  $('#projectSelect').value = state.project.id;
  renderStats();
  renderAssets();
  renderEpisodes();
  $('#projectTitle').textContent = animeProject ? `《${animeProject.title}》·国风动态漫试点` : state.project.id;
  $('#projectDescription').textContent = animeProject ? '固定角色与场景资产驱动的低成本本地动态漫，远程视频模型仅作为可选增强。' : 'VideoCreator Engine 项目资产。';
  const latestVideo = [...(state.project.files || [])].reverse().find((file) => file.kind === 'video');
  if (latestVideo) {
    const mediaUrl = `/media/${encodeURIComponent(state.project.id)}/${latestVideo.path.split('/').map(encodeURIComponent).join('/')}`;
    showOutput(mediaUrl, 'local_ken_burns', latestVideo.path, latestVideo.path.includes('motion-test') ? 6 : null);
  }
  if ($('#projectTable')) renderProjectTable();
  updateGenerateButton();
}

async function load() {
  try {
    const [projects, animeProjects, health] = await Promise.all([api('/api/projects'), api('/api/novel-anime/projects'), api('/api/health')]);
    state.projects = projects.projects;
    state.animeProjects = animeProjects.projects;
    state.providers = health.providers;
    state.integrations = health.integrations || [];
    if (state.animeProjects.length) {
      await loadStudio(state.studioProjectId || state.animeProjects[0].directory_id);
      state.pipelineProjectId = state.pipelineProjectId || state.animeProjects[0].directory_id;
      await loadPipeline(state.pipelineProjectId);
    }
    $('#projectSelect').innerHTML = state.projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');
    renderProviders();
    renderProviderSettings();
    renderProjectTable();
    renderAnimeProjects();
    if (state.animeProjects.length) {
      state.imageStudioProjectId = state.imageStudioProjectId || state.animeProjects[0].directory_id;
      await loadImageStudio(state.imageStudioProjectId);
    }
    if (state.projects.length) await loadProject(state.projects.find((project) => project.id === 'jinghua-yuan-local-pilot')?.id || state.projects[0].id);
    log(`已载入 ${state.projects.length} 个项目和 ${state.providers.length} 条 Provider 路线`);
  } catch (error) { log(error.message, true); }
}

async function generate() {
  const button = $('#generateButton');
  button.disabled = true;
  button.textContent = '生成中…';
  log(`开始调用 ${state.selectedProvider}`);
  try {
    const result = await api('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      project_id: state.project.id, image_path: state.selectedImage, provider: state.selectedProvider, model: $('#modelInput').value, shot_duration: Number($('#durationInput').value), prompt: $('#promptInput').value, confirm_billable: $('#billableConfirm').checked,
    }) });
    showOutput(result.media_url, result.provider, result.output_path, result.duration_seconds);
    log(`生成完成：${result.output_path}`);
  } catch (error) { log(error.message, true); $('#outputStatus').textContent = '生成失败'; }
  finally { button.innerHTML = '<span>✦</span>生成镜头'; updateGenerateButton(); }
}

function showOutput(mediaUrl, provider, outputPath, duration) {
  $('#outputEmpty').classList.add('hidden');
  $('#outputResult').classList.remove('hidden');
  $('#outputVideo').src = mediaUrl;
  $('#resultProvider').textContent = provider;
  $('#resultPath').textContent = outputPath;
  $('#resultDuration').textContent = duration ? `${Number(duration).toFixed(1)} 秒 · 可人工审核` : '本地成片 · 可人工审核';
  $('#outputStatus').textContent = '已完成';
}

async function generateStoryboard() {
  const button = $('#storyboardButton');
  button.disabled = true;
  button.textContent = '分镜生成中…';
  log('开始生成完整本地分镜（3 镜头 + 配音 + 字幕）');
  try {
    const result = await api('/api/storyboard/local', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: state.project.id }) });
    showOutput(result.media_url, result.provider, result.output, 8.34);
    log(`完整本地分镜完成：${result.output}`);
  } catch (error) { log(error.message, true); $('#outputStatus').textContent = '生成失败'; }
  finally { button.innerHTML = '<span>◈</span>生成完整本地分镜'; button.disabled = false; }
}

$('#pipelineProjectSelect').addEventListener('change', (event) => loadPipeline(event.target.value).catch((error) => log(error.message, true)));
$('#pipelineRunButton').addEventListener('click', runAutoPipeline);
$('#pipelineApproveButton').addEventListener('click', approvePipeline);
$('#imageStudioProject').addEventListener('change', (event) => loadImageStudio(event.target.value).catch((error) => log(error.message, true)));
$('#imageStudioSaveKey').addEventListener('click', saveImageStudioKey);
$('#imageStudioSaveComfy').addEventListener('click', saveComfyUIEndpoint);
$('#imageStudioProviderSelect').addEventListener('change', (event) => {
  state.imageStudioProviderPreference = event.target.value;
  renderImageStudio();
});
$('#generateCharacterBibleButton').addEventListener('click', () => generateImageStudio('character-bible'));
$('#generateKeyframeButton').addEventListener('click', () => generateImageStudio('keyframe'));
$('#imageStudioApproveButton').addEventListener('click', () => reviewImageStudio('APPROVED'));
$('#imageStudioChangesButton').addEventListener('click', () => reviewImageStudio('CHANGES_REQUESTED'));
$('#projectSelect').addEventListener('change', (event) => loadProject(event.target.value).catch((error) => log(error.message, true)));
$('#billableConfirm').addEventListener('change', updateGenerateButton);
$('#generateButton').addEventListener('click', generate);
$('#storyboardButton').addEventListener('click', generateStoryboard);
$('#refreshButton').addEventListener('click', () => load());
$('#studioRefreshButton').addEventListener('click', () => loadStudio().catch((error) => log(error.message, true)));
$('#snapshotButton').addEventListener('click', createSnapshot);
$('#studioProjectSelect').addEventListener('change', (event) => loadStudio(event.target.value).catch((error) => log(error.message, true)));
$('#clearLog').addEventListener('click', () => { $('#logList').innerHTML = ''; });
document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => setView(item.dataset.view, item.dataset.workspace || state.currentWorkspace)));
load();
