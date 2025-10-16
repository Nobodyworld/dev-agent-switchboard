const state = {
  tasks: [],
  tasksById: new Map(),
  filter: 'all',
  planVersion: null,
  planUpdatedAt: null,
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
              <button class="px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700 focus:outline-none focus:ring" data-action="complete" data-task-id="${task.id}">Complete</button>
              <button class="px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 focus:outline-none focus:ring" data-action="delete" data-task-id="${task.id}">Delete</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join('');

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
      if (message.type === 'plan_version') {
        refreshPlan();
      }
    } catch (error) {
      console.warn('Failed to parse websocket payload', error);
    }
  };

  ws.onclose = () => {
    stopPing();
    reconnectAttempts += 1;
    console.warn(`ws closed; reconnecting in ${WS_RECONNECT_DELAY_MS / 1000}s (attempt #${reconnectAttempts})`);
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
  if (action === 'complete') {
    completeTask(taskId);
  } else if (action === 'delete') {
    deleteTask(taskId);
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
}

function initialize() {
  initEventListeners();
  connectWS();
  refreshPlan();
}

document.addEventListener('DOMContentLoaded', initialize);
