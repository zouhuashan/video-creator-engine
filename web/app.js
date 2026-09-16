const state = { projects: [], project: null, providers: [], selectedProvider: 'local_ken_burns', selectedImage: null, currentView: 'workspace' };

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

function setView(view) {
  state.currentView = view;
  document.querySelectorAll('.nav-item').forEach((nav) => nav.classList.toggle('active', nav.dataset.view === view));
  ['workspace', 'projects', 'providers'].forEach((name) => $(`#${name}View`).classList.toggle('hidden', name !== view));
  $('#outputPanel').classList.toggle('hidden', view !== 'workspace');
  $('#logPanel')?.classList.toggle('hidden', view !== 'workspace');
  if (view === 'projects') renderProjectTable();
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

function updateGenerateButton() {
  const remote = state.providers.find((provider) => provider.id === state.selectedProvider)?.remote;
  $('#generateButton').disabled = !state.project || !state.selectedImage || (remote && !$('#billableConfirm').checked);
}

async function loadProject(projectId) {
  state.project = await api(`/api/projects/${encodeURIComponent(projectId)}`);
  $('#projectSelect').value = state.project.id;
  renderStats();
  renderAssets();
  $('#projectTitle').textContent = state.project.id === 'jinghua-yuan-local-pilot' ? '《镜花缘》·唐小山试制' : state.project.id;
  $('#projectDescription').textContent = state.project.id === 'jinghua-yuan-local-pilot' ? '角色、场景、连续剧情与动态镜头的本地验证项目。' : 'VideoCreator Engine 项目资产。';
  if ($('#projectTable')) renderProjectTable();
  updateGenerateButton();
}

async function load() {
  try {
    const [projects, health] = await Promise.all([api('/api/projects'), api('/api/health')]);
    state.projects = projects.projects;
    state.providers = health.providers;
    $('#projectSelect').innerHTML = state.projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');
    renderProviders();
    renderProviderSettings();
    renderProjectTable();
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
    $('#outputEmpty').classList.add('hidden');
    $('#outputResult').classList.remove('hidden');
    $('#outputVideo').src = result.media_url;
    $('#resultProvider').textContent = result.provider;
    $('#resultPath').textContent = result.output_path;
    $('#resultDuration').textContent = `${Number(result.duration_seconds).toFixed(1)} 秒 · 可人工审核`;
    $('#outputStatus').textContent = '已完成';
    log(`生成完成：${result.output_path}`);
  } catch (error) { log(error.message, true); $('#outputStatus').textContent = '生成失败'; }
  finally { button.innerHTML = '<span>✦</span>生成镜头'; updateGenerateButton(); }
}

$('#projectSelect').addEventListener('change', (event) => loadProject(event.target.value).catch((error) => log(error.message, true)));
$('#billableConfirm').addEventListener('change', updateGenerateButton);
$('#generateButton').addEventListener('click', generate);
$('#refreshButton').addEventListener('click', () => load());
$('#clearLog').addEventListener('click', () => { $('#logList').innerHTML = ''; });
document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => setView(item.dataset.view)));
load();
