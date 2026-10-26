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

// Navigation Tabs
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const pageViews = document.querySelectorAll('.page-view');
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');

  const titles = {
    dashboard: { title: '总览控制', subtitle: '监控爬虫实时运行状态与全局任务调度' },
    targets: { title: '目标管理', subtitle: '维护微博采集目标用户队列与增量配置' },
    settings: { title: '参数配置', subtitle: '可视化调整所有爬虫参数或编辑 config.json 源码' },
    logs: { title: '实时日志', subtitle: '实时捕捉爬虫标准输出与错误排查' },
    data: { title: '数据预览', subtitle: '探索本地 SQLite 数据库中采集到的历史数据' }
  };

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const tab = item.getAttribute('data-tab');
      if (tab === state.currentTab) return;

      navItems.forEach(n => n.classList.remove('active'));
      item.classList.add('active');

      pageViews.forEach(v => v.classList.remove('active'));
      const activeView = document.getElementById(`view-${tab}`);
      if (activeView) activeView.classList.add('active');

      state.currentTab = tab;
      if (titles[tab]) {
        pageTitle.textContent = titles[tab].title;
        pageSubtitle.textContent = titles[tab].subtitle;
      }

      // Tab specific refresh
      if (tab === 'targets') fetchUsers();
      if (tab === 'settings') fetchConfig();
      if (tab === 'logs') fetchLogs();
      if (tab === 'data') fetchData();
    });
  });
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

  // Dashboard Cookie Test
  document.getElementById('btn-test-cookie-dash').addEventListener('click', runCookieCheck);
}

async function runCookieCheck() {
  const banner = document.getElementById('cookie-status-banner');
  banner.innerHTML = '正在与微博移动端接口通信验证 Cookie，请稍候...';
  try {
    const res = await fetch('/api/cookie/check', { method: 'POST' });
    const json = await res.json();
    if (json.valid) {
      banner.innerHTML = `<span style="color: var(--accent-emerald); font-weight: 600;">✅ ${json.message}</span> (当前账号: <strong>${json.user ? json.user.screen_name : ''}</strong>)`;
      showToast(json.message, 'success');
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

function updateWriteModeCardsVisibility() {
  const cardsMap = {
    mysql: document.getElementById('card-cfg-mysql'),
    mongo: document.getElementById('card-cfg-mongo'),
    sqlite: document.getElementById('card-cfg-sqlite'),
    post: document.getElementById('card-cfg-post'),
    markdown: document.getElementById('card-cfg-markdown')
  };

  document.querySelectorAll('.cfg-writemode-cb').forEach(cb => {
    const card = cardsMap[cb.value];
    if (card) {
      if (cb.checked) {
        card.classList.add('active');
      } else {
        card.classList.remove('active');
      }
    }
  });
}

function populateConfigForm(cfg) {
  if (!cfg) return;

  // Basic
  document.getElementById('cfg-only-original').checked = (cfg.only_crawl_original === 1);
  document.getElementById('cfg-remove-html').checked = (cfg.remove_html_tag === 1);
  document.getElementById('cfg-since-date').value = cfg.since_date || '';
  document.getElementById('cfg-end-date').value = cfg.end_date || '';
  document.getElementById('cfg-start-page').value = cfg.start_page || 1;
  document.getElementById('cfg-page-count').value = cfg.page_weibo_count || 20;

  // Cookie
  document.getElementById('cfg-cookie').value = cfg.cookie || '';

  // Media
  document.getElementById('cfg-orig-pic').checked = (cfg.original_pic_download === 1);
  document.getElementById('cfg-retweet-pic').checked = (cfg.retweet_pic_download === 1);
  document.getElementById('cfg-orig-video').checked = (cfg.original_video_download === 1);
  document.getElementById('cfg-orig-livephoto').checked = (cfg.original_live_photo_download === 1);
  document.getElementById('cfg-write-exif').checked = (cfg.write_time_in_exif === 1);

  // Write mode
  const writeModes = Array.isArray(cfg.write_mode) ? cfg.write_mode : [];
  document.querySelectorAll('.cfg-writemode-cb').forEach(cb => {
    cb.checked = writeModes.includes(cb.value);
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
  document.getElementById('cfg-missing-report').checked = (cfg.missing_weibo_report === 1);

  // Update card visibility
  updateWriteModeCardsVisibility();

  // Advanced
  document.getElementById('cfg-download-comment').checked = (cfg.download_comment === 1);
  document.getElementById('cfg-comment-count').value = cfg.comment_max_download_count || 1000;
  document.getElementById('cfg-download-repost').checked = (cfg.download_repost === 1);
}

function collectConfigForm() {
  const cfg = state.currentConfig ? { ...state.currentConfig } : {};

  cfg.only_crawl_original = document.getElementById('cfg-only-original').checked ? 1 : 0;
  cfg.remove_html_tag = document.getElementById('cfg-remove-html').checked ? 1 : 0;

  const sinceVal = document.getElementById('cfg-since-date').value.trim();
  cfg.since_date = /^\d+$/.test(sinceVal) ? parseInt(sinceVal, 10) : sinceVal;

  cfg.end_date = document.getElementById('cfg-end-date').value.trim();
  cfg.start_page = parseInt(document.getElementById('cfg-start-page').value, 10) || 1;
  cfg.page_weibo_count = parseInt(document.getElementById('cfg-page-count').value, 10) || 20;

  cfg.cookie = document.getElementById('cfg-cookie').value.trim();

  cfg.original_pic_download = document.getElementById('cfg-orig-pic').checked ? 1 : 0;
  cfg.retweet_pic_download = document.getElementById('cfg-retweet-pic').checked ? 1 : 0;
  cfg.original_video_download = document.getElementById('cfg-orig-video').checked ? 1 : 0;
  cfg.original_live_photo_download = document.getElementById('cfg-orig-livephoto').checked ? 1 : 0;
  cfg.write_time_in_exif = document.getElementById('cfg-write-exif').checked ? 1 : 0;

  const modes = [];
  document.querySelectorAll('.cfg-writemode-cb:checked').forEach(cb => {
    modes.push(cb.value);
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
  cfg.missing_weibo_report = document.getElementById('cfg-missing-report').checked ? 1 : 0;

  // Advanced
  cfg.download_comment = document.getElementById('cfg-download-comment').checked ? 1 : 0;
  cfg.comment_max_download_count = parseInt(document.getElementById('cfg-comment-count').value, 10) || 1000;
  cfg.download_repost = document.getElementById('cfg-download-repost').checked ? 1 : 0;

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
  document.getElementById('btn-save-config').addEventListener('click', async () => {
    let payload = {};
    if (state.configMode === 'form') {
      payload.parsed = collectConfigForm();
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
  });

  // Listen to write_mode checkboxes to dynamically expand / collapse config cards
  document.querySelectorAll('.cfg-writemode-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      updateWriteModeCardsVisibility();
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
        resultDiv.innerHTML = `<span style="color: var(--accent-emerald);">✅ ${json.message} (账号: ${json.user.screen_name})</span>`;
      } else {
        resultDiv.innerHTML = `<span style="color: var(--accent-rose);">❌ ${json.message}</span>`;
      }
    } catch (e) {
      resultDiv.innerHTML = `<span style="color: var(--accent-rose);">连接失败: ${e}</span>`;
    }
  });
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
  const kw = document.getElementById('data-search-keyword').value.trim();
  const url = `/api/data/weibos?page=${state.dataPage}&page_size=${state.dataPageSize}${kw ? '&keyword=' + encodeURIComponent(kw) : ''}`;

  try {
    const res = await fetch(url);
    const json = await res.json();
    if (json.code === 200) {
      renderDataTable(json.data);
    }
  } catch (e) {
    console.error('Fetch data error:', e);
  }
}

function renderDataTable(data) {
  const tbody = document.getElementById('data-tbody');
  const totalLabel = document.getElementById('data-total-label');
  const pageIndicator = document.getElementById('data-page-indicator');

  if (!data || !data.exists || !data.items || data.items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 40px;">暂无匹配的微博数据（请检查是否在配置中开启了 sqlite 输出并执行过爬取）</td></tr>';
    totalLabel.textContent = '共 0 条记录';
    pageIndicator.textContent = `第 1 页`;
    return;
  }

  totalLabel.textContent = `共 ${data.total} 条记录`;
  pageIndicator.textContent = `第 ${data.page} 页 / 共 ${Math.ceil(data.total / data.page_size)} 页`;

  tbody.innerHTML = data.items.map(item => {
    const link = item.bid ? `https://m.weibo.cn/status/${item.bid}` : `https://m.weibo.cn/detail/${item.id}`;
    return `
      <tr>
        <td><strong>${escapeHtml(item.screen_name || item.user_id)}</strong></td>
        <td>
          <div style="max-height: 80px; overflow-y: auto; font-size: 0.88rem;">
            ${escapeHtml(item.text || '')}
          </div>
        </td>
        <td><span style="font-size: 0.8rem; color: var(--text-dim);">${escapeHtml(item.created_at || '')}</span></td>
        <td>
          <span style="font-size: 0.82rem; color: var(--text-muted);">
            👍 ${item.attitudes_count || 0} &nbsp;|&nbsp; 💬 ${item.comments_count || 0} &nbsp;|&nbsp; 🔁 ${item.reposts_count || 0}
          </span>
        </td>
        <td style="text-align: right;">
          <a href="${link}" target="_blank" class="btn btn-secondary btn-sm" title="跳转微博">查看</a>
        </td>
      </tr>
    `;
  }).join('');
}

function initDataExplorer() {
  document.getElementById('btn-search-data').addEventListener('click', () => {
    state.dataPage = 1;
    fetchData();
  });

  document.getElementById('data-search-keyword').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      state.dataPage = 1;
      fetchData();
    }
  });

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
