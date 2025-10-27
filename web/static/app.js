const state = {
  tasks: [],
  tasksById: new Map(),
  filter: 'all',
  planVersion: null,
  planUpdatedAt: null,
  systemState: {
    maintenance_mode: false,
    message: null,
    updated_at: null,
    version: null,
  },
  configuration: null,
  configurationFetchedAt: null,
  configurationLoading: false,
  diagnostics: null,
  diagnosticsVisible: false,
  diagnosticsLoading: false,
  diagnosticsFetchedAt: null,
  taskAnalytics: null,
  taskAnalyticsFetchedAt: null,
};

let ws;
let wsPingTimer;
let reconnectAttempts = 0;

const PING_INTERVAL_MS = 30000;
const WS_RECONNECT_DELAY_MS = 2000;
const STATUS_BADGE_CLASSES = {
  pending: 'bg-yellow-100 text-yellow-800',
  in_progress: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
};
const ADMIN_TOKEN_STORAGE_KEY = 'switchboardAdminToken';

function escapeHtml(value) {
  if (value == null) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatStatusLabel(status) {
  if (!status) return '';
  return status.replace(/_/g, ' ');
}

function formatBytes(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return 'unknown';
  }
  let number = Number(value);
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  for (const unit of units) {
    if (number < 1024 || unit === units[units.length - 1]) {
      if (unit === 'B') {
        return `${Math.round(number)} ${unit}`;
      }
      return `${number.toFixed(1)} ${unit}`;
    }
    number /= 1024;
  }
  return `${number.toFixed(1)} TiB`;
}

function showToast(message, variant = 'error') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast--${variant}`;
  toast.setAttribute('role', 'status');

  const messageEl = document.createElement('div');
  messageEl.className = 'toast__message';
  messageEl.textContent = message;
  toast.appendChild(messageEl);

  toast.addEventListener('click', () => hideToast(toast));

  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.add('is-visible');
  });

  setTimeout(() => hideToast(toast), 5000);
}

function hideToast(toast) {
  if (!toast || toast.dataset.dismissed) return;
  toast.dataset.dismissed = 'true';
  toast.classList.remove('is-visible');
  toast.addEventListener(
    'transitionend',
    () => {
      toast.remove();
    },
    { once: true }
  );
  // In case transitions are disabled.
  setTimeout(() => toast.remove(), 400);
}

function loadAdminToken() {
  try {
    return localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || '';
  } catch (error) {
    console.warn('Unable to read admin token from storage', error);
    return '';
  }
}

function persistAdminToken(token) {
  try {
    if (token) {
      localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    }
  } catch (error) {
    console.warn('Unable to persist admin token', error);
  }
}

async function extractErrorDetails(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      const data = await response.json();
      if (data && typeof data.error === 'string') {
        return data.error;
      }
      if (data && typeof data.detail === 'string') {
        return data.detail;
      }
    } catch (err) {
      console.error('Failed to parse error JSON', err);
    }
  }
  try {
    const text = await response.text();
    return text.trim();
  } catch (err) {
    console.error('Failed to read error response', err);
  }
  return '';
}

async function apiFetch(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    console.error('Network error while fetching', url, error);
    showToast(`Network request to ${url} failed. Please check your connection and retry.`, 'error');
    throw error;
  }

  if (!response.ok) {
    const details = await extractErrorDetails(response);
    const method = options.method || 'GET';
    const reason = details ? `: ${details}` : '';
    showToast(`Request ${method} ${url} failed (${response.status} ${response.statusText})${reason}`, 'error');
    const error = new Error('Request failed');
    error.response = response;
    error.details = details;
    throw error;
  }
  return response;
}

async function apiFetchJson(url, options = {}) {
  const response = await apiFetch(url, options);
  try {
    return await response.json();
  } catch (error) {
    console.error('Failed to parse JSON from', url, error);
    showToast(`Received invalid JSON from ${url}.`, 'error');
    throw error;
  }
}

async function copyToClipboard(value, label) {
  if (!value) return;
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(value);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = value;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    showToast(`${label} copied to clipboard.`, 'success');
  } catch (error) {
    console.error('Failed to copy value', error);
    showToast(`Unable to copy ${label.toLowerCase()}.`, 'error');
  }
}

function renderPlanMeta() {
  const meta = document.getElementById('planMeta');
  if (!meta) return;
  const versionEl = document.getElementById('planVersion');
  const updatedEl = document.getElementById('planUpdated');

  if (state.planVersion == null) {
    meta.classList.add('hidden');
    return;
  }

  versionEl.textContent = state.planVersion;
  if (state.planUpdatedAt) {
    const parsed = new Date(state.planUpdatedAt);
    if (!Number.isNaN(parsed.valueOf())) {
      updatedEl.textContent = parsed.toLocaleString();
      updatedEl.dateTime = parsed.toISOString();
    } else {
      updatedEl.textContent = state.planUpdatedAt;
      updatedEl.removeAttribute('dateTime');
    }
  } else {
    updatedEl.textContent = '—';
    updatedEl.removeAttribute('dateTime');
  }
  meta.classList.remove('hidden');
}


function renderAnalytics() {
  const summary = document.getElementById('analyticsSummary');
  const cards = document.getElementById('analyticsCards');
  const updatedWrapper = document.getElementById('analyticsUpdatedWrapper');
  const updatedEl = document.getElementById('analyticsUpdated');
  if (!summary || !cards) {
    return;
  }

  const analytics = state.taskAnalytics;
  if (!analytics) {
    summary.textContent = 'Analytics unavailable. Try refreshing to load metrics.';
    cards.innerHTML =
      '<p class="text-sm text-gray-500">Task analytics are not available right now.</p>';
    if (updatedWrapper && updatedEl) {
      updatedWrapper.classList.add('hidden');
      updatedEl.textContent = '—';
      updatedEl.removeAttribute('dateTime');
    }
    return;
  }

  const { ready_tasks, blocked_tasks, total_tasks } = analytics;
  summary.textContent = `${total_tasks} tasks — ${ready_tasks} ready, ${blocked_tasks} blocked.`;

  if (updatedWrapper && updatedEl) {
    const fetchedAt = state.taskAnalyticsFetchedAt
      ? new Date(state.taskAnalyticsFetchedAt)
      : null;
    if (fetchedAt && !Number.isNaN(fetchedAt.valueOf())) {
      updatedEl.textContent = fetchedAt.toLocaleTimeString();
      updatedEl.dateTime = fetchedAt.toISOString();
      updatedWrapper.classList.remove('hidden');
    } else {
      updatedWrapper.classList.add('hidden');
      updatedEl.textContent = '—';
      updatedEl.removeAttribute('dateTime');
    }
  }

  const statusList = `
    <dl class="analytics-list">
      <div><dt>Pending</dt><dd>${analytics.pending_tasks}</dd></div>
      <div><dt>In progress</dt><dd>${analytics.in_progress_tasks}</dd></div>
      <div><dt>Completed</dt><dd>${analytics.completed_tasks}</dd></div>
    </dl>
  `;

  const flowList = `
    <dl class="analytics-list">
      <div><dt>Ready</dt><dd>${analytics.ready_tasks}</dd></div>
      <div><dt>Blocked</dt><dd>${analytics.blocked_tasks}</dd></div>
      <div><dt>Average deps</dt><dd>${analytics.average_dependencies.toFixed(2)}</dd></div>
    </dl>
  `;

  const dependencyNotes = [];
  dependencyNotes.push(`<span>${analytics.with_dependencies} with dependencies</span>`);
  dependencyNotes.push(`<span>${analytics.without_dependencies} without dependencies</span>`);
  dependencyNotes.push(`<span>${analytics.dependency_edges} total edges</span>`);
  if (analytics.missing_dependency_tasks || analytics.missing_dependency_edges) {
    dependencyNotes.push(
      `<span class="text-amber-700 font-medium">Warnings: ${analytics.missing_dependency_tasks} tasks reference ${analytics.missing_dependency_edges} missing edges</span>`
    );
  }

  const dependencyList = `
    <ul class="analytics-list analytics-list--compact">
      ${dependencyNotes.map((item) => `<li>${item}</li>`).join('')}
    </ul>
  `;

  cards.innerHTML = `
    <article class="analytics-card" aria-label="Status distribution">${statusList}</article>
    <article class="analytics-card" aria-label="Flow readiness">${flowList}</article>
    <article class="analytics-card" aria-label="Dependency insights">${dependencyList}</article>
  `;
}

function renderConfiguration() {
  const summary = document.getElementById('configurationSummary');
  const rateList = document.getElementById('configurationRate');
  const storageList = document.getElementById('configurationStorage');
  const databaseList = document.getElementById('configurationDatabase');
  const envTable = document.getElementById('configurationEnvironment');
  const warningsWrapper = document.getElementById('configurationWarningsWrapper');
  const warningsList = document.getElementById('configurationWarnings');
  const updatedWrapper = document.getElementById('configurationUpdatedWrapper');
  const updatedEl = document.getElementById('configurationUpdated');
  const refresh = document.getElementById('refreshConfiguration');
  if (
    !summary ||
    !rateList ||
    !storageList ||
    !databaseList ||
    !envTable ||
    !refresh
  ) {
    return;
  }

  if (state.configurationLoading) {
    refresh.disabled = true;
    refresh.textContent = 'Refreshing…';
  } else {
    refresh.disabled = false;
    refresh.textContent = 'Refresh';
  }

  const snapshot = state.configuration;
  if (!snapshot) {
    summary.textContent = 'Configuration has not been loaded yet.';
    rateList.innerHTML = '<p class="text-xs text-gray-500">No data available.</p>';
    storageList.innerHTML = '<p class="text-xs text-gray-500">No data available.</p>';
    databaseList.innerHTML = '<p class="text-xs text-gray-500">No data available.</p>';
    envTable.innerHTML =
      '<tr><td colspan="3" class="border px-2 py-2 text-sm text-gray-500">No environment data loaded.</td></tr>';
    if (warningsWrapper && warningsList) {
      warningsWrapper.classList.add('hidden');
      warningsList.innerHTML = '';
    }
    if (updatedWrapper && updatedEl) {
      updatedWrapper.classList.add('hidden');
      updatedEl.textContent = '—';
      updatedEl.removeAttribute('dateTime');
    }
    return;
  }

  const settings = snapshot.settings || {};
  const rate = settings.rate_limit || {};
  const lease = settings.lease || {};
  const extensions = settings.extensions || {};
  const storage = snapshot.storage || {};
  const database = snapshot.database || {};
  const admin = snapshot.admin || {};

  const rateStatus = rate.enabled ? 'enabled' : 'disabled';
  const leaseSeconds =
    typeof lease.duration_seconds === 'number'
      ? `${lease.duration_seconds}s`
      : 'unknown';
  let storageDescriptor = 'unavailable';
  if (storage.writable === true) {
    storageDescriptor = 'writable';
  } else if (storage.writable === false) {
    storageDescriptor = 'read-only';
  }

  summary.textContent = `Rate limiter ${rateStatus}; lease ${leaseSeconds}; storage ${storageDescriptor}.`;

  if (updatedWrapper && updatedEl) {
    const fetchedAt = state.configurationFetchedAt
      ? new Date(state.configurationFetchedAt)
      : null;
    if (fetchedAt && !Number.isNaN(fetchedAt.valueOf())) {
      updatedEl.textContent = fetchedAt.toLocaleTimeString();
      updatedEl.dateTime = fetchedAt.toISOString();
      updatedWrapper.classList.remove('hidden');
    } else {
      updatedWrapper.classList.add('hidden');
      updatedEl.textContent = '—';
      updatedEl.removeAttribute('dateTime');
    }
  }

  const trustedBypass = Array.isArray(rate.trusted_bypass) && rate.trusted_bypass.length
    ? rate.trusted_bypass.map((value) => escapeHtml(String(value))).join(', ')
    : '—';
  const trustedProxies = Array.isArray(rate.trusted_proxies) && rate.trusted_proxies.length
    ? rate.trusted_proxies.map((value) => escapeHtml(String(value))).join(', ')
    : '—';

  rateList.innerHTML = `
    <div><dt>Status</dt><dd>${rateStatus}</dd></div>
    <div><dt>Requests</dt><dd>${rate.requests ?? '—'}</dd></div>
    <div><dt>Window</dt><dd>${rate.window_seconds ?? '—'}s</dd></div>
    <div><dt>Trusted bypass</dt><dd>${trustedBypass}</dd></div>
    <div><dt>Trusted proxies</dt><dd>${trustedProxies}</dd></div>
  `;
  const registered = Array.isArray(extensions.registered)
    ? extensions.registered
    : [];
  rateList.insertAdjacentHTML(
    'beforeend',
    `<div><dt>Extensions</dt><dd>${registered.length} active</dd></div>`
  );
  if (extensions.contract_version) {
    rateList.insertAdjacentHTML(
      'beforeend',
      `<div><dt>Contract</dt><dd>${escapeHtml(String(extensions.contract_version))}</dd></div>`
    );
  }
  rateList.insertAdjacentHTML(
    'beforeend',
    `<div><dt>Admin token</dt><dd>${admin.configured ? 'configured' : 'not configured'}</dd></div>`
  );

  storageList.innerHTML = `
    <div><dt>Root</dt><dd id="configurationStorageRoot">${escapeHtml(storage.root || '—')}</dd></div>
    <div><dt>Exists</dt><dd>${storage.exists === true ? 'yes' : storage.exists === false ? 'no' : 'unknown'}</dd></div>
    <div><dt>Writable</dt><dd>${storage.writable === true ? 'yes' : storage.writable === false ? 'no' : 'unknown'}</dd></div>
    <div><dt>Free space</dt><dd>${formatBytes(storage.free_bytes)}</dd></div>
    <div><dt>Total space</dt><dd>${formatBytes(storage.total_bytes)}</dd></div>
  `;
  const storageRootCell = document.getElementById('configurationStorageRoot');
  if (storageRootCell && storage.root) {
    const copyButton = document.createElement('button');
    copyButton.type = 'button';
    copyButton.className = 'copy-button';
    copyButton.dataset.copyValue = storage.root;
    copyButton.dataset.copyLabel = 'Storage root';
    copyButton.textContent = 'Copy path';
    storageRootCell.parentElement?.appendChild(copyButton);
  }

  const configuredViaEnv = database.configured_via_env ? 'environment' : 'default';
  const engineOptions = database.engine_options && typeof database.engine_options === 'object'
    ? database.engine_options
    : {};
  databaseList.innerHTML = `
    <div><dt>URL</dt><dd>${escapeHtml(database.url || 'unknown')}</dd></div>
    <div><dt>Driver</dt><dd>${escapeHtml(database.driver || 'n/a')}</dd></div>
    <div><dt>Source</dt><dd>${escapeHtml(configuredViaEnv)}</dd></div>
    <div><dt>Engine options</dt><dd>${Object.keys(engineOptions).length}</dd></div>
  `;
  if (Object.keys(engineOptions).length) {
    const optionSummary = Object.entries(engineOptions)
      .map(([key, value]) => `${escapeHtml(String(key))}=${escapeHtml(String(value))}`)
      .join(', ');
    databaseList.insertAdjacentHTML(
      'beforeend',
      `<div><dt>Options</dt><dd>${optionSummary}</dd></div>`
    );
  }

  const environmentEntries = Array.isArray(snapshot.environment)
    ? snapshot.environment
    : [];
  if (environmentEntries.length) {
    envTable.innerHTML = environmentEntries
      .map(
        (entry) => `
          <tr>
            <td class="border px-2 py-1 align-top">${escapeHtml(entry.name)}</td>
            <td class="border px-2 py-1 align-top font-mono text-xs">${escapeHtml(entry.value)}</td>
            <td class="border px-2 py-1 align-top">${escapeHtml(entry.source || 'environment')}</td>
          </tr>
        `
      )
      .join('');
  } else {
    envTable.innerHTML =
      '<tr><td colspan="3" class="border px-2 py-2 text-sm text-gray-500">No environment overrides detected.</td></tr>';
  }

  if (warningsWrapper && warningsList) {
    const warnings = Array.isArray(snapshot.warnings)
      ? snapshot.warnings
      : [];
    if (warnings.length) {
      warningsWrapper.classList.remove('hidden');
      warningsList.innerHTML = warnings
        .map((warning) => `<li>${escapeHtml(String(warning))}</li>`)
        .join('');
    } else {
      warningsWrapper.classList.add('hidden');
      warningsList.innerHTML = '';
    }
  }
}

function formatTimestamp(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return null;
  }
  return date;
}

function renderDiagnostics() {
  const summary = document.getElementById('diagnosticsSummary');
  const panel = document.getElementById('diagnosticsPanel');
  const toggle = document.getElementById('toggleDiagnostics');
  const refresh = document.getElementById('refreshDiagnostics');
  const updatedWrapper = document.getElementById('diagnosticsUpdatedWrapper');
  const updatedTime = document.getElementById('diagnosticsUpdated');

  if (!summary || !panel || !toggle || !refresh) {
    return;
  }

  if (state.diagnosticsLoading) {
    refresh.disabled = true;
    refresh.textContent = 'Refreshing…';
    summary.textContent = 'Refreshing diagnostics…';
  } else {
    refresh.disabled = false;
    refresh.textContent = 'Refresh';
    if (state.diagnostics) {
      const warnings = Array.isArray(state.diagnostics.warnings)
        ? state.diagnostics.warnings.length
        : 0;
      summary.textContent = warnings
        ? `Diagnostics loaded with ${warnings} warning${warnings === 1 ? '' : 's'}.`
        : 'Diagnostics loaded successfully.';
    } else {
      summary.textContent = 'Diagnostics have not been loaded yet.';
    }
  }

  const fetchedAt = state.diagnostics?.generated_at || state.diagnosticsFetchedAt;
  const parsed = formatTimestamp(fetchedAt);
  if (updatedWrapper && updatedTime) {
    if (parsed) {
      updatedTime.textContent = parsed.toLocaleString();
      updatedTime.dateTime = parsed.toISOString();
      updatedWrapper.classList.remove('hidden');
    } else {
      updatedTime.textContent = '';
      updatedTime.removeAttribute('dateTime');
      updatedWrapper.classList.add('hidden');
    }
  }

  if (state.diagnosticsVisible) {
    panel.classList.remove('hidden');
    toggle.textContent = 'Hide details';
    toggle.setAttribute('aria-expanded', 'true');
  } else {
    panel.classList.add('hidden');
    toggle.textContent = 'Show details';
    toggle.setAttribute('aria-expanded', 'false');
  }

  if (!state.diagnostics) {
    renderDiagnosticsRuntime(null);
    renderDiagnosticsSettings(null);
    renderDiagnosticsFeatures(null);
    renderDiagnosticsPackages([]);
    renderDiagnosticsWarnings([]);
    return;
  }

  renderDiagnosticsRuntime(state.diagnostics.runtime);
  renderDiagnosticsSettings(state.diagnostics.settings);
  renderDiagnosticsFeatures(state.diagnostics.features);
  renderDiagnosticsPackages(state.diagnostics.packages);
  renderDiagnosticsWarnings(state.diagnostics.warnings);
}

function renderDiagnosticsRuntime(runtime) {
  const container = document.getElementById('diagnosticsRuntime');
  if (!container) return;
  if (!runtime) {
    container.innerHTML = '<p class="text-gray-400">Runtime metadata unavailable.</p>';
    return;
  }
  const started = formatTimestamp(runtime.started_at);
  const rows = [
    { label: 'Started', value: started ? started.toLocaleString() : '—' },
    {
      label: 'Uptime',
      value:
        typeof runtime.uptime_seconds === 'number'
          ? `${runtime.uptime_seconds.toFixed(1)}s`
          : '—',
    },
    { label: 'PID', value: runtime.pid != null ? String(runtime.pid) : '—' },
    { label: 'Version', value: runtime.version || '—' },
    { label: 'Environment', value: runtime.environment || '—' },
    { label: 'Commit', value: runtime.commit_sha || '—' },
  ];
  container.innerHTML = rows
    .map(
      ({ label, value }) =>
        `<div class="flex justify-between gap-2"><dt class="font-semibold text-gray-700">${escapeHtml(label)}</dt><dd class="text-right">${escapeHtml(String(value))}</dd></div>`
    )
    .join('');
}

function renderDiagnosticsSettings(settings) {
  const container = document.getElementById('diagnosticsSettings');
  if (!container) return;
  if (!settings) {
    container.innerHTML = '<p class="text-gray-400">Settings payload unavailable.</p>';
    return;
  }
  const rate = settings.rate_limit || {};
  const lease = settings.lease || {};
  const extensions = settings.extensions || {};
  const modules = Array.isArray(extensions.modules)
    ? extensions.modules
        .filter(Boolean)
        .map((item) => escapeHtml(String(item)))
        .join(', ')
    : '';
  const registeredCount = Array.isArray(extensions.registered)
    ? extensions.registered.length
    : 0;
  const rateLabel = rate.enabled
    ? `${rate.requests ?? '—'} req / ${rate.window_seconds ?? '—'}s`
    : 'Disabled';
  container.innerHTML = `
    <div class="flex justify-between gap-2"><dt class="font-semibold text-gray-700">Lease duration</dt><dd class="text-right">${escapeHtml(String(lease.duration_seconds ?? '—'))}s</dd></div>
    <div class="flex justify-between gap-2"><dt class="font-semibold text-gray-700">Rate limit</dt><dd class="text-right">${escapeHtml(rateLabel)}</dd></div>
    <div class="flex justify-between gap-2"><dt class="font-semibold text-gray-700">Modules</dt><dd class="text-right">${modules || 'None'}</dd></div>
    <div class="flex justify-between gap-2"><dt class="font-semibold text-gray-700">Registered extensions</dt><dd class="text-right">${registeredCount}</dd></div>
  `;
}

function renderDiagnosticsFeatures(features) {
  const list = document.getElementById('diagnosticsFeatures');
  if (!list) return;
  if (!features || typeof features !== 'object') {
    list.innerHTML = '<li class="text-gray-400">Feature data unavailable.</li>';
    return;
  }
  const entries = Object.entries(features)
    .sort(([a], [b]) => a.localeCompare(b));
  if (!entries.length) {
    list.innerHTML = '<li class="text-gray-400">Feature data unavailable.</li>';
    return;
  }
  list.innerHTML = entries
    .map(([key, value]) => {
      const label = escapeHtml(key.replace(/_/g, ' '));
      if (typeof value === 'boolean') {
        const icon = value ? '✅' : '⚠️';
        const tone = value ? 'text-green-700' : 'text-amber-700';
        const descriptor = value ? 'Enabled' : 'Disabled';
        return `<li><span class="${tone} font-semibold">${icon}</span> ${label}: <span>${descriptor}</span></li>`;
      }
      return `<li><span class="font-semibold text-gray-700">${label}:</span> ${escapeHtml(String(value))}</li>`;
    })
    .join('');
}

function renderDiagnosticsPackages(packages) {
  const tbody = document.getElementById('diagnosticsPackages');
  if (!tbody) return;
  if (!Array.isArray(packages) || !packages.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="border px-2 py-2 text-sm text-gray-500">No package data reported.</td></tr>';
    return;
  }
  const statusStyles = {
    ok: { label: 'OK', classes: 'bg-green-100 text-green-700' },
    mismatch: { label: 'Mismatch', classes: 'bg-amber-100 text-amber-700' },
    missing: { label: 'Missing', classes: 'bg-red-100 text-red-700' },
  };
  tbody.innerHTML = packages
    .map((pkg) => {
      const status = statusStyles[pkg.status] || {
        label: pkg.status,
        classes: 'bg-gray-100 text-gray-700',
      };
      const installed = pkg.installed ? escapeHtml(pkg.installed) : '—';
      const required = pkg.required ? escapeHtml(pkg.required) : '—';
      const name = pkg.homepage
        ? `<a class="text-blue-600 hover:underline" href="${escapeHtml(pkg.homepage)}" target="_blank" rel="noopener">${escapeHtml(pkg.name)}</a>`
        : escapeHtml(pkg.name);
      const summary = pkg.summary ? `<div class="text-xs text-gray-500">${escapeHtml(pkg.summary)}</div>` : '';
      return `
        <tr>
          <td class="border px-2 py-1 align-top">${name}${summary}</td>
          <td class="border px-2 py-1 align-top">${installed}</td>
          <td class="border px-2 py-1 align-top">${required}</td>
          <td class="border px-2 py-1 align-top"><span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold ${status.classes}">${escapeHtml(status.label)}</span></td>
        </tr>
      `;
    })
    .join('');
}

function renderDiagnosticsWarnings(warnings) {
  const list = document.getElementById('diagnosticsWarnings');
  if (!list) return;
  if (!Array.isArray(warnings) || warnings.length === 0) {
    list.innerHTML = '<li class="text-gray-400">No warnings reported.</li>';
    return;
  }
  list.innerHTML = warnings
    .map((warning) => `<li>• ${escapeHtml(String(warning))}</li>`)
    .join('');
}

async function refreshConfiguration({ silent = false } = {}) {
  if (state.configurationLoading) {
    return;
  }
  state.configurationLoading = true;
  renderConfiguration();
  try {
    const payload = await apiFetchJson('/api/configuration');
    state.configuration = payload;
    state.configurationFetchedAt = new Date().toISOString();
  } catch (error) {
    console.error('Failed to load configuration', error);
    if (!silent) {
      showToast('Unable to load configuration. Try again shortly.', 'error');
    }
  } finally {
    state.configurationLoading = false;
    renderConfiguration();
  }
}

async function refreshDiagnostics({ silent = false } = {}) {
  if (state.diagnosticsLoading) {
    return;
  }
  state.diagnosticsLoading = true;
  renderDiagnostics();
  try {
    const payload = await apiFetchJson('/api/diagnostics');
    state.diagnostics = payload;
    state.diagnosticsFetchedAt = payload.generated_at || new Date().toISOString();
    renderDiagnostics();
  } catch (error) {
    console.error('Failed to load diagnostics', error);
    if (!silent) {
      showToast('Unable to load diagnostics. Try again shortly.', 'error');
    }
  } finally {
    state.diagnosticsLoading = false;
    renderDiagnostics();
  }
}

function toggleDiagnosticsPanel() {
  state.diagnosticsVisible = !state.diagnosticsVisible;
  renderDiagnostics();
  if (state.diagnosticsVisible && !state.diagnostics && !state.diagnosticsLoading) {
    refreshDiagnostics({ silent: true });
  }
}

function applySystemState(payload) {
  if (!payload || typeof payload !== 'object') {
    return;
  }
  const enabled = Boolean(payload.maintenance_mode);
  const message = typeof payload.message === 'string' ? payload.message.trim() : null;
  const updatedAt = payload.updated_at || null;
  const version = typeof payload.version === 'number' ? payload.version : null;
  state.systemState = {
    maintenance_mode: enabled,
    message: message || null,
    updated_at: updatedAt,
    version,
  };
  if (state.diagnostics && typeof state.diagnostics === 'object') {
    state.diagnostics.system_state = {
      maintenance_mode: state.systemState.maintenance_mode,
      message: state.systemState.message,
      updated_at: state.systemState.updated_at,
      version: state.systemState.version,
    };
    renderDiagnostics();
  }
  renderMaintenanceState();
}

function renderMaintenanceState() {
  const summary = document.getElementById('maintenanceSummary');
  if (!summary) return;
  const details = document.getElementById('maintenanceDetails');
  const updatedWrapper = document.getElementById('maintenanceUpdatedWrapper');
  const updated = document.getElementById('maintenanceUpdated');
  const banner = document.getElementById('maintenanceBanner');
  const bannerText = document.getElementById('maintenanceBannerText');
  const bannerMessage = document.getElementById('maintenanceBannerMessage');
  const toggle = document.getElementById('maintenanceToggle');
  const messageInput = document.getElementById('maintenanceMessageInput');
  const adminInput = document.getElementById('adminTokenInput');

  const { maintenance_mode: enabled, message, updated_at: updatedAt } = state.systemState;

  summary.textContent = enabled
    ? 'Maintenance mode enabled — new checkouts are paused.'
    : 'Maintenance mode disabled — agents may checkout tasks.';

  if (details) {
    if (message) {
      details.textContent = message;
      details.classList.remove('hidden');
    } else {
      details.textContent = '';
      details.classList.add('hidden');
    }
  }

  if (updated && updatedWrapper) {
    if (updatedAt) {
      const parsed = new Date(updatedAt);
      if (!Number.isNaN(parsed.valueOf())) {
        updated.textContent = parsed.toLocaleString();
        updated.dateTime = parsed.toISOString();
      } else {
        updated.textContent = updatedAt;
        updated.removeAttribute('dateTime');
      }
      updatedWrapper.classList.remove('hidden');
    } else {
      updated.textContent = '';
      updated.removeAttribute('dateTime');
      updatedWrapper.classList.add('hidden');
    }
  }

  if (banner) {
    if (enabled) {
      banner.classList.remove('hidden');
      if (bannerText) {
        bannerText.textContent = 'Maintenance mode is active. New task checkouts are paused.';
      }
      if (bannerMessage) {
        bannerMessage.textContent = message || 'Continue working on in-progress tasks or stand by.';
      }
    } else {
      banner.classList.add('hidden');
      if (bannerMessage) {
        bannerMessage.textContent = '';
      }
    }
  }

  if (toggle) {
    toggle.checked = Boolean(enabled);
    toggle.setAttribute('aria-checked', enabled ? 'true' : 'false');
  }

  if (messageInput && document.activeElement !== messageInput) {
    messageInput.value = message || '';
  }

  if (adminInput && !adminInput.dataset.dirty) {
    adminInput.value = loadAdminToken();
  }
}

function renderTaskList() {
  const container = document.getElementById('tasks');
  if (!container) return;
  const tasks = state.filter === 'all'
    ? state.tasks
    : state.tasks.filter((task) => task.status === state.filter);

  if (!tasks.length) {
    container.innerHTML = '<p class="text-sm text-gray-600">No tasks match this filter yet—create one or try a different status.</p>';
    return;
  }

  const rows = tasks
    .map((task) => {
      const badgeClass = STATUS_BADGE_CLASSES[task.status] || 'bg-gray-100 text-gray-800';
      const statusLabel = escapeHtml(formatStatusLabel(task.status));
      const dependencies = renderDependencies(task);
      const actionButtons = [];
      if (task.status === 'pending') {
        actionButtons.push(`
          <button class="px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 focus:outline-none focus:ring" data-action="start" data-task-id="${task.id}">Start</button>
        `);
      }
      actionButtons.push(`
        <button class="px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700 focus:outline-none focus:ring" data-action="complete" data-task-id="${task.id}">Complete</button>
      `);
      actionButtons.push(`
        <button class="px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 focus:outline-none focus:ring" data-action="delete" data-task-id="${task.id}">Delete</button>
      `);

      return `
        <tr>
          <td class="border px-2 py-1 align-top">${task.id}</td>
          <td class="border px-2 py-1 align-top">
            <div class="font-medium">${escapeHtml(task.title)}</div>
            ${task.description ? `<p class="text-xs text-gray-500 mt-1">${escapeHtml(task.description)}</p>` : ''}
          </td>
          <td class="border px-2 py-1 align-top">
            <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold ${badgeClass}">${statusLabel}</span>
          </td>
          <td class="border px-2 py-1 align-top">${dependencies}</td>
          <td class="border px-2 py-1 align-top">
            <div class="flex flex-col sm:flex-row gap-2">
              ${actionButtons.join('')}
            </div>
          </td>
        </tr>
      `;
    })
    .join('');

  // TODO(P2, 4d) - Replace innerHTML templating with DOM diffing to improve performance on large task lists.
  container.innerHTML = `
    <div class="overflow-x-auto">
      <table class="w-full text-sm border-collapse">
        <thead>
          <tr class="bg-gray-100 text-left">
            <th class="border px-2 py-1">ID</th>
            <th class="border px-2 py-1">Title</th>
            <th class="border px-2 py-1">Status</th>
            <th class="border px-2 py-1">Depends On</th>
            <th class="border px-2 py-1">Actions</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderDependencies(task) {
  if (!Array.isArray(task.depends_on) || task.depends_on.length === 0) {
    return '<span class="text-gray-400">None</span>';
  }

  const chips = task.depends_on.map((depId) => {
    const depTask = state.tasksById.get(depId);
    const tooltip = depTask
      ? `${depTask.title} (#${depTask.id}) • ${formatStatusLabel(depTask.status)}`
      : `Task #${depId} (not found)`;
    return `<span class="tooltip-chip" tabindex="0" data-tooltip="${escapeHtml(tooltip)}">#${depId}</span>`;
  });

  return `<div class="chip-row">${chips.join('')}</div>`;
}

async function refreshPlan() {
  try {
    const plan = await apiFetchJson('/api/plan');
    state.tasks = Array.isArray(plan.tasks) ? plan.tasks : [];
    state.tasksById = new Map(state.tasks.map((task) => [task.id, task]));
    state.planVersion = plan.version;
    state.planUpdatedAt = plan.updated_at;
    renderPlanMeta();
    renderTaskList();
    refreshAnalytics({ silent: true });
  } catch (error) {
    console.error('Failed to refresh plan', error);
    if (!state.tasks.length) {
      const container = document.getElementById('tasks');
      if (container) {
        container.innerHTML = '<p class="text-sm text-red-600">Unable to load tasks. Please retry once the connection is restored.</p>';
      }
    }
  }
}

async function refreshAnalytics({ silent = false } = {}) {
  if (!silent) {
    const summary = document.getElementById('analyticsSummary');
    if (summary) {
      summary.textContent = 'Loading task analytics…';
    }
  }
  try {
    const payload = await apiFetchJson('/api/tasks/analytics');
    state.taskAnalytics = payload;
    state.taskAnalyticsFetchedAt = new Date().toISOString();
    renderAnalytics();
  } catch (error) {
    console.error('Failed to load task analytics', error);
    state.taskAnalytics = null;
    state.taskAnalyticsFetchedAt = null;
    renderAnalytics();
    if (!silent) {
      showToast('Unable to load task analytics at the moment.', 'error');
    }
  }
}

async function refreshSystemState({ silent = false } = {}) {
  try {
    const payload = await apiFetchJson('/api/system-state');
    applySystemState(payload);
  } catch (error) {
    console.error('Failed to refresh system state', error);
    if (!silent) {
      showToast('Unable to load system status. Some controls may be stale.', 'error');
    }
  }
}

function startPing() {
  if (wsPingTimer) clearInterval(wsPingTimer);
  wsPingTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send('ping');
    }
  }, PING_INTERVAL_MS);
}

function stopPing() {
  if (wsPingTimer) {
    clearInterval(wsPingTimer);
    wsPingTimer = undefined;
  }
}

function connectWS() {
  const scheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
  ws = new WebSocket(`${scheme}${window.location.host}/ws/plan`);

  ws.onopen = () => {
    if (reconnectAttempts > 0) {
      console.log(`ws reconnected after ${reconnectAttempts} attempt${reconnectAttempts === 1 ? '' : 's'}`);
    } else {
      console.log('ws open');
    }
    reconnectAttempts = 0;
    startPing();
  };

  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.state) {
        applySystemState(message.state);
      }
      if (message.type === 'plan_version') {
        refreshPlan();
      } else if (message.type === 'plan_snapshot') {
        refreshPlan();
      } else if (message.type === 'system_state') {
        // already applied above; refresh if payload omitted state details
        if (!message.state) {
          refreshSystemState({ silent: true });
        }
      }
    } catch (error) {
      console.warn('Failed to parse websocket payload', error);
    }
  };

  ws.onclose = () => {
    stopPing();
    reconnectAttempts += 1;
    console.warn(`ws closed; reconnecting in ${WS_RECONNECT_DELAY_MS / 1000}s (attempt #${reconnectAttempts})`);
    // TODO(P1, 1d) - Switch to exponential backoff with jitter to avoid synchronized reconnect storms.
    setTimeout(connectWS, WS_RECONNECT_DELAY_MS);
  };
}

function parseDependencies(input) {
  if (!input) return [];
  return input
    .split(',')
    .map((token) => token.trim())
    .filter(Boolean)
    .map((token) => Number.parseInt(token, 10))
    .filter((value) => !Number.isNaN(value));
}

async function handleCreateTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const title = formData.get('title');
  const description = formData.get('description') || '';
  const dependsRaw = formData.get('depends_on') || '';

  if (!title || !String(title).trim()) {
    showToast('Please provide a title for the task.', 'error');
    return;
  }

  const payload = {
    title: String(title).trim(),
    description: String(description || ''),
    depends_on: parseDependencies(String(dependsRaw || '')),
  };

  try {
    await apiFetchJson('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    form.reset();
    showToast('Task created successfully.', 'success');
    await refreshPlan();
  } catch (error) {
    console.error('Failed to create task', error);
  }
}

async function completeTask(taskId) {
  const task = state.tasksById.get(taskId);
  const title = task ? task.title : `#${taskId}`;
  const confirmMessage = `Mark task ${title} as complete?`;
  if (!window.confirm(confirmMessage)) return;
  try {
    await apiFetch(`/api/tasks/${taskId}/complete?agent_id=admin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: 'UI complete' }),
    });
    showToast(`Task #${taskId} marked complete.`, 'success');
    await refreshPlan();
  } catch (error) {
    console.error('Failed to complete task', error);
  }
}

async function startTask(taskId) {
  try {
    const result = await apiFetchJson(`/api/tasks/checkout?agent_id=admin&task_id=${taskId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (result && result.task) {
      showToast(`Task #${taskId} started.`, 'success');
    } else {
      let message = `Task #${taskId} could not be started.`;
      if (result && result.reason) {
        if (result.reason === 'task_not_found') {
          message = `Task #${taskId} no longer exists.`;
        } else if (result.reason === 'task_not_available') {
          message = `Task #${taskId} is not available to start.`;
        } else if (result.reason === 'no_available_tasks') {
          message = 'No tasks are currently available to start.';
        } else if (result.reason === 'maintenance_mode') {
          const detail = result.message || 'Maintenance mode is active; checkouts are paused.';
          message = detail;
          await refreshSystemState({ silent: true });
        }
      }
      showToast(message, 'error');
    }
    await refreshPlan();
  } catch (error) {
    console.error('Failed to start task', error);
  }
}

async function deleteTask(taskId) {
  const task = state.tasksById.get(taskId);
  const title = task ? task.title : `#${taskId}`;
  const confirmMessage = `Delete task ${title}? This cannot be undone.`;
  if (!window.confirm(confirmMessage)) return;
  try {
    await apiFetch(`/api/tasks/${taskId}`, {
      method: 'DELETE',
    });
    showToast(`Task #${taskId} deleted.`, 'success');
    await refreshPlan();
  } catch (error) {
    console.error('Failed to delete task', error);
  }
}

function handleTaskAction(event) {
  const actionButton = event.target.closest('[data-action]');
  if (!actionButton) return;
  const taskId = Number.parseInt(actionButton.dataset.taskId || '', 10);
  if (Number.isNaN(taskId)) return;
  const action = actionButton.dataset.action;
  if (action === 'start') {
    startTask(taskId);
  } else if (action === 'complete') {
    completeTask(taskId);
  } else if (action === 'delete') {
    deleteTask(taskId);
  }
}

async function handleMaintenanceSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const toggle = form.querySelector('#maintenanceToggle');
  const messageInput = form.querySelector('#maintenanceMessageInput');
  const tokenInput = form.querySelector('#adminTokenInput');
  const enabled = toggle ? Boolean(toggle.checked) : false;
  const message = messageInput ? messageInput.value.trim() : '';
  const token = tokenInput ? tokenInput.value.trim() : '';

  persistAdminToken(token);

  const actionLabel = enabled ? 'enable maintenance mode' : 'disable maintenance mode';
  if (!window.confirm(`Are you sure you want to ${actionLabel}?`)) {
    return;
  }

  const payload = {
    maintenance_mode: enabled,
    message: message || null,
  };
  if (typeof state.systemState.version === 'number') {
    payload.expected_version = state.systemState.version;
  }

  const headers = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  try {
    const response = await apiFetchJson('/api/system-state', {
      method: 'PUT',
      headers,
      body: JSON.stringify(payload),
    });
    applySystemState(response);
    showToast('System state updated.', 'success');
  } catch (error) {
    console.error('Failed to update system state', error);
    if (error && error.response && error.response.status === 409) {
      showToast('System state update conflicted. Reloading latest state.', 'error');
      await refreshSystemState({ silent: true });
    }
  }
}

function initEventListeners() {
  const filter = document.getElementById('statusFilter');
  if (filter) {
    filter.addEventListener('change', (event) => {
      state.filter = event.target.value;
      renderTaskList();
    });
  }

  const refreshButton = document.getElementById('refreshTasks');
  if (refreshButton) {
    refreshButton.addEventListener('click', (event) => {
      event.preventDefault();
      refreshPlan();
    });
  }

  const createForm = document.getElementById('createTask');
  if (createForm) {
    createForm.addEventListener('submit', handleCreateTask);
  }

  const tasksContainer = document.getElementById('tasks');
  if (tasksContainer) {
    tasksContainer.addEventListener('click', handleTaskAction);
  }

  const maintenanceForm = document.getElementById('maintenanceForm');
  if (maintenanceForm) {
    maintenanceForm.addEventListener('submit', handleMaintenanceSubmit);
  }

  const diagnosticsToggle = document.getElementById('toggleDiagnostics');
  if (diagnosticsToggle) {
    diagnosticsToggle.addEventListener('click', (event) => {
      event.preventDefault();
      toggleDiagnosticsPanel();
    });
  }

  const diagnosticsRefresh = document.getElementById('refreshDiagnostics');
  if (diagnosticsRefresh) {
    diagnosticsRefresh.addEventListener('click', (event) => {
      event.preventDefault();
      refreshDiagnostics();
    });
  }

  const configurationRefresh = document.getElementById('refreshConfiguration');
  if (configurationRefresh) {
    configurationRefresh.addEventListener('click', (event) => {
      event.preventDefault();
      refreshConfiguration();
    });
  }

  const analyticsRefresh = document.getElementById('refreshAnalytics');
  if (analyticsRefresh) {
    analyticsRefresh.addEventListener('click', (event) => {
      event.preventDefault();
      refreshAnalytics();
    });
  }

  const adminTokenInput = document.getElementById('adminTokenInput');
  if (adminTokenInput) {
    adminTokenInput.value = loadAdminToken();
    adminTokenInput.addEventListener('input', (event) => {
      event.currentTarget.dataset.dirty = 'true';
    });
    adminTokenInput.addEventListener('blur', (event) => {
      persistAdminToken(event.currentTarget.value.trim());
    });
  }

  const clearTokenButton = document.getElementById('clearAdminToken');
  if (clearTokenButton) {
    clearTokenButton.addEventListener('click', () => {
      persistAdminToken('');
      const field = document.getElementById('adminTokenInput');
      if (field) {
        field.value = '';
        delete field.dataset.dirty;
      }
      showToast('Admin token cleared for this browser session.', 'success');
    });
  }
}

function initialize() {
  initEventListeners();
  connectWS();
  renderMaintenanceState();
  renderConfiguration();
  renderDiagnostics();
  renderAnalytics();
  refreshPlan();
  refreshSystemState();
  refreshConfiguration({ silent: true });
  refreshDiagnostics({ silent: true });
  refreshAnalytics({ silent: true });
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('.copy-button');
  if (!button) {
    return;
  }
  const value = button.dataset.copyValue || '';
  if (!value) {
    return;
  }
  const label = button.dataset.copyLabel || 'Value';
  copyToClipboard(value, label);
});

document.addEventListener('DOMContentLoaded', initialize);
