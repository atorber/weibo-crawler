/**
 * Weibo Crawler Web Console - Interactive Logic
 */

// Application State
const state = {
  currentTab: 'dashboard',
  configMode: 'form', // 'form' or 'json'
  currentConfig: null,
  rawConfigText: '',
  status: {},
  users: [],
  dataPage: 1,
  dataPageSize: 10,
  autoScroll: true,
  logFilterLevel: 'ALL',
  logFilterKeyword: ''
};

// DOM Content Loaded Initializer
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initNavigation();
  initModals();
  initControlButtons();
  initConfigCenter();
  initUsersManager();
  initLogStreamer();
  initDataExplorer();
  initApiDocs();

  // Start polling
  fetchStatus();
  setInterval(fetchStatus, 1500);

  // Load initial data
  fetchUsers();
  fetchConfig();
});

// Toast System
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
  toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Theme Switcher
function initTheme() {
  const savedTheme = localStorage.getItem('weibo_console_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);

  document.getElementById('theme-toggle-btn').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('weibo_console_theme', next);
  });
}

// Navigation Tabs & Routing
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const pageViews = document.querySelectorAll('.page-view');
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');

  const titles = {
    dashboard: { title: '总览控制', subtitle: '监控爬虫实时运行状态与全局任务调度' },
    targets: { title: '目标管理', subtitle: '维护微博采集目标用户队列与增量配置' },
    settings: { title: '参数配置', subtitle: '可视化调整所有爬虫参数或编辑 config.json 源码' },
    output: { title: '数据存储', subtitle: '配置结构化文本、数据库与 Webhook 目标介质及开关' },
    logs: { title: '实时日志', subtitle: '实时捕捉爬虫标准输出与错误排查' },
    data: { title: '数据预览', subtitle: '探索本地 SQLite 数据库中采集到的历史数据' },
    api: { title: 'RESTful API 接口中心', subtitle: '标准化 HTTP 接口调用规范、参数说明与系统集成' }
  };

  function resolveTabFromUrl() {
    // 1. Pathname: /targets, /console/targets, /output, /api-docs, etc.
    const pathname = window.location.pathname.replace(/^\/+|\/+$/g, '');
    if (pathname) {
      const parts = pathname.split('/');
      const lastSegment = parts[parts.length - 1];
      if (lastSegment === 'api' || lastSegment === 'api-docs' || lastSegment === 'docs') return 'api';
      if (titles[lastSegment]) return lastSegment;
    }

    // 2. Query param: ?tab=targets
    const urlParams = new URLSearchParams(window.location.search);
    const qTab = urlParams.get('tab');
    if (qTab) {
      if (qTab === 'api' || qTab === 'api-docs' || qTab === 'docs') return 'api';
      if (titles[qTab]) return qTab;
    }

    // 3. Hash: #targets
    const hashTab = window.location.hash.replace('#', '');
    if (hashTab) {
      if (hashTab === 'api' || hashTab === 'api-docs' || hashTab === 'docs') return 'api';
      if (titles[hashTab]) return hashTab;
    }

    return 'dashboard';
  }

  function switchTab(tab, updateHistory = true) {
    if (!titles[tab]) tab = 'dashboard';

    navItems.forEach(n => {
      if (n.getAttribute('data-tab') === tab) {
        n.classList.add('active');
      } else {
        n.classList.remove('active');
      }
    });

    pageViews.forEach(v => v.classList.remove('active'));
    const activeView = document.getElementById(`view-${tab}`);
    if (activeView) activeView.classList.add('active');

    state.currentTab = tab;
    if (titles[tab]) {
      pageTitle.textContent = titles[tab].title;
      pageSubtitle.textContent = titles[tab].subtitle;
      document.title = `${titles[tab].title} - Weibo Crawler Web 控制台`;
    }

    // Update browser URL route
    if (updateHistory) {
      const targetUrl = tab === 'dashboard' ? '/' : (tab === 'api' ? '/api-docs' : `/${tab}`);
      if (window.location.pathname !== targetUrl) {
        window.history.pushState({ tab }, '', targetUrl);
      }
    }

    // Tab specific refresh
    if (tab === 'targets') fetchUsers();
    if (tab === 'settings' || tab === 'output') fetchConfig();
    if (tab === 'logs') fetchLogs();
    if (tab === 'data') fetchData();
    if (tab === 'api') {
      const baseEl = document.getElementById('api-base-url-display');
      if (baseEl) baseEl.textContent = window.location.origin;
    }
  }

  // Bind click handlers to menu items
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const tab = item.getAttribute('data-tab');
      if (tab === state.currentTab) return;
      switchTab(tab, true);
    });
  });

  // Handle browser back/forward buttons
  window.addEventListener('popstate', (e) => {
    const tab = (e.state && e.state.tab) || resolveTabFromUrl();
    switchTab(tab, false);
  });

  // Initial tab resolution on page load
  const initialTab = resolveTabFromUrl();
  switchTab(initialTab, false);
}

// Status & Process Controls
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const json = await res.json();
    if (json.code === 200) {
      updateStatusUI(json.data);
    }
  } catch (err) {
    console.error('Failed to fetch status:', err);
  }
}

function updateStatusUI(data) {
  state.status = data;
  const isRunning = data.is_running;

  // Radar dot & sidebar text
  const radar = document.getElementById('sidebar-radar');
  const sidebarText = document.getElementById('sidebar-status-text');
  if (isRunning) {
    radar.className = 'radar-dot running';
    sidebarText.textContent = '运行中';
  } else if (data.status === 'STOPPED') {
    radar.className = 'radar-dot stopped';
    sidebarText.textContent = '已停止';
  } else {
    radar.className = 'radar-dot';
    sidebarText.textContent = '空闲中';
  }

  // Dashboard banner
  const metaStatus = document.getElementById('meta-status');
  metaStatus.textContent = isRunning ? 'RUNNING 运行中' : `${data.status} ${isRunning ? '' : '(空闲)'}`;
  metaStatus.style.color = isRunning ? 'var(--accent-emerald)' : (data.status === 'FAILED' ? 'var(--accent-rose)' : 'var(--text-muted)');

  document.getElementById('meta-pid').textContent = data.pid || '-';
  document.getElementById('meta-start-time').textContent = data.start_time || '-';
  document.getElementById('meta-current-user').textContent = data.current_user || (isRunning ? '初始化中...' : '-');

  // Metrics
  if (data.metrics) {
    document.getElementById('stat-user-count').textContent = data.metrics.user_count || 0;
    document.getElementById('stat-weibo-count').textContent = data.metrics.total_weibos || 0;
    document.getElementById('stat-log-count').textContent = data.metrics.log_entries_count || 0;
  }

  // Duration
  const durSec = data.duration || 0;
  const m = Math.floor(durSec / 60);
  const s = durSec % 60;
  document.getElementById('stat-duration').textContent = `${m > 0 ? m + 'm ' : ''}${s}s`;
  document.getElementById('stat-duration-sub').textContent = isRunning ? '任务持续执行中' : (data.start_time ? '最近一次耗时' : '未启动');

  // Button disabled states
  document.getElementById('btn-quick-start').disabled = isRunning;
  document.getElementById('btn-main-start').disabled = isRunning;
  document.getElementById('btn-quick-stop').disabled = !isRunning;
  document.getElementById('btn-main-stop').disabled = !isRunning;

  // If on logs tab, fetch logs regularly
  if (state.currentTab === 'logs') {
    fetchLogs();
  }
}

function initControlButtons() {
  const handleStart = async (uidList = null) => {
    try {
      const body = uidList ? { user_id_list: uidList } : {};
      const res = await fetch('/api/service/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
      } else {
        showToast(data.message, 'error');
      }
      fetchStatus();
    } catch (e) {
      showToast('启动请求失败: ' + e, 'error');
    }
  };

  const handleStop = async () => {
    try {
      const res = await fetch('/api/service/stop', { method: 'POST' });
      const data = await res.json();
      showToast(data.message, data.success ? 'info' : 'error');
      fetchStatus();
    } catch (e) {
      showToast('停止请求失败: ' + e, 'error');
    }
  };

  const handleRestart = async () => {
    try {
      const res = await fetch('/api/service/restart', { method: 'POST' });
      const data = await res.json();
      showToast(data.message, data.success ? 'success' : 'error');
      fetchStatus();
    } catch (e) {
      showToast('重启请求失败: ' + e, 'error');
    }
  };

  document.getElementById('btn-quick-start').addEventListener('click', () => handleStart());
  document.getElementById('btn-main-start').addEventListener('click', () => handleStart());
  document.getElementById('btn-quick-stop').addEventListener('click', handleStop);
  document.getElementById('btn-main-stop').addEventListener('click', handleStop);
  document.getElementById('btn-quick-restart').addEventListener('click', () => handleRestart());
  document.getElementById('btn-main-restart').addEventListener('click', () => handleRestart());

  // Dashboard Cookie Test & Update
  document.getElementById('btn-test-cookie-dash').addEventListener('click', runCookieCheck);

  const quickImportBtn = document.getElementById('btn-quick-import-browser');
  if (quickImportBtn) {
    quickImportBtn.addEventListener('click', () => {
      openModal('modal-update-cookie');
      const modalBrowser = document.getElementById('select-modal-browser');
      if (modalBrowser) modalBrowser.value = 'auto';
      importCookieFromBrowser({
        browserSelectId: 'select-modal-browser',
        statusDivId: 'modal-browser-import-status',
        targetInputId: 'quick-cookie-input'
      });
    });
  }

  const openCookieBtn = document.getElementById('btn-open-cookie-modal');
  if (openCookieBtn) {
    openCookieBtn.addEventListener('click', () => {
      const currentCookie = (state.currentConfig && state.currentConfig.cookie) || document.getElementById('cfg-cookie')?.value || '';
      document.getElementById('quick-cookie-input').value = currentCookie;
      openModal('modal-update-cookie');
    });
  }

  const modalImportBtn = document.getElementById('btn-modal-import-browser');
  if (modalImportBtn) {
    modalImportBtn.addEventListener('click', () => {
      importCookieFromBrowser({
        browserSelectId: 'select-modal-browser',
        statusDivId: 'modal-browser-import-status',
        targetInputId: 'quick-cookie-input'
      });
    });
  }

  const confirmCookieBtn = document.getElementById('btn-confirm-update-cookie');
  if (confirmCookieBtn) {
    confirmCookieBtn.addEventListener('click', async () => {
      const newCookie = document.getElementById('quick-cookie-input').value.trim();
      if (!newCookie) {
        showToast('请输入有效的 Cookie 字符串', 'error');
        return;
      }

      confirmCookieBtn.disabled = true;
      confirmCookieBtn.textContent = '保存中...';

      try {
        // 1. 获取现有配置副本或从表单收集
        const current = state.currentConfig ? { ...state.currentConfig } : collectConfigForm();
        current.cookie = newCookie;

        // 2. 发送更新配置请求
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parsed: current })
        });
        const json = await res.json();

        if (json.code === 200) {
          showToast('Cookie 保存成功，正在进行连通性检测...', 'success');
          closeModal('modal-update-cookie');

          // 同步参数配置页面的 Cookie 输入框
          const cfgCookieInput = document.getElementById('cfg-cookie');
          if (cfgCookieInput) cfgCookieInput.value = newCookie;

          // 重新拉取配置
          await fetchConfig();

          // 3. 自动触发即刻测试
          await runCookieCheck();
        } else {
          showToast(json.message || 'Cookie 保存失败', 'error');
        }
      } catch (e) {
        showToast('更新 Cookie 异常: ' + e, 'error');
      } finally {
        confirmCookieBtn.disabled = false;
        confirmCookieBtn.textContent = '保存并测试';
      }
    });
  }
}

async function importCookieFromBrowser({ browserSelectId, statusDivId, targetInputId, onFinish } = {}) {
  const browserSelect = document.getElementById(browserSelectId);
  const statusDiv = document.getElementById(statusDivId);
  const targetInput = document.getElementById(targetInputId);
  const browser = browserSelect ? browserSelect.value : 'auto';

  if (statusDiv) {
    statusDiv.style.display = 'block';
    statusDiv.style.background = 'rgba(59, 130, 246, 0.1)';
    statusDiv.style.color = '#93c5fd';
    statusDiv.innerHTML = '⏳ 正在尝试读取本地浏览器 Cookie 并进行连通性验证，请稍候...';
  }

  try {
    const res = await fetch('/api/cookie/import_browser', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ browser })
    });
    const json = await res.json();

    if (json.code === 200 && json.success) {
      if (targetInput) {
        targetInput.value = json.cookie;
      }
      if (statusDiv) {
        statusDiv.style.background = 'rgba(16, 185, 129, 0.12)';
        statusDiv.style.color = '#10b981';
        let accountTxt = json.user && json.user.screen_name ? ` (登录账号: ${json.user.screen_name})` : '';
        statusDiv.innerHTML = `✅ ${json.message}${accountTxt}`;
      }
      showToast(`已成功从 ${json.browser} 提取 Cookie！`, 'success');
      if (typeof onFinish === 'function') onFinish(json);
    } else {
      if (statusDiv) {
        statusDiv.style.background = 'rgba(244, 63, 94, 0.12)';
        statusDiv.style.color = '#f43f5e';
        statusDiv.innerHTML = `❌ ${json.message || '提取失败'}`;
      }
      showToast(json.message || '提取失败', 'error');
    }
  } catch (err) {
    if (statusDiv) {
      statusDiv.style.background = 'rgba(244, 63, 94, 0.12)';
      statusDiv.style.color = '#f43f5e';
      statusDiv.innerHTML = `❌ 提取异常: ${err}`;
    }
    showToast('提取异常: ' + err, 'error');
  }
}

async function runCookieCheck() {
  const banner = document.getElementById('cookie-status-banner');
  banner.innerHTML = '正在与微博官方服务器通信验证 Cookie，请稍候...';
  try {
    const res = await fetch('/api/cookie/check', { method: 'POST' });
    const json = await res.json();
    if (json.valid) {
      banner.innerHTML = `<span style="color: var(--accent-emerald); font-weight: 600;">✅ ${json.message}</span>`;
      showToast('Cookie 连通性验证成功', 'success');
    } else {
      banner.innerHTML = `<span style="color: var(--accent-rose); font-weight: 600;">⚠️ ${json.message}</span>`;
      showToast(json.message, 'error');
    }
  } catch (err) {
    banner.innerHTML = `<span style="color: var(--accent-rose);">❌ 测试连接出错: ${err}</span>`;
  }
}

// User Targets Management
async function fetchUsers() {
  try {
    const res = await fetch('/api/users');
    const json = await res.json();
    if (json.code === 200) {
      state.users = json.data;
      renderUsersTable(state.users);
      populateUserFilterDropdown();
    }
  } catch (e) {
    console.error('Failed to fetch users:', e);
  }
}

function renderUsersTable(users) {
  const tbody = document.getElementById('users-tbody');
  if (!users || users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 40px;">暂无目标用户，点击右上角添加或批量导入</td></tr>';
    return;
  }

  tbody.innerHTML = users.map(u => {
    const nameLetter = u.screen_name ? u.screen_name.charAt(0) : 'U';
    return `
      <tr>
        <td>
          <div class="user-badge">
            <div class="user-avatar-circle">${escapeHtml(nameLetter)}</div>
            <span>${escapeHtml(u.id)}</span>
          </div>
        </td>
        <td><strong>${escapeHtml(u.screen_name || '未备注')}</strong></td>
        <td><code>${escapeHtml(u.since_date || '使用全局设置')}</code></td>
        <td>${escapeHtml(u.query || '全部')}</td>
        <td style="text-align: right;">
          <div class="table-actions" style="justify-content: flex-end;">
            <a href="https://m.weibo.cn/u/${u.id}" target="_blank" class="btn btn-secondary btn-sm" title="打开主页">🔗</a>
            <button class="btn btn-outline-primary btn-sm btn-run-single" data-uid="${u.id}" title="仅爬取此用户">▶ 爬取</button>
            <button class="btn btn-secondary btn-sm btn-delete-user" data-uid="${u.id}" title="删除用户">🗑️</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  // Bind single run
  tbody.querySelectorAll('.btn-run-single').forEach(btn => {
    btn.addEventListener('click', () => {
      const uid = btn.getAttribute('data-uid');
      if (confirm(`确认立即针对博主 UID [${uid}] 启动爬取任务吗？`)) {
        startSingleUserCrawl(uid);
      }
    });
  });

  // Bind delete
  tbody.querySelectorAll('.btn-delete-user').forEach(btn => {
    btn.addEventListener('click', async () => {
      const uid = btn.getAttribute('data-uid');
      if (confirm(`确定要从爬取队列中移除博主 UID: ${uid} 吗？`)) {
        await deleteUser(uid);
      }
    });
  });
}

async function startSingleUserCrawl(uid) {
  try {
    const res = await fetch('/api/service/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id_list: [uid] })
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    fetchStatus();
  } catch (err) {
    showToast('启动单用户任务失败: ' + err, 'error');
  }
}

async function deleteUser(uid) {
  try {
    const res = await fetch(`/api/users/${uid}`, { method: 'DELETE' });
    const json = await res.json();
    if (json.code === 200) {
      showToast(json.message, 'success');
      fetchUsers();
    } else {
      showToast(json.message, 'error');
    }
  } catch (e) {
    showToast('删除失败: ' + e, 'error');
  }
}

function initUsersManager() {
  // Search filter
  document.getElementById('search-users-input').addEventListener('input', (e) => {
    const kw = e.target.value.trim().toLowerCase();
    if (!kw) {
      renderUsersTable(state.users);
      return;
    }
    const filtered = state.users.filter(u =>
      (u.id && u.id.includes(kw)) ||
      (u.screen_name && u.screen_name.toLowerCase().includes(kw))
    );
    renderUsersTable(filtered);
  });

  // Confirm Add User
  document.getElementById('btn-confirm-add-user').addEventListener('click', async () => {
    const uid = document.getElementById('modal-uid').value.trim();
    if (!uid || !/^\d+$/.test(uid)) {
      showToast('请输入合法的微博纯数字 ID', 'error');
      return;
    }
    const screenName = document.getElementById('modal-screen-name').value.trim();
    const sinceDate = document.getElementById('modal-since-date').value.trim();
    const query = document.getElementById('modal-query').value.trim();

    try {
      const res = await fetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: uid,
          screen_name: screenName,
          since_date: sinceDate,
          query: query
        })
      });
      const json = await res.json();
      if (json.code === 200) {
        showToast(json.message, 'success');
        closeModal('modal-add-user');
        // Clear inputs
        document.getElementById('modal-uid').value = '';
        document.getElementById('modal-screen-name').value = '';
        fetchUsers();
      } else {
        showToast(json.message, 'error');
      }
    } catch (e) {
      showToast('添加失败: ' + e, 'error');
    }
  });

  // Confirm Batch Import
  document.getElementById('btn-confirm-import').addEventListener('click', async () => {
    const text = document.getElementById('import-text-area').value.trim();
    if (!text) {
      showToast('请输入导入文本', 'error');
      return;
    }
    try {
      const res = await fetch('/api/users/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, mode: 'append' })
      });
      const json = await res.json();
      if (json.code === 200) {
        showToast(json.message, 'success');
        closeModal('modal-import-users');
        document.getElementById('import-text-area').value = '';
        fetchUsers();
      } else {
        showToast(json.message, 'error');
      }
    } catch (e) {
      showToast('导入失败: ' + e, 'error');
    }
  });
}

// Config Center
async function fetchConfig() {
  try {
    const res = await fetch('/api/config');
    const json = await res.json();
    if (json.code === 200) {
      state.currentConfig = json.parsed;
      state.rawConfigText = json.raw;
      populateConfigForm(json.parsed);
      document.getElementById('raw-json-editor').value = json.raw;
    }
  } catch (err) {
    console.error('Failed to fetch config:', err);
  }
}

function getModeDisplayName(mode) {
  const map = {
    csv: 'CSV 表格',
    json: 'JSON 数据',
    sqlite: 'SQLite 数据库',
    mysql: 'MySQL 关系数据库',
    mongo: 'MongoDB 文档数据库',
    post: 'HTTP POST Webhook',
    markdown: 'Markdown 归档'
  };
  return map[mode] || mode;
}

function updateFormatCardVisual(mode, isEnabled) {
  const card = document.getElementById('card-cfg-' + mode);
  const badge = document.getElementById('badge-status-' + mode);
  if (card) {
    if (isEnabled) {
      card.classList.add('is-enabled');
      card.classList.remove('is-disabled');
    } else {
      card.classList.add('is-disabled');
      card.classList.remove('is-enabled');
    }
  }
  if (badge) {
    if (isEnabled) {
      badge.className = 'badge-tag badge-tag-enabled';
      badge.textContent = '● 已开启';
    } else {
      badge.className = 'badge-tag badge-tag-disabled';
      badge.textContent = '○ 未开启';
    }
  }
}

function validateFormatConfig(mode) {
  if (mode === 'mysql') {
    const host = document.getElementById('cfg-mysql-host')?.value.trim();
    const port = document.getElementById('cfg-mysql-port')?.value.trim();
    const user = document.getElementById('cfg-mysql-user')?.value.trim();
    const password = document.getElementById('cfg-mysql-password')?.value;

    if (!host) {
      return { valid: false, message: '无法开启 MySQL：主机地址 (host) 不能为空', focusId: 'cfg-mysql-host' };
    }
    if (!port || isNaN(parseInt(port, 10)) || parseInt(port, 10) <= 0) {
      return { valid: false, message: '无法开启 MySQL：端口号 (port) 必须为有效数字（如 3306）', focusId: 'cfg-mysql-port' };
    }
    if (!user) {
      return { valid: false, message: '无法开启 MySQL：用户名 (user) 不能为空', focusId: 'cfg-mysql-user' };
    }
    if (!password) {
      return { valid: false, message: '无法开启 MySQL：数据库密码 (password) 不能为空，请先填写密码', focusId: 'cfg-mysql-password' };
    }
    return { valid: true };
  }

  if (mode === 'mongo') {
    const uri = document.getElementById('cfg-mongo-uri')?.value.trim();
    if (!uri) {
      return { valid: false, message: '无法开启 MongoDB：连接 URI (mongodb_URI) 不能为空', focusId: 'cfg-mongo-uri' };
    }
    if (!uri.startsWith('mongodb://') && !uri.startsWith('mongodb+srv://')) {
      return { valid: false, message: '无法开启 MongoDB：URI 格式不正确，必须以 mongodb:// 或 mongodb+srv:// 开头', focusId: 'cfg-mongo-uri' };
    }
    return { valid: true };
  }

  if (mode === 'sqlite') {
    const path = document.getElementById('cfg-sqlite-path')?.value.trim();
    if (!path) {
      return { valid: false, message: '无法开启 SQLite：数据库文件路径 (sqlite_db_path) 不能为空', focusId: 'cfg-sqlite-path' };
    }
    return { valid: true };
  }

  if (mode === 'post') {
    const url = document.getElementById('cfg-post-url')?.value.trim();
    if (!url) {
      return { valid: false, message: '无法开启 HTTP POST：Webhook 接口 URL 不能为空', focusId: 'cfg-post-url' };
    }
    if (!/^https?:\/\//i.test(url)) {
      return { valid: false, message: '无法开启 HTTP POST：接口 URL 必须以 http:// 或 https:// 开头', focusId: 'cfg-post-url' };
    }
    return { valid: true };
  }

  return { valid: true };
}

function updateWriteModeCardsVisibility() {
  const modes = ['csv', 'json', 'sqlite', 'mysql', 'mongo', 'post', 'markdown'];
  modes.forEach(mode => {
    const sw = document.getElementById('switch-mode-' + mode);
    if (sw) {
      updateFormatCardVisual(mode, sw.checked);
    }
  });
}

function populateConfigForm(cfg) {
  if (!cfg) return;

  // 1. Basic
  document.getElementById('cfg-only-original').checked = (cfg.only_crawl_original === 1);
  document.getElementById('cfg-remove-html').checked = (cfg.remove_html_tag === 1);
  const uidListVal = Array.isArray(cfg.user_id_list) ? cfg.user_id_list.join(', ') : (cfg.user_id_list || 'user_id_list.txt');
  document.getElementById('cfg-user-id-list').value = uidListVal;
  document.getElementById('cfg-output-dir').value = cfg.output_directory || 'weibo_data';
  document.getElementById('cfg-since-date').value = cfg.since_date || '';
  document.getElementById('cfg-end-date').value = cfg.end_date || '';
  document.getElementById('cfg-start-page').value = cfg.start_page || 1;
  document.getElementById('cfg-page-count').value = cfg.page_weibo_count || 20;

  // 2. Cookie
  document.getElementById('cfg-cookie').value = cfg.cookie || '';

  // 3. Media
  document.getElementById('cfg-orig-pic').checked = (cfg.original_pic_download === 1);
  document.getElementById('cfg-retweet-pic').checked = (cfg.retweet_pic_download === 1);
  document.getElementById('cfg-orig-video').checked = (cfg.original_video_download === 1);
  document.getElementById('cfg-retweet-video').checked = (cfg.retweet_video_download === 1);
  document.getElementById('cfg-orig-livephoto').checked = (cfg.original_live_photo_download === 1);
  document.getElementById('cfg-retweet-livephoto').checked = (cfg.retweet_live_photo_download === 1);
  document.getElementById('cfg-comment-pic').checked = (cfg.comment_pic_download === 1);
  document.getElementById('cfg-write-exif').checked = (cfg.write_time_in_exif === 1);
  document.getElementById('cfg-change-file-time').checked = (cfg.change_file_time !== 0);

  // Folder name mapping (download_folder_name)
  const df = cfg.download_folder_name || {};
  document.getElementById('cfg-df-orig-img').value = df.original_image_folder || 'img';
  document.getElementById('cfg-df-retweet-img').value = df.retweet_image_folder || 'img';
  document.getElementById('cfg-df-orig-video').value = df.original_video_folder || 'video';
  document.getElementById('cfg-df-retweet-video').value = df.retweet_video_folder || 'video';
  document.getElementById('cfg-df-orig-livephoto').value = df.original_live_photo_folder || 'live_photo';
  document.getElementById('cfg-df-retweet-livephoto').value = df.retweet_live_photo_folder || 'live_photo';

  // 4. Write mode & outputs
  const writeModes = Array.isArray(cfg.write_mode) ? cfg.write_mode : [];
  ['csv', 'json', 'sqlite', 'mysql', 'mongo', 'post', 'markdown'].forEach(mode => {
    const sw = document.getElementById('switch-mode-' + mode);
    if (sw) {
      sw.checked = writeModes.includes(mode);
      updateFormatCardVisual(mode, sw.checked);
    }
  });
  document.getElementById('cfg-uid-folder').checked = (cfg.user_id_as_folder_name === 1);

  // Database & Output sub-configs
  // MySQL
  const mysql = cfg.mysql_config || {};
  document.getElementById('cfg-mysql-host').value = mysql.host || 'localhost';
  document.getElementById('cfg-mysql-port').value = mysql.port || 3306;
  document.getElementById('cfg-mysql-user').value = mysql.user || 'root';
  document.getElementById('cfg-mysql-password').value = mysql.password || '';
  document.getElementById('cfg-mysql-charset').value = mysql.charset || 'utf8mb4';

  // Mongo
  document.getElementById('cfg-mongo-uri').value = cfg.mongodb_URI || '';

  // SQLite
  document.getElementById('cfg-sqlite-path').value = cfg.sqlite_db_path || 'weibodata.db';
  document.getElementById('cfg-sqlite-binary').checked = (cfg.store_binary_in_sqlite === 1);

  // POST
  const post = cfg.post_config || {};
  document.getElementById('cfg-post-url').value = post.api_url || '';
  document.getElementById('cfg-post-token').value = post.api_token || '';

  // Markdown
  if (cfg.markdown_split_by) document.getElementById('cfg-md-split').value = cfg.markdown_split_by;
  if (cfg.markdown_sort_order) document.getElementById('cfg-md-order').value = cfg.markdown_sort_order;
  if (cfg.markdown_image_order) document.getElementById('cfg-md-img-order').value = cfg.markdown_image_order;
  document.getElementById('cfg-missing-report').checked = (cfg.missing_weibo_report === 1);

  // Markdown preview syntax
  const mdp = cfg.markdown_preview || {};
  document.getElementById('cfg-mdp-orig-img').checked = (mdp.original_image_preview !== 0);
  document.getElementById('cfg-mdp-retweet-img').checked = (mdp.retweet_image_preview !== 0);
  document.getElementById('cfg-mdp-inline-img').checked = (mdp.inline_image_preview !== 0);
  document.getElementById('cfg-mdp-link').checked = (mdp.link_preview === 1);
  document.getElementById('cfg-mdp-orig-video').checked = (mdp.original_video_preview === 1);
  document.getElementById('cfg-mdp-retweet-video').checked = (mdp.retweet_video_preview === 1);
  document.getElementById('cfg-mdp-orig-livephoto').checked = (mdp.original_live_photo_preview === 1);
  document.getElementById('cfg-mdp-retweet-livephoto').checked = (mdp.retweet_live_photo_preview === 1);

  // Markdown relative link directory
  const mfd = cfg.markdown_file_dir || {};
  document.getElementById('cfg-mfd-orig-img').value = mfd.original_image_dir || 'img';
  document.getElementById('cfg-mfd-retweet-img').value = mfd.retweet_image_dir || 'img';
  document.getElementById('cfg-mfd-orig-video').value = mfd.original_video_dir || 'video';
  document.getElementById('cfg-mfd-retweet-video').value = mfd.retweet_video_dir || 'video';
  document.getElementById('cfg-mfd-orig-livephoto').value = mfd.original_live_photo_dir || 'live_photo';
  document.getElementById('cfg-mfd-retweet-livephoto').value = mfd.retweet_live_photo_dir || 'live_photo';

  // 5. Advanced & Interactions
  document.getElementById('cfg-download-comment').checked = (cfg.download_comment === 1);
  document.getElementById('cfg-comment-count').value = cfg.comment_max_download_count || 100;
  document.getElementById('cfg-download-repost').checked = (cfg.download_repost === 1);
  document.getElementById('cfg-repost-count').value = cfg.repost_max_download_count || 100;

  // 6. Anti-Ban Protection
  const ab = cfg.anti_ban_config || {};
  document.getElementById('cfg-ab-enabled').checked = (ab.enabled !== false);
  document.getElementById('cfg-ab-max-weibo').value = ab.max_weibo_per_session !== undefined ? ab.max_weibo_per_session : 500;
  document.getElementById('cfg-ab-batch-size').value = ab.batch_size !== undefined ? ab.batch_size : 50;
  document.getElementById('cfg-ab-batch-delay').value = ab.batch_delay !== undefined ? ab.batch_delay : 30;
  document.getElementById('cfg-ab-delay-min').value = ab.request_delay_min !== undefined ? ab.request_delay_min : 8;
  document.getElementById('cfg-ab-delay-max').value = ab.request_delay_max !== undefined ? ab.request_delay_max : 15;
  document.getElementById('cfg-ab-max-time').value = ab.max_session_time !== undefined ? ab.max_session_time : 600;
  document.getElementById('cfg-ab-max-errors').value = ab.max_api_errors !== undefined ? ab.max_api_errors : 5;
  document.getElementById('cfg-ab-rest-time').value = ab.rest_time_min !== undefined ? ab.rest_time_min : 180;
  document.getElementById('cfg-ab-rest-prob').value = ab.random_rest_probability !== undefined ? ab.random_rest_probability : 0.01;

  // Update card visibility
  updateWriteModeCardsVisibility();
}

function collectConfigForm() {
  const cfg = state.currentConfig ? { ...state.currentConfig } : {};

  // 1. Basic
  cfg.only_crawl_original = document.getElementById('cfg-only-original').checked ? 1 : 0;
  cfg.remove_html_tag = document.getElementById('cfg-remove-html').checked ? 1 : 0;
  const uidRaw = document.getElementById('cfg-user-id-list').value.trim();
  if (uidRaw.includes(',') || uidRaw.includes('\n')) {
    cfg.user_id_list = uidRaw.split(/[\s,]+/).filter(Boolean);
  } else {
    cfg.user_id_list = uidRaw || 'user_id_list.txt';
  }
  cfg.output_directory = document.getElementById('cfg-output-dir').value.trim() || 'weibo_data';

  const sinceVal = document.getElementById('cfg-since-date').value.trim();
  cfg.since_date = /^\d+$/.test(sinceVal) ? parseInt(sinceVal, 10) : sinceVal;

  cfg.end_date = document.getElementById('cfg-end-date').value.trim();
  cfg.start_page = parseInt(document.getElementById('cfg-start-page').value, 10) || 1;
  cfg.page_weibo_count = parseInt(document.getElementById('cfg-page-count').value, 10) || 20;

  // 2. Cookie
  cfg.cookie = document.getElementById('cfg-cookie').value.trim();

  // 3. Media
  cfg.original_pic_download = document.getElementById('cfg-orig-pic').checked ? 1 : 0;
  cfg.retweet_pic_download = document.getElementById('cfg-retweet-pic').checked ? 1 : 0;
  cfg.original_video_download = document.getElementById('cfg-orig-video').checked ? 1 : 0;
  cfg.retweet_video_download = document.getElementById('cfg-retweet-video').checked ? 1 : 0;
  cfg.original_live_photo_download = document.getElementById('cfg-orig-livephoto').checked ? 1 : 0;
  cfg.retweet_live_photo_download = document.getElementById('cfg-retweet-livephoto').checked ? 1 : 0;
  cfg.comment_pic_download = document.getElementById('cfg-comment-pic').checked ? 1 : 0;
  cfg.write_time_in_exif = document.getElementById('cfg-write-exif').checked ? 1 : 0;
  cfg.change_file_time = document.getElementById('cfg-change-file-time').checked ? 1 : 0;

  cfg.download_folder_name = {
    original_image_folder: document.getElementById('cfg-df-orig-img').value.trim() || 'img',
    retweet_image_folder: document.getElementById('cfg-df-retweet-img').value.trim() || 'img',
    original_video_folder: document.getElementById('cfg-df-orig-video').value.trim() || 'video',
    retweet_video_folder: document.getElementById('cfg-df-retweet-video').value.trim() || 'video',
    original_live_photo_folder: document.getElementById('cfg-df-orig-livephoto').value.trim() || 'live_photo',
    retweet_live_photo_folder: document.getElementById('cfg-df-retweet-livephoto').value.trim() || 'live_photo'
  };

  // 4. Write mode & Outputs
  const modes = [];
  ['csv', 'json', 'sqlite', 'mysql', 'mongo', 'post', 'markdown'].forEach(mode => {
    const sw = document.getElementById('switch-mode-' + mode);
    if (sw && sw.checked) {
      modes.push(mode);
    }
  });
  cfg.write_mode = modes;
  cfg.user_id_as_folder_name = document.getElementById('cfg-uid-folder').checked ? 1 : 0;

  // MySQL
  cfg.mysql_config = {
    host: document.getElementById('cfg-mysql-host').value.trim() || 'localhost',
    port: parseInt(document.getElementById('cfg-mysql-port').value, 10) || 3306,
    user: document.getElementById('cfg-mysql-user').value.trim() || 'root',
    password: document.getElementById('cfg-mysql-password').value,
    charset: document.getElementById('cfg-mysql-charset').value.trim() || 'utf8mb4'
  };

  // Mongo
  cfg.mongodb_URI = document.getElementById('cfg-mongo-uri').value.trim();

  // SQLite
  cfg.sqlite_db_path = document.getElementById('cfg-sqlite-path').value.trim() || 'weibodata.db';
  cfg.store_binary_in_sqlite = document.getElementById('cfg-sqlite-binary').checked ? 1 : 0;

  // POST
  cfg.post_config = {
    api_url: document.getElementById('cfg-post-url').value.trim(),
    api_token: document.getElementById('cfg-post-token').value.trim()
  };

  // Markdown
  cfg.markdown_split_by = document.getElementById('cfg-md-split').value;
  cfg.markdown_sort_order = document.getElementById('cfg-md-order').value;
  cfg.markdown_image_order = document.getElementById('cfg-md-img-order').value;
  cfg.missing_weibo_report = document.getElementById('cfg-missing-report').checked ? 1 : 0;

  cfg.markdown_preview = {
    link_preview: document.getElementById('cfg-mdp-link').checked ? 1 : 0,
    original_video_preview: document.getElementById('cfg-mdp-orig-video').checked ? 1 : 0,
    retweet_video_preview: document.getElementById('cfg-mdp-retweet-video').checked ? 1 : 0,
    original_image_preview: document.getElementById('cfg-mdp-orig-img').checked ? 1 : 0,
    retweet_image_preview: document.getElementById('cfg-mdp-retweet-img').checked ? 1 : 0,
    original_live_photo_preview: document.getElementById('cfg-mdp-orig-livephoto').checked ? 1 : 0,
    retweet_live_photo_preview: document.getElementById('cfg-mdp-retweet-livephoto').checked ? 1 : 0,
    inline_image_preview: document.getElementById('cfg-mdp-inline-img').checked ? 1 : 0
  };

  cfg.markdown_file_dir = {
    original_image_dir: document.getElementById('cfg-mfd-orig-img').value.trim() || 'img',
    retweet_image_dir: document.getElementById('cfg-mfd-retweet-img').value.trim() || 'img',
    original_video_dir: document.getElementById('cfg-mfd-orig-video').value.trim() || 'video',
    retweet_video_dir: document.getElementById('cfg-mfd-retweet-video').value.trim() || 'video',
    original_live_photo_dir: document.getElementById('cfg-mfd-orig-livephoto').value.trim() || 'live_photo',
    retweet_live_photo_dir: document.getElementById('cfg-mfd-retweet-livephoto').value.trim() || 'live_photo'
  };

  // 5. Advanced & Interactions
  cfg.download_comment = document.getElementById('cfg-download-comment').checked ? 1 : 0;
  cfg.comment_max_download_count = parseInt(document.getElementById('cfg-comment-count').value, 10) || 100;
  cfg.download_repost = document.getElementById('cfg-download-repost').checked ? 1 : 0;
  cfg.repost_max_download_count = parseInt(document.getElementById('cfg-repost-count').value, 10) || 100;

  // 6. Anti-Ban Protection
  const prevAb = (state.currentConfig && state.currentConfig.anti_ban_config) || {};
  cfg.anti_ban_config = {
    ...prevAb,
    enabled: document.getElementById('cfg-ab-enabled').checked,
    max_weibo_per_session: parseInt(document.getElementById('cfg-ab-max-weibo').value, 10) || 500,
    batch_size: parseInt(document.getElementById('cfg-ab-batch-size').value, 10) || 50,
    batch_delay: parseInt(document.getElementById('cfg-ab-batch-delay').value, 10) || 30,
    request_delay_min: parseInt(document.getElementById('cfg-ab-delay-min').value, 10) || 8,
    request_delay_max: parseInt(document.getElementById('cfg-ab-delay-max').value, 10) || 15,
    max_session_time: parseInt(document.getElementById('cfg-ab-max-time').value, 10) || 600,
    max_api_errors: parseInt(document.getElementById('cfg-ab-max-errors').value, 10) || 5,
    rest_time_min: parseInt(document.getElementById('cfg-ab-rest-time').value, 10) || 180,
    random_rest_probability: parseFloat(document.getElementById('cfg-ab-rest-prob').value) || 0.01
  };

  return cfg;
}

function initConfigCenter() {
  // Subtabs
  const subnavBtns = document.querySelectorAll('.settings-tab-btn');
  const subnavSections = document.querySelectorAll('.settings-group-section');

  subnavBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      subnavBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const targetId = btn.getAttribute('data-subtab');
      subnavSections.forEach(sec => sec.classList.remove('active'));
      const activeSec = document.getElementById(targetId);
      if (activeSec) activeSec.classList.add('active');
    });
  });

  // Switch between Visual Form and Raw JSON
  const toggleBtn = document.getElementById('btn-toggle-config-mode');
  const formBox = document.getElementById('config-form-container');
  const jsonBox = document.getElementById('config-json-editor-container');

  toggleBtn.addEventListener('click', () => {
    if (state.configMode === 'form') {
      // Sync form into json
      const current = collectConfigForm();
      document.getElementById('raw-json-editor').value = JSON.stringify(current, null, 4);
      formBox.style.display = 'none';
      jsonBox.style.display = 'block';
      toggleBtn.textContent = '📋 切换为可视化表单';
      state.configMode = 'json';
    } else {
      // Parse json into form
      try {
        const val = document.getElementById('raw-json-editor').value;
        const parsed = JSON.parse(val);
        state.currentConfig = parsed;
        populateConfigForm(parsed);
      } catch (e) {
        showToast('JSON 格式有误，无法同步到表单视图，请先修正', 'error');
        return;
      }
      formBox.style.display = 'flex';
      jsonBox.style.display = 'none';
      toggleBtn.textContent = '📝 切换为 JSON 源码视图';
      state.configMode = 'form';
    }
  });

  // Save config
  async function handleSaveConfig() {
    let payload = {};
    if (state.configMode === 'form' || state.currentTab === 'output') {
      const collected = collectConfigForm();
      // 校验所有已开启的输出格式配置项是否完整
      for (const mode of collected.write_mode) {
        const check = validateFormatConfig(mode);
        if (!check.valid) {
          showToast(`保存受阻：已开启的 ${getModeDisplayName(mode)} 配置未完善（${check.message}）`, 'error');
          if (check.focusId) {
            const input = document.getElementById(check.focusId);
            if (input) {
              input.focus();
              input.classList.add('input-error-pulse');
              setTimeout(() => input.classList.remove('input-error-pulse'), 1500);
            }
          }
          return;
        }
      }
      payload.parsed = collected;
    } else {
      payload.raw = document.getElementById('raw-json-editor').value;
    }

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if (json.code === 200) {
        showToast(json.message, 'success');
        fetchConfig();
      } else {
        showToast(json.message, 'error');
      }
    } catch (e) {
      showToast('保存配置出错: ' + e, 'error');
    }
  }

  ['btn-save-config', 'btn-save-output-config', 'btn-save-output-config-bottom'].forEach(btnId => {
    const btn = document.getElementById(btnId);
    if (btn) btn.addEventListener('click', handleSaveConfig);
  });

  // Listen to format toggle switches and validate before enabling
  document.querySelectorAll('.cfg-mode-switch').forEach(sw => {
    sw.addEventListener('change', () => {
      const mode = sw.getAttribute('data-mode');
      if (sw.checked) {
        const check = validateFormatConfig(mode);
        if (!check.valid) {
          // 校验不通过：阻止开启并提示具体缺失项
          sw.checked = false;
          updateFormatCardVisual(mode, false);
          showToast(check.message, 'error');
          if (check.focusId) {
            const input = document.getElementById(check.focusId);
            if (input) {
              input.focus();
              input.classList.add('input-error-pulse');
              setTimeout(() => input.classList.remove('input-error-pulse'), 1500);
            }
          }
          return;
        }
        updateFormatCardVisual(mode, true);
        showToast(`已开启 ${getModeDisplayName(mode)} 输出`, 'success');
      } else {
        updateFormatCardVisual(mode, false);
      }
    });
  });

  // Toggle MySQL Password visibility
  const togglePwdBtn = document.getElementById('btn-toggle-mysql-pwd');
  if (togglePwdBtn) {
    togglePwdBtn.addEventListener('click', () => {
      const pwdInput = document.getElementById('cfg-mysql-password');
      if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        togglePwdBtn.textContent = '🔒';
      } else {
        pwdInput.type = 'password';
        togglePwdBtn.textContent = '👁️';
      }
    });
  }

  // Import Cookie from Browser in settings
  const settingsImportBtn = document.getElementById('btn-settings-import-browser');
  if (settingsImportBtn) {
    settingsImportBtn.addEventListener('click', () => {
      importCookieFromBrowser({
        browserSelectId: 'select-settings-browser',
        statusDivId: 'settings-browser-import-status',
        targetInputId: 'cfg-cookie',
        onFinish: (data) => {
          const resDiv = document.getElementById('settings-cookie-test-result');
          if (resDiv && data.valid) {
            resDiv.innerHTML = `<span style="color: var(--accent-emerald);">✅ ${data.message}</span>`;
          }
        }
      });
    });
  }

  // Test Cookie in settings
  document.getElementById('btn-check-cookie-settings').addEventListener('click', async () => {
    const cookie = document.getElementById('cfg-cookie').value.trim();
    const resultDiv = document.getElementById('settings-cookie-test-result');
    resultDiv.innerHTML = '正在测试 Cookie...';
    try {
      const res = await fetch('/api/cookie/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cookie })
      });
      const json = await res.json();
      if (json.valid) {
        resultDiv.innerHTML = `<span style="color: var(--accent-emerald);">✅ ${json.message}</span>`;
      } else {
        resultDiv.innerHTML = `<span style="color: var(--accent-rose);">❌ ${json.message}</span>`;
      }
    } catch (e) {
      resultDiv.innerHTML = `<span style="color: var(--accent-rose);">连接失败: ${e}</span>`;
    }
  });

  // -----------------------------------------------------------
  // Connectivity Tests for MySQL, MongoDB, and Webhook
  // -----------------------------------------------------------
  // 1. MySQL Test
  const btnTestMysql = document.getElementById('btn-test-mysql');
  if (btnTestMysql) {
    btnTestMysql.addEventListener('click', async () => {
      const host = document.getElementById('cfg-mysql-host').value.trim();
      const port = parseInt(document.getElementById('cfg-mysql-port').value.trim()) || 3306;
      const user = document.getElementById('cfg-mysql-user').value.trim();
      const password = document.getElementById('cfg-mysql-password').value;
      const charset = document.getElementById('cfg-mysql-charset').value.trim() || 'utf8mb4';
      const resultDiv = document.getElementById('test-result-mysql');

      if (!host) {
        showToast('请先填写 MySQL 主机地址', 'error');
        document.getElementById('cfg-mysql-host').focus();
        return;
      }
      if (!user) {
        showToast('请先填写 MySQL 用户名', 'error');
        document.getElementById('cfg-mysql-user').focus();
        return;
      }

      btnTestMysql.disabled = true;
      btnTestMysql.innerHTML = '<span>⏳ 正在连接测试...</span>';
      resultDiv.innerHTML = '<span style="color: var(--text-dim);">正在尝试连接 MySQL 数据库...</span>';

      try {
        const res = await fetch('/api/test/mysql', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ host, port, user, password, charset })
        });
        const json = await res.json();
        if (json.valid) {
          resultDiv.innerHTML = `<span style="color: var(--accent-emerald); font-weight: 500;">✅ ${json.message}</span>`;
          showToast('MySQL 连通性测试通过', 'success');
        } else {
          resultDiv.innerHTML = `<span style="color: var(--accent-rose); font-weight: 500;">❌ ${json.message}</span>`;
          showToast(json.message, 'error');
        }
      } catch (err) {
        resultDiv.innerHTML = `<span style="color: var(--accent-rose);">❌ 测试请求异常: ${err}</span>`;
      } finally {
        btnTestMysql.disabled = false;
        btnTestMysql.innerHTML = '<span>⚡ 测试 MySQL 连通性</span>';
      }
    });
  }

  // 2. MongoDB Test
  const btnTestMongo = document.getElementById('btn-test-mongo');
  if (btnTestMongo) {
    btnTestMongo.addEventListener('click', async () => {
      const uri = document.getElementById('cfg-mongo-uri').value.trim();
      const resultDiv = document.getElementById('test-result-mongo');

      if (!uri) {
        showToast('请先填写 MongoDB 连接 URI', 'error');
        document.getElementById('cfg-mongo-uri').focus();
        return;
      }

      btnTestMongo.disabled = true;
      btnTestMongo.innerHTML = '<span>⏳ 正在连接测试...</span>';
      resultDiv.innerHTML = '<span style="color: var(--text-dim);">正在尝试连接 MongoDB 数据库...</span>';

      try {
        const res = await fetch('/api/test/mongodb', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uri })
        });
        const json = await res.json();
        if (json.valid) {
          resultDiv.innerHTML = `<span style="color: var(--accent-emerald); font-weight: 500;">✅ ${json.message}</span>`;
          showToast('MongoDB 连通性测试通过', 'success');
        } else {
          resultDiv.innerHTML = `<span style="color: var(--accent-rose); font-weight: 500;">❌ ${json.message}</span>`;
          showToast(json.message, 'error');
        }
      } catch (err) {
        resultDiv.innerHTML = `<span style="color: var(--accent-rose);">❌ 测试请求异常: ${err}</span>`;
      } finally {
        btnTestMongo.disabled = false;
        btnTestMongo.innerHTML = '<span>⚡ 测试 MongoDB 连通性</span>';
      }
    });
  }

  // 3. Webhook (HTTP POST) Test
  const btnTestPost = document.getElementById('btn-test-post');
  if (btnTestPost) {
    btnTestPost.addEventListener('click', async () => {
      const url = document.getElementById('cfg-post-url').value.trim();
      const token = document.getElementById('cfg-post-token').value.trim();
      const resultDiv = document.getElementById('test-result-post');

      if (!url) {
        showToast('请先填写 Webhook 接收接口 URL', 'error');
        document.getElementById('cfg-post-url').focus();
        return;
      }

      btnTestPost.disabled = true;
      btnTestPost.innerHTML = '<span>⏳ 正在发送请求...</span>';
      resultDiv.innerHTML = '<span style="color: var(--text-dim);">正在向 Webhook 地址发送检测请求...</span>';

      try {
        const res = await fetch('/api/test/webhook', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url, token })
        });
        const json = await res.json();
        if (json.valid) {
          resultDiv.innerHTML = `<span style="color: var(--accent-emerald); font-weight: 500;">✅ ${json.message}</span>`;
          showToast('Webhook 连通性测试成功', 'success');
        } else {
          resultDiv.innerHTML = `<span style="color: var(--accent-rose); font-weight: 500;">❌ ${json.message}</span>`;
          showToast(json.message, 'error');
        }
      } catch (err) {
        resultDiv.innerHTML = `<span style="color: var(--accent-rose);">❌ 测试请求异常: ${err}</span>`;
      } finally {
        btnTestPost.disabled = false;
        btnTestPost.innerHTML = '<span>⚡ 测试 Webhook 连通性</span>';
      }
    });
  }
}

// Live Log Streamer
async function fetchLogs() {
  try {
    const level = state.logFilterLevel;
    const kw = state.logFilterKeyword;
    const url = `/api/logs?limit=300&level=${encodeURIComponent(level)}&keyword=${encodeURIComponent(kw)}`;
    const res = await fetch(url);
    const json = await res.json();
    if (json.code === 200) {
      renderLogs(json.logs);
    }
  } catch (e) {
    console.error('Fetch logs error:', e);
  }
}

function renderLogs(logs) {
  const screen = document.getElementById('log-screen-body');
  if (!logs || logs.length === 0) {
    screen.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding-top: 40px;">暂无日志输出</div>';
    return;
  }

  screen.innerHTML = logs.map(line => {
    let levelBadge = '';
    let lineClass = '';

    if (line.includes('ERROR') || line.includes('error') || line.includes('失败')) {
      levelBadge = '<span class="log-level-badge level-error">ERROR</span>';
    } else if (line.includes('WARNING') || line.includes('warn') || line.includes('警告')) {
      levelBadge = '<span class="log-level-badge level-warn">WARN</span>';
    } else if (line.includes('INFO')) {
      levelBadge = '<span class="log-level-badge level-info">INFO</span>';
    }

    return `
      <div class="log-line">
        ${levelBadge}
        <span>${escapeHtml(line)}</span>
      </div>
    `;
  }).join('');

  if (state.autoScroll) {
    screen.scrollTop = screen.scrollHeight;
  }
}

function initLogStreamer() {
  document.getElementById('auto-scroll-toggle').addEventListener('change', (e) => {
    state.autoScroll = e.target.checked;
  });

  document.getElementById('log-level-select').addEventListener('change', (e) => {
    state.logFilterLevel = e.target.value;
    fetchLogs();
  });

  document.getElementById('log-search-input').addEventListener('input', (e) => {
    state.logFilterKeyword = e.target.value.trim();
    fetchLogs();
  });

  document.getElementById('btn-clear-logs').addEventListener('click', async () => {
    try {
      await fetch('/api/logs/clear', { method: 'POST' });
      document.getElementById('log-screen-body').innerHTML = '';
      showToast('日志已清空', 'info');
    } catch (e) {
      showToast('清空失败: ' + e, 'error');
    }
  });
}

// Data Explorer
async function fetchData() {
  const userSelect = document.getElementById('data-filter-user');
  const userId = userSelect ? userSelect.value.trim() : '';

  const startInput = document.getElementById('data-filter-start-date');
  const startDate = startInput ? startInput.value.trim() : '';

  const endInput = document.getElementById('data-filter-end-date');
  const endDate = endInput ? endInput.value.trim() : '';

  const kwInput = document.getElementById('data-search-keyword');
  const kw = kwInput ? kwInput.value.trim() : '';

  let url = `/api/data/weibos?page=${state.dataPage}&page_size=${state.dataPageSize}`;
  if (userId) url += `&user_id=${encodeURIComponent(userId)}`;
  if (startDate) url += `&start_date=${encodeURIComponent(startDate)}`;
  if (endDate) url += `&end_date=${encodeURIComponent(endDate)}`;
  if (kw) url += `&keyword=${encodeURIComponent(kw)}`;

  try {
    const res = await fetch(url);
    const json = await res.json();
    if (json.code === 200) {
      if (json.data && Array.isArray(json.data.available_users)) {
        populateUserFilterDropdown(json.data.available_users);
      }
      renderDataTable(json.data);
    }
  } catch (e) {
    console.error('Fetch data error:', e);
  }
}

function populateUserFilterDropdown(dbUsers = []) {
  const select = document.getElementById('data-filter-user');
  if (!select) return;

  const currentVal = select.value;
  const userMap = new Map();

  // 1. Add users found in SQLite database
  if (Array.isArray(dbUsers)) {
    dbUsers.forEach(u => {
      if (u.user_id) {
        userMap.set(String(u.user_id), u.screen_name || u.user_id);
      }
    });
  }

  // 2. Also merge configured target users
  if (Array.isArray(state.users)) {
    state.users.forEach(u => {
      if (u.id && !userMap.has(String(u.id))) {
        userMap.set(String(u.id), u.screen_name || u.id);
      }
    });
  }

  // Build options
  let optionsHtml = '<option value="">全部博主</option>';
  userMap.forEach((name, uid) => {
    const displayName = (name && name !== uid) ? `${name} (${uid})` : uid;
    optionsHtml += `<option value="${escapeHtml(uid)}">${escapeHtml(displayName)}</option>`;
  });

  select.innerHTML = optionsHtml;
  if (currentVal && userMap.has(currentVal)) {
    select.value = currentVal;
  }
}

function renderDataTable(data) {
  const tbody = document.getElementById('data-tbody');
  const totalLabel = document.getElementById('data-total-label');
  const pageIndicator = document.getElementById('data-page-indicator');

  if (!data || !data.exists || !data.items || data.items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 40px;">暂无匹配的微博数据（请检查筛选条件，或在配置中开启 sqlite 输出并执行过爬取）</td></tr>';
    totalLabel.textContent = '共 0 条数据';
    pageIndicator.textContent = `第 1 页`;
    return;
  }

  totalLabel.textContent = `共 ${data.total} 条数据`;
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  pageIndicator.textContent = `第 ${data.page} 页 / 共 ${totalPages} 页`;

  tbody.innerHTML = data.items.map(item => {
    const link = item.bid ? `https://m.weibo.cn/status/${item.bid}` : `https://m.weibo.cn/detail/${item.id}`;
    return `
      <tr>
        <td><strong>${escapeHtml(item.screen_name || item.user_id)}</strong></td>
        <td>
          <div style="max-height: 80px; overflow-y: auto; font-size: 0.88rem; line-height: 1.5;">
            ${escapeHtml(item.text || '')}
          </div>
        </td>
        <td><span style="font-size: 0.8rem; color: var(--text-dim); white-space: nowrap;">${escapeHtml(item.created_at || '')}</span></td>
        <td>
          <span style="font-size: 0.82rem; color: var(--text-muted); white-space: nowrap;">
            👍 ${item.attitudes_count || 0} &nbsp;|&nbsp; 💬 ${item.comments_count || 0} &nbsp;|&nbsp; 🔁 ${item.reposts_count || 0}
          </span>
        </td>
        <td style="text-align: right;">
          <a href="${link}" target="_blank" class="btn btn-secondary btn-sm" title="跳转微博原文">查看</a>
        </td>
      </tr>
    `;
  }).join('');
}

function initDataExplorer() {
  const btnSearch = document.getElementById('btn-search-data');
  const btnReset = document.getElementById('btn-reset-data');
  const kwInput = document.getElementById('data-search-keyword');
  const userSelect = document.getElementById('data-filter-user');
  const startInput = document.getElementById('data-filter-start-date');
  const endInput = document.getElementById('data-filter-end-date');

  // Trigger search on button click
  if (btnSearch) {
    btnSearch.addEventListener('click', () => {
      state.dataPage = 1;
      fetchData();
    });
  }

  // Trigger search on reset
  if (btnReset) {
    btnReset.addEventListener('click', () => {
      if (userSelect) userSelect.value = '';
      if (startInput) startInput.value = '';
      if (endInput) endInput.value = '';
      if (kwInput) kwInput.value = '';
      state.dataPage = 1;
      fetchData();
    });
  }

  // Auto trigger on dropdown / date change
  if (userSelect) {
    userSelect.addEventListener('change', () => {
      state.dataPage = 1;
      fetchData();
    });
  }

  if (startInput) {
    startInput.addEventListener('change', () => {
      state.dataPage = 1;
      fetchData();
    });
  }

  if (endInput) {
    endInput.addEventListener('change', () => {
      state.dataPage = 1;
      fetchData();
    });
  }

  // Trigger search on Enter in keyword input
  if (kwInput) {
    kwInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        state.dataPage = 1;
        fetchData();
      }
    });
  }

  // Pagination
  document.getElementById('btn-data-prev').addEventListener('click', () => {
    if (state.dataPage > 1) {
      state.dataPage--;
      fetchData();
    }
  });

  document.getElementById('btn-data-next').addEventListener('click', () => {
    state.dataPage++;
    fetchData();
  });
}

// Modal System
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add('active');
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove('active');
}

function initModals() {
  document.getElementById('btn-open-add-user-modal').addEventListener('click', () => {
    openModal('modal-add-user');
  });

  document.getElementById('btn-open-import-modal').addEventListener('click', () => {
    openModal('modal-import-users');
  });

  document.querySelectorAll('.modal-close').forEach(btn => {
    btn.addEventListener('click', () => {
      const modalId = btn.getAttribute('data-modal');
      closeModal(modalId);
    });
  });

  // Click background to close
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.classList.remove('active');
      }
    });
  });
}

// RESTful API Documentation Center
function initApiDocs() {
  const catButtons = document.querySelectorAll('.api-cat-btn');
  const searchInput = document.getElementById('api-search-input');
  const cards = document.querySelectorAll('.api-card');

  function filterCards() {
    const activeBtn = document.querySelector('.api-cat-btn.active');
    const activeCat = activeBtn ? activeBtn.getAttribute('data-cat') : 'all';
    const kw = (searchInput ? searchInput.value : '').trim().toLowerCase();

    cards.forEach(card => {
      const cardCat = card.getAttribute('data-cat');
      const cardSearch = (card.getAttribute('data-search') || '').toLowerCase();
      const matchCat = (activeCat === 'all' || cardCat === activeCat);
      const matchKw = (!kw || cardSearch.includes(kw));

      if (matchCat && matchKw) {
        card.style.display = 'block';
      } else {
        card.style.display = 'none';
      }
    });
  }

  catButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      catButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterCards();
    });
  });

  if (searchInput) {
    searchInput.addEventListener('input', filterCards);
  }
}

