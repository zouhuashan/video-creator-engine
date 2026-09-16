const state = { projects: [], animeProjects: [], project: null, providers: [], selectedProvider: 'local_ken_burns', selectedImage: null, currentView: 'workspace' };

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
  $('#providerSettings').innerHTML = remoteProviders.map((provider) => {
    const ready = provider.configured;
    const status = ready ? (provider.source === 'session' ? '本次服务已配置' : '环境变量已配置') : '尚未配置';
    return `<div class="provider-setting"><div class="provider-setting-head"><div><strong>${escapeHtml(provider.label)}</strong><small>环境变量：${escapeHtml(provider.env)} · 输入后只保存在当前服务进程内</small></div><span class="key-status${ready ? ' ready' : ''}">● ${escapeHtml(status)}</span></div><div class="key-form"><input type="password" autocomplete="off" data-key-input="${escapeHtml(provider.id)}" placeholder="粘贴 ${escapeHtml(provider.label)} API Key"><button data-save-key="${escapeHtml(provider.id)}">保存密钥</button></div></div>`;
  }).join('');
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
    return `<article class="anime-project-card"><div class="anime-project-head"><div><span class="section-kicker">${escapeHtml(project.ip_id)} · ${escapeHtml(project.series_id)}</span><h3>${escapeHtml(project.title)}</h3></div><span class="result-chip">${escapeHtml(project.status)}</span></div><div class="hierarchy-row"><span>剧集 1</span><span>${project.season_count} 季</span><span>${project.episode_count} 集</span></div><div class="episode-token-row">${project.episode_ids.map((id) => `<span>${escapeHtml(id)}</span>`).join('')}</div><div class="source-row"><span>${escapeHtml(sourceText)}</span><strong class="${sources?.publication_allowed ? 'allowed' : 'blocked'}">${sources?.publication_allowed ? '可发布' : '禁止发布'}</strong></div><div class="runtime-row">${escapeHtml(bibleText)}</div><div class="runtime-row">${escapeHtml(planText)}</div><div class="runtime-row">${escapeHtml(episodePlanText)}</div><div class="runtime-row">${escapeHtml(scriptText)}</div><div class="runtime-row">${escapeHtml(reviewText)}</div><div class="runtime-row">${escapeHtml(visualText)}</div><div class="runtime-row">${escapeHtml(characterText)}</div><div class="runtime-row">${escapeHtml(environmentText)}</div><div class="runtime-row">${escapeHtml(assetReviewText)}</div><div class="runtime-row">${escapeHtml(shotText)}</div><div class="runtime-row">${escapeHtml(storyboardText)}</div><div class="runtime-row">${escapeHtml(animaticText)}</div><div class="runtime-row">${escapeHtml(animaticReviewText)}</div><div class="repository-row"><small>${escapeHtml(repositoryText)}</small><button data-impact-project="${escapeHtml(project.directory_id)}" data-impact-root="${escapeHtml(project.ip_id)}" ${repository ? '' : 'disabled'}>分析 IP 影响</button></div><div class="runtime-row">${escapeHtml(runtimeText)}</div><div class="impact-result" data-impact-result="${escapeHtml(project.directory_id)}"></div><small class="manifest-note">${escapeHtml(project.project_id)} · novel-anime-project.json</small></article>`;
  }).join('');
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

function setView(view) {
  state.currentView = view;
  document.querySelectorAll('.nav-item').forEach((nav) => nav.classList.toggle('active', nav.dataset.view === view));
  ['workspace', 'anime', 'projects', 'providers'].forEach((name) => $(`#${name}View`).classList.toggle('hidden', name !== view));
  $('#outputPanel').classList.toggle('hidden', view !== 'workspace');
  $('#logPanel')?.classList.toggle('hidden', view !== 'workspace');
  if (view === 'projects') renderProjectTable();
  if (view === 'anime') renderAnimeProjects();
  if (view === 'providers') renderProviderSettings();
  window.scrollTo({ top: 0, behavior: 'smooth' });
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
  $('#projectSelect').value = state.project.id;
  renderStats();
  renderAssets();
  renderEpisodes();
  $('#projectTitle').textContent = state.project.id === 'jinghua-yuan-local-pilot' ? '《镜花缘》·唐小山试制' : state.project.id;
  $('#projectDescription').textContent = state.project.id === 'jinghua-yuan-local-pilot' ? '角色、场景、连续剧情与动态镜头的本地验证项目。' : 'VideoCreator Engine 项目资产。';
  if ($('#projectTable')) renderProjectTable();
  updateGenerateButton();
}

async function load() {
  try {
    const [projects, animeProjects, health] = await Promise.all([api('/api/projects'), api('/api/novel-anime/projects'), api('/api/health')]);
    state.projects = projects.projects;
    state.animeProjects = animeProjects.projects;
    state.providers = health.providers;
    $('#projectSelect').innerHTML = state.projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');
    renderProviders();
    renderProviderSettings();
    renderProjectTable();
    renderAnimeProjects();
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
  $('#resultDuration').textContent = `${Number(duration || 0).toFixed(1)} 秒 · 可人工审核`;
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

$('#projectSelect').addEventListener('change', (event) => loadProject(event.target.value).catch((error) => log(error.message, true)));
$('#billableConfirm').addEventListener('change', updateGenerateButton);
$('#generateButton').addEventListener('click', generate);
$('#storyboardButton').addEventListener('click', generateStoryboard);
$('#refreshButton').addEventListener('click', () => load());
$('#clearLog').addEventListener('click', () => { $('#logList').innerHTML = ''; });
document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => setView(item.dataset.view)));
load();
