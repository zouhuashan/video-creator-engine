const state = { projects: [], animeProjects: [], project: null, providers: [], integrations: [], studio: null, readiness: null, backups: null, activeNovelProjectId: null, studioProjectId: null, imageStudio: null, imageStudioProjectId: null, imageStudioSelected: null, imageStudioProviderPreference: 'AUTO', imageStudioStylePreset: 'CINEMATIC_3D_DONGHUA', graybox: null, grayboxProjectId: null, grayboxPollTimer: null, gptKeyframes: null, gptKeyframePollTimer: null, gptCodexLogs: null, gptCodexLogsLoading: false, costFirstPlan: null, costFirstProjectId: null, pipeline: null, pipelineProjectId: null, voiceTimeline: null, voiceTimelineProjectId: null, finalAudio: null, finalAudioProjectId: null, novelImportResult: null, selectedProvider: 'local_ken_burns', selectedImage: null, currentView: 'workspace', currentWorkspace: 'overview' };
const ACTIVE_NOVEL_PROJECT_KEY = 'videocreator.activeNovelProjectId.v1';
const IMAGE_STYLE_PROJECT_KEY_PREFIX = 'videocreator.imageStylePreset.v2.';

function storedImageStylePreset(projectId) {
  const id = String(projectId || '').trim();
  if (!id) return '';
  try { return String(window.localStorage.getItem(IMAGE_STYLE_PROJECT_KEY_PREFIX + id) || '').trim(); }
  catch (_) { return ''; }
}

function rememberImageStylePreset(projectId, presetId) {
  const id = String(projectId || '').trim();
  const preset = String(presetId || '').trim();
  if (!id || !preset) return;
  try { window.localStorage.setItem(IMAGE_STYLE_PROJECT_KEY_PREFIX + id, preset); } catch (_) {}
}

function storedActiveNovelProjectId() {
  try { return String(window.localStorage.getItem(ACTIVE_NOVEL_PROJECT_KEY) || '').trim(); }
  catch (_) { return ''; }
}

function rememberActiveNovelProject(projectId) {
  const value = String(projectId || '').trim();
  if (!value) return;
  try { window.localStorage.setItem(ACTIVE_NOVEL_PROJECT_KEY, value); } catch (_) {}
}

function clearActiveNovelProject() {
  state.activeNovelProjectId = null;
  state.studioProjectId = null;
  state.pipelineProjectId = null;
  state.imageStudioProjectId = null;
  state.imageStudio = null;
  state.gptKeyframes = null;
  state.gptCodexLogs = null;
  state.gptCodexLogsLoading = false;
  state.costFirstPlan = null;
  state.costFirstProjectId = null;
  state.studio = null;
  state.pipeline = null;
  state.voiceTimeline = null;
  state.voiceTimelineProjectId = null;
  state.finalAudio = null;
  state.finalAudioProjectId = null;
  try { window.localStorage.removeItem(ACTIVE_NOVEL_PROJECT_KEY); } catch (_) {}
}

function resolveActiveNovelProject(preferred = '') {
  const projects = state.animeProjects || [];
  if (!projects.length) return '';

  const valid = (value) => {
    const id = String(value || '').trim();
    return id && projects.some((item) => item.directory_id === id) ? id : '';
  };

  // Explicit navigation/import always wins.
  const explicit = valid(preferred) || valid(state.novelImportResult?.directory_id) || valid(state.activeNovelProjectId);
  if (explicit) return explicit;

  // On a fresh page load, the newest imported novel is the default across the
  // whole product. This prevents an old browser-local selection from silently
  // sending new Image Studio assets into the wrong project.
  const newest = [...projects].sort((a, b) =>
    String(b.created_at || b.updated_at || '').localeCompare(String(a.created_at || a.updated_at || ''))
  )[0];
  if (newest?.directory_id) return newest.directory_id;

  return valid(storedActiveNovelProjectId()) || projects[0].directory_id;
}

function novelProjectOptionLabel(project) {
  const title = String(project?.title || project?.directory_id || '未命名项目');
  const sameTitleCount = (state.animeProjects || []).filter((item) => String(item.title || '') === String(project?.title || '')).length;
  if (sameTitleCount <= 1) return title;
  const id = String(project?.directory_id || '');
  return `${title} · ${id.slice(-8) || id}`;
}

function setActiveNovelProject(projectId, { persist = true } = {}) {
  const value = String(projectId || '').trim();
  if (!value || !state.animeProjects.some((item) => item.directory_id === value)) return '';
  state.activeNovelProjectId = value;
  state.studioProjectId = value;
  state.pipelineProjectId = value;
  state.imageStudioProjectId = value;
  state.voiceTimelineProjectId = value;
  state.finalAudioProjectId = value;
  if (persist) rememberActiveNovelProject(value);
  const selectors = ['#studioProjectSelect', '#pipelineProjectSelect', '#imageStudioProject'];
  selectors.forEach((selector) => {
    const element = $(selector);
    if (element && [...element.options].some((option) => option.value === value)) element.value = value;
  });
  if ($('#projectSelect') && state.projects.some((project) => project.id === value)) $('#projectSelect').value = value;
  return value;
}


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
  const raw = await response.text();
  let data = {};
  if (raw) {
    try { data = JSON.parse(raw); }
    catch (_) {
      if (!response.ok) throw new Error(`请求失败（${response.status}）：后端未返回有效 JSON；若刚更新了 VideoCreator，请重启一次 Web 服务。`);
      throw new Error('后端返回了无法解析的数据');
    }
  }
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
    select.innerHTML = state.animeProjects.map((item) => `<option value="${escapeHtml(item.directory_id)}">${escapeHtml(novelProjectOptionLabel(item))}</option>`).join('');
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
  `).join('') : '<div class="empty-state">点击“创建整集（本地执行）”，软件会真实执行可用本地步骤；远程计费仍不会被静默触发。</div>';

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

async function runPipelinePreflight() {
  const projectId = state.pipelineProjectId || state.animeProjects[0]?.directory_id;
  if (!projectId) { log('没有可用国漫项目', true); return; }
  const button = $('#pipelinePreflightButton');
  button.disabled = true;
  button.textContent = '自检中…';
  try {
    const result = await api(`/api/pipeline/preflight?project_id=${encodeURIComponent(projectId)}`);
    const comfy = result.comfyui || {};
    const tools = result.tools || {};
    const summary = [
      `ComfyUI ${comfy.connected && comfy.checkpoint_count ? 'READY' : 'BLOCKED'}`,
      `FFmpeg ${tools.ffmpeg ? 'READY' : 'MISSING'}`,
      `ffprobe ${tools.ffprobe ? 'READY' : 'MISSING'}`,
      `TTS ${tools.macos_say ? 'READY' : 'DEGRADED'}`,
    ].join(' · ');
    $('#pipelineNext').textContent = result.status === 'READY' ? `环境就绪 · ${summary}` : `环境阻断 · ${(result.blockers || []).join('；')}`;
    log(`流水线环境自检：${result.status} · ${summary}`, result.status !== 'READY');
  } catch (error) {
    log(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>✓</span>环境自检';
  }
}

async function runAutoPipeline() {
  const projectId = state.pipelineProjectId || state.animeProjects[0]?.directory_id;
  if (!projectId) { log('没有可用国漫项目', true); return; }
  const button = $('#pipelineRunButton');
  button.disabled = true;
  button.textContent = '整集执行中…';
  log(`启动整集软件流水线（本地真实执行）：${projectId}`);
  try {
    state.pipeline = await api('/api/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, dry_run: false, confirm_billable: false, image_provider: 'AUTO' }),
    });
    renderPipeline();
    log(`流水线完成：${state.pipeline.status} · ${state.pipeline.progress}%`);
  } catch (error) {
    log(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>▶</span>创建整集（本地执行）';
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

function formatGrayboxSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes} 分 ${rest} 秒`;
}

function syncGrayboxPolling() {
  const running = state.graybox?.render?.status === 'RUNNING';
  if (running && !state.grayboxPollTimer && state.grayboxProjectId) {
    state.grayboxPollTimer = window.setInterval(async () => {
      try {
        const current = await api(`/api/novel-anime/projects/${encodeURIComponent(state.grayboxProjectId)}/graybox`);
        state.graybox = current;
        renderGraybox();
      } catch (error) {
        $('#grayboxLiveSummary').textContent = `状态刷新失败：${error.message}`;
      }
    }, 2000);
  } else if (!running && state.grayboxPollTimer) {
    window.clearInterval(state.grayboxPollTimer);
    state.grayboxPollTimer = null;
  }
}

function renderGrayboxReferenceSelect(selector, candidates, boundPath, emptyLabel) {
  const select = $(selector);
  if (!select) return;
  const current = select.value;
  const items = Array.isArray(candidates) ? candidates : [];
  select.innerHTML = [
    `<option value="">${escapeHtml(emptyLabel)}</option>`,
    ...items.map((item) => {
      const status = item.review_status ? ` · ${item.review_status}` : '';
      const source = item.source === 'scene_upload'
        ? '上传场景'
        : item.source === 'image_studio_keyframe'
          ? '关键帧'
          : 'Image Studio';
      return `<option value="${escapeHtml(item.path)}">${escapeHtml(item.label || item.path)} · ${escapeHtml(source)}${escapeHtml(status)}</option>`;
    }),
  ].join('');
  const preferred = boundPath || current;
  if (preferred && items.some((item) => item.path === preferred)) select.value = preferred;
}

function renderGrayboxReferencePreview(imageSelector, emptySelector, entry) {
  const image = $(imageSelector);
  const empty = $(emptySelector);
  if (entry?.media_url) {
    if ((image.getAttribute('src') || '') !== entry.media_url) image.src = entry.media_url;
    image.classList.remove('hidden');
    empty.classList.add('hidden');
  } else {
    image.removeAttribute('src');
    image.classList.add('hidden');
    empty.classList.remove('hidden');
  }
}

async function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('读取场景参考图失败'));
    reader.onload = () => {
      const value = String(reader.result || '');
      const comma = value.indexOf(',');
      if (comma < 0) return reject(new Error('场景参考图编码失败'));
      resolve(value.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}

function syncCodexKeyframePolling() {
  const batchStatus = String(state.gptKeyframes?.codex_batch?.status || '');
  const running = batchStatus === 'RUNNING' || batchStatus === 'CANCEL_REQUESTED';
  if (running && !state.gptKeyframePollTimer && state.grayboxProjectId) {
    state.gptKeyframePollTimer = window.setInterval(async () => {
      try {
        state.gptKeyframes = await api('/api/novel-anime/projects/' + encodeURIComponent(state.grayboxProjectId) + '/graybox/gpt-keyframes');
        renderGptKeyframes();
      } catch (error) {
        const message = $('#gptCodexBatchMessage');
        if (message) message.textContent = 'Codex 状态刷新失败：' + error.message;
      }
    }, 2000);
  } else if (!running && state.gptKeyframePollTimer) {
    window.clearInterval(state.gptKeyframePollTimer);
    state.gptKeyframePollTimer = null;
  }
}

function renderCodexBatchLogs() {
  const panel = $('#gptCodexLogsPanel');
  const summary = $('#gptCodexLogsSummary');
  const list = $('#gptCodexLogsList');
  if (!panel || !summary || !list) return;
  const data = state.gptCodexLogs;
  if (!data) {
    panel.classList.add('hidden');
    summary.textContent = '尚未读取日志。';
    list.innerHTML = '';
    return;
  }
  const entries = data.entries || [];
  panel.classList.remove('hidden');
  summary.textContent = data.summary || (entries.length ? 'Codex 日志已载入。' : '当前没有 Codex 日志。');
  if (!entries.length) {
    list.innerHTML = '<div class="empty-state">当前没有可显示的 Codex 帧日志。</div>';
    return;
  }
  list.innerHTML = entries.map((entry) => {
    const failed = entry.status === 'FAILED';
    const title = escapeHtml(entry.id || ('GPT-KF-' + String(entry.index).padStart(3, '0')));
    const error = entry.error ? '<div class="codex-log-error">' + escapeHtml(entry.error) + '</div>' : '';
    const tail = escapeHtml(entry.tail || '日志文件存在，但尾部为空。');
    return '<details class="codex-log-entry" ' + (failed ? 'open' : '') + '>' +
      '<summary><strong>' + title + '</strong><span class="pipeline-stage-status ' + (failed ? 'fail' : entry.status === 'READY' ? 'pass' : 'pending') + '">' + escapeHtml(entry.status || 'UNKNOWN') + '</span><small>attempt ' + Number(entry.attempts || 0) + '</small></summary>' +
      error +
      '<pre>' + tail + '</pre>' +
      '<small class="codex-log-path">' + escapeHtml(entry.log_path || '') + '</small>' +
    '</details>';
  }).join('');
}

async function loadCodexBatchLogs({ forceOpen = true } = {}) {
  const projectId = state.grayboxProjectId;
  if (!projectId || state.gptCodexLogsLoading) return;
  state.gptCodexLogsLoading = true;
  const button = $('#gptCodexLogsRefresh');
  if (button) {
    button.disabled = true;
    button.textContent = '正在读取日志…';
  }
  try {
    state.gptCodexLogs = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/gpt-keyframes/codex-batch/logs');
    renderCodexBatchLogs();
    if (forceOpen) $('#gptCodexLogsPanel')?.classList.remove('hidden');
  } catch (error) {
    log('读取 Codex 日志失败：' + error.message, true);
  } finally {
    state.gptCodexLogsLoading = false;
    if (button) {
      button.disabled = false;
      button.textContent = '查看 / 刷新 Codex 日志';
    }
  }
}

function costFirstRouteLabel(route) {
  return ({
    LOCAL_SCENE_PLATE: 'FREE · 场景图 + 本地镜头',
    LOCAL_MICRO_MOTION: 'FREE VIDEO · 单图本地微动',
    LOCAL_TWO_CUT: 'LOW COST · 两张图本地切镜',
    H3_CANDIDATE: 'PAID LAST RESORT · H3 候选',
  })[route] || route || 'UNKNOWN';
}

function renderCostFirstDiagnostics(
  diagnostics = state.costFirstPlan?.diagnostics || null,
  rebuildSteps = state.costFirstPlan?.rebuild_steps || [],
  blockers = state.costFirstPlan?.blockers || []
) {
  const panel = $('#costFirstDiagnosticsPanel');
  const status = $('#costFirstDiagnosticsStatus');
  const output = $('#costFirstDiagnosticsLog');
  if (!panel || !status || !output) return;

  if (!diagnostics) {
    status.textContent = 'NOT READ';
    output.textContent = '尚未读取 P36 诊断。点击“查看 / 刷新 P36 诊断”。';
    return;
  }

  const script = diagnostics.episode_script || {};
  const seed = diagnostics.scene_seed || {};
  const shots = diagnostics.shot_breakdown || {};
  const timing = diagnostics.voice_timing || {};
  const plan = diagnostics.plan || {};
  const lines = [
    '[P36 DIAGNOSTICS]',
    'checked_at: ' + (diagnostics.checked_at || '—'),
    'project: ' + (diagnostics.project_id || '—'),
    '',
    '[Episode Script]',
    'path: ' + (script.path || 'writing-room/episodes'),
    'exists: ' + Boolean(script.exists),
    'json files: ' + Number(script.json_file_count || 0),
    'revision: ' + (script.revision ?? '—'),
    'episodes: ' + Number(script.episode_count || 0),
    'scenes: ' + Number(script.scene_count || 0),
    'units: ' + Number(script.unit_count || 0),
    ...(script.error ? ['ERROR: ' + script.error] : []),
    '',
    '[Scene Seed]',
    'path: ' + (seed.path || 'writing-room/scene-seeds.json'),
    'exists: ' + Boolean(seed.exists),
    'episodes: ' + Number(seed.episode_count || 0),
    'scenes: ' + Number(seed.scene_count || 0),
    'units: ' + Number(seed.unit_count || 0),
    ...(seed.error ? ['ERROR: ' + seed.error] : []),
    '',
    '[Shot Breakdown]',
    'path: ' + (shots.path || 'storyboard/shot-breakdown.json'),
    'exists: ' + Boolean(shots.exists),
    'revision: ' + (shots.revision ?? '—'),
    'scenes: ' + Number(shots.scene_count || 0),
    'shots: ' + Number(shots.shot_count || 0),
    ...(shots.error ? ['ERROR: ' + shots.error] : []),
    '',
    '[Voice Timeline]',
    'path: ' + (timing.path || 'audio/shot-timing.json'),
    'exists: ' + Boolean(timing.exists),
    'ACTUAL_TTS shots: ' + Number(timing.actual_tts_count || 0),
    ...(timing.error ? ['ERROR: ' + timing.error] : []),
    '',
    '[Saved P36 Plan]',
    'path: ' + (plan.path || 'rendering/cost-first-plan.json'),
    'exists: ' + Boolean(plan.exists),
    'saved status: ' + (plan.status || '—'),
    'saved routes: ' + Number(plan.route_count || 0),
    ...(plan.error ? ['ERROR: ' + plan.error] : []),
  ];

  const allBlockers = [...(diagnostics.blockers || []), ...(blockers || [])]
    .filter((item, index, values) => item && values.indexOf(item) === index);
  if (allBlockers.length) {
    lines.push('', '[BLOCKERS]');
    allBlockers.forEach((item) => lines.push('- ' + item));
  }
  if ((rebuildSteps || []).length) {
    lines.push('', '[LAST REBUILD]');
    rebuildSteps.forEach((step) => {
      lines.push((step.status || 'UNKNOWN') + ' · ' + (step.stage || 'STEP') + ' · ' + (step.detail || ''));
    });
  }

  status.textContent = diagnostics.status || (allBlockers.length ? 'BLOCKED' : 'READY');
  output.textContent = lines.join('\n');
  if (
    diagnostics.status === 'BLOCKED' ||
    allBlockers.length ||
    (rebuildSteps || []).some((step) => ['FAIL', 'EMPTY', 'MISSING_OR_INVALID', 'SOURCE_REIMPORT_REQUIRED'].includes(step.status))
  ) panel.open = true;
}

async function loadCostFirstDiagnostics({ forceOpen = true } = {}) {
  const projectId = state.grayboxProjectId || state.costFirstProjectId;
  const panel = $('#costFirstDiagnosticsPanel');
  const status = $('#costFirstDiagnosticsStatus');
  const output = $('#costFirstDiagnosticsLog');
  if (!projectId) {
    if (status) status.textContent = 'NO PROJECT';
    if (output) output.textContent = '当前没有选中国漫项目。';
    if (panel && forceOpen) panel.open = true;
    return;
  }
  if (status) status.textContent = 'READING';
  if (output) output.textContent = '正在读取 P36 上游诊断…';
  if (panel && forceOpen) panel.open = true;
  try {
    const diagnostics = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/cost-first-routing/diagnostics');
    state.costFirstPlan = { ...(state.costFirstPlan || {}), diagnostics };
    renderCostFirstDiagnostics(diagnostics, state.costFirstPlan.rebuild_steps || [], state.costFirstPlan.blockers || []);
  } catch (error) {
    if (status) status.textContent = 'ERROR';
    if (output) output.textContent = '读取 P36 诊断失败：' + error.message;
    log('读取 P36 诊断失败：' + error.message, true);
  }
}


function openCostFirstImportRepair() {
  const projectId = state.grayboxProjectId || state.costFirstProjectId || state.activeNovelProjectId;
  const project = (state.animeProjects || []).find((item) => item.directory_id === projectId);
  if (project?.title && $('#novelImportTitle')) $('#novelImportTitle').value = project.title;
  if (project?.episode_count && $('#novelImportEpisodes')) $('#novelImportEpisodes').value = String(project.episode_count);
  setView('novelImport');
  log('旧项目 Scene Seed 回填：请选择当初导入的同一个 TXT。系统按相同 SHA 复用原项目，不会新建重复项目。');
}


function renderCostFirstPlan() {
  const data = state.costFirstPlan;
  const status = $('#costFirstStatus');
  const summary = $('#costFirstSummary');
  const routes = $('#costFirstRoutes');
  if (!status || !summary || !routes) return;
  if (!data) {
    status.textContent = 'NOT READY';
    status.classList.add('off');
    routes.innerHTML = '<div class="empty-state">当前项目还没有可分析的 Shot Breakdown / Script。</div>';
    renderCostFirstDiagnostics(null, [], []);
    return;
  }

  status.textContent = data.status || 'PLANNED';
  status.classList.toggle('off', String(data.status || '').startsWith('BLOCKED') || data.status === 'ERROR');
  const s = data.summary || {};
  const hasShots = Number(s.shot_count || 0) > 0;
  summary.innerHTML =
    '<div><span>如果全部 H3</span><strong>' + Number(s.all_h3_estimated_shells || 0).toFixed(1) + ' 贝壳</strong></div>' +
    '<div><span>混合路线 H3</span><strong>' + Number(s.hybrid_h3_estimated_shells || 0).toFixed(1) + ' 贝壳</strong></div>' +
    '<div><span>预计节省</span><strong>' + (hasShots ? Number(s.estimated_shell_savings_percent || 0).toFixed(1) + '% · ' + Number(s.estimated_shells_saved || 0).toFixed(1) + ' 贝壳' : '--') + '</strong></div>' +
    '<div><span>需新生成静帧</span><strong>' + (hasShots ? Number(s.estimated_new_still_generations_after_reuse || 0) + ' 张' : '--') + '</strong></div>';
  renderCostFirstDiagnostics(data.diagnostics || null, data.rebuild_steps || [], data.blockers || []);

  const groups = {
    LOCAL_SCENE_PLATE: [],
    LOCAL_MICRO_MOTION: [],
    LOCAL_TWO_CUT: [],
    H3_CANDIDATE: [],
  };
  (data.routes || []).forEach((item) => (groups[item.route] || (groups[item.route] = [])).push(item));
  const order = ['LOCAL_SCENE_PLATE', 'LOCAL_MICRO_MOTION', 'LOCAL_TWO_CUT', 'H3_CANDIDATE'];

  if (!(data.routes || []).length) {
    const blockerItems = data.blockers || [];
    const blockers = blockerItems.map((item) => '<li>' + escapeHtml(item) + '</li>').join('');
    const needsSourceRepair =
      blockerItems.some((item) => String(item).includes('重新选择同一个 TXT')) ||
      (data.rebuild_steps || []).some((step) => step.status === 'SOURCE_REIMPORT_REQUIRED');
    routes.innerHTML = '<div class="empty-state"><strong>当前没有可路由 Shot</strong>' +
      (blockers ? '<ul>' + blockers + '</ul>' : '<p>请先完成 Episode Script / Shot Breakdown。</p>') +
      (needsSourceRepair ? '<button class="secondary-button" id="costFirstOpenImportRepair">去小说导入：选择同一个 TXT 回填</button>' : '') +
      '<p>下面的“P36 诊断 / 日志”会直接告诉你卡在哪一层。</p>' +
      '</div>';
    const repairButton = $('#costFirstOpenImportRepair');
    if (repairButton) repairButton.addEventListener('click', openCostFirstImportRepair);
    const panel = $('#costFirstDiagnosticsPanel');
    if (panel) panel.open = true;
    return;
  }

  routes.innerHTML = order.map((routeName) => {
    const items = groups[routeName] || [];
    if (!items.length) return '';
    const cards = items.map((item) => {
      const escalation = item.h3_escalation || {};
      const approved = Boolean(escalation.approved);
      const reasons = (item.reasons || []).map((reason) => '<li>' + escapeHtml(reason) + '</li>').join('');
      const keywords = [...(item.motion?.high_keywords || []), ...(item.motion?.medium_keywords || []), ...(item.motion?.subtle_keywords || [])].slice(0, 8);
      const preview = item.local_preview || {};
      const vfx = item.vfx_recipe || {};
      const localAction = item.route !== 'H3_CANDIDATE'
        ? '<div class="cost-first-local-preview">' +
            '<input type="text" maxlength="500" placeholder="特效描述：雪夜灯火、薄雾、花瓣或剑气" data-vfx-brief="' + escapeHtml(item.shot_id) + '">' +
            '<label class="cost-first-vfx-confirm"><input type="checkbox" data-vfx-confirm="' + escapeHtml(item.shot_id) + '">确认使用本机 Codex 额度（只发送效果描述和镜头规格）</label>' +
            '<button class="secondary-button small-button" data-codex-vfx="' + escapeHtml(item.shot_id) + '">Codex 设计特效方案</button>' +
            (vfx.status === 'READY' ? '<small class="cost-first-vfx-recipe">Codex 方案：' + escapeHtml(vfx.recipe?.summary || '') + ' · ' + (vfx.recipe?.layers || []).map((layer) => escapeHtml(layer.type)).join('、') + ' · 图片未上传</small>' : '') +
            '<input type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" ' + (Number(item.required_new_stills || 0) === 2 ? 'multiple ' : '') + 'data-cost-local-files="' + escapeHtml(item.shot_id) + '">' +
            '<button class="secondary-button small-button" data-cost-local="' + escapeHtml(item.shot_id) + '" data-required="' + Number(item.required_new_stills || 0) + '">本地生成预览</button>' +
            (preview.media_url ? '<video controls playsinline preload="metadata" src="' + escapeHtml(preview.media_url) + '"></video><small>' + escapeHtml(preview.provider || '') + ' · ' + Number(preview.duration_seconds || 0).toFixed(2) + 's · 视频生成 0 贝壳' + (preview.vfx_recipe ? ' · Codex 特效已合成' : '') + '</small>' : '<small>上传 ' + Number(item.required_new_stills || 0) + ' 张最终图，仅在本机 FFmpeg 渲染。</small>') +
          '</div>'
        : '';
      const h3Action = item.route === 'H3_CANDIDATE'
        ? '<div class="cost-first-h3-lock">' +
            '<span class="' + (approved ? 'status-dot' : 'status-dot off') + '">' + (approved ? 'H3 APPROVED' : 'H3 LOCKED') + '</span>' +
            '<button class="' + (approved ? 'secondary-button' : 'danger-button') + ' small-button" data-cost-h3="' + escapeHtml(item.shot_id) + '" data-approved="' + (approved ? '1' : '0') + '">' + (approved ? '重新锁定 H3' : '人工允许 H3') + '</button>' +
            (approved && escalation.reason ? '<small>原因：' + escapeHtml(escalation.reason) + '</small>' : '<small>默认不允许付费视频生成。</small>') +
          '</div>'
        : '';
      return '<article class="cost-first-route-card ' + (item.route === 'H3_CANDIDATE' ? 'h3-candidate' : '') + '">' +
        '<div class="cost-first-route-head"><div><strong>' + escapeHtml(item.shot_id) + '</strong><small>' + escapeHtml(item.episode_id) + ' · ' + Number(item.duration_seconds || 0).toFixed(2) + 's · motion score ' + Number(item.motion?.score || 0).toFixed(2) + '</small></div><span class="cost-route-badge">' + escapeHtml(costFirstRouteLabel(item.route)) + '</span></div>' +
        '<ul>' + reasons + '</ul>' +
        '<div class="cost-first-route-meta"><span>新静帧 ' + Number(item.required_new_stills || 0) + '</span><span>时长来源 ' + escapeHtml(item.timing_source || 'SHOT_BREAKDOWN') + '</span><span>全 H3≈' + Number(item.h3_full_cost_shells || 0).toFixed(1) + ' 贝壳</span><span>本镜头预计省 ' + Number(item.estimated_shells_saved || 0).toFixed(1) + ' 贝壳</span>' + (keywords.length ? '<span>动作词：' + escapeHtml(keywords.join('、')) + '</span>' : '') + '</div>' +
        localAction + h3Action +
      '</article>';
    }).join('');
    return '<section class="cost-first-group"><div class="cost-first-group-head"><strong>' + escapeHtml(costFirstRouteLabel(routeName)) + '</strong><span>' + items.length + ' 镜头</span></div><div class="cost-first-grid">' + cards + '</div></section>';
  }).join('') || '<div class="empty-state">暂无镜头路由。</div>';

  routes.querySelectorAll('[data-cost-h3]').forEach((button) => button.addEventListener('click', () => toggleCostFirstH3(button)));
  routes.querySelectorAll('[data-codex-vfx]').forEach((button) => button.addEventListener('click', () => planCodexVFX(button)));
  routes.querySelectorAll('[data-cost-local]').forEach((button) => button.addEventListener('click', () => renderCostFirstLocalPreview(button)));
}

async function planCodexVFX(button) {
  const projectId = state.grayboxProjectId || state.costFirstProjectId;
  const shotId = button.dataset.codexVfx;
  const briefInput = Array.from(document.querySelectorAll('[data-vfx-brief]')).find((item) => item.dataset.vfxBrief === shotId);
  const consent = Array.from(document.querySelectorAll('[data-vfx-confirm]')).find((item) => item.dataset.vfxConfirm === shotId);
  const effectBrief = String(briefInput?.value || '').trim();
  if (!projectId || !shotId || effectBrief.length < 8) {
    log('请填写至少 8 个字的特效描述。', true);
    return;
  }
  if (!consent?.checked) {
    log('请先确认本次会使用 Codex 套餐额度。只会发送效果描述和镜头规格，不上传图片。', true);
    return;
  }
  button.disabled = true;
  button.textContent = 'Codex 正在设计…';
  try {
    const result = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/cost-first-routing/vfx-recipe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shot_id: shotId, effect_brief: effectBrief, confirm_codex_usage: true }),
    });
    state.costFirstPlan = result.plan;
    renderCostFirstPlan();
    log(shotId + ' Codex 特效方案已生成：' + (result.recipe.recipe.summary || '完成') + '。图片未上传；视频效果由本地 FFmpeg 合成。');
  } catch (error) {
    button.disabled = false;
    button.textContent = 'Codex 设计特效方案';
    log('Codex 特效方案失败：' + error.message, true);
  }
}

async function renderCostFirstLocalPreview(button) {
  const projectId = state.grayboxProjectId || state.costFirstProjectId;
  const shotId = button.dataset.costLocal;
  const expected = Number(button.dataset.required || 0);
  if (!projectId || !shotId || !expected) return;
  const input = Array.from(document.querySelectorAll('[data-cost-local-files]')).find((item) => item.dataset.costLocalFiles === shotId);
  const files = Array.from(input?.files || []);
  if (files.length !== expected) {
    log(shotId + ' 需要恰好 ' + expected + ' 张最终图。', true);
    return;
  }
  if (files.some((file) => file.size <= 0 || file.size > 12 * 1024 * 1024)) {
    log('每张本地图必须在 1 byte 到 12 MB 之间。', true);
    return;
  }
  button.disabled = true;
  button.textContent = '本地渲染中…';
  try {
    const images = [];
    for (const file of files) images.push({ filename: file.name, content_base64: await fileToBase64(file) });
    const result = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/cost-first-routing/local-preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shot_id: shotId, images }),
    });
    state.costFirstPlan = result.plan;
    renderCostFirstPlan();
    log(shotId + ' 本地预览完成：' + result.preview.provider + ' · ' + Number(result.preview.duration_seconds || 0).toFixed(2) + 's · 0 贝壳。');
  } catch (error) {
    log(error.message, true);
    button.disabled = false;
    button.textContent = '本地生成预览';
  }
}

async function loadCostFirstPlan(projectId = state.grayboxProjectId || state.costFirstProjectId) {
  if (!projectId) return;
  state.costFirstProjectId = projectId;
  try {
    state.costFirstPlan = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/cost-first-routing');
  } catch (error) {
    state.costFirstPlan = null;
    log('P36 成本路线暂不可用：' + error.message, true);
  }
  renderCostFirstPlan();
}

async function rebuildCostFirstPlan() {
  const projectId = state.grayboxProjectId || state.costFirstProjectId;
  const button = $('#costFirstRebuild');
  const status = $('#costFirstStatus');
  const routes = $('#costFirstRoutes');
  if (!projectId) {
    status.textContent = 'NO PROJECT';
    status.classList.add('off');
    routes.innerHTML = '<div class="empty-state">当前没有选中国漫项目，无法分析镜头。</div>';
    log('P36 无法重建：当前没有选中国漫项目。', true);
    return;
  }
  button.disabled = true;
  button.textContent = '正在分析…';
  status.textContent = 'ANALYZING';
  status.classList.remove('off');
  routes.innerHTML = '<div class="empty-state">正在读取 Episode Script / Shot Breakdown，并计算最低成本路线…</div>';
  const diagnosticPanel = $('#costFirstDiagnosticsPanel');
  const diagnosticStatus = $('#costFirstDiagnosticsStatus');
  const diagnosticLog = $('#costFirstDiagnosticsLog');
  if (diagnosticPanel) diagnosticPanel.open = true;
  if (diagnosticStatus) diagnosticStatus.textContent = 'RUNNING';
  if (diagnosticLog) diagnosticLog.textContent = '[P36 REBUILD]\nRUNNING · PROJECT · ' + projectId + '\nRUNNING · SHOT_BREAKDOWN · 检查现有镜头…';
  try {
    state.costFirstPlan = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/cost-first-routing/rebuild', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    renderCostFirstPlan();
    const summary = state.costFirstPlan.summary || {};
    const sceneBackfill = state.costFirstPlan.auto_backfilled_episode_scenes ? ' · 已自动回填 Episode Script scenes' : '';
    const rebuilt = state.costFirstPlan.auto_rebuilt_shot_breakdown ? ' · 已自动重建 Shot Breakdown' : '';
    const reimportRequired = (state.costFirstPlan.rebuild_steps || []).some((step) => step.status === 'SOURCE_REIMPORT_REQUIRED');
    if ((state.costFirstPlan.routes || []).length) {
      log('P36 成本路线已重建：' + (state.costFirstPlan.routes || []).length + ' 个 Shot · 预计节省 ' + Number(summary.estimated_shell_savings_percent || 0).toFixed(1) + '% H3 贝壳' + sceneBackfill + rebuilt + '。');
    } else if (reimportRequired) {
      log('P36：这是旧导入项目，原 TXT 没有保存在项目里。请回到“小说导入”，重新选择同一个 TXT 一次；系统会复用当前项目，只回填 scenes，不会创建重复项目。', true);
    } else {
      log('P36 仍无可路由 Shot：请查看本面板 P36 诊断 / 日志。' + sceneBackfill + rebuilt, true);
    }
  } catch (error) {
    state.costFirstPlan = null;
    status.textContent = 'ERROR';
    status.classList.add('off');
    routes.innerHTML = '<div class="empty-state"><strong>P36 分析失败</strong><p>' + escapeHtml(error.message) + '</p></div>';
    if (diagnosticPanel) diagnosticPanel.open = true;
    if (diagnosticStatus) diagnosticStatus.textContent = 'ERROR';
    if (diagnosticLog) diagnosticLog.textContent = '[P36 REBUILD]\nFAIL · ' + error.message;
    log('P36 重建失败：' + error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = '重新分析全部镜头';
  }
}

async function toggleCostFirstH3(button) {
  const projectId = state.grayboxProjectId || state.costFirstProjectId;
  const shotId = button.dataset.costH3;
  const approved = button.dataset.approved === '1';
  if (!projectId || !shotId) return;

  if (approved) {
    if (!window.confirm('重新锁定这个镜头的 H3？锁定后不会进入付费视频生成。')) return;
    try {
      state.costFirstPlan = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/cost-first-routing/h3-escalation', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shot_id: shotId, approved: false }),
      });
      renderCostFirstPlan();
      renderGraybox();
      log(shotId + ' 已重新锁定 H3。');
    } catch (error) { log(error.message, true); }
    return;
  }

  const reason = window.prompt('H3 是最后兜底。请写明为什么这个镜头不能使用本地单图微动 / 两段切镜（至少 6 个字）：', '');
  if (!reason) return;
  try {
    state.costFirstPlan = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/cost-first-routing/h3-escalation', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shot_id: shotId, approved: true, reason: reason }),
    });
    renderCostFirstPlan();
    renderGraybox();
    log(shotId + ' 已人工允许 H3；真正发起 H3 时仍需独立付费确认。');
  } catch (error) { log(error.message, true); }
}

function renderGptKeyframes() {
  const data = state.gptKeyframes || {};
  const frames = data.frames || [];
  const status = data.status || 'NOT_PREPARED';
  const statusEl = $('#gptKeyframeStatus');
  if (!statusEl) return;
  statusEl.textContent = status;
  statusEl.classList.toggle('off', status !== 'VIDEO_READY' && status !== 'READY');

  const countSelect = $('#gptKeyframeCount');
  if (countSelect && ['9', '17'].includes(String(data.keyframe_count || ''))) countSelect.value = String(data.keyframe_count);

  const graybox = state.graybox || {};
  const refs = graybox.references || {};
  const review = graybox.spec?.review || {};
  const render = graybox.render || {};
  const hasExistingGraybox = Boolean(render.output_path && Number(render.output_bytes || 0) > 1024);
  const hasUsableGraybox = Boolean(render.output_ready && !render.render_stale);
  const canAdoptExisting = Boolean(render.render_stale && hasExistingGraybox);
  const canPrepare = Boolean((hasUsableGraybox || canAdoptExisting) && refs.ready);
  const needsGrayboxApproval = canPrepare && review.status !== 'APPROVED';
  $('#gptKeyframePrepare').disabled = !canPrepare;
  $('#gptKeyframePrepare').textContent = canAdoptExisting
    ? '① 确认沿用现有白模并抽帧'
    : needsGrayboxApproval ? '① 确认白模并抽取控制帧' : '① 抽取 Blender 控制帧';

  const referenceSummary = $('#gptKeyframeReferenceSummary');
  if (data.character_reference && data.scene_reference) {
    const characterLink = data.character_reference_url ? '<a href="' + escapeHtml(data.character_reference_url) + '" target="_blank" rel="noopener noreferrer">人物参考</a>' : escapeHtml(data.character_reference);
    const sceneLink = data.scene_reference_url ? '<a href="' + escapeHtml(data.scene_reference_url) + '" target="_blank" rel="noopener noreferrer">场景参考</a>' : escapeHtml(data.scene_reference);
    referenceSummary.innerHTML = '输入锁定：' + characterLink + ' + ' + sceneLink + ' + Blender 控制帧 · ' + Number(data.generated_count || 0) + '/' + Number(data.keyframe_count || 0) + ' 张 AI 帧已回传';
  } else {
    const blockers = [];
    if (!hasUsableGraybox && !canAdoptExisting) blockers.push(render.render_stale ? '白模已失效且没有可沿用 MP4' : '缺有效白模');
    if (!refs.character_bound) blockers.push('缺人物参考');
    if (!refs.scene_bound) blockers.push('缺场景参考');
    referenceSummary.textContent = canPrepare
      ? (canAdoptExisting
          ? '检测到旧 render hash，但白模 MP4 仍存在。点击①可人工确认沿用，不需要重新渲染。'
          : needsGrayboxApproval
            ? '白模 / 人物 / 场景已就绪；点击①后会让你确认白模，通过后自动抽帧。'
            : '人物 / 场景 / 白模均已就绪，可以直接抽取控制帧。')
      : '当前阻断：' + (blockers.length ? blockers.join(' · ') : '等待项目状态刷新');
  }

  const grid = $('#gptKeyframeGrid');
  if (!frames.length) {
    grid.innerHTML = '<div class="empty-state">尚未准备控制帧。首轮建议 9 张，确认人物与古宅稳定后再试 17 张。</div>';
  } else {
    grid.innerHTML = frames.map(function(frame) {
      const ready = frame.status === 'READY' && frame.generated_url;
      const reset = frame.reference_mode === 'CANONICAL_RESET';
      return '<article class="gpt-keyframe-card">' +
        '<div class="gpt-keyframe-card-head"><div><strong>' + escapeHtml(frame.id) + '</strong><small>' + Number(frame.timestamp_seconds || 0).toFixed(2) + 's · ' + escapeHtml(frame.reference_mode || '') + '</small></div><span class="pipeline-stage-status ' + (ready ? 'pass' : frame.status === 'FAILED' ? 'fail' : 'pending') + '">' + escapeHtml(frame.status || 'CONTROL_READY') + '</span></div>' +
        '<div class="gpt-keyframe-images">' +
          '<figure><img src="' + escapeHtml(frame.control_url || '') + '" alt="Blender control frame"><figcaption>Blender 控制帧</figcaption></figure>' +
          (ready ? '<figure><img src="' + escapeHtml(frame.generated_url) + '" alt="AI final keyframe"><figcaption>AI 最终关键帧</figcaption></figure>' : '<div class="gpt-keyframe-missing">等待 ChatGPT 最终帧</div>') +
        '</div>' +
        '<div class="gpt-keyframe-actions">' +
          '<a class="secondary-button small-button" href="' + escapeHtml(frame.control_url || '#') + '" target="_blank" rel="noopener noreferrer">打开控制帧</a>' +
          '<button class="secondary-button small-button" data-gpt-copy="' + Number(frame.index) + '">复制 Prompt</button>' +
        '</div>' +
        '<details class="gpt-keyframe-prompt"><summary>' + (reset ? 'Canonical Reset 提示词' : 'Continuity 提示词') + '</summary><textarea readonly>' + escapeHtml(frame.prompt || '') + '</textarea></details>' +
        '<div class="gpt-keyframe-upload"><input type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" data-gpt-file="' + Number(frame.index) + '"><button class="primary-button small-button" data-gpt-upload="' + Number(frame.index) + '">' + (ready ? '替换最终帧' : '上传 ChatGPT 最终帧') + '</button></div>' +
        (frame.previous_index == null ? '<small class="gpt-keyframe-note">只需人物参考 + 场景参考 + 当前控制帧。</small>' : '<small class="gpt-keyframe-note">额外带上 GPT-KF-' + String(frame.previous_index).padStart(3, '0') + ' 最终帧作为连续性参考。</small>') +
        (frame.codex_error ? '<div class="gpt-keyframe-error">Codex：' + escapeHtml(frame.codex_error) + '</div>' : '') +
      '</article>';
    }).join('');
    grid.querySelectorAll('[data-gpt-copy]').forEach((button) => button.addEventListener('click', () => copyGptKeyframePrompt(Number(button.dataset.gptCopy))));
    grid.querySelectorAll('[data-gpt-upload]').forEach((button) => button.addEventListener('click', () => uploadGptKeyframe(Number(button.dataset.gptUpload), button)));
  }

  const codex = data.codex_batch || {};
  const codexStatus = String(codex.status || 'IDLE');
  const codexRunning = codexStatus === 'RUNNING' || codexStatus === 'CANCEL_REQUESTED';
  const codexInstalled = Boolean(codex.installed);
  const codexTotal = Number(codex.total_count || data.keyframe_count || frames.length || 0);
  const codexCompleted = Number(codex.completed_count || data.generated_count || 0);
  const codexFailed = Number(codex.failed_count || frames.filter((frame) => frame.status === 'FAILED').length);
  const codexRemaining = Math.max(0, codexTotal - codexCompleted);
  const codexStatusEl = $('#gptCodexBatchStatus');
  if (codexStatusEl) {
    codexStatusEl.textContent = !codexInstalled ? 'CODEX NOT INSTALLED' : codexStatus;
    codexStatusEl.classList.toggle('off', !codexInstalled || !['PASS', 'RUNNING'].includes(codexStatus));
  }
  const progressText = $('#gptCodexBatchProgress');
  if (progressText) progressText.textContent = codexCompleted + ' / ' + codexTotal + (codexFailed ? ' · ' + codexFailed + ' FAILED' : '');
  const progressBar = $('#gptCodexBatchProgressBar');
  if (progressBar) progressBar.style.width = (codexTotal ? Math.max(0, Math.min(100, codexCompleted * 100 / codexTotal)) : 0) + '%';
  const batchMessage = $('#gptCodexBatchMessage');
  if (batchMessage) {
    batchMessage.textContent = !codexInstalled
      ? '未检测到 codex CLI；可使用下方 ChatGPT Web 手工备用。'
      : (codex.message || (frames.length ? 'Codex 已就绪，可批量生成剩余关键帧。' : '先抽取 Blender 控制帧。'));
  }

  const usageConfirm = Boolean($('#gptCodexUsageConfirm')?.checked);
  const uploadConfirm = Boolean($('#gptCodexUploadConfirm')?.checked);
  const codexStart = $('#gptCodexBatchStart');
  if (codexStart) {
    codexStart.disabled = !codexInstalled || !frames.length || !codexRemaining || codexRunning || !usageConfirm || !uploadConfirm;
    codexStart.textContent = codexFailed
      ? '② Codex 重试失败 / 剩余 ' + codexRemaining + ' 张'
      : codexRemaining
        ? '② Codex 批量生成剩余 ' + codexRemaining + ' 张'
        : '✓ Codex 关键帧已全部完成';
  }
  const codexStop = $('#gptCodexBatchStop');
  if (codexStop) {
    codexStop.classList.toggle('hidden', !codexRunning);
    codexStop.disabled = codexStatus === 'CANCEL_REQUESTED';
  }
  if ($('#gptCodexConcurrency')) $('#gptCodexConcurrency').disabled = codexRunning;
  if ($('#gptCodexUsageConfirm')) $('#gptCodexUsageConfirm').disabled = codexRunning;
  if ($('#gptCodexUploadConfirm')) $('#gptCodexUploadConfirm').disabled = codexRunning;

  if (codexFailed > 0 && !codexRunning && !state.gptCodexLogs && !state.gptCodexLogsLoading) {
    window.setTimeout(() => loadCodexBatchLogs({ forceOpen: true }), 0);
  }
  renderCodexBatchLogs();

  const readyForVideo = frames.length > 1 && Number(data.generated_count || 0) === Number(data.keyframe_count || 0);
  $('#gptKeyframeInterpolate').disabled = !readyForVideo;
  const interpolation = data.interpolation || {};
  const outputWrap = $('#gptKeyframeOutput');
  const video = $('#gptKeyframeVideo');
  if (interpolation.media_url) {
    const src = interpolation.media_url + '?v=' + encodeURIComponent(String(data.updated_at || interpolation.output_bytes || 'ready'));
    if ((video.getAttribute('src') || '') !== src) video.src = src;
    $('#gptKeyframeOutputMeta').textContent = Number(data.keyframe_count || 0) + ' AI keyframes → ' + Number(interpolation.target_fps || data.target_fps || 24) + 'fps · ' + escapeHtml(interpolation.backend || 'FFMPEG_MINTERPOLATE');
    outputWrap.classList.remove('hidden');
  } else {
    video.removeAttribute('src');
    outputWrap.classList.add('hidden');
  }
  $('#gptKeyframeHint').textContent = status === 'VIDEO_READY'
    ? 'P35 本地视频已生成。先播放检查脸/衣服/建筑闪烁与插帧伪影；如果 9 帧不够，再改用 17 帧。'
    : codexRunning
      ? 'Codex 正在后台逐波生成关键帧；页面每 2 秒自动刷新。Canonical Reset 可并发，Continuity 会等待上一张 READY。'
      : frames.length
        ? '优先点击 Codex 批量生成；成功帧会自动保存、规范化并标为 READY。失败帧不会自动烧第二次额度，可手工重试。'
        : '先准备 Blender 控制帧；之后可让 Codex 自动读取全部 Prompt 并生成到 P35 目录。';
  syncCodexKeyframePolling();
}

async function loadGptKeyframes(projectId = state.grayboxProjectId) {
  if (!projectId) return;
  state.gptKeyframes = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/gpt-keyframes');
  renderGptKeyframes();
}

async function prepareGptKeyframes() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) return;
  const button = $('#gptKeyframePrepare');
  let reviewStatus = String(state.graybox?.spec?.review?.status || 'PENDING').toUpperCase();
  let render = state.graybox?.render || {};
  const refs = state.graybox?.references || {};
  const hasExistingGraybox = Boolean(render.output_path && Number(render.output_bytes || 0) > 1024);
  let staleAdoptionConfirmed = false;

  if (render.render_stale && hasExistingGraybox) {
    staleAdoptionConfirmed = window.confirm(
      '当前白模 MP4 仍然存在，但它使用的是旧版 render hash，因此被误标成 STALE。\n\n如果你刚才看到的这个白模镜头、人物走位和动作就是要继续使用的骨架，点击“确定”即可沿用现有 MP4，不会重新渲染 192 帧。'
    );
    if (!staleAdoptionConfirmed) return;
  } else if (!render.output_ready || render.render_stale) {
    log(render.render_stale ? '当前白模没有可安全沿用的 MP4，请重新生成。' : '请先生成 Blender 白模。', true);
    return;
  }

  if (!refs.ready) {
    log('请先完成当前镜头的人物参考 + 场景参考绑定。', true);
    return;
  }

  if (!staleAdoptionConfirmed && reviewStatus !== 'APPROVED') {
    const confirmed = window.confirm('当前 Blender 白模已经生成，人物与场景参考也已绑定。\n\n继续 P35 前需要把当前白模标记为“通过”。\n确认这个白模的镜头、走位和动作可以作为关键帧控制骨架吗？');
    if (!confirmed) return;
  }

  button.disabled = true;
  button.textContent = staleAdoptionConfirmed ? '正在沿用现有白模并抽帧…' : reviewStatus === 'APPROVED' ? '正在抽取控制帧…' : '正在确认白模并抽帧…';
  try {
    if (staleAdoptionConfirmed) {
      state.graybox = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/adopt-render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm_existing_render: true }),
      });
      render = state.graybox?.render || {};
      reviewStatus = String(state.graybox?.spec?.review?.status || reviewStatus).toUpperCase();
      log('现有 Blender 白模已重新绑定到新的 render signature；未重新渲染。');
    }

    if (reviewStatus !== 'APPROVED') {
      state.graybox = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'APPROVED', note: 'P35 Web keyframe route approved before control-frame extraction' }),
      });
      reviewStatus = 'APPROVED';
      log('当前 Blender 白模已确认通过，继续准备 P35 控制帧。');
    }

    state.gptKeyframes = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/gpt-keyframes/prepare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyframe_count: Number($('#gptKeyframeCount').value || 9) }),
    });
    renderGraybox();
    log('P35 Blender 控制帧已准备：' + state.gptKeyframes.keyframe_count + ' 张。');
  } catch (error) { log(error.message, true); }
  finally { renderGptKeyframes(); }
}

async function copyGptKeyframePrompt(index) {
  const frame = (state.gptKeyframes?.frames || []).find((item) => Number(item.index) === Number(index));
  if (!frame?.prompt) return;
  try {
    await navigator.clipboard.writeText(frame.prompt);
    log(frame.id + ' Prompt 已复制。');
  } catch (_) {
    log('浏览器未允许自动复制，请展开卡片中的提示词手工复制。', true);
  }
}

async function uploadGptKeyframe(index, button) {
  const projectId = state.grayboxProjectId;
  const input = document.querySelector('[data-gpt-file="' + index + '"]');
  const file = input?.files?.[0];
  if (!projectId || !file) { log('请选择 ChatGPT 生成的关键帧图片。', true); return; }
  if (file.size <= 0 || file.size > 16 * 1024 * 1024) { log('关键帧图片必须在 1 byte 到 16 MB 之间。', true); return; }
  button.disabled = true;
  button.textContent = '上传中…';
  try {
    const contentBase64 = await fileToBase64(file);
    state.gptKeyframes = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/gpt-keyframes/upload', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: index, filename: file.name, content_base64: contentBase64 }),
    });
    renderGptKeyframes();
    log('P35 ' + String(index).padStart(3, '0') + ' 最终关键帧已回传并规范化为 9:16。');
  } catch (error) { log(error.message, true); button.disabled = false; button.textContent = '上传 ChatGPT 最终帧'; }
}

async function startCodexKeyframeBatch() {
  const projectId = state.grayboxProjectId;
  if (!projectId) return;
  const usageConfirm = Boolean($('#gptCodexUsageConfirm')?.checked);
  const uploadConfirm = Boolean($('#gptCodexUploadConfirm')?.checked);
  if (!usageConfirm || !uploadConfirm) {
    log('启动 Codex 批量生成前，需要同时确认套餐用量和参考图上传。', true);
    renderGptKeyframes();
    return;
  }
  const button = $('#gptCodexBatchStart');
  button.disabled = true;
  button.textContent = '正在启动 Codex…';
  try {
    state.gptCodexLogs = null;
    renderCodexBatchLogs();
    state.gptKeyframes = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/gpt-keyframes/codex-batch/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        concurrency: Number($('#gptCodexConcurrency')?.value || 2),
        confirm_codex_usage: true,
        confirm_reference_upload: true,
      }),
    });
    renderGptKeyframes();
    log('P35 Codex ImageGen 批量生成已启动；只生成未完成/失败帧。');
  } catch (error) {
    log(error.message, true);
    renderGptKeyframes();
  }
}

async function stopCodexKeyframeBatch() {
  const projectId = state.grayboxProjectId;
  if (!projectId) return;
  const button = $('#gptCodexBatchStop');
  button.disabled = true;
  button.textContent = '正在停止…';
  try {
    state.gptKeyframes = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/gpt-keyframes/codex-batch/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    renderGptKeyframes();
    log('已请求停止 P35 Codex 批量生成；已完成关键帧会保留。');
  } catch (error) {
    log(error.message, true);
    button.disabled = false;
    button.textContent = '停止批量生成';
  }
}

async function interpolateGptKeyframes() {
  const projectId = state.grayboxProjectId;
  if (!projectId) return;
  const button = $('#gptKeyframeInterpolate');
  button.disabled = true;
  button.textContent = '本地插帧中…';
  try {
    state.gptKeyframes = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/graybox/gpt-keyframes/interpolate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    renderGptKeyframes();
    log('P35 本地 24fps 视频已生成：' + (state.gptKeyframes.interpolation?.output || 'READY'));
  } catch (error) { log(error.message, true); }
  finally { button.textContent = '④ 本地插帧 → 24fps'; renderGptKeyframes(); }
}
function renderGraybox() {
  const data = state.graybox || {};
  const render = data.render || {};
  const spec = data.spec || {};
  const review = spec.review || {};
  const minimax = data.minimax || {};
  const references = data.references || {};
  const binding = references.binding || {};
  const characterReference = binding.character_reference || null;
  const sceneReference = binding.scene_reference || null;
  const installed = Boolean(data.blender_installed);

  $('#grayboxStatus').textContent = render.status === 'PASS' && render.output_ready ? 'GRAYBOX READY' : installed ? (render.status || 'READY') : 'NO BLENDER';
  $('#grayboxStatus').classList.toggle('off', !installed || render.status === 'FAIL');
  $('#grayboxBlender').textContent = installed ? 'READY' : 'NOT INSTALLED';
  $('#grayboxSpecStatus').textContent = data.spec_ready
    ? `READY · REVIEW ${review.status || 'PENDING'}`
    : 'NOT READY';
  $('#grayboxRenderStatus').textContent = render.render_stale ? 'STALE · NEED RERENDER' : (render.status || (render.output_ready ? 'PASS' : 'NOT STARTED'));
  $('#grayboxMiniMaxStatus').textContent = `MiniMax H3 · ${minimax.configured ? 'READY' : 'NOT CONFIGURED'}`;
  $('#grayboxReviewStatus').textContent = review.status || 'PENDING';

  renderGrayboxReferenceSelect(
    '#grayboxCharacterReferenceSelect',
    references.character_candidates || [],
    characterReference?.path || '',
    references.character_candidates?.length ? '选择人物参考…' : '暂无人物参考图'
  );
  renderGrayboxReferenceSelect(
    '#grayboxSceneReferenceSelect',
    references.scene_candidates || [],
    sceneReference?.path || '',
    references.scene_candidates?.length ? '选择已有场景参考…' : '暂无已有场景参考'
  );
  renderGrayboxReferencePreview('#grayboxCharacterReferencePreview', '#grayboxCharacterReferenceEmpty', characterReference);
  renderGrayboxReferencePreview('#grayboxSceneReferencePreview', '#grayboxSceneReferenceEmpty', sceneReference);
  $('#grayboxCharacterReferenceMeta').textContent = characterReference
    ? `${characterReference.label || characterReference.character_id || '人物参考'} · ${characterReference.review_status || 'BOUND'} · ${characterReference.style_label || '未记录风格'}`
    : (references.character_candidates?.length
      ? '请选择一张 Image Studio 角色图并绑定到当前镜头。'
      : '当前项目还没有可绑定的角色图；先在 Image Studio 生成一张角色定妆 / LookDev。');
  $('#grayboxSceneReferenceMeta').textContent = sceneReference
    ? `${sceneReference.label || '场景参考'} · ${sceneReference.source === 'scene_upload' ? 'Web 上传' : '项目已有素材'}`
    : '可选择项目已有关键帧，或直接上传古宅 / 门楼场景参考图。';
  $('#grayboxReferenceStatus').textContent = references.ready ? 'READY' : `${references.character_bound ? '人物✓' : '人物×'} · ${references.scene_bound ? '场景✓' : '场景×'}`;
  $('#grayboxReferenceStatus').classList.toggle('off', !references.ready);
  $('#grayboxReferencePackageStatus').textContent = references.ready
    ? '最终输入包 READY：Blender 白模 MP4 + 人物参考图 + 场景参考图 + Shot Prompt。'
    : `最终输入包未完成：${references.character_bound ? '' : '缺人物参考 '}${references.scene_bound ? '' : '缺场景参考'}`.trim();
  $('#grayboxBindCharacterReference').disabled = !(references.character_candidates || []).length;
  $('#grayboxBindSceneReference').disabled = !(references.scene_candidates || []).length;

  const currentFrame = Number(render.current_frame || 0);
  const totalFrames = Number(render.total_frames || 0);
  const percent = Math.max(0, Math.min(100, Number(render.progress_percent || 0)));
  const heartbeatAge = render.heartbeat_seconds_ago;
  const logAge = render.log_updated_seconds_ago;
  const processAlive = Boolean(render.process_alive);
  $('#grayboxProgressBar').style.width = `${percent}%`;
  $('#grayboxFrameProgress').textContent = totalFrames
    ? `${currentFrame} / ${totalFrames} 帧 · ${percent.toFixed(1)}%`
    : '等待帧进度';
  $('#grayboxHeartbeat').textContent = heartbeatAge == null
    ? '暂无渲染心跳'
    : `${formatGrayboxSeconds(heartbeatAge)}前有渲染活动`;
  $('#grayboxElapsed').textContent = render.elapsed_seconds == null
    ? '运行时长：—'
    : `已运行 ${formatGrayboxSeconds(render.elapsed_seconds)}`;
  const activityAge = heartbeatAge == null ? Number.POSITIVE_INFINITY : Number(heartbeatAge);
  const possiblyStalled = render.status === 'RUNNING' && processAlive && activityAge > 60;
  $('#grayboxProcessStatus').textContent = render.status === 'RUNNING'
    ? (possiblyStalled ? 'PROCESS ALIVE · STALLED?' : processAlive ? 'PROCESS ALIVE' : 'PROCESS CHECKING')
    : (render.status || 'IDLE');
  $('#grayboxProcessStatus').classList.toggle('off', render.status !== 'RUNNING' || !processAlive || possiblyStalled);
  $('#grayboxLiveSummary').textContent = render.status === 'RUNNING'
    ? (processAlive
      ? (possiblyStalled
        ? `Blender 进程仍存活，但已 ${formatGrayboxSeconds(activityAge)}没有新的渲染活动；可能卡住，请展开日志确认。`
        : `Blender 进程存活 · ${render.progress_source === 'heartbeat' ? '逐帧心跳' : render.progress_source === 'blender_log' ? '从 Blender 日志解析帧数' : '等待首个帧心跳'}`)
      : 'Blender 状态仍为 RUNNING，正在确认进程状态…')
    : render.status === 'PASS'
      ? 'Blender 白模渲染完成'
      : render.status === 'FAIL'
        ? `渲染失败：${render.detail || 'Blender 进程已退出'}`
        : '等待渲染';
  $('#grayboxLogAge').textContent = logAge == null ? '暂无日志时间' : `最后更新：${formatGrayboxSeconds(logAge)}前`;
  $('#grayboxLiveLog').textContent = render.log_tail || '暂无 Blender 日志。';

  if (spec.duration_seconds) {
    $('#grayboxShotTitle').textContent = `${Number(spec.duration_seconds).toFixed(1)} 秒 · 古宅入场镜头`;
    const actor = spec.actor || {};
    $('#grayboxShotDetail').textContent = `${spec.character?.name || '项目角色'}：从古宅门口走入 → ${Number(actor.stop_time || 0).toFixed(1)}s 停下 → ${Number(actor.look_up_time || 0).toFixed(1)}s 抬头看灯 → 镜头缓慢前推。`;
  }

  const preview = $('#grayboxPreview');
  const empty = $('#grayboxVideoEmpty');
  if (render.media_url) {
    const nextSrc = render.media_url + `?v=${encodeURIComponent(data.render?.spec_sha256 || render.output_bytes || 'ready')}`;
    const currentSrc = preview.getAttribute('src') || '';
    if (currentSrc !== nextSrc) {
      const wasPlaying = !preview.paused && !preview.ended;
      const currentTime = Number(preview.currentTime || 0);
      preview.src = nextSrc;
      if (currentTime > 0) {
        preview.addEventListener('loadedmetadata', () => {
          if (Number.isFinite(preview.duration)) preview.currentTime = Math.min(currentTime, Math.max(0, preview.duration - 0.05));
          if (wasPlaying) preview.play().catch(() => {});
        }, { once: true });
      }
    }
    preview.classList.remove('hidden');
    empty.classList.add('hidden');
    $('#grayboxRenderMeta').textContent = render.render_stale
      ? `STALE HASH · MP4 可人工沿用 · ${spec.fps || 24}fps · ${spec.width || 720}×${spec.height || 1280}`
      : `${spec.fps || 24}fps · ${spec.width || 720}×${spec.height || 1280} · ${review.status || 'PENDING'}`;
  } else {
    preview.removeAttribute('src');
    preview.classList.add('hidden');
    empty.classList.remove('hidden');
    empty.textContent = render.render_stale
      ? '镜头方案已修改，旧白模已失效。请重新生成 Blender 白模。'
      : (render.detail || '生成后可直接在这里检查镜头、走位、动作和遮挡关系。');
    $('#grayboxRenderMeta').textContent = render.status || '等待生成';
  }

  const finalItem = (data.final_items || [])[0];
  const finalPreview = $('#grayboxFinalPreview');
  const finalEmpty = $('#grayboxFinalEmpty');
  if (finalItem?.media_url) {
    if ((finalPreview.getAttribute('src') || '') !== finalItem.media_url) finalPreview.src = finalItem.media_url;
    finalPreview.classList.remove('hidden');
    finalEmpty.classList.add('hidden');
    $('#grayboxFinalMeta').textContent = `${finalItem.model || 'MiniMax H3'} · ${finalItem.resolution || ''} · ${finalItem.review_status || 'PENDING'}`;
  } else {
    finalPreview.removeAttribute('src');
    finalPreview.classList.add('hidden');
    finalEmpty.classList.remove('hidden');
    $('#grayboxFinalMeta').textContent = '尚未生成';
  }

  const smoke = data.smoke_review || {};
  const smokeCharacter = $('#grayboxSmokeCharacter');
  const smokeScene = $('#grayboxSmokeScene');
  const smokeMotion = $('#grayboxSmokeMotion');
  const smokeNote = $('#grayboxSmokeNote');
  smokeCharacter.value = smoke.character_identity || 'PENDING';
  smokeScene.value = smoke.scene_fidelity || 'PENDING';
  smokeMotion.value = smoke.motion_skeleton || 'PENDING';
  if (document.activeElement !== smokeNote) smokeNote.value = smoke.note || '';
  $('#grayboxSmokeStatus').textContent = smoke.stale ? 'STALE' : (smoke.status || 'PENDING');
  $('#grayboxSmokeStatus').classList.toggle('off', smoke.status !== 'PASS' || smoke.stale);
  $('#grayboxSaveSmokeReview').disabled = !finalItem?.media_url;
  $('#grayboxSmokeHint').textContent = !finalItem?.media_url
    ? '先生成 MiniMax 最终成片，再检查人物身份、古宅场景和白模动态。'
    : smoke.stale
      ? '最新成片已经变化；旧 smoke 结论已失效，请重新检查三项。'
      : smoke.status === 'PASS'
        ? 'P32-02 smoke PASS：人物身份 + 古宅场景 + Blender 动态骨架已同时通过。'
        : smoke.status === 'FAIL'
          ? '本次 smoke 有失败项；请根据失败轴修改参考图、Prompt 或白模后重新生成。'
          : '逐项播放对照：人物身份 / 场景 / 白模运镜走位时序，三项全部 PASS 才算 smoke 通过。';

  if (!$('#grayboxPrompt').value.trim() && data.default_prompt) $('#grayboxPrompt').value = data.default_prompt;
  const ensureButton = $('#grayboxEnsureSpecButton');
  ensureButton.disabled = !state.grayboxProjectId || data.spec_ready;
  ensureButton.textContent = data.spec_ready ? '✓ 镜头方案已就绪' : '① 生成镜头方案';
  $('#grayboxStepHint').textContent = data.spec_ready
    ? (render.output_ready
      ? '镜头方案和当前白模已匹配；请播放检查，满意后点击“白模通过”。'
      : '镜头方案已生成。下一步直接点击“② 生成 Blender 白模”。')
    : '先点击“① 生成镜头方案”，再进入 Blender 白模。';
  $('#grayboxRenderButton').disabled = !installed || !data.spec_ready || render.status === 'RUNNING';
  $('#grayboxAdjustButton').disabled = !data.spec_ready || render.status === 'RUNNING';
  $('#grayboxApproveButton').disabled = !render.output_ready || render.status === 'RUNNING';
  $('#grayboxRequestChangesButton').disabled = !data.spec_ready || render.status === 'RUNNING';
  const h3Select = $('#grayboxH3ShotSelect');
  const h3Candidates = (state.costFirstPlan?.routes || []).filter((item) => item.route === 'H3_CANDIDATE');
  const previousH3 = h3Select?.value || '';
  if (h3Select) {
    h3Select.innerHTML = '<option value="">选择已批准的 P36 H3 候选…</option>' + h3Candidates.map((item) => {
      const approved = Boolean(item.h3_escalation?.approved);
      return '<option value="' + escapeHtml(item.shot_id) + '">' + escapeHtml(item.shot_id) + ' · ' + Number(item.duration_seconds || 0).toFixed(2) + 's · ' + (approved ? 'APPROVED' : 'LOCKED') + '</option>';
    }).join('');
    if (previousH3 && h3Candidates.some((item) => item.shot_id === previousH3)) h3Select.value = previousH3;
    else {
      const firstApproved = h3Candidates.find((item) => item.h3_escalation?.approved);
      if (firstApproved) h3Select.value = firstApproved.shot_id;
    }
  }
  const selectedH3 = h3Candidates.find((item) => item.shot_id === h3Select?.value);
  const p36H3Approved = Boolean(selectedH3?.h3_escalation?.approved);
  $('#grayboxGenerateFinalButton').disabled = !render.output_ready || !minimax.configured || review.status !== 'APPROVED' || !references.ready || !p36H3Approved;
  $('#grayboxHint').textContent = review.status !== 'APPROVED'
    ? '先检查白模镜头、走位、动作和遮挡；白模通过后才允许调用付费 AI 视频 Provider。'
    : !references.ready
      ? '白模已通过；继续绑定人物参考 + 场景参考，完成最终输入包后才能生成成片。'
      : !p36H3Approved
        ? 'H3 仍锁定：必须先在 P36 将确实无法本地解决的 H3 候选写明原因并人工批准。'
        : 'P36 H3 已批准；本次时长使用该 Shot 的 Voice Timeline/Shot Breakdown 实际时长，仍需付费与上传二次确认。';
  renderGptKeyframes();
  syncGrayboxPolling();
}

async function loadGraybox(projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId)) {
  if (!projectId) return;
  state.grayboxProjectId = projectId;
  state.graybox = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox`);
  try {
    state.gptKeyframes = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/gpt-keyframes`);
  } catch (_) {
    state.gptKeyframes = null;
  }
  try {
    state.costFirstPlan = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/cost-first-routing`);
    state.costFirstProjectId = projectId;
  } catch (_) {
    state.costFirstPlan = null;
  }
  renderGraybox();
  renderCostFirstPlan();
}

async function ensureGrayboxShotSpec() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) { log('没有可用的国漫项目', true); return; }
  const button = $('#grayboxEnsureSpecButton');
  button.disabled = true;
  button.textContent = '镜头方案处理中…';
  $('#grayboxStepHint').textContent = '正在创建并校验 Shot Spec…';
  $('#grayboxLogLine').textContent = '正在生成 8 秒古宅入场镜头方案…';
  try {
    state.graybox = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/spec`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    state.grayboxProjectId = projectId;
    renderGraybox();
    $('#grayboxLogLine').textContent = '镜头方案已就绪。下一步点击“② 生成 Blender 白模”。';
    log('P32 镜头方案 READY：下一步可生成 Blender 白模。');
  } catch (error) {
    $('#grayboxStepHint').textContent = `镜头方案失败：${error.message}`;
    $('#grayboxLogLine').textContent = error.message;
    log(error.message, true);
  } finally {
    renderGraybox();
  }
}

async function waitForGrayboxRender(projectId) {
  for (let index = 0; index < 240; index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
    const current = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox`);
    state.graybox = current;
    renderGraybox();
    if (current.render?.status === 'PASS' && current.render?.output_ready) return current;
    if (current.render?.status === 'FAIL') throw new Error(current.render?.detail || 'Blender 白模渲染失败');
  }
  throw new Error('Blender 白模渲染等待超时；请查看 graybox 日志。');
}

async function renderGrayboxShot() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) return;
  const button = $('#grayboxRenderButton');
  button.disabled = true;
  button.textContent = 'Blender 渲染中…';
  $('#grayboxLogLine').textContent = '正在后台调用 Blender 构建场景、人物、动作、镜头并渲染 MP4…';
  try {
    await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/render`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    await waitForGrayboxRender(projectId);
    $('#grayboxLogLine').textContent = 'Blender 白模已完成。请直接播放检查；不满意可用自然语言微调。';
    log('P32 Blender 白模完成，可在 Web 直接预览。');
  } catch (error) {
    $('#grayboxLogLine').textContent = error.message;
    log(error.message, true);
  } finally {
    button.textContent = '② 生成 Blender 白模';
    await loadGraybox(projectId).catch(() => {});
  }
}

async function adjustGrayboxShot() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  const instruction = $('#grayboxAdjustInput').value.trim();
  if (!projectId || !instruction) { log('请输入白模微调要求', true); return; }
  const button = $('#grayboxAdjustButton');
  button.disabled = true;
  try {
    const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/adjust`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instruction }),
    });
    state.graybox = result;
    renderGraybox();
    $('#grayboxLogLine').textContent = `已应用：${(result.changes || []).join('；')}。正在重做白模…`;
    log(`P32 白模微调：${instruction}`);
    await renderGrayboxShot();
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; }
}

async function reviewGraybox(status) {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) return;
  try {
    state.graybox = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/review`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, note: status === 'APPROVED' ? 'Web graybox review approved' : $('#grayboxAdjustInput').value.trim() }),
    });
    renderGraybox();
    log(status === 'APPROVED' ? 'Blender 白模已通过；下一步确认人物参考与场景参考绑定。' : '白模标记为需要修改。');
  } catch (error) { log(error.message, true); }
}

async function installGrayboxSmokePack() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) { log('没有可用的国漫项目', true); return; }
  const button = $('#grayboxInstallSmokePack');
  button.disabled = true;
  button.textContent = '安装并绑定中…';
  try {
    state.graybox = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/references/install-smoke-pack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    renderGraybox();
    $('#grayboxLogLine').textContent = '内置 P32 Smoke 人物 + 古宅参考已安装并自动绑定，可直接用于 Gemini / MiniMax 首轮验证。';
    log('P32 Smoke reference pack 已安装并绑定。');
  } catch (error) {
    $('#grayboxLogLine').textContent = error.message;
    log(error.message, true);
  } finally {
    button.textContent = '使用内置 Smoke 人物 + 古宅参考';
    renderGraybox();
  }
}

async function bindGrayboxReference(kind) {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) return;
  const isCharacter = kind === 'character';
  const select = $(isCharacter ? '#grayboxCharacterReferenceSelect' : '#grayboxSceneReferenceSelect');
  const button = $(isCharacter ? '#grayboxBindCharacterReference' : '#grayboxBindSceneReference');
  const path = select.value;
  if (!path) {
    log(isCharacter ? '请先选择人物参考图' : '请先选择场景参考图', true);
    return;
  }
  button.disabled = true;
  try {
    state.graybox = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/references/bind`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, path }),
    });
    renderGraybox();
    log(isCharacter ? '人物参考已绑定到当前白模镜头。' : '场景参考已绑定到当前白模镜头。');
  } catch (error) {
    log(error.message, true);
  } finally {
    renderGraybox();
  }
}

async function uploadGrayboxSceneReference() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) return;
  const file = $('#grayboxSceneReferenceFile').files?.[0];
  if (!file) { log('请先选择一张场景参考图', true); return; }
  const limit = Number(state.graybox?.references?.max_scene_upload_bytes || 12 * 1024 * 1024);
  if (file.size <= 0 || file.size > limit) {
    log(`场景参考图必须在 1 byte 到 ${Math.round(limit / 1024 / 1024)} MB 之间`, true);
    return;
  }
  if (!/\.(png|jpe?g|webp)$/i.test(file.name)) {
    log('场景参考图必须是 PNG、JPEG 或 WebP', true);
    return;
  }
  const button = $('#grayboxUploadSceneReference');
  button.disabled = true;
  button.textContent = '上传绑定中…';
  try {
    const contentBase64 = await fileToBase64(file);
    state.graybox = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/references/scene-upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, content_base64: contentBase64 }),
    });
    $('#grayboxSceneReferenceFile').value = '';
    renderGraybox();
    log('场景参考图已上传并自动绑定到当前镜头。');
  } catch (error) {
    log(error.message, true);
  } finally {
    button.textContent = '上传并绑定场景图';
    renderGraybox();
  }
}

async function saveMiniMaxKey() {
  const input = $('#grayboxMiniMaxKey');
  const button = $('#grayboxSaveMiniMaxKey');
  button.disabled = true;
  try {
    await api('/api/settings/keys', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: 'minimax_h3', key: input.value }),
    });
    input.value = '';
    await loadGraybox();
    log('MiniMax H3 Key 已保存到当前 Web 服务进程。');
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; }
}

async function generateGrayboxFinal() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) return;
  const referencesReady = Boolean(state.graybox?.references?.ready);
  if (!referencesReady) {
    log('生成最终视频前必须先绑定人物参考图和场景参考图。', true);
    return;
  }
  const h3ShotId = $('#grayboxH3ShotSelect')?.value || '';
  const h3Route = (state.costFirstPlan?.routes || []).find((item) => item.shot_id === h3ShotId);
  if (!h3ShotId || h3Route?.route !== 'H3_CANDIDATE' || !h3Route?.h3_escalation?.approved) {
    log('必须先在 P36 选择并人工批准一个 H3_CANDIDATE 镜头。', true);
    return;
  }
  const confirmBillable = $('#grayboxBillableConfirm').checked;
  const uploadAuthorized = $('#grayboxUploadConfirm').checked;
  if (!confirmBillable || !uploadAuthorized) {
    log('生成最终视频前需要同时确认付费调用与白模/人物/场景参考素材上传授权。', true);
    return;
  }
  if (!window.confirm('将上传当前白模 MP4 + 人物参考图 + 场景参考图给 MiniMax H3，并产生 API 费用。确认继续？')) return;
  const button = $('#grayboxGenerateFinalButton');
  button.disabled = true;
  button.textContent = 'MiniMax H3 生成中…';
  $('#grayboxLogLine').textContent = '正在提交：Blender 白模 + 人物参考 + 场景参考 → MiniMax H3…';
  try {
    const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/final`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shot_id: h3ShotId,
        prompt: $('#grayboxPrompt').value.trim(),
        resolution: $('#grayboxResolution').value,
        confirm_billable: true,
        upload_authorized: true,
      }),
    });
    await loadGraybox(projectId);
    $('#grayboxFinalPreview').src = result.media_url;
    $('#grayboxLogLine').textContent = 'MiniMax H3 最终镜头已返回，请人工检查与白模的运镜、走位和动作时序是否一致。';
    log(`P32 AI 最终镜头完成：${result.output}`);
  } catch (error) {
    $('#grayboxLogLine').textContent = error.message;
    log(error.message, true);
  } finally {
    button.textContent = '③ 白模 → MiniMax H3 成片';
    renderGraybox();
  }
}

async function saveGrayboxSmokeReview() {
  const projectId = resolveActiveNovelProject(state.grayboxProjectId || state.imageStudioProjectId);
  if (!projectId) return;
  const finalItem = (state.graybox?.final_items || [])[0];
  if (!finalItem?.media_url) {
    log('必须先生成 MiniMax H3 最终成片，才能保存 smoke 验收。', true);
    return;
  }
  const button = $('#grayboxSaveSmokeReview');
  button.disabled = true;
  button.textContent = '保存验收中…';
  try {
    state.graybox = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/graybox/smoke-review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        character_identity: $('#grayboxSmokeCharacter').value,
        scene_fidelity: $('#grayboxSmokeScene').value,
        motion_skeleton: $('#grayboxSmokeMotion').value,
        note: $('#grayboxSmokeNote').value.trim(),
      }),
    });
    renderGraybox();
    const review = state.graybox?.smoke_review || {};
    $('#grayboxLogLine').textContent = review.status === 'PASS'
      ? 'P32-02 smoke PASS：人物身份、古宅场景、白模动态三项同时通过。'
      : review.status === 'FAIL'
        ? 'P32-02 smoke 已记录失败项；按失败轴调整后重新生成本镜头。'
        : 'P32-02 smoke 已保存，仍有待检查项。';
    log(`P32 smoke review: ${review.status || 'PENDING'}`);
  } catch (error) {
    $('#grayboxLogLine').textContent = error.message;
    log(error.message, true);
  } finally {
    button.textContent = '保存本次 smoke 验收';
    renderGraybox();
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
    return `<article class="anime-project-card"><div class="anime-project-head"><div><span class="section-kicker">${escapeHtml(project.ip_id)} · ${escapeHtml(project.series_id)}</span><h3>${escapeHtml(project.title)}</h3></div><span class="result-chip">${escapeHtml(project.status)}</span></div><div class="hierarchy-row"><span>剧集 1</span><span>${project.season_count} 季</span><span>${project.episode_count} 集</span></div><div class="episode-token-row">${project.episode_ids.map((id) => `<span>${escapeHtml(id)}</span>`).join('')}</div><div class="source-row"><span>${escapeHtml(sourceText)}</span><strong class="${sources?.publication_allowed ? 'allowed' : 'blocked'}">${sources?.publication_allowed ? '可发布' : '禁止发布'}</strong></div><div class="runtime-row readiness-summary">${escapeHtml(readinessText)}</div><div class="runtime-row">${escapeHtml(bibleText)}</div><div class="runtime-row">${escapeHtml(planText)}</div><div class="runtime-row">${escapeHtml(episodePlanText)}</div><div class="runtime-row">${escapeHtml(scriptText)}</div><div class="runtime-row">${escapeHtml(reviewText)}</div><div class="runtime-row">${escapeHtml(visualText)}</div><div class="runtime-row">${escapeHtml(characterText)}</div><div class="runtime-row">${escapeHtml(environmentText)}</div><div class="runtime-row">${escapeHtml(assetReviewText)}</div><div class="runtime-row">${escapeHtml(shotText)}</div><div class="runtime-row">${escapeHtml(storyboardText)}</div><div class="runtime-row">${escapeHtml(animaticText)}</div><div class="runtime-row">${escapeHtml(animaticReviewText)}</div><div class="runtime-row">${escapeHtml(voiceText)}</div><div class="runtime-row">${escapeHtml(audioText)}</div><div class="runtime-row">${escapeHtml(audioMixText)}</div><div class="runtime-row">${escapeHtml(dynamicText)}</div><div class="runtime-row">${escapeHtml(editText)}</div><div class="runtime-row">${escapeHtml(qcText)}</div><div class="runtime-row">${escapeHtml(acceptanceText)}</div><div class="repository-row"><small>${escapeHtml(repositoryText)}</small><button data-open-anime-project="${escapeHtml(project.directory_id)}">进入制作台</button><button data-impact-project="${escapeHtml(project.directory_id)}" data-impact-root="${escapeHtml(project.ip_id)}" ${repository ? '' : 'disabled'}>分析 IP 影响</button><button class="danger-action" data-delete-anime-project="${escapeHtml(project.directory_id)}" data-delete-anime-title="${escapeHtml(project.title)}">删除项目</button></div><div class="runtime-row">${escapeHtml(runtimeText)}</div><div class="impact-result" data-impact-result="${escapeHtml(project.directory_id)}"></div><small class="manifest-note">${escapeHtml(project.project_id)} · novel-anime-project.json</small></article>`;
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
  document.querySelectorAll('[data-delete-anime-project]').forEach((button) => button.addEventListener('click', async () => {
    const projectId = button.dataset.deleteAnimeProject;
    const title = button.dataset.deleteAnimeTitle || projectId;
    if (!window.confirm(`确认删除《${title}》？\n\n该项目目录、生成素材和项目数据库都会从本地 VideoCreator 中删除，此操作不可撤销。`)) return;
    button.disabled = true;
    button.textContent = '删除中…';
    try {
      const result = await api('/api/novel-anime/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, confirm_delete: true }),
      });
      if (state.activeNovelProjectId === projectId || state.imageStudioProjectId === projectId || state.studioProjectId === projectId) {
        clearActiveNovelProject();
      }
      if (state.novelImportResult?.directory_id === projectId) state.novelImportResult = null;
      await load(result.default_project_id || '');
      setView('anime');
      log(`已删除项目：《${result.title || title}》`);
    } catch (error) {
      log(error.message, true);
      button.disabled = false;
      button.textContent = '删除项目';
    }
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

function voiceTimelineShotTiming(data, line) {
  return (data?.shot_timing || []).find((item) => item.episode_id === line.episode_id && item.shot_id === line.shot_id) || null;
}

function finalAudioOptionList(items) {
  return ['<option value="">不使用</option>'].concat((items || []).map(function(item) {
    return '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>';
  })).join('');
}

function renderFinalAudioSection(episodeId) {
  const data = state.finalAudio;
  if (!data) return '<div class="final-audio-section"><div class="empty-state">正在载入 Final Voice…</div></div>';
  const provider = data.provider || {};
  const locks = [data.locks?.narrator].concat(data.locks?.characters || []).filter(Boolean);
  const episode = (data.episodes || []).find(function(item) { return item.episode_id === episodeId; }) || {};
  const candidates = data.audio_candidates || {};
  const lockCards = locks.map(function(lock) {
    return '<article class="voice-lock-card" data-voice-lock-card="' + escapeHtml(lock.character_id) + '">' +
      '<div><strong>' + escapeHtml(lock.character_name || lock.character_id) + '</strong><small>' +
      escapeHtml(lock.character_id) + ' · ' + escapeHtml(lock.status || 'UNLOCKED') + '</small></div>' +
      '<label>Fish voice_id<input class="text-field" data-lock-voice-id value="' + escapeHtml(lock.voice_id || '') + '" placeholder="Fish Audio reference_id"></label>' +
      '<label>语速<input class="text-field" data-lock-speed type="number" min="0.5" max="2" step="0.05" value="' + Number(lock.speed || 1).toFixed(2) + '"></label>' +
      '<label>默认情绪<input class="text-field" data-lock-emotion value="' + escapeHtml(lock.emotion_default || '') + '" placeholder="calm / sad / angry"></label>' +
      '<button class="secondary-button small-button" data-save-voice-lock="' + escapeHtml(lock.character_id) + '">锁定声线</button>' +
      '</article>';
  }).join('');

  const finalLines = (episode.lines || []).map(function(line) {
    const timingText = Number(line.duration_seconds || 0).toFixed(2);
    const sourceText = line.source_duration_seconds
      ? ' · 原始正式声 ' + Number(line.source_duration_seconds).toFixed(2) + 's → 已对齐 ' + Number(line.aligned_duration_seconds || 0).toFixed(2) + 's'
      : '';
    return '<article class="final-voice-line">' +
      '<div><span class="pipeline-stage-status ' + (line.final_status === 'READY' ? 'pass' : 'pending') + '">' + escapeHtml(line.final_status || 'NOT_RUN') + '</span>' +
      '<strong>' + escapeHtml(line.text || '') + '</strong>' +
      '<small>' + escapeHtml(line.kind || '') + ' · ' + escapeHtml(line.speaker_character_id || 'NARRATOR') + ' · Timing ' + timingText + 's' + sourceText + '</small>' +
      (line.final_audio_url ? '<audio controls preload="metadata" src="' + escapeHtml(line.final_audio_url) + '"></audio>' : '') +
      '</div><button class="secondary-button small-button" data-generate-final-line="' + escapeHtml(line.unit_id) + '" ' +
      (provider.configured && episode.timing_status === 'READY' ? '' : 'disabled') + '>单句正式重生成</button></article>';
  }).join('');

  const mix = episode.final_mix || {};
  return '<section class="final-audio-section">' +
    '<div class="final-audio-head"><div><span class="section-kicker">P34 / FINAL VOICE + FINAL MIX</span>' +
    '<strong>正式角色配音 · 声线锁 · BGM 自动 Ducking</strong>' +
    '<small>Fish Audio 仅在明确付费确认后调用。正式语音会自动压缩/拉伸到 P33 已锁定的 Timing Voice 时长，不允许换声线后重新打乱镜头。</small></div>' +
    '<span class="status-dot ' + (provider.configured ? '' : 'off') + '">' + (provider.configured ? 'FISH READY' : 'FISH KEY MISSING') + '</span></div>' +
    '<div class="final-audio-key-row"><input class="text-field" id="finalAudioKey" type="password" autocomplete="off" placeholder="Fish Audio API Key（仅当前 Web 进程）">' +
    '<button class="secondary-button small-button" id="finalAudioSaveKey">保存 Fish Key</button><small>' + escapeHtml(provider.source || 'none') + ' · Key 不写盘</small></div>' +
    '<div class="voice-lock-grid">' + (lockCards || '<div class="empty-state">当前没有需要锁定的角色声线。</div>') + '</div>' +
    '<div class="final-voice-gate"><label><input type="checkbox" id="finalVoiceBillable"> 我确认正式 Fish Audio TTS 会产生费用</label>' +
    '<label><input type="checkbox" id="finalVoiceUpload"> 我允许将本集对白/旁白文本发送给 Fish Audio</label>' +
    '<button class="primary-button small-button" id="generateFinalVoiceEpisode" ' + (provider.configured && episode.timing_status === 'READY' ? '' : 'disabled') + '>生成本集正式配音</button>' +
    '<span>' + escapeHtml(episode.final_voice_status || 'NOT_RUN') + ' · ' + Number(episode.ready_line_count || 0) + '/' + Number(episode.line_count || 0) + ' 句</span></div>' +
    '<div class="final-voice-line-list">' + (finalLines || '<div class="empty-state">先完成本集 P33 Timing Voice。</div>') + '</div>' +
    '<div class="final-mix-card"><div><strong>Final Mix</strong><small>对白/旁白优先；有 BGM 时自动 sidechain ducking；最终 -16 LUFS / -1 dBTP。</small></div>' +
    '<div class="final-audio-upload"><select class="select-field" id="finalAudioAssetKind"><option value="bgm">BGM</option><option value="ambience">环境音</option><option value="sfx">SFX</option></select><input class="text-field" id="finalAudioAssetFile" type="file" accept="audio/*,.wav,.mp3,.m4a,.aac,.aiff,.aif,.flac"><button class="secondary-button small-button" id="uploadFinalAudioAsset">上传音频素材</button></div>' +
    '<label>BGM<select class="select-field" id="finalMixBgm">' + finalAudioOptionList(candidates.bgm) + '</select></label>' +
    '<label>环境音<select class="select-field" id="finalMixAmbience">' + finalAudioOptionList(candidates.ambience) + '</select></label>' +
    '<label>SFX<select class="select-field" id="finalMixSfx">' + finalAudioOptionList(candidates.sfx) + '</select></label>' +
    '<button class="secondary-button small-button" id="generateFinalMix" ' + (episode.final_voice_status === 'READY' ? '' : 'disabled') + '>生成 Final Mix</button>' +
    '<div class="final-mix-result"><span>' + escapeHtml(mix.status || 'NOT_RUN') + (mix.dialogue_ducking ? ' · BGM DUCKING ON' : '') + '</span>' +
    (mix.m4a_url ? '<audio controls preload="metadata" src="' + escapeHtml(mix.m4a_url) + '"></audio>' : '') +
    (mix.wav_url ? '<a href="' + escapeHtml(mix.wav_url) + '" target="_blank" rel="noopener noreferrer">WAV</a>' : '') +
    '</div></div></section>';
}

async function refreshFinalAudio(projectId = state.finalAudioProjectId || state.studio?.directory_id) {
  if (!projectId) return;
  state.finalAudioProjectId = projectId;
  state.finalAudio = await api('/api/novel-anime/projects/' + encodeURIComponent(projectId) + '/final-audio');
}

function finalVoiceGate() {
  return {
    confirm_billable: Boolean($('#finalVoiceBillable')?.checked),
    text_upload_authorized: Boolean($('#finalVoiceUpload')?.checked),
  };
}

async function saveFinalAudioKey() {
  const input = $('#finalAudioKey');
  const key = input?.value?.trim() || '';
  if (!key) { log('请输入 Fish Audio API Key', true); return; }
  const button = $('#finalAudioSaveKey');
  button.disabled = true;
  try {
    await api('/api/settings/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'fish_audio', key: key }),
    });
    input.value = '';
    await refreshFinalAudio();
    renderVoiceTimeline();
    log('Fish Audio Key 已保存到当前 Web 服务进程，不写盘。');
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; }
}

async function saveVoiceLock(characterId, button) {
  const card = button.closest('[data-voice-lock-card]');
  button.disabled = true;
  try {
    state.finalAudio = await api('/api/novel-anime/projects/' + encodeURIComponent(state.finalAudioProjectId) + '/final-audio/voice-lock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        character_id: characterId,
        provider: 'fish_audio',
        voice_id: card.querySelector('[data-lock-voice-id]').value.trim(),
        speed: Number(card.querySelector('[data-lock-speed]').value || 1),
        emotion_default: card.querySelector('[data-lock-emotion]').value.trim(),
      }),
    });
    renderVoiceTimeline();
    log(characterId + ' 正式声线锁已保存。');
  } catch (error) { log(error.message, true); button.disabled = false; }
}

async function generateFinalVoiceEpisode() {
  const episodeId = $('#voiceTimelineEpisode')?.value || $('#voiceTimelinePanel')?.dataset.episodeId || '';
  const button = $('#generateFinalVoiceEpisode');
  button.disabled = true;
  button.textContent = '正在生成正式配音…';
  try {
    state.finalAudio = await api('/api/novel-anime/projects/' + encodeURIComponent(state.finalAudioProjectId) + '/final-audio/generate-episode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ episode_id: episodeId }, finalVoiceGate())),
    });
    renderVoiceTimeline();
    log(episodeId + ' 正式角色配音已生成并自动对齐 Timing Voice。');
  } catch (error) { log(error.message, true); button.disabled = false; button.textContent = '生成本集正式配音'; }
}

async function generateFinalVoiceLine(unitId, button) {
  const episodeId = $('#voiceTimelineEpisode')?.value || $('#voiceTimelinePanel')?.dataset.episodeId || '';
  button.disabled = true;
  button.textContent = '生成中…';
  try {
    const result = await api('/api/novel-anime/projects/' + encodeURIComponent(state.finalAudioProjectId) + '/final-audio/generate-line', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ episode_id: episodeId, unit_id: unitId }, finalVoiceGate())),
    });
    state.finalAudio = result.status_view;
    renderVoiceTimeline();
    log(unitId + ' 正式配音已重新生成并时长对齐。');
  } catch (error) { log(error.message, true); button.disabled = false; button.textContent = '单句正式重生成'; }
}

async function uploadFinalAudioAsset() {
  const file = $('#finalAudioAssetFile')?.files?.[0];
  const kind = $('#finalAudioAssetKind')?.value || 'bgm';
  if (!file) { log('请选择要上传的 BGM / 环境音 / SFX 文件', true); return; }
  if (file.size <= 0 || file.size > 30 * 1024 * 1024) { log('音频文件必须在 1 byte 到 30 MB 之间', true); return; }
  const button = $('#uploadFinalAudioAsset');
  button.disabled = true;
  button.textContent = '上传中…';
  try {
    const contentBase64 = await fileToBase64(file);
    const result = await api('/api/novel-anime/projects/' + encodeURIComponent(state.finalAudioProjectId) + '/final-audio/upload-asset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: kind, filename: file.name, content_base64: contentBase64 }),
    });
    state.finalAudio = result.status_view;
    renderVoiceTimeline();
    log('音频素材已上传：' + result.path);
  } catch (error) {
    log(error.message, true);
    button.disabled = false;
    button.textContent = '上传音频素材';
  }
}

async function generateFinalMix() {
  const episodeId = $('#voiceTimelineEpisode')?.value || $('#voiceTimelinePanel')?.dataset.episodeId || '';
  const button = $('#generateFinalMix');
  button.disabled = true;
  button.textContent = '正在混音…';
  try {
    const result = await api('/api/novel-anime/projects/' + encodeURIComponent(state.finalAudioProjectId) + '/final-audio/mix', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        episode_id: episodeId,
        bgm_path: $('#finalMixBgm')?.value || '',
        ambience_path: $('#finalMixAmbience')?.value || '',
        sfx_path: $('#finalMixSfx')?.value || '',
      }),
    });
    state.finalAudio = result.status_view;
    renderVoiceTimeline();
    log(episodeId + ' Final Mix 完成：-16 LUFS / -1 dBTP' + (result.dialogue_ducking ? ' · BGM 自动 Ducking 已启用。' : '。'));
  } catch (error) { log(error.message, true); button.disabled = false; button.textContent = '生成 Final Mix'; }
}

function renderVoiceTimeline() {
  const target = $('#voiceTimelinePanel');
  if (!target) return;
  const data = state.voiceTimeline;
  if (!data) {
    target.innerHTML = '<div class="empty-state">正在载入 Voice Timeline…</div>';
    return;
  }
  const episodes = data.episodes || [];
  if (!episodes.length) {
    target.innerHTML = '<div class="empty-state">当前剧本没有对白或旁白。先在编剧室生成 DIALOGUE / NARRATION 后再进入配音。</div>';
    return;
  }

  const previous = target.dataset.episodeId;
  const active = episodes.find((item) => item.episode_id === previous) || episodes[0];
  target.dataset.episodeId = active.episode_id;
  const readyCount = episodes.filter((item) => item.status === 'READY').length;
  const sourceLabel = data.asr_round_trip === false ? 'SCRIPT → TTS TIMING → SUBTITLE' : 'UNKNOWN';
  const voice = active.voice || 'Tingting';

  const lines = active.lines || [];
  const lineCards = lines.map((line) => {
    const timing = voiceTimelineShotTiming(data, line);
    const speaker = line.kind === 'NARRATION' ? '旁白' : (line.speaker_character_id || '角色');
    const duration = Number(line.duration_seconds || line.estimated_duration_seconds || 0);
    return `<article class="voice-line-card">
      <div class="voice-line-time"><strong>${Number(line.start_seconds || 0).toFixed(2)}s</strong><span>→ ${Number(line.end_seconds || 0).toFixed(2)}s</span></div>
      <div class="voice-line-copy">
        <div class="voice-line-meta"><span>${escapeHtml(speaker)}</span><span>${escapeHtml(line.kind)}</span><span>${escapeHtml(line.status || 'PLANNED')}</span></div>
        <strong>${escapeHtml(line.text || '')}</strong>
        <small>${escapeHtml(line.scene_id || 'NO SCENE')} · ${escapeHtml(line.shot_id || 'NO SHOT')} · 语音 ${duration.toFixed(2)}s${timing ? ` · 建议镜头 ${Number(timing.recommended_duration_seconds || 0).toFixed(2)}s · ${escapeHtml(timing.timing_source || '')}` : ''}</small>
        ${line.audio_url ? `<audio controls preload="metadata" src="${escapeHtml(line.audio_url)}"></audio>` : '<em>尚未生成本地 Timing Voice</em>'}
      </div>
    </article>`;
  }).join('');

  const subtitleLinks = [
    active.srt_url ? `<a href="${escapeHtml(active.srt_url)}" target="_blank" rel="noopener noreferrer">SRT 字幕</a>` : '',
    active.ass_url ? `<a href="${escapeHtml(active.ass_url)}" target="_blank" rel="noopener noreferrer">ASS 字幕</a>` : '',
  ].filter(Boolean).join('');

  target.innerHTML = `
    <div class="voice-timeline-head">
      <div>
        <span class="section-kicker">VOICE FIRST / ZERO-COST TIMING</span>
        <strong>先定声音时长，再决定 Blender / H3 镜头时长</strong>
        <small>临时配音使用本机 macOS say，只用于 Timing，不调用付费 TTS；字幕直接来自剧本文本，不走 Whisper / ASR。</small>
      </div>
      <span class="status-dot ${readyCount ? '' : 'off'}">${readyCount}/${episodes.length} READY</span>
    </div>
    <div class="voice-timeline-toolbar">
      <label><span>集数</span><select class="select-field" id="voiceTimelineEpisode">${episodes.map((episode) => `<option value="${escapeHtml(episode.episode_id)}" ${episode.episode_id === active.episode_id ? 'selected' : ''}>${escapeHtml(episode.episode_id)} · ${episode.line_count || 0} 句 · ${Number(episode.duration_seconds || 0).toFixed(1)}s</option>`).join('')}</select></label>
      <label><span>Timing Voice</span><input class="text-field" id="voiceTimelineVoice" value="${escapeHtml(voice)}" placeholder="Tingting"></label>
      <button class="primary-button small-button" id="voiceTimelineGenerate">生成本集临时配音 + 字幕</button>
      <button class="secondary-button small-button" id="voiceTimelineApplyTiming" ${active.status === 'READY' ? '' : 'disabled'}>应用到镜头时长</button>
    </div>
    <div class="voice-timeline-summary">
      <span>来源：${escapeHtml(sourceLabel)}</span>
      <span>本集 ${active.generated_line_count || 0}/${active.line_count || 0} 句已生成</span>
      <span>预计/实际时长 ${Number(active.duration_seconds || 0).toFixed(2)}s</span>
      <span>付费：0</span>
      ${subtitleLinks ? `<span class="voice-subtitle-links">${subtitleLinks}</span>` : '<span>字幕：待生成</span>'}
    </div>
    <div class="voice-line-list">${lineCards}</div>
    <div class="voice-timeline-note">生成完成后，系统会同时写入 <code>audio/voice-timeline.json</code>、<code>audio/shot-timing.json</code>、SRT 和 ASS。点击“应用到镜头时长”后，只写回当前集的 ACTUAL_TTS 时长，并明确要求下游 Storyboard / Animatic 重建。</div>
    ${renderFinalAudioSection(active.episode_id)}
  `;

  $('#voiceTimelineEpisode')?.addEventListener('change', (event) => {
    target.dataset.episodeId = event.target.value;
    renderVoiceTimeline();
  });
  $('#voiceTimelineGenerate')?.addEventListener('click', generateVoiceTimelinePreview);
  $('#voiceTimelineApplyTiming')?.addEventListener('click', applyVoiceTimelineTiming);
  $('#finalAudioSaveKey')?.addEventListener('click', saveFinalAudioKey);
  document.querySelectorAll('[data-save-voice-lock]').forEach((button) => button.addEventListener('click', () => saveVoiceLock(button.dataset.saveVoiceLock, button)));
  $('#generateFinalVoiceEpisode')?.addEventListener('click', generateFinalVoiceEpisode);
  document.querySelectorAll('[data-generate-final-line]').forEach((button) => button.addEventListener('click', () => generateFinalVoiceLine(button.dataset.generateFinalLine, button)));
  $('#uploadFinalAudioAsset')?.addEventListener('click', uploadFinalAudioAsset);
  $('#generateFinalMix')?.addEventListener('click', generateFinalMix);
}

async function applyVoiceTimelineTiming() {
  const target = $('#voiceTimelinePanel');
  const projectId = state.studio?.directory_id || state.voiceTimelineProjectId;
  const episodeId = $('#voiceTimelineEpisode')?.value || target?.dataset.episodeId || '';
  const button = $('#voiceTimelineApplyTiming');
  if (!projectId || !episodeId || !button) return;
  button.disabled = true;
  button.textContent = '正在写回镜头…';
  try {
    const result = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/voice-timeline/apply-shot-timing`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: episodeId }),
    });
    log(`${episodeId} 已按真实 TTS 时长更新 ${result.updated_shot_count || 0} 个镜头；Storyboard / Animatic 需要按新时长重建。`);
    await loadStudio(projectId);
    state.currentWorkspace = 'audio';
    renderStudio();
  } catch (error) {
    log(error.message, true);
    button.disabled = false;
    button.textContent = '应用到镜头时长';
  }
}

async function loadVoiceTimeline(projectId = state.studio?.directory_id || state.voiceTimelineProjectId) {
  if (!projectId) return;
  state.voiceTimelineProjectId = projectId;
  try {
    const [timeline, finalAudio] = await Promise.all([
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/voice-timeline`),
      api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/final-audio`),
    ]);
    state.voiceTimeline = timeline;
    state.finalAudio = finalAudio;
    state.finalAudioProjectId = projectId;
    renderVoiceTimeline();
  } catch (error) {
    const target = $('#voiceTimelinePanel');
    if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

async function generateVoiceTimelinePreview() {
  const target = $('#voiceTimelinePanel');
  const projectId = state.studio?.directory_id || state.voiceTimelineProjectId;
  const episodeId = $('#voiceTimelineEpisode')?.value || target?.dataset.episodeId || '';
  const voice = $('#voiceTimelineVoice')?.value?.trim() || 'Tingting';
  const button = $('#voiceTimelineGenerate');
  if (!projectId || !episodeId) return;
  button.disabled = true;
  button.textContent = '正在生成本地 Timing Voice…';
  try {
    state.voiceTimeline = await api(`/api/novel-anime/projects/${encodeURIComponent(projectId)}/voice-timeline/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: episodeId, voice }),
    });
    target.dataset.episodeId = episodeId;
    renderVoiceTimeline();
    await loadStudio(projectId);
    state.currentWorkspace = 'audio';
    renderStudio();
    log(`${episodeId} Timing Voice + SRT/ASS 已生成；现在可用真实语音时长驱动镜头长度。`);
  } catch (error) {
    log(error.message, true);
    button.disabled = false;
    button.textContent = '生成本集临时配音 + 字幕';
  }
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
  select.innerHTML = state.animeProjects.map((item) => `<option value="${escapeHtml(item.directory_id)}">${escapeHtml(novelProjectOptionLabel(item))}</option>`).join('');
  select.value = state.studio.directory_id;
  $('#studioTabs').innerHTML = workspaces.map((item) => `<button class="studio-tab${item.id === active.id ? ' active' : ''}" data-studio-workspace="${escapeHtml(item.id)}">${escapeHtml(item.title)}</button>`).join('');
  document.querySelectorAll('[data-studio-workspace]').forEach((button) => button.addEventListener('click', () => { state.currentWorkspace = button.dataset.studioWorkspace; $('#studioDetail').classList.add('hidden'); renderStudio(); }));
  renderReadiness();
  const entries = Object.entries(active.data || {}).filter(([key]) => key !== 'project' && key !== 'readiness');
  const cards = entries.map(([key, value]) => `<button class="studio-data-card" data-studio-resource="${escapeHtml(key)}"><strong>${escapeHtml(key)}</strong><small>${escapeHtml(compactValue(value))}</small><span class="card-link">查看详情 →</span></button>`).join('');
  const action = active.id === 'review' ? `<div class="review-action"><strong>记录审片问题</strong><div class="form-row"><input id="issueTitle" class="text-field" placeholder="问题标题"><input id="issueRefs" class="text-field" placeholder="关联 ID（逗号分隔）"><button class="secondary-button small-button" id="issueButton">创建问题单</button></div><small>问题会写入项目 QC，仍需人工处理后才能通过发布门。</small></div>` : '';
  const characterGallery = active.id === 'assets' ? '<div class="native-asset-section"><div class="panel-heading"><div><span class="section-kicker">LOCAL CHARACTER ASSETS</span><h3>角色转面与零成本动作预览</h3><p class="panel-subtitle">直接使用本地透明角色图和程序化镜头，不上传素材，不调用外部模型。</p></div></div><div class="character-asset-gallery" id="characterAssetGallery"><div class="empty-state">正在载入角色资产…</div></div></div>' : '';
  const episodeMasterGallery = active.id === 'render' ? '<div class="native-asset-section"><div class="panel-heading"><div><span class="section-kicker">LOCAL EPISODE REVIEW</span><h3>《镜花缘》前五集本地母版</h3><p class="panel-subtitle">在线播放、检查剧情/画面/声音/字幕，并逐集保存人工审核。这里不会自动发布。</p></div></div><div id="episodeMasterGallery"><div class="empty-state">正在载入五集母版…</div></div></div>' : '';
  const voiceTimelinePanel = active.id === 'audio' ? '<div class="native-asset-section"><div id="voiceTimelinePanel"><div class="empty-state">正在载入 Voice Timeline…</div></div></div>' : '';
  $('#studioContent').innerHTML = `<div class="studio-hero"><div><span class="section-kicker">${escapeHtml(state.studio.project_id)}</span><h3>${escapeHtml(state.studio.title)} · ${escapeHtml(active.title)}</h3><p>${escapeHtml(active.description)}。页面直接读取项目 Schema、状态机和 QC 结果，不维护 Web 独立数据。</p></div><span class="studio-status">${escapeHtml(active.status)}</span></div><div class="studio-data-grid">${cards || '<div class="empty-state">当前工作区暂无数据。</div>'}</div>${characterGallery}${voiceTimelinePanel}${episodeMasterGallery}${action}<div class="studio-api">工作区 API：/api/novel-anime/projects/${encodeURIComponent(state.studio.directory_id)}/workspaces</div>`;
  if (active.id === 'assets') loadCharacterAssetGallery();
  if (active.id === 'audio') loadVoiceTimeline(state.studio.directory_id);
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
  ['workspace', 'novelImport', 'anime', 'studio', 'imageStudio', 'projects', 'providers'].forEach((name) => $(`#${name}View`).classList.toggle('hidden', name !== view));
  $('#outputPanel').classList.toggle('hidden', view !== 'workspace');
  $('#logPanel')?.classList.toggle('hidden', view !== 'workspace');
  if (view === 'projects') renderProjectTable();
  if (view === 'anime') renderAnimeProjects();
  if (view === 'studio') renderStudio();
  if (view === 'imageStudio') {
    const target = resolveActiveNovelProject(state.imageStudioProjectId);
    if (target) {
      setActiveNovelProject(target);
      loadImageStudio(target).catch((error) => log(error.message, true));
    }
  }
  if (view === 'providers') renderProviderSettings();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateNovelImportRightsUI() {
  const formal = $('#novelImportRights').value === 'OWNED_OR_LICENSED';
  $('#novelImportRightsConfirmRow').classList.toggle('hidden', !formal);
  if (!formal) $('#novelImportRightsConfirm').checked = false;
}

async function readNovelTxt(file) {
  if (!file) throw new Error('请先选择小说 TXT');
  if (!file.name.toLowerCase().endsWith('.txt')) throw new Error('小说文件必须是 .txt');
  if (file.size <= 0 || file.size > 20 * 1024 * 1024) throw new Error('小说 TXT 必须在 1 byte 到 20 MB 之间');
  const bytes = await file.arrayBuffer();
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch (_) {
    throw new Error('小说 TXT 必须使用 UTF-8 编码');
  }
}

async function importNovelProject() {
  const button = $('#novelImportButton');
  const file = $('#novelImportFile').files?.[0];
  const title = $('#novelImportTitle').value.trim();
  const author = $('#novelImportAuthor').value.trim();
  const episodeCount = Number($('#novelImportEpisodes').value || 5);
  const rightsMode = $('#novelImportRights').value;
  const rightsConfirmed = $('#novelImportRightsConfirm').checked;

  if (!title) { log('请输入小说名称', true); return; }
  if (!Number.isInteger(episodeCount) || episodeCount < 1 || episodeCount > 999) { log('首季集数必须是 1–999', true); return; }
  if (rightsMode === 'OWNED_OR_LICENSED' && !rightsConfirmed) { log('正式进入改编流程前，需要确认作者/授权状态', true); return; }

  button.disabled = true;
  button.textContent = '正在创建项目并导入…';
  $('#novelImportStatus').textContent = 'IMPORTING';
  $('#novelImportResult').classList.add('hidden');
  try {
    const sourceText = await readNovelTxt(file);
    const result = await api('/api/novel-anime/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, author, episode_count: episodeCount, rights_mode: rightsMode, rights_confirmed: rightsConfirmed, source_name: file.name, source_text: sourceText }),
    });
    state.novelImportResult = result;
    $('#novelImportStatus').textContent = 'PASS';
    $('#novelImportResultTitle').textContent = result.reused_existing
      ? (result.scene_backfill?.status === 'READY'
          ? `《${result.title}》已复用原项目，并完成 scenes 回填`
          : `《${result.title}》已存在，已复用原项目`)
      : `《${result.title}》已建立独立项目`;
    const backfill = result.scene_backfill || {};
    const backfillMeta = backfill.scene_count ? ' · 已生成 ' + backfill.scene_count + ' 个 scene / ' + (backfill.shot_count || 0) + ' 个 Shot' : '';
    $('#novelImportResultMeta').textContent = (result.import?.chapter_count || 0) + ' 章 · ' + (result.character_count || result.import?.character_candidates || 0) + ' 个角色 · 首季 ' + result.episode_count + ' 集 · ' + (result.script_adaptation_allowed ? '可进入本地改编' : '仅技术测试') + ' · 原始 TXT 不落库，仅保留 Scene Seed / 改编脚本' + backfillMeta;
    $('#novelImportResult').classList.remove('hidden');
    state.activeNovelProjectId = result.directory_id;
    state.studioProjectId = result.directory_id;
    state.pipelineProjectId = result.directory_id;
    state.imageStudioProjectId = result.directory_id;
    rememberActiveNovelProject(result.directory_id);
    await load(result.directory_id);
    setView('novelImport');
    log((result.reused_existing ? '已识别相同 TXT 并复用原项目' : '小说导入完成') + '：' + result.title + ' · ' + (result.import?.chapter_count || 0) + ' 章 · ' + (result.character_count || result.import?.character_candidates || 0) + ' 个角色' + (backfill.scene_count ? ' · scenes ' + backfill.scene_count + ' · Shots ' + (backfill.shot_count || 0) : ''));
  } catch (error) {
    $('#novelImportStatus').textContent = 'FAIL';
    log(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>＋</span>创建项目并导入小说';
  }
}

async function openImportedNovelStudio() {
  const result = state.novelImportResult;
  if (!result?.directory_id) return;
  try {
    await loadStudio(result.directory_id);
    setView('studio', 'overview');
    log(`进入新项目制作台：${result.title}`);
  } catch (error) { log(error.message, true); }
}
async function deleteCurrentImageStudioProject() {
  const projectId = String($('#imageStudioProject')?.value || state.imageStudioProjectId || '').trim();
  const project = state.animeProjects.find((item) => item.directory_id === projectId);
  if (!projectId || !project) { log('当前没有可删除的国漫项目', true); return; }
  if (!window.confirm(`确认删除《${project.title}》？\n\n项目目录、已生成图片和项目数据库都会删除，此操作不可撤销。`)) return;

  const button = $('#imageStudioDeleteProjectButton');
  button.disabled = true;
  button.textContent = '删除中…';
  try {
    const result = await api('/api/novel-anime/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, confirm_delete: true }),
    });
    clearActiveNovelProject();
    if (state.novelImportResult?.directory_id === projectId) state.novelImportResult = null;
    await load(result.default_project_id || '');
    if (result.default_project_id) {
      setView('imageStudio');
      log(`已删除《${result.title || project.title}》 [${projectId}]，剩余 ${Number(result.remaining_project_count || 0)} 个项目，已切换到剩余项目。`);
    } else {
      setView('anime');
      log(`已删除《${result.title || project.title}》，当前已没有国漫项目。`);
    }
  } catch (error) {
    log(error.message, true);
  } finally {
    button.textContent = '删除当前项目';
    button.disabled = !(state.animeProjects || []).length;
  }
}

function renderImageStudio() {
  const data = state.imageStudio;
  const select = $('#imageStudioProject');
  const projects = state.animeProjects || [];
  select.innerHTML = projects.map((item) => `<option value="${escapeHtml(item.directory_id)}">${escapeHtml(novelProjectOptionLabel(item))}</option>`).join('');
  const activeProjectId = resolveActiveNovelProject(data?.project_id || state.imageStudioProjectId);
  if (activeProjectId) select.value = activeProjectId;
  const activeProject = projects.find((item) => item.directory_id === activeProjectId);
  $('#imageStudioActiveProjectHint').textContent = activeProject
    ? `当前生成目标：《${activeProject.title}》 · ${activeProject.directory_id}`
    : '当前生成目标：未选择项目';
  const deleteProjectButton = $('#imageStudioDeleteProjectButton');
  if (deleteProjectButton) {
    deleteProjectButton.disabled = !activeProject;
    deleteProjectButton.title = activeProject ? `删除《${activeProject.title}》` : '当前没有可删除项目';
  }

  const providers = data?.providers || [];
  const openai = providers.find((item) => item.provider_id === 'OPENAI_IMAGE' || item.id === 'openai_image') || data?.provider || {};
  const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image') || {};
  const routing = data?.routing || {};
  const providerSelect = $('#imageStudioProviderSelect');
  if (providerSelect) providerSelect.value = state.imageStudioProviderPreference || data?.default_provider || 'AUTO';
  const stylePresets = data?.style_presets || [];
  const styleSelect = $('#imageStudioStylePreset');
  if (styleSelect) {
    styleSelect.innerHTML = stylePresets.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join('');
    if (!stylePresets.some((item) => item.id === state.imageStudioStylePreset)) {
      state.imageStudioStylePreset = data?.default_style_preset || stylePresets[0]?.id || 'CINEMATIC_3D_DONGHUA';
    }
    styleSelect.value = state.imageStudioStylePreset;
  }
  const activeStyle = stylePresets.find((item) => item.id === state.imageStudioStylePreset) || stylePresets[0] || {};
  $('#imageStudioStyleHint').textContent = activeStyle.description
    ? `${activeStyle.description} · Prompt / Negative 自动切换${activeStyle.lora_id ? ' · 支持 LoRA 自动增强' : ''}${activeStyle.preferred_provider === 'OPENAI_IMAGE' ? ' · AUTO 优先高质量最终视觉' : ''}`
    : '每种风格自动切换 Prompt / Negative / 可选 LoRA。';
  const localReady = Boolean(comfyui.connected && comfyui.workflow_ready);
  const remoteReady = Boolean(openai.configured);
  const finalProviderRequired = Boolean(activeStyle.final_provider_required);
  if (finalProviderRequired && !remoteReady) {
    $('#imageStudioStyleHint').textContent += ' · 当前未配置 OpenAI Image：该最终 LookDev 路线已阻止 Animagine 本地预览冒充最终结果。';
  }
  const preference = state.imageStudioProviderPreference || 'AUTO';
  const autoPrefersRemote = preference === 'AUTO' && activeStyle.preferred_provider === 'OPENAI_IMAGE' && remoteReady;
  $('#imageStudioProvider').textContent = preference === 'COMFYUI_IMAGE'
    ? (finalProviderRequired ? 'BLOCKED · Final requires OpenAI' : 'ComfyUI Local')
    : preference === 'OPENAI_IMAGE'
      ? (openai.label || 'OpenAI Image')
      : autoPrefersRemote
        ? 'AUTO → OpenAI Final'
        : finalProviderRequired
          ? 'AUTO → Final Provider Required'
          : (localReady ? 'AUTO → ComfyUI' : 'AUTO → OpenAI');
  $('#imageStudioModel').textContent = finalProviderRequired
    ? (remoteReady ? (openai.model || 'OpenAI Image') : 'OpenAI Image required')
    : (preference === 'OPENAI_IMAGE' || autoPrefersRemote)
      ? (openai.model || 'OpenAI Image')
      : localReady ? (comfyui.checkpoint || 'Local checkpoint') : (openai.model || '—');
  const finalRouteReady = !finalProviderRequired || remoteReady;
  $('#imageStudioStatus').textContent = finalRouteReady
    ? ((localReady || remoteReady) ? 'READY' : 'NO PROVIDER')
    : 'FINAL PROVIDER REQUIRED';
  $('#imageStudioStatus').classList.toggle('off', !finalRouteReady || !(localReady || remoteReady));
  $('#imageStudioRoute').textContent = routing.final_visual_route || 'IMAGE_PROVIDER_ROUTER';
  $('#imageStudioBlenderRole').textContent = `Blender · ${routing.blender_role || 'AUXILIARY_3D_CONTROL'}`;
  $('#imageStudioComfyUrl').value = comfyui.base_url || 'http://127.0.0.1:8188';
  const service = comfyui.service || {};
  const installer = comfyui.installer || {};
  const modelInstaller = comfyui.model_installer || {};
  const loraInstaller = comfyui.lora_installer || {};
  const serviceState = service.state || (localReady ? 'RUNNING' : 'UNKNOWN');
  const installRunning = installer.status === 'RUNNING';
  const installReady = Boolean(installer.installed || service.installed);
  const modelRunning = modelInstaller.status === 'RUNNING';
  const modelInstalled = Boolean(modelInstaller.installed || comfyui.checkpoint_count);
  const loraRunning = loraInstaller.status === 'RUNNING';
  const loraInstalled = Boolean(loraInstaller.installed);
  $('#imageStudioComfyServiceStatus').textContent = serviceState;
  $('#imageStudioComfyServiceStatus').classList.toggle('off', serviceState !== 'RUNNING');
  $('#imageStudioInstallComfy').disabled = installRunning || serviceState === 'RUNNING';
  $('#imageStudioInstallComfy').textContent = installRunning ? '安装中…' : (installReady ? '↻ 修复 / 更新 ComfyUI' : '↓ 安装 ComfyUI');
  $('#imageStudioStartComfy').disabled = installRunning || !installReady || Boolean(service.managed) || Boolean(service.connected);
  $('#imageStudioStopComfy').disabled = !Boolean(service.managed);
  $('#imageStudioComfyHint').textContent = localReady
    ? `本地 ComfyUI 已连接 · ${comfyui.checkpoint_count || 0} 个 checkpoint · 不产生远程 API 费用。`
    : `${service.detail || 'ComfyUI 服务未就绪'} · ${comfyui.detail || ''}`.replace(/ · $/, '');

  const progress = $('#imageStudioComfyInstallProgress');
  if (installRunning || installer.status === 'FAIL' || installer.status === 'PASS') {
    progress.classList.remove('hidden');
    $('#imageStudioComfyInstallStep').textContent = installer.step || '—';
    $('#imageStudioComfyInstallDetail').textContent = installer.detail || '—';
    $('#imageStudioComfyInstallState').textContent = installer.status || '—';
  } else {
    progress.classList.add('hidden');
  }

  const model = modelInstaller.model || {};
  const modelPercent = Math.max(0, Math.min(100, Number(modelInstaller.progress_percent || (modelInstalled ? 100 : 0))));
  const modelDownloaded = Number(modelInstaller.downloaded_bytes || 0);
  const modelExpected = Number(modelInstaller.expected_bytes || model.expected_bytes || 0);
  const gib = (value) => value ? (value / 1024 / 1024 / 1024).toFixed(2) : '0.00';
  $('#imageStudioComfyModelName').textContent = model.label || 'Animagine XL 4.0';
  $('#imageStudioComfyModelStatus').textContent = modelRunning ? (modelInstaller.step || 'DOWNLOADING') : (modelInstalled ? 'INSTALLED' : (modelInstaller.status || 'NOT INSTALLED'));
  $('#imageStudioComfyModelStatus').classList.toggle('off', !modelInstalled);
  $('#imageStudioComfyModelMeta').textContent = `${model.purpose || '动漫基础 checkpoint（国风由系统风格锁加强）'} · ${modelExpected ? gib(modelExpected) + ' GB' : '约 6.94 GB'} · ${model.license || 'openrail++'} · SHA256 校验`;
  $('#imageStudioInstallModel').disabled = !installReady || installRunning || modelRunning || modelInstalled;
  $('#imageStudioInstallModel').textContent = modelRunning ? '下载中…' : (modelInstalled ? '✓ 模型已安装' : '↓ 安装动漫基础模型');
  $('#imageStudioComfyModelSize').textContent = `${modelPercent.toFixed(1)}%${modelExpected ? ` · ${gib(modelDownloaded)} / ${gib(modelExpected)} GB` : ''}`;
  $('#imageStudioComfyModelProgressBar').style.width = `${modelPercent}%`;
  $('#imageStudioComfyModelDetail').textContent = modelInstalled
    ? `已安装 ${model.filename || comfyui.checkpoint || 'checkpoint'}；${localReady ? 'ComfyUI 已识别，可直接本地生图。' : '正在等待 ComfyUI 启动并刷新 checkpoint。'}`
    : modelRunning
      ? `${modelInstaller.detail || '正在下载'} · 支持断点续传 · ${modelInstaller.log_path || 'logs/comfyui-model-install.log'}`
      : modelInstaller.status === 'FAIL'
        ? `模型安装失败：${modelInstaller.detail || '可重新点击继续断点下载'}`
        : installReady
          ? '核心环境已就绪；点击一次即可下载、断点续传、校验并安装到 ComfyUI checkpoints。'
          : '请先完成 ComfyUI 核心安装。';

  const lora = loraInstaller.lora || {};
  const loraPercent = Math.max(0, Math.min(100, Number(loraInstaller.progress_percent || (loraInstalled ? 100 : 0))));
  const loraDownloaded = Number(loraInstaller.downloaded_bytes || 0);
  const loraExpected = Number(loraInstaller.expected_bytes || lora.expected_bytes || 0);
  const loraRecognized = Boolean(lora.filename && (comfyui.loras || []).includes(lora.filename));
  $('#imageStudioComfyLoraName').textContent = lora.label || 'SDXL 中国国风插画 LoRA';
  $('#imageStudioComfyLoraStatus').textContent = activeStyle.id === 'CINEMATIC_3D_DONGHUA'
    ? 'NOT USED BY 3D'
    : loraRunning
      ? (loraInstaller.step || 'DOWNLOADING')
      : (loraInstalled ? (loraRecognized ? 'READY' : 'INSTALLED') : (loraInstaller.status || 'NOT INSTALLED'));
  $('#imageStudioComfyLoraStatus').classList.toggle('off', !loraRecognized);
  $('#imageStudioComfyLoraMeta').textContent = `${lora.purpose || '中国古风风格增强'} · ${loraExpected ? (loraExpected / 1024 / 1024).toFixed(0) + ' MB' : '约 341 MB'} · ${lora.license || 'openrail++'} · ${lora.base_model || 'SDXL'}`;
  $('#imageStudioInstallLora').disabled = !installReady || installRunning || loraRunning || loraInstalled;
  $('#imageStudioInstallLora').textContent = loraRunning ? '下载中…' : (loraInstalled ? (loraRecognized ? '✓ 国风 LoRA 已启用' : '✓ 已安装，待刷新') : '↓ 安装国风 LoRA');
  $('#imageStudioComfyLoraSize').textContent = `${loraPercent.toFixed(1)}%${loraExpected ? ` · ${(loraDownloaded / 1024 / 1024).toFixed(0)} / ${(loraExpected / 1024 / 1024).toFixed(0)} MB` : ''}`;
  $('#imageStudioComfyLoraProgressBar').style.width = `${loraPercent}%`;
  $('#imageStudioComfyLoraDetail').textContent = activeStyle.id === 'CINEMATIC_3D_DONGHUA'
    ? '当前“电影级 3D 国漫”不会加载这颗插画 LoRA；它会把画面拉回 2D。该 LoRA 仅供中国古风插画 / 仙侠 / 武侠 / 水墨预设使用。'
    : loraRecognized
      ? `ComfyUI 已识别 ${lora.filename}；当前插画类国风预设可自动加载。`
      : loraInstalled
        ? `LoRA 已安装；需要 ComfyUI 刷新模型列表后自动启用。`
        : loraRunning
          ? `${loraInstaller.detail || '正在下载国风 LoRA'} · 支持断点续传 · ${loraInstaller.log_path || 'logs/comfyui-lora-install.log'}`
          : loraInstaller.status === 'FAIL'
            ? `LoRA 安装失败：${loraInstaller.detail || '可重新点击继续断点下载'}`
            : '未安装时仍可用 Prompt 风格锁；该 LoRA 只增强 2D/2.5D 国风插画预设。';

  const installHint = $('#imageStudioComfyInstallHint');
  if (installRunning) {
    installHint.classList.remove('hidden');
    installHint.textContent = `正在安装核心运行环境 · 日志：${installer.log_path || 'logs/comfyui-install.log'}。不会自动下载 checkpoint 模型。`;
  } else if (serviceState === 'NOT_INSTALLED') {
    installHint.classList.remove('hidden');
    installHint.textContent = '未检测到 ComfyUI。可以直接点击“安装 ComfyUI”；核心环境会安装到项目 .dependencies/ComfyUI，不污染系统 Python，也不会自动下载大型模型。';
  } else if (installer.status === 'PASS' && !comfyui.checkpoint_count) {
    installHint.classList.remove('hidden');
    installHint.textContent = 'ComfyUI 核心已安装。当前还没有 checkpoint 模型；服务可以启动，但生图还需要下一步选择模型。';
  } else if (installer.status === 'FAIL') {
    installHint.classList.remove('hidden');
    installHint.textContent = `ComfyUI 安装失败：${installer.detail || '请查看安装日志'} · ${installer.log_path || 'logs/comfyui-install.log'}`;
  } else if (service.home) {
    installHint.classList.remove('hidden');
    installHint.textContent = `检测目录：${service.home} · 日志：${service.log_path || 'logs/comfyui-service.log'}`;
  } else {
    installHint.classList.add('hidden');
    installHint.textContent = '';
  }
  $('#imageStudioKeyHint').textContent = openai.configured
    ? `${finalProviderRequired ? '3D 最终视觉 Provider' : 'OpenAI fallback'} 已配置（${openai.source === 'environment' ? '环境变量' : '当前 Web 会话'}），密钥不会显示或写入文件。`
    : finalProviderRequired
      ? '当前参考视频·电影级 3D 国漫需要 OpenAI Image；未配置时会阻止生成，不再回退到 Animagine 平面预览。'
      : 'OpenAI 仅作为远程 fallback；未配置时 AUTO 不会产生远程调用。';

  const character = data?.character || {};
  const characterReady = data?.character_ready !== false;
  const lock = character.visual_lock || {};
  $('#imageStudioCharacterLock').innerHTML = `<strong>${escapeHtml(character.character_id || 'PROJECT CHARACTER')} · ${escapeHtml(character.name || '项目角色')}</strong><small>${escapeHtml(lock.face || '')}</small><small>${escapeHtml(lock.hair || '')}</small><small>${escapeHtml(lock.costume || '')}</small>`;
  const characterButton = $('#generateCharacterBibleButton');
  const repairPanel = $('#imageStudioCharacterRepair');
  repairPanel.classList.toggle('hidden', characterReady);
  // Character bootstrap itself is local and free, so keep the primary action
  // clickable even before a Provider is ready. After bootstrap the normal
  // provider gate applies to image generation.
  const finalLookDev = activeStyle.render_role === 'FINAL_VISUAL' && activeStyle.layout_mode === 'SINGLE_LOOKDEV_HERO';
  const finalRouteBlocked = finalLookDev && activeStyle.final_provider_required && !remoteReady;
  characterButton.disabled = characterReady ? (finalRouteBlocked || !(localReady || remoteReady)) : false;
  characterButton.title = characterReady
    ? (finalRouteBlocked ? '该 3D LookDev 最终路线需要 OpenAI Image；本地 Animagine 只保留给概念预览。' : '')
    : '点击后自动从当前项目已保存的导入元数据重建角色资料，然后继续生成；无需重新上传 TXT。';
  characterButton.innerHTML = finalLookDev
    ? '<span>✦</span>生成最终 3D LookDev'
    : '<span>✦</span>生成角色定妆板';

  const items = data?.items || [];
  const recentElsewhere = data?.recent_elsewhere || [];
  $('#imageStudioCount').textContent = `${items.length} 张`;
  if (!items.length) {
    state.imageStudioSelected = null;
    $('#imageStudioResult').classList.add('hidden');
    $('#imageStudioEmpty').classList.remove('hidden');
    $('#imageStudioPreview').removeAttribute('src');
    if (recentElsewhere.length) {
      $('#imageStudioGallery').innerHTML = recentElsewhere.map((item) => `
        <button class="image-studio-thumb image-studio-foreign-thumb" data-image-studio-project="${escapeHtml(item.project_id)}">
          <img src="${escapeHtml(item.media_url)}" alt="${escapeHtml(item.artifact_type || 'image')}" loading="lazy">
          <span>
            <strong>其他项目最近生成</strong>
            <small>属于《${escapeHtml(item.project_title || item.project_id)}》 · 点击切换查看</small>
          </span>
        </button>
      `).join('');
      document.querySelectorAll('[data-image-studio-project]').forEach((button) => button.addEventListener('click', () => {
        const projectId = setActiveNovelProject(button.dataset.imageStudioProject);
        if (!projectId) return;
        loadImageStudio(projectId)
          .then(() => log(`已切换到包含最近生图的项目：${projectId}`))
          .catch((error) => log(error.message, true));
      }));
    } else {
      $('#imageStudioGallery').innerHTML = '<div class="empty-state">当前项目还没有 AI 生图资产。</div>';
    }
    return;
  }
  $('#imageStudioGallery').innerHTML = items.map((item, index) => `
    <button class="image-studio-thumb" data-image-studio-index="${index}">
      <img src="${escapeHtml(imageStudioMediaUrl(item))}" alt="${escapeHtml(item.artifact_type || 'image')}" loading="lazy">
      <span><strong>${escapeHtml(item.artifact_type === 'character_bible' ? (item.layout_mode === 'SINGLE_LOOKDEV_HERO' ? '最终 3D LookDev' : '角色定妆板') : '镜头关键帧')}</strong><small>${escapeHtml(item.style_label || '未记录风格')} · ${escapeHtml(item.render_role || 'UNSPECIFIED')} · ${escapeHtml(item.review_status || 'PENDING')}</small></span>
    </button>
  `).join('');
  document.querySelectorAll('[data-image-studio-index]').forEach((button) => button.addEventListener('click', () => {
    const item = items[Number(button.dataset.imageStudioIndex)];
    showImageStudioResult(item);
  }));
  if ($('#imageStudioResult').classList.contains('hidden')) showImageStudioResult(items[0]);
}

function imageStudioMediaUrl(item) {
  if (!item) return '';
  const projectId = String(item.project_id || state.imageStudioProjectId || '').trim();
  const output = String(item.output || '').trim();
  if (projectId && output) {
    const encodedProject = encodeURIComponent(projectId);
    const encodedPath = output.split('/').filter(Boolean).map(encodeURIComponent).join('/');
    const version = encodeURIComponent(String(item.created_at || item.artifact_id || '1'));
    return `/media/${encodedProject}/${encodedPath}?v=${version}`;
  }
  return String(item.media_url || '');
}

function showImageStudioResult(item) {
  if (!item) return;
  state.imageStudioSelected = item;
  $('#imageStudioEmpty').classList.add('hidden');
  $('#imageStudioResult').classList.remove('hidden');

  const preview = $('#imageStudioPreview');
  const previewError = $('#imageStudioPreviewError');
  const mediaUrl = imageStudioMediaUrl(item);
  previewError.classList.remove('visible');
  previewError.textContent = '';
  preview.onload = () => {
    previewError.classList.remove('visible');
    previewError.textContent = '';
  };
  preview.onerror = () => {
    previewError.classList.add('visible');
    previewError.textContent = `图片已生成，但 Web 无法加载媒体文件：${mediaUrl || '缺少 media URL'}。请刷新页面；若仍失败，查看 Web 日志中的 /media 请求状态。`;
    log(`AI 生图文件加载失败：${mediaUrl || item.output || 'unknown'}`, true);
  };
  if (item.media_valid === false) {
    preview.removeAttribute('src');
    previewError.classList.add('visible');
    previewError.textContent = `生成文件存在，但文件头不是有效 PNG/JPEG/WebP（${Number(item.media_bytes || 0)} bytes）。请重新生成；旧文件不会被当成有效视觉资产。`;
    log(`AI 生图文件格式无效：${item.output || 'unknown'}`, true);
  } else {
    preview.src = mediaUrl;
  }
  $('#imageStudioResultType').textContent = item.artifact_type === 'character_bible'
    ? (item.layout_mode === 'SINGLE_LOOKDEV_HERO' ? '最终 3D LookDev' : '角色定妆板')
    : '镜头关键帧';
  $('#imageStudioResultPath').textContent = item.output || '—';
  $('#imageStudioResultInfo').textContent = `${item.provider || 'Image Provider'} · ${item.model || ''} · ${item.style_label || '未记录风格'} · ${item.render_role || 'UNSPECIFIED'} · ${item.lora_applied ? `LoRA ${item.lora_name || 'ON'} @ ${Number(item.lora_strength || 0).toFixed(2)}` : 'No illustration LoRA'} · ${item.size || ''} · 人工审核 ${item.review_status || 'PENDING'}`;
  $('#imageStudioReview').textContent = item.review_status || 'PENDING';
}

async function loadImageStudio(projectId = resolveActiveNovelProject(state.imageStudioProjectId)) {
  if (!projectId) return;
  if (state.animeProjects.some((item) => item.directory_id === projectId)) setActiveNovelProject(projectId);
  else state.imageStudioProjectId = projectId;
  state.imageStudio = await api(`/api/image-studio/status?project_id=${encodeURIComponent(projectId)}`);
  const validStyles = state.imageStudio?.style_presets || [];
  const remembered = storedImageStylePreset(projectId);
  const defaultPreset = state.imageStudio?.default_style_preset || 'CINEMATIC_3D_DONGHUA';
  state.imageStudioStylePreset = validStyles.some((item) => item.id === remembered)
    ? remembered
    : defaultPreset;
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
    log(`ComfyUI：${result.detail || (result.connected ? '连接正常' : '未连接')}`);
  } catch (error) { log(error.message, true); }
  finally { button.disabled = false; button.textContent = '保存并检测'; }
}

async function waitForComfyUIReady(maxChecks = 24) {
  for (let index = 0; index < maxChecks; index += 1) {
    const status = await api('/api/comfyui/service/status');
    if (status.connected) return status;
    if (status.state === 'NOT_INSTALLED' || status.state === 'ERROR' || status.state === 'STOPPED') return status;
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  return api('/api/comfyui/service/status');
}

async function refreshComfyUIInstallStatus() {
  const installer = await api('/api/comfyui/install/status');
  if (state.imageStudio) {
    const providers = state.imageStudio.providers || [];
    const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image');
    if (comfyui) comfyui.installer = installer;
    renderImageStudio();
  }
  return installer;
}

async function refreshComfyUIModelStatus() {
  const modelInstaller = await api('/api/comfyui/models/status');
  if (state.imageStudio) {
    const providers = state.imageStudio.providers || [];
    const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image');
    if (comfyui) comfyui.model_installer = modelInstaller;
    renderImageStudio();
  }
  return modelInstaller;
}

async function refreshComfyUILoraStatus() {
  const loraInstaller = await api('/api/comfyui/loras/status');
  if (state.imageStudio) {
    const providers = state.imageStudio.providers || [];
    const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image');
    if (comfyui) comfyui.lora_installer = loraInstaller;
    renderImageStudio();
  }
  return loraInstaller;
}

async function installComfyUILora() {
  const button = $('#imageStudioInstallLora');
  button.disabled = true;
  button.textContent = '下载中…';
  try {
    await api('/api/comfyui/loras/install/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lora_id: 'sdxl-chinese-style-illustration' }),
    });
    log('中国国风 LoRA 下载已启动（约 341 MB）；支持断点续传，完成后自动 SHA256 校验。');
    let loraInstaller = await refreshComfyUILoraStatus();
    for (let index = 0; index < 5400 && loraInstaller.status === 'RUNNING'; index += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      loraInstaller = await refreshComfyUILoraStatus();
    }
    if (loraInstaller.status !== 'PASS') {
      if (loraInstaller.status !== 'RUNNING') log(`国风 LoRA 安装未完成：${loraInstaller.detail || loraInstaller.status || '未知错误'}`, true);
      return;
    }

    log('国风 LoRA 下载与 SHA256 校验完成；正在刷新 ComfyUI 模型列表。');
    let service = await api('/api/comfyui/service/status');
    if (service.managed && (service.connected || service.state === 'RUNNING' || service.state === 'STARTING')) {
      await api('/api/comfyui/service/stop', { method: 'POST' });
      service = await api('/api/comfyui/service/start', { method: 'POST' });
      await waitForComfyUIReady(60);
    } else if (!service.connected && service.installed) {
      service = await api('/api/comfyui/service/start', { method: 'POST' });
      if (service.managed || service.state === 'STARTING') await waitForComfyUIReady(60);
    }
    await loadImageStudio(state.imageStudioProjectId);
    const providers = state.imageStudio?.providers || [];
    const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image') || {};
    const filename = loraInstaller.lora?.filename || 'sdxl-chinese-style-illustration.safetensors';
    if ((comfyui.loras || []).includes(filename)) {
      log('中国国风 LoRA READY；中国古风 / 仙侠 / 武侠 / 水墨预设现在会自动加载。');
    } else if (service.connected && !service.managed) {
      log('LoRA 已安装；当前是外部 ComfyUI 进程，请重启该外部 ComfyUI 后刷新页面。', true);
    } else {
      log('LoRA 已安装；ComfyUI 正在刷新，稍后页面会自动识别。');
    }
  } catch (error) {
    log(error.message, true);
  } finally {
    await loadImageStudio(state.imageStudioProjectId).catch(() => {});
  }
}

async function installComfyUIModel() {
  const button = $('#imageStudioInstallModel');
  button.disabled = true;
  button.textContent = '下载中…';
  try {
    await api('/api/comfyui/models/install/start', { method: 'POST' });
    log('动漫基础 checkpoint 下载已启动；系统会自动叠加中国古风风格锁；支持断点续传，完成后自动 SHA256 校验。');
    let modelInstaller = await refreshComfyUIModelStatus();
    for (let index = 0; index < 10800 && modelInstaller.status === 'RUNNING'; index += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      modelInstaller = await refreshComfyUIModelStatus();
    }
    if (modelInstaller.status !== 'PASS') {
      if (modelInstaller.status !== 'RUNNING') log(`checkpoint 安装未完成：${modelInstaller.detail || modelInstaller.status || '未知错误'}`, true);
      return;
    }

    log('checkpoint 下载与 SHA256 校验完成；正在刷新本地 ComfyUI。');
    let service = await api('/api/comfyui/service/status');
    if (service.managed && (service.connected || service.state === 'RUNNING' || service.state === 'STARTING')) {
      await api('/api/comfyui/service/stop', { method: 'POST' });
      service = await api('/api/comfyui/service/start', { method: 'POST' });
    } else if (!service.connected && service.installed) {
      service = await api('/api/comfyui/service/start', { method: 'POST' });
    }
    if (service.managed || service.state === 'STARTING') await waitForComfyUIReady(60);
    await loadImageStudio(state.imageStudioProjectId);
    const providers = state.imageStudio?.providers || [];
    const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image') || {};
    if (comfyui.workflow_ready) {
      log(`本地视觉工厂 READY：${comfyui.checkpoint || modelInstaller.model?.filename || 'checkpoint'}`);
    } else if (service.connected && !service.managed) {
      log('checkpoint 已安装；当前是外部 ComfyUI 进程，需要该外部进程重新加载 checkpoint 列表。', true);
    } else {
      log('checkpoint 已安装；ComfyUI 正在启动，稍后刷新即可看到模型。');
    }
  } catch (error) {
    log(error.message, true);
    await loadImageStudio(state.imageStudioProjectId).catch(() => {});
  } finally {
    await loadImageStudio(state.imageStudioProjectId).catch(() => {});
  }
}

async function installComfyUI() {
  const button = $('#imageStudioInstallComfy');
  button.disabled = true;
  button.textContent = '安装中…';
  try {
    await api('/api/comfyui/install/start', { method: 'POST' });
    log('ComfyUI 核心安装已启动；不会自动下载 checkpoint 模型。');
    let installer = await refreshComfyUIInstallStatus();
    for (let index = 0; index < 600 && installer.status === 'RUNNING'; index += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      installer = await refreshComfyUIInstallStatus();
    }
    await loadImageStudio(state.imageStudioProjectId);
    if (installer.status === 'PASS') {
      log('ComfyUI 核心安装完成。下一步可以启动服务；若没有 checkpoint，页面会继续提示模型未安装。');
    } else if (installer.status !== 'RUNNING') {
      log(`ComfyUI 安装未完成：${installer.detail || installer.status || '未知错误'}`, true);
    }
  } catch (error) {
    log(error.message, true);
    await loadImageStudio(state.imageStudioProjectId).catch(() => {});
  } finally {
    button.disabled = false;
    const providers = state.imageStudio?.providers || [];
    const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image') || {};
    const installed = Boolean(comfyui.installer?.installed || comfyui.service?.installed);
    button.textContent = installed ? '↻ 修复 / 更新 ComfyUI' : '↓ 安装 ComfyUI';
  }
}

async function startComfyUIService() {
  const button = $('#imageStudioStartComfy');
  button.disabled = true;
  button.textContent = '启动中…';
  try {
    await api('/api/comfyui/service/start', { method: 'POST' });
    let status = await waitForComfyUIReady();
    await loadImageStudio(state.imageStudioProjectId);
    if (status.connected) log('ComfyUI 本地服务已启动并连接。');
    else log(`ComfyUI：${status.detail || status.state || '尚未就绪'}`, true);
  } catch (error) {
    log(error.message, true);
    await loadImageStudio(state.imageStudioProjectId).catch(() => {});
  } finally {
    button.disabled = false;
    button.innerHTML = '▶ 启动 ComfyUI';
  }
}

async function stopComfyUIService() {
  const button = $('#imageStudioStopComfy');
  button.disabled = true;
  button.textContent = '停止中…';
  try {
    const result = await api('/api/comfyui/service/stop', { method: 'POST' });
    await loadImageStudio(state.imageStudioProjectId);
    log(`ComfyUI：${result.detail || '已停止'}`);
  } catch (error) {
    log(error.message, true);
    await loadImageStudio(state.imageStudioProjectId).catch(() => {});
  } finally {
    button.disabled = false;
    button.innerHTML = '■ 停止';
  }
}

async function bootstrapImageStudioCharacters({ autoGenerate = false } = {}) {
  const projectId = resolveActiveNovelProject(state.imageStudioProjectId);
  if (!projectId) { log('没有可用的国漫项目', true); return; }

  const button = $('#imageStudioCharacterRepairButton');
  const mainButton = $('#generateCharacterBibleButton');
  button.disabled = true;
  mainButton.disabled = true;
  button.textContent = '正在重建角色…';
  mainButton.textContent = '正在重建角色…';

  try {
    const result = await api('/api/image-studio/character-bootstrap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId }),
    });
    log(`项目角色资料已恢复：${result.character_count || 0} 个角色 · ${result.source || 'project metadata'}`);
    await loadImageStudio(projectId);
    if (state.imageStudio?.character_ready === false) {
      throw new Error('该旧项目的导入元数据没有可恢复角色。新导入已强制在创建项目时完成角色抽取，不会再生成这种空项目。');
    }
    if (autoGenerate) await generateImageStudio('character-bible');
  } catch (error) {
    log(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = '自动重建角色资料';
    await loadImageStudio(projectId).catch(() => {});
  }
}

async function handleCharacterBibleAction() {
  if (state.imageStudio?.character_ready === false) {
    await bootstrapImageStudioCharacters({ autoGenerate: true });
    return;
  }
  await generateImageStudio('character-bible');
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

function imageStudioGenerationView(label) {
  const wrap = $('#imageStudioGenerationProgress');
  const title = $('#imageStudioGenerationTitle');
  const detail = $('#imageStudioGenerationDetail');
  const percent = $('#imageStudioGenerationPercent');
  const bar = $('#imageStudioGenerationProgressBar');
  const startedAt = Date.now();
  let lastProgressAt = 0;

  wrap.classList.remove('hidden');
  title.textContent = `正在生成${label}`;
  detail.textContent = '任务已提交，等待 ComfyUI 开始执行…';
  percent.textContent = '0%';
  bar.style.width = '0%';

  const timer = window.setInterval(() => {
    if (Date.now() - lastProgressAt < 1500) return;
    const elapsed = Math.max(1, Math.floor((Date.now() - startedAt) / 1000));
    detail.textContent = `ComfyUI 正在计算 · 已运行 ${elapsed} 秒`;
  }, 1000);

  return {
    update(value, max, message = '') {
      const current = Math.max(0, Number(value) || 0);
      const total = Math.max(0, Number(max) || 0);
      const ratio = total > 0 ? Math.min(100, current * 100 / total) : 0;
      lastProgressAt = Date.now();
      percent.textContent = total > 0 ? `${Math.round(ratio)}%` : '运行中';
      bar.style.width = `${ratio}%`;
      detail.textContent = message || (total > 0 ? `采样进度 ${current}/${total}` : 'ComfyUI 正在执行…');
    },
    running(message) {
      lastProgressAt = Date.now();
      percent.textContent = '运行中';
      detail.textContent = message;
    },
    complete(message) {
      window.clearInterval(timer);
      lastProgressAt = Date.now();
      percent.textContent = '100%';
      bar.style.width = '100%';
      title.textContent = `${label}生成完成`;
      detail.textContent = message || '图片已保存并载入预览';
    },
    fail(message) {
      window.clearInterval(timer);
      title.textContent = `${label}生成失败`;
      detail.textContent = message || '生成失败';
      percent.textContent = 'FAIL';
    },
    stop() {
      window.clearInterval(timer);
    },
  };
}

async function openComfyUIProgressSocket(baseUrl, clientId, progressView, button) {
  if (!baseUrl || !clientId) return null;
  let url;
  try {
    const parsed = new URL(baseUrl);
    parsed.protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    parsed.pathname = '/ws';
    parsed.search = `?clientId=${encodeURIComponent(clientId)}`;
    url = parsed.toString();
  } catch (_) {
    return null;
  }

  return new Promise((resolve) => {
    let settled = false;
    let socket;
    const done = (value) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      resolve(value);
    };
    const timeout = window.setTimeout(() => {
      try { socket?.close(); } catch (_) {}
      progressView.running('任务已提交；实时进度连接不可用，继续等待 ComfyUI 完成…');
      done(null);
    }, 1800);

    try {
      socket = new WebSocket(url);
    } catch (_) {
      done(null);
      return;
    }

    socket.onopen = () => {
      progressView.running('已连接 ComfyUI，等待采样开始…');
      done(socket);
    };
    socket.onerror = () => done(null);
    socket.onmessage = (event) => {
      if (typeof event.data !== 'string') return;
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      const data = message?.data || {};
      if (data.prompt_id && typeof data.prompt_id !== 'string') return;

      if (message.type === 'progress') {
        const value = Number(data.value || 0);
        const max = Number(data.max || 0);
        progressView.update(value, max, max ? `采样进度 ${value}/${max}` : 'ComfyUI 正在采样…');
        if (max > 0) button.textContent = `生成中 ${value}/${max}`;
      } else if (message.type === 'progress_state') {
        const nodes = data.nodes && typeof data.nodes === 'object' ? Object.values(data.nodes) : [];
        const active = nodes.find((node) => node?.state === 'executing') || nodes[nodes.length - 1];
        if (active && Number(active.max || 0) > 0) {
          const value = Number(active.value || 0);
          const max = Number(active.max || 0);
          progressView.update(value, max, `采样进度 ${value}/${max}`);
          button.textContent = `生成中 ${value}/${max}`;
        }
      } else if (message.type === 'execution_start') {
        progressView.running('ComfyUI 已开始执行工作流…');
      } else if (message.type === 'executing' && data.node) {
        progressView.running('ComfyUI 正在执行节点…');
      } else if (message.type === 'execution_success') {
        progressView.update(1, 1, 'ComfyUI 执行完成，正在保存图片…');
      } else if (message.type === 'execution_error') {
        progressView.fail(data.exception_message || 'ComfyUI 工作流执行失败');
      }
    };
  });
}

async function generateImageStudio(kind) {
  const projectId = resolveActiveNovelProject(state.imageStudioProjectId);
  if (!projectId) { log('没有可用的国漫项目', true); return; }
  setActiveNovelProject(projectId);
  if (state.imageStudio?.project_id !== projectId) {
    await loadImageStudio(projectId);
  }
  const providers = state.imageStudio?.providers || [];
  const openai = providers.find((item) => item.provider_id === 'OPENAI_IMAGE' || item.id === 'openai_image') || state.imageStudio?.provider || {};
  const comfyui = providers.find((item) => item.provider_id === 'COMFYUI_IMAGE' || item.id === 'comfyui_image') || {};
  const preference = state.imageStudioProviderPreference || 'AUTO';
  const activeStyle = (state.imageStudio?.style_presets || []).find((item) => item.id === state.imageStudioStylePreset)
    || (state.imageStudio?.style_presets || [])[0]
    || {};
  const localReady = Boolean(comfyui.connected && comfyui.workflow_ready);
  const remoteReady = Boolean(openai.configured);
  const finalLookDev = activeStyle.render_role === 'FINAL_VISUAL' && activeStyle.layout_mode === 'SINGLE_LOOKDEV_HERO';
  const finalProviderRequired = Boolean(activeStyle.final_provider_required);
  const autoPrefersRemote = preference === 'AUTO' && activeStyle.preferred_provider === 'OPENAI_IMAGE' && remoteReady;
  const usesRemote = preference === 'OPENAI_IMAGE' || autoPrefersRemote || (preference === 'AUTO' && !localReady);
  const label = kind === 'character-bible'
    ? (finalLookDev ? '最终 3D LookDev' : '角色定妆板')
    : '镜头关键帧';
  if (kind === 'character-bible' && state.imageStudio?.character_ready === false) {
    log('当前小说项目尚未抽取角色资料；已阻止使用全局演示角色生成。', true);
    return;
  }
  if (finalProviderRequired) {
    if (preference === 'COMFYUI_IMAGE') {
      log('“参考视频·电影级 3D 国漫”不再允许使用 Animagine 本地预览；请选择 AUTO 或 OpenAI Image。', true);
      return;
    }
    if (!remoteReady) {
      log('“参考视频·电影级 3D 国漫”需要 OpenAI Image 最终视觉 Provider。当前未配置 API Key，因此已阻止继续生成平面预览。', true);
      return;
    }
  }
  if (preference === 'COMFYUI_IMAGE' && !localReady) { log('ComfyUI 本地 Provider 尚未就绪', true); return; }
  if (usesRemote) {
    if (!openai.configured) { log('当前最终视觉路线需要 OpenAI Image，但尚未配置 API Key', true); return; }
    const reason = activeStyle.render_role === 'FINAL_VISUAL' ? '参考视频·电影级 3D 国漫最终视觉' : 'OpenAI Image';
    if (!window.confirm(`将使用 ${reason} 生成${label}，可能产生 API 费用。确认继续？`)) return;
  }

  const button = kind === 'character-bible' ? $('#generateCharacterBibleButton') : $('#generateKeyframeButton');
  const original = button.innerHTML;
  const progressView = imageStudioGenerationView(label);
  const clientId = usesRemote
    ? ''
    : `videocreator-${window.crypto?.randomUUID?.() || (Date.now().toString(36) + Math.random().toString(36).slice(2))}`;
  let progressSocket = null;

  button.disabled = true;
  button.dataset.generating = 'true';
  button.textContent = '生成中…';
  const projectTitle = state.animeProjects.find((item) => item.directory_id === projectId)?.title || projectId;
  log(`开始生成${label} · 项目《${projectTitle}》 · 风格 ${activeStyle?.label || state.imageStudioStylePreset} · ${usesRemote ? 'OpenAI FINAL' : 'ComfyUI local'}…`);
  try {
    if (!usesRemote) {
      progressSocket = await openComfyUIProgressSocket(comfyui.base_url || 'http://127.0.0.1:8188', clientId, progressView, button);
    } else {
      progressView.running('OpenAI Image 正在生成；远程 Provider 暂无本地采样步进度…');
    }

    const result = await api(`/api/image-studio/${kind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        custom_prompt: $('#imageStudioPrompt').value.trim(),
        confirm_billable: usesRemote,
        provider_preference: preference,
        style_preset: state.imageStudioStylePreset || state.imageStudio?.default_style_preset || 'CINEMATIC_3D_DONGHUA',
        comfyui_client_id: clientId,
      }),
    });
    progressView.complete('生成完成，图片已保存并载入预览');
    showImageStudioResult(result);
    await loadImageStudio(projectId);
    showImageStudioResult(result);
    log(`${label}生成完成：${result.output}`);
  } catch (error) {
    progressView.fail(error.message);
    log(error.message, true);
  } finally {
    progressView.stop();
    try { progressSocket?.close(); } catch (_) {}
    delete button.dataset.generating;
    const characterBlocked = kind === 'character-bible' && state.imageStudio?.character_ready === false;
    button.disabled = characterBlocked;
    button.innerHTML = characterBlocked ? '角色资料待抽取' : original;
  }
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

async function load(preferredProjectId = '') {
  try {
    const [projects, animeProjects, health] = await Promise.all([api('/api/projects'), api('/api/novel-anime/projects'), api('/api/health')]);
    state.projects = projects.projects;
    state.animeProjects = animeProjects.projects;
    state.providers = health.providers;
    state.integrations = health.integrations || [];

    const activeNovelProjectId = resolveActiveNovelProject(preferredProjectId);
    if (activeNovelProjectId) setActiveNovelProject(activeNovelProjectId);

    $('#projectSelect').innerHTML = state.projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');
    renderProviders();
    renderProviderSettings();
    renderProjectTable();
    renderAnimeProjects();

    if (activeNovelProjectId) {
      await loadStudio(activeNovelProjectId);
      await loadPipeline(activeNovelProjectId);
      await loadImageStudio(activeNovelProjectId);
      await loadGraybox(activeNovelProjectId);
    }

    if (state.projects.length) {
      const workspaceProjectId = state.projects.some((project) => project.id === activeNovelProjectId)
        ? activeNovelProjectId
        : state.projects[0].id;
      await loadProject(workspaceProjectId);
    }
    log(`已载入 ${state.projects.length} 个项目和 ${state.providers.length} 条 Provider 路线${activeNovelProjectId ? ` · 当前小说项目 ${activeNovelProjectId}` : ''}`);
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

$('#grayboxEnsureSpecButton').addEventListener('click', ensureGrayboxShotSpec);
$('#grayboxRenderButton').addEventListener('click', renderGrayboxShot);
$('#grayboxRefreshButton').addEventListener('click', () => loadGraybox().catch((error) => log(error.message, true)));
$('#grayboxAdjustButton').addEventListener('click', adjustGrayboxShot);
$('#grayboxApproveButton').addEventListener('click', () => reviewGraybox('APPROVED'));
$('#grayboxRequestChangesButton').addEventListener('click', () => reviewGraybox('CHANGES_REQUESTED'));
$('#grayboxInstallSmokePack').addEventListener('click', installGrayboxSmokePack);
$('#grayboxBindCharacterReference').addEventListener('click', () => bindGrayboxReference('character'));
$('#grayboxBindSceneReference').addEventListener('click', () => bindGrayboxReference('scene'));
$('#grayboxUploadSceneReference').addEventListener('click', uploadGrayboxSceneReference);
$('#grayboxSaveMiniMaxKey').addEventListener('click', saveMiniMaxKey);
$('#grayboxGenerateFinalButton').addEventListener('click', generateGrayboxFinal);
$('#grayboxSaveSmokeReview').addEventListener('click', saveGrayboxSmokeReview);
$('#costFirstRebuild').addEventListener('click', rebuildCostFirstPlan);
$('#costFirstDiagnosticsRefresh').addEventListener('click', () => loadCostFirstDiagnostics({ forceOpen: true }));
$('#gptKeyframePrepare').addEventListener('click', prepareGptKeyframes);
$('#gptCodexBatchStart').addEventListener('click', startCodexKeyframeBatch);
$('#gptCodexBatchStop').addEventListener('click', stopCodexKeyframeBatch);
$('#gptCodexLogsRefresh').addEventListener('click', () => loadCodexBatchLogs({ forceOpen: true }));
$('#gptCodexUsageConfirm').addEventListener('change', renderGptKeyframes);
$('#gptCodexUploadConfirm').addEventListener('change', renderGptKeyframes);
$('#gptKeyframeInterpolate').addEventListener('click', interpolateGptKeyframes);

$('#novelImportRights').addEventListener('change', updateNovelImportRightsUI);
$('#novelImportFile').addEventListener('change', (event) => {
  const file = event.target.files?.[0];
  $('#novelImportFileName').textContent = file?.name || '选择 UTF-8 TXT 文件';
  $('#novelImportFileHint').textContent = file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · 浏览器会先校验 UTF-8，再上传到本地 VideoCreator。` : '最大 20 MB；支持“第一章 / 第1章 / 第一回 / 第一卷”等章节标题自动切分。';
});
$('#novelImportButton').addEventListener('click', importNovelProject);
$('#novelImportOpenStudio').addEventListener('click', openImportedNovelStudio);
updateNovelImportRightsUI();
$('#pipelineProjectSelect').addEventListener('change', (event) => {
  const projectId = setActiveNovelProject(event.target.value);
  if (projectId) loadPipeline(projectId).catch((error) => log(error.message, true));
});
$('#pipelinePreflightButton').addEventListener('click', runPipelinePreflight);
$('#pipelineRunButton').addEventListener('click', runAutoPipeline);
$('#pipelineApproveButton').addEventListener('click', approvePipeline);
$('#imageStudioProject').addEventListener('change', (event) => {
  const projectId = setActiveNovelProject(event.target.value);
  if (projectId) {
    loadImageStudio(projectId).catch((error) => log(error.message, true));
    loadGraybox(projectId).catch((error) => log(error.message, true));
  }
});
$('#imageStudioDeleteProjectButton').addEventListener('click', deleteCurrentImageStudioProject);
$('#imageStudioSaveKey').addEventListener('click', saveImageStudioKey);
$('#imageStudioSaveComfy').addEventListener('click', saveComfyUIEndpoint);
$('#imageStudioInstallComfy').addEventListener('click', installComfyUI);
$('#imageStudioInstallModel').addEventListener('click', installComfyUIModel);
$('#imageStudioInstallLora').addEventListener('click', installComfyUILora);
$('#imageStudioStartComfy').addEventListener('click', startComfyUIService);
$('#imageStudioStopComfy').addEventListener('click', stopComfyUIService);
$('#imageStudioProviderSelect').addEventListener('change', (event) => {
  state.imageStudioProviderPreference = event.target.value;
  renderImageStudio();
});
$('#imageStudioStylePreset').addEventListener('change', (event) => {
  state.imageStudioStylePreset = event.target.value;
  rememberImageStylePreset(state.imageStudioProjectId, state.imageStudioStylePreset);
  renderImageStudio();
  const style = (state.imageStudio?.style_presets || []).find((item) => item.id === state.imageStudioStylePreset);
  log(`AI 生图风格已切换：${style?.label || state.imageStudioStylePreset}${style?.lora_id ? ' · 已启用可选国风 LoRA 路由' : ''}`);
});
$('#generateCharacterBibleButton').addEventListener('click', handleCharacterBibleAction);
$('#imageStudioCharacterRepairButton').addEventListener('click', () => bootstrapImageStudioCharacters({ autoGenerate: false }));
$('#generateKeyframeButton').addEventListener('click', () => generateImageStudio('keyframe'));
$('#imageStudioApproveButton').addEventListener('click', () => reviewImageStudio('APPROVED'));
$('#imageStudioChangesButton').addEventListener('click', () => reviewImageStudio('CHANGES_REQUESTED'));
$('#projectSelect').addEventListener('change', (event) => {
  const projectId = event.target.value;
  if (state.animeProjects.some((item) => item.directory_id === projectId)) setActiveNovelProject(projectId);
  loadProject(projectId).catch((error) => log(error.message, true));
});
$('#billableConfirm').addEventListener('change', updateGenerateButton);
$('#generateButton').addEventListener('click', generate);
$('#storyboardButton').addEventListener('click', generateStoryboard);
$('#refreshButton').addEventListener('click', () => load());
$('#studioRefreshButton').addEventListener('click', () => loadStudio().catch((error) => log(error.message, true)));
$('#snapshotButton').addEventListener('click', createSnapshot);
$('#studioProjectSelect').addEventListener('change', (event) => {
  const projectId = setActiveNovelProject(event.target.value);
  if (projectId) loadStudio(projectId).catch((error) => log(error.message, true));
});
$('#clearLog').addEventListener('click', () => { $('#logList').innerHTML = ''; });
document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => setView(item.dataset.view, item.dataset.workspace || state.currentWorkspace)));
load();
