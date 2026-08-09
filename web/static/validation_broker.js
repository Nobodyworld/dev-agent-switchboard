import {
  apiFetchJson,
  escapeHtml,
  loadAdminToken,
  showToast,
} from './app.js';

const POLL_INTERVAL_MS = 4000;
const HISTORY_LIMIT = 25;
const ACTIVE_WORK_ORDER_STATUSES = new Set([
  'pending_approval',
  'approved',
  'queued',
  'assigned',
  'running',
]);
const TERMINAL_WORK_ORDER_STATUSES = new Set([
  'succeeded',
  'failed',
  'timed_out',
  'cancelled',
  'rejected',
  'expired',
]);

const brokerState = {
  overview: null,
  manifests: [],
  workers: [],
  history: [],
  historyTotal: 0,
  historyOffset: 0,
  selectedRequest: null,
  selectedProjection: null,
  selectedRoute: null,
  selectedRun: null,
  pollTimer: null,
};

function authorizedHeaders({ json = true } = {}) {
  const headers = {};
  if (json) headers['Content-Type'] = 'application/json';
  const token = loadAdminToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

function setBrokerStatus(message, tone = '') {
  const element = document.getElementById('brokerStatus');
  if (!element) return;
  element.textContent = message;
  if (tone) element.dataset.tone = tone;
  else delete element.dataset.tone;
}

function setProfileStatus(message, tone = '') {
  const element = document.getElementById('profileStatus');
  if (!element) return;
  element.textContent = message;
  if (tone) element.dataset.tone = tone;
  else delete element.dataset.tone;
}

function formatInteger(value) {
  if (value === null || value === undefined || value === '') return '—';
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : '—';
}

function formatSeconds(value) {
  if (!Number.isFinite(Number(value))) return '—';
  const seconds = Number(value);
  if (seconds < 60) return `${seconds.toFixed(seconds % 1 ? 1 : 0)} s`;
  return `${(seconds / 60).toFixed(1)} min`;
}

function formatPercent(value) {
  return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '—';
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? '—' : date.toLocaleString();
}

function formatQuotaReset(value) {
  if (!value) return 'Not scheduled';
  const formatted = formatDate(value);
  return formatted === '—' ? 'Not available' : formatted;
}

function timezoneAwareIso(value) {
  if (!value) return null;
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.valueOf()) ? null : date.toISOString();
}

function formatLabel(value) {
  return value ? String(value).replaceAll('_', ' ') : '—';
}

function shortSha(value) {
  return value ? String(value).slice(0, 8) : '—';
}

function badge(value, tone = '') {
  const attribute = tone ? ` data-tone="${tone}"` : '';
  return `<span class="broker-badge"${attribute}>${escapeHtml(formatLabel(value))}</span>`;
}

function stateTone(value) {
  if (['succeeded', 'reused', 'published_current', 'active', 'online'].includes(value)) {
    return 'success';
  }
  if (['fresh'].includes(value)) return 'fresh';
  if (
    ['failed', 'timed_out', 'cancelled', 'expired', 'published_stale', 'stale'].includes(value)
  ) {
    return 'warning';
  }
  return '';
}

function renderMetrics() {
  const container = document.getElementById('brokerMetrics');
  if (!container) return;
  const overview = brokerState.overview;
  if (!overview) {
    container.innerHTML = '<p class="broker-empty">Metrics are unavailable.</p>';
    return;
  }
  const cards = [
    ['Deterministic executions avoided', overview.avoided_work.deterministic_executions_avoided],
    ['Reference execution time avoided', formatSeconds(overview.avoided_work.reference_seconds_avoided)],
    ['Comparison units avoided', overview.avoided_work.comparison_units_avoided],
    ['Fresh successful runs', overview.runs.fresh_successful],
    ['Reused successful runs', overview.runs.reused_successful],
    ['Reuse rate', formatPercent(overview.avoided_work.reuse_rate)],
    ['Current publications', overview.publications.current],
    ['Stale publications', overview.publications.stale],
  ];
  container.innerHTML = cards
    .map(
      ([label, value]) => `
        <dl class="broker-metric">
          <dt>${escapeHtml(label)}</dt>
          <dd>${typeof value === 'number' ? formatInteger(value) : escapeHtml(value)}</dd>
        </dl>
      `
    )
    .join('');
}

function renderManifestChoices() {
  const select = document.getElementById('validationManifest');
  if (!select) return;
  const previous = select.value;
  select.innerHTML = brokerState.manifests.length
    ? brokerState.manifests
        .map(
          (manifest) =>
            `<option value="${escapeHtml(`${manifest.name}@${manifest.version}`)}">${escapeHtml(manifest.name)} v${escapeHtml(manifest.version)}</option>`
        )
        .join('')
    : '<option value="">No trusted manifests available</option>';
  if (previous && Array.from(select.options).some((option) => option.value === previous)) {
    select.value = previous;
  }
}

function renderWorkerChoices() {
  const preferred = document.getElementById('validationPreferredExecutor');
  const profileWorker = document.getElementById('profileWorker');
  if (!preferred || !profileWorker) return;
  const preferredValue = preferred.value;
  const profileValue = profileWorker.value;
  const options = brokerState.workers
    .map(
      (worker) =>
        `<option value="${escapeHtml(worker.worker_id)}">${escapeHtml(worker.display_name)} · ${escapeHtml(worker.worker_id)}</option>`
    )
    .join('');
  preferred.innerHTML = `<option value="">Any capable worker</option>${options}`;
  profileWorker.innerHTML = brokerState.workers.length
    ? `<option value="">Choose a worker</option>${options}`
    : '<option value="">No workers registered</option>';
  if (preferredValue) preferred.value = preferredValue;
  if (profileValue) profileWorker.value = profileValue;
}

function renderWorkers() {
  const container = document.getElementById('brokerWorkers');
  if (!container) return;
  if (!brokerState.workers.length) {
    container.innerHTML = '<p class="broker-empty">No execution workers are registered.</p>';
    return;
  }
  container.innerHTML = brokerState.workers
    .map((worker) => {
      const profile = worker.profile;
      const browsers = Array.isArray(worker.browsers) && worker.browsers.length
        ? worker.browsers.join(', ')
        : 'Not reported';
      const profileDetails = profile
        ? `
          <dl>
            <div><dt>Profile</dt><dd>${badge(profile.enabled ? 'enabled' : 'disabled', profile.enabled ? 'success' : 'warning')}</dd></div>
            <div><dt>Comparison units</dt><dd>${formatInteger(profile.estimated_cost_units_per_run)}</dd></div>
            <div><dt>Revision</dt><dd>${formatInteger(profile.revision)}</dd></div>
            <div><dt>Quota</dt><dd>${formatInteger(profile.quota_remaining_units)} / ${formatInteger(profile.quota_capacity_units)}</dd></div>
            <div><dt>Quota reset</dt><dd>${escapeHtml(formatQuotaReset(profile.quota_reset_at))}</dd></div>
            <div><dt>Priority</dt><dd>${formatInteger(profile.routing_priority)}</dd></div>
          </dl>
        `
        : '<p class="broker-help">No operator routing profile.</p>';
      return `
        <section class="broker-worker-card" data-worker-id="${escapeHtml(worker.worker_id)}">
          <header>
            <div>
              <strong>${escapeHtml(worker.display_name)}</strong>
              <p class="broker-code">${escapeHtml(worker.worker_id)}</p>
            </div>
            <div>${badge(worker.status, stateTone(worker.status))} ${badge(worker.activity_state, stateTone(worker.activity_state))}</div>
          </header>
          <dl>
            <div><dt>Platform</dt><dd>${escapeHtml(worker.operating_system)} / ${escapeHtml(worker.architecture)}</dd></div>
            <div><dt>Capacity</dt><dd>${formatInteger(worker.active_run_count)} active / ${formatInteger(worker.max_concurrency)} maximum</dd></div>
            <div><dt>Last heartbeat</dt><dd>${escapeHtml(formatDate(worker.last_heartbeat_at))}</dd></div>
            <div><dt>Last checkout poll</dt><dd>${escapeHtml(formatDate(worker.last_checkout_poll_at))}</dd></div>
          </dl>
          <dl>
            <div><dt>Python</dt><dd>${escapeHtml(worker.python_version || 'Not reported')}</dd></div>
            <div><dt>Node</dt><dd>${escapeHtml(worker.node_version || 'Not reported')}</dd></div>
            <div><dt>Docker</dt><dd>${worker.docker_available ? 'Available' : 'Unavailable'}</dd></div>
            <div><dt>Browsers</dt><dd>${escapeHtml(browsers)}</dd></div>
            <div><dt>GPU</dt><dd>${worker.gpu_available ? 'Available' : 'Unavailable'}</dd></div>
            <div><dt>Unity</dt><dd>${worker.unity_available ? 'Available' : 'Unavailable'}</dd></div>
            <div><dt>Desktop automation</dt><dd>${worker.desktop_available ? 'Available' : 'Unavailable'}</dd></div>
            <div><dt>Network</dt><dd>${escapeHtml(formatLabel(worker.network_policy_capability))}</dd></div>
            <div><dt>Repository writes</dt><dd>${worker.repository_write_capability ? 'Enabled' : 'Disabled'}</dd></div>
          </dl>
          ${profileDetails}
          <button type="button" class="broker-button broker-button--quiet" data-profile-edit="${escapeHtml(worker.worker_id)}">${profile ? 'Edit profile' : 'Create profile'}</button>
        </section>
      `;
    })
    .join('');
}

function populateProfileForm(workerId) {
  const worker = brokerState.workers.find((item) => item.worker_id === workerId);
  const form = document.getElementById('routingProfileForm');
  if (!form || !worker) return;
  const profile = worker.profile;
  form.elements.worker_id.value = worker.worker_id;
  form.elements.estimated_cost_units_per_run.value =
    profile?.estimated_cost_units_per_run ?? '';
  form.elements.quota_capacity_units.value = profile?.quota_capacity_units ?? '';
  form.elements.quota_remaining_units.value = profile?.quota_remaining_units ?? '';
  form.elements.routing_priority.value = profile?.routing_priority ?? 0;
  form.elements.enabled.checked = profile?.enabled ?? true;
  form.elements.expected_revision.value = profile?.revision ?? '';
  document.getElementById('resetProfileQuota').disabled = !profile;
  setProfileStatus(
    profile
      ? `Editing revision ${profile.revision}. A newer server revision will return a conflict.`
      : 'Creating the first operator-owned profile for this worker.'
  );
}

function currentProjectionForRequest(requestId) {
  return brokerState.history.find((item) => item.request_id === requestId) || null;
}

async function optionalDetail(url) {
  try {
    return await apiFetchJson(url, {
      headers: authorizedHeaders({ json: false }),
    });
  } catch (error) {
    if ([404, 409].includes(error?.response?.status)) return null;
    throw error;
  }
}

async function refreshSelectedDetails() {
  const request = brokerState.selectedRequest;
  brokerState.selectedRoute = null;
  brokerState.selectedRun = null;
  if (!request) return;
  const runId = brokerState.selectedProjection?.run_id || request.terminal_run_id;
  if (runId) {
    brokerState.selectedRun = await optionalDetail(`/api/execution/runs/${runId}`);
    brokerState.selectedRoute = brokerState.selectedRun?.route_provenance || null;
    return;
  }
  if (request.work_order_status === 'queued') {
    brokerState.selectedRoute = await optionalDetail(
      `/api/execution/work-orders/${request.work_order_id}/route-assessment`
    );
  }
}

function measuredDuration(run, projection) {
  if (run?.started_at && run?.finished_at) {
    const started = new Date(run.started_at);
    const finished = new Date(run.finished_at);
    if (!Number.isNaN(started.valueOf()) && !Number.isNaN(finished.valueOf())) {
      return Math.max(0, (finished.valueOf() - started.valueOf()) / 1000);
    }
  }
  return projection?.run_duration_seconds ?? null;
}

function renderRequestDetail() {
  const container = document.getElementById('brokerRequestDetail');
  const refresh = document.getElementById('refreshRequest');
  if (!container || !refresh) return;
  const request = brokerState.selectedRequest;
  if (!request) {
    refresh.disabled = true;
    container.className = 'broker-empty';
    container.textContent = 'Select a request from history or submit a new validation.';
    stopRequestPolling();
    return;
  }
  refresh.disabled = false;
  container.className = '';
  const projection = brokerState.selectedProjection || {};
  const run = brokerState.selectedRun;
  const route = brokerState.selectedRoute || run?.route_provenance || null;
  const evidence = run?.evidence_metadata || null;
  const status = request.work_order_status;
  const canApprove = status === 'pending_approval';
  const canQueue = status === 'approved';
  const canCancel = !TERMINAL_WORK_ORDER_STATUSES.has(status);
  const canExpire = ['approved', 'queued'].includes(status);
  const canPublish = Boolean(request.evidence_fingerprint);
  const selectedWorker = route?.selected_worker_id || run?.worker_id || projection.selected_worker_id;
  const reuseDecision = run?.reuse_decision || projection.reuse_decision || 'pending';
  const sourceRunId = run?.reused_from_run_id || evidence?.reuse_provenance?.source_run_id;
  const sourceFingerprint =
    run?.source_evidence_fingerprint || evidence?.reuse_provenance?.source_evidence_fingerprint;
  const evidenceFingerprint = evidence?.fingerprint || request.evidence_fingerprint;
  const duration = measuredDuration(run, projection);
  const executedSteps = Array.isArray(evidence?.steps) ? evidence.steps.length : null;
  container.innerHTML = `
    <dl class="broker-detail-list">
      <dt>Request</dt><dd>#${request.request_id}</dd>
      <dt>Repository</dt><dd>${escapeHtml(request.repository_full_name)}</dd>
      <dt>Pull request</dt><dd>#${formatInteger(request.pull_request_number)}</dd>
      <dt>Created</dt><dd>${escapeHtml(formatDate(request.created_at))}</dd>
      <dt>Last head resolution</dt><dd>${escapeHtml(formatDate(request.last_resolved_at))}</dd>
      <dt>Exact head</dt><dd><span class="broker-code">${escapeHtml(request.tested_head_sha)}</span> <button type="button" class="copy-button" data-copy-value="${escapeHtml(request.tested_head_sha)}" data-copy-label="Head SHA">Copy SHA</button></dd>
      <dt>Base SHA</dt><dd class="broker-code">${escapeHtml(request.base_sha)}</dd>
      <dt>Manifest</dt><dd>${escapeHtml(`${request.manifest_name}@${request.manifest_version}`)} <span class="broker-code">${escapeHtml(request.manifest_digest)}</span></dd>
      <dt>Work order</dt><dd>#${request.work_order_id} ${badge(status, stateTone(status))}</dd>
      <dt>Reuse policy</dt><dd>${badge(request.reuse_policy)}</dd>
      <dt>Routing policy</dt><dd>${badge(request.routing_policy)}</dd>
      <dt>Selected route</dt><dd>${escapeHtml(selectedWorker || 'Not available')}</dd>
      <dt>Route reason</dt><dd>${escapeHtml(formatLabel(route?.reason))}</dd>
      <dt>Comparison units</dt><dd>${formatInteger(route?.estimated_cost_units ?? projection.estimated_cost_units)}</dd>
      <dt>Eligible candidates</dt><dd>${formatInteger(route?.eligible_candidate_count)}</dd>
      <dt>Explicit pin</dt><dd>${route ? (route.explicit_pin_applied ? 'Applied' : 'Not applied') : 'Not available'}</dd>
      <dt>Profile revision</dt><dd>${formatInteger(route?.selected_routing_profile_revision)}</dd>
      <dt>Quota</dt><dd>${formatInteger(route?.required_quota_units ?? request.required_quota_units)} required / ${formatInteger(route?.reserved_quota_units)} reserved · ${escapeHtml(formatLabel(route?.quota_reservation_state))}</dd>
      <dt>Reuse decision</dt><dd>${badge(reuseDecision, stateTone(reuseDecision))}</dd>
      <dt>Source run</dt><dd>${sourceRunId ? `#${formatInteger(sourceRunId)}` : 'Not available'}</dd>
      <dt>Source evidence</dt><dd class="broker-code">${escapeHtml(sourceFingerprint || 'Not available')}</dd>
      <dt>Run</dt><dd>${run ? `#${run.id} ${badge(run.status, stateTone(run.status))}` : 'Not available'}</dd>
      <dt>Assigned</dt><dd>${escapeHtml(formatDate(run?.assigned_at))}</dd>
      <dt>Started</dt><dd>${escapeHtml(formatDate(run?.started_at))}</dd>
      <dt>Finished</dt><dd>${escapeHtml(formatDate(run?.finished_at))}</dd>
      <dt>Measured duration</dt><dd>${duration === null ? 'Not available' : escapeHtml(formatSeconds(duration))}</dd>
      <dt>Executed steps</dt><dd>${executedSteps === null ? 'Not available' : formatInteger(executedSteps)}</dd>
      <dt>Cleanup</dt><dd>${escapeHtml(formatLabel(run?.cleanup_status))}</dd>
      <dt>Terminal reason</dt><dd>${escapeHtml(formatLabel(run?.terminal_reason))}</dd>
      <dt>Evidence</dt><dd class="broker-code">${escapeHtml(evidenceFingerprint || 'Not available')}</dd>
      <dt>Publication</dt><dd>${badge(request.publication_state, stateTone(request.publication_state))} · ${escapeHtml(formatLabel(request.publication_decision))}</dd>
      <dt>Updated</dt><dd>${escapeHtml(formatDate(request.updated_at))}</dd>
    </dl>
    <div class="broker-action-row" data-request-actions>
      <button type="button" class="broker-button broker-button--secondary" data-request-action="approve" ${canApprove ? '' : 'disabled title="Approval is available only while pending."'}>Approve</button>
      <button type="button" class="broker-button broker-button--primary" data-request-action="approve-queue" ${canApprove ? '' : 'disabled title="Approve and queue is available only while pending."'}>Approve &amp; queue</button>
      <button type="button" class="broker-button broker-button--secondary" data-request-action="queue" ${canQueue ? '' : 'disabled title="Queue is available only after approval."'}>Queue</button>
      <button type="button" class="broker-button broker-button--danger" data-request-action="cancel" ${canCancel ? '' : 'disabled title="Terminal work cannot be cancelled."'}>Cancel</button>
      <button type="button" class="broker-button broker-button--quiet" data-request-action="expire" ${canExpire ? '' : 'disabled title="Only approved or queued work can expire."'}>Expire</button>
      <button type="button" class="broker-button broker-button--secondary" data-request-action="publish" ${canPublish ? '' : 'disabled title="Successful compact evidence is required before publication."'}>Publish evidence</button>
    </div>
    <p class="broker-help">Actions are enabled only when the persisted lifecycle permits them. Publication always rechecks the GitHub head.</p>
  `;
  syncRequestPolling();
}

function renderHistory() {
  const container = document.getElementById('brokerHistory');
  const summary = document.getElementById('brokerHistorySummary');
  const previous = document.getElementById('historyPrevious');
  const next = document.getElementById('historyNext');
  if (!container || !summary || !previous || !next) return;
  if (!brokerState.history.length) {
    container.innerHTML = '<p class="broker-empty">No validation requests match these filters.</p>';
  } else {
    const rows = brokerState.history
      .map(
        (item) => `
          <tr data-history-request="${item.request_id}">
            <td><button type="button" class="broker-button broker-button--quiet" data-select-request="${item.request_id}">#${item.request_id}</button></td>
            <td>${escapeHtml(item.repository_full_name)} #${item.pull_request_number}</td>
            <td><span class="broker-code">${escapeHtml(shortSha(item.tested_head_sha))}</span> <button type="button" class="copy-button" data-copy-value="${escapeHtml(item.tested_head_sha)}" data-copy-label="Head SHA">Copy</button></td>
            <td>${badge(item.work_order_status, stateTone(item.work_order_status))}</td>
            <td>${item.reuse_decision ? badge(item.reuse_decision, stateTone(item.reuse_decision)) : '—'}</td>
            <td>${escapeHtml(item.selected_worker_id || '—')}</td>
            <td>${formatInteger(item.estimated_cost_units)}</td>
            <td>${badge(item.publication_state, stateTone(item.publication_state))}</td>
            <td>${escapeHtml(formatDate(item.created_at))}</td>
          </tr>
        `
      )
      .join('');
    container.innerHTML = `
      <table class="broker-table">
        <thead><tr><th>Request</th><th>Source</th><th>Exact SHA</th><th>Lifecycle</th><th>Decision</th><th>Worker</th><th>Units</th><th>Publication</th><th>Created</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }
  const first = brokerState.historyTotal ? brokerState.historyOffset + 1 : 0;
  const last = Math.min(
    brokerState.historyOffset + brokerState.history.length,
    brokerState.historyTotal
  );
  summary.textContent = `Showing ${first}–${last} of ${brokerState.historyTotal} requests`;
  previous.disabled = brokerState.historyOffset === 0;
  next.disabled = brokerState.historyOffset + HISTORY_LIMIT >= brokerState.historyTotal;
}

async function refreshOverview() {
  const days = document.getElementById('brokerWindow')?.value || '30';
  brokerState.overview = await apiFetchJson(
    `/api/execution/operator/overview?window_days=${encodeURIComponent(days)}`,
    { headers: authorizedHeaders({ json: false }) }
  );
  renderMetrics();
}

async function refreshManifests() {
  brokerState.manifests = await apiFetchJson('/api/execution/manifests', {
    headers: authorizedHeaders({ json: false }),
  });
  renderManifestChoices();
}

async function refreshWorkers() {
  const page = await apiFetchJson('/api/execution/workers?limit=100&offset=0', {
    headers: authorizedHeaders({ json: false }),
  });
  brokerState.workers = Array.isArray(page.items) ? page.items : [];
  renderWorkerChoices();
  renderWorkers();
  const selectedWorker = document.getElementById('profileWorker')?.value;
  if (selectedWorker) populateProfileForm(selectedWorker);
}

function historyQuery() {
  const form = document.getElementById('brokerHistoryFilters');
  const params = new URLSearchParams({
    limit: String(HISTORY_LIMIT),
    offset: String(brokerState.historyOffset),
  });
  if (form) {
    for (const [key, rawValue] of new FormData(form).entries()) {
      const value = String(rawValue).trim();
      if (value) params.set(key, value);
    }
  }
  return params;
}

async function refreshHistory() {
  const page = await apiFetchJson(`/api/execution/operator/history?${historyQuery()}`, {
    headers: authorizedHeaders({ json: false }),
  });
  brokerState.history = Array.isArray(page.items) ? page.items : [];
  brokerState.historyTotal = Number(page.total) || 0;
  if (brokerState.selectedRequest) {
    brokerState.selectedProjection = currentProjectionForRequest(
      brokerState.selectedRequest.request_id
    );
    await refreshSelectedDetails();
    renderRequestDetail();
  }
  renderHistory();
}

async function refreshSelectedRequest({ silent = false } = {}) {
  if (!brokerState.selectedRequest) return;
  const requestId = brokerState.selectedRequest.request_id;
  try {
    brokerState.selectedRequest = await apiFetchJson(
      `/api/execution/github/requests/${requestId}`,
      { headers: authorizedHeaders({ json: false }) }
    );
    brokerState.selectedProjection = currentProjectionForRequest(requestId);
    await refreshSelectedDetails();
    renderRequestDetail();
  } catch (error) {
    console.error('Failed to refresh selected validation request', error);
    if (!silent) setBrokerStatus('Unable to refresh the selected request.', 'error');
  }
}

async function selectRequest(requestId) {
  brokerState.selectedProjection = currentProjectionForRequest(requestId);
  brokerState.selectedRequest = await apiFetchJson(
    `/api/execution/github/requests/${requestId}`,
    { headers: authorizedHeaders({ json: false }) }
  );
  await refreshSelectedDetails();
  renderRequestDetail();
  document.getElementById('brokerRequestDetail')?.scrollIntoView({
    behavior: 'smooth',
    block: 'nearest',
  });
}

function stopRequestPolling() {
  if (brokerState.pollTimer) {
    clearInterval(brokerState.pollTimer);
    brokerState.pollTimer = null;
  }
}

function syncRequestPolling() {
  stopRequestPolling();
  const status = brokerState.selectedRequest?.work_order_status;
  if (!ACTIVE_WORK_ORDER_STATUSES.has(status)) return;
  brokerState.pollTimer = setInterval(async () => {
    await refreshSelectedRequest({ silent: true });
    await refreshHistory();
    await refreshOverview();
  }, POLL_INTERVAL_MS);
}

async function refreshBrokerWorkspace({ announce = false } = {}) {
  setBrokerStatus('Refreshing bounded operator projections…');
  const results = await Promise.allSettled([
    refreshOverview(),
    refreshManifests(),
    refreshWorkers(),
    refreshHistory(),
  ]);
  const failures = results.filter((result) => result.status === 'rejected').length;
  if (failures) {
    setBrokerStatus(
      `${failures} broker surface${failures === 1 ? '' : 's'} could not be loaded. Enter the admin token above if access is protected.`,
      'error'
    );
  } else {
    const windowDays = brokerState.overview?.window?.days || 30;
    setBrokerStatus(
      `Operator projections refreshed. Metrics cover the last ${windowDays} days.`,
      'success'
    );
    if (announce) showToast('Validation broker refreshed.', 'success');
  }
}

async function handleValidationRequest(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const [manifestName, manifestVersion] = String(data.get('manifest') || '').split('@');
  const maximumCost = String(data.get('maximum_cost_units') || '').trim();
  const preferredExecutor = String(data.get('preferred_executor') || '').trim();
  const payload = {
    repository_full_name: String(data.get('repository_full_name') || '').trim(),
    pull_request_number: Number(data.get('pull_request_number')),
    manifest: { name: manifestName, version: manifestVersion },
    reuse_policy: data.get('reuse_policy'),
    routing_policy: data.get('routing_policy'),
    maximum_cost_units: maximumCost ? Number(maximumCost) : null,
    required_quota_units: Number(data.get('required_quota_units') || 0),
    preferred_executor: preferredExecutor || null,
  };
  try {
    brokerState.selectedRequest = await apiFetchJson(
      '/api/execution/github/pull-requests/validate',
      {
        method: 'POST',
        headers: authorizedHeaders(),
        body: JSON.stringify(payload),
      }
    );
    setBrokerStatus(
      `Validation request #${brokerState.selectedRequest.request_id} resolved exact head ${shortSha(brokerState.selectedRequest.tested_head_sha)}.`,
      'success'
    );
    showToast('GitHub validation request resolved.', 'success');
    await Promise.all([refreshHistory(), refreshOverview()]);
    brokerState.selectedProjection = currentProjectionForRequest(
      brokerState.selectedRequest.request_id
    );
    renderRequestDetail();
  } catch (error) {
    console.error('Failed to request GitHub validation', error);
    setBrokerStatus(
      error?.details
        ? `Validation request failed: ${error.details}`
        : 'Validation request failed. Check GitHub adapter configuration and retry.',
      'error'
    );
  }
}

async function handleProfileSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const workerId = String(data.get('worker_id') || '');
  const worker = brokerState.workers.find((item) => item.worker_id === workerId);
  if (!worker) return;
  const base = {
    enabled: form.elements.enabled.checked,
    estimated_cost_units_per_run: Number(data.get('estimated_cost_units_per_run')),
    quota_capacity_units: Number(data.get('quota_capacity_units')),
    quota_remaining_units: Number(data.get('quota_remaining_units')),
    quota_reset_at: timezoneAwareIso(worker.profile?.quota_reset_at),
    routing_priority: Number(data.get('routing_priority')),
  };
  const existing = worker.profile;
  const url = existing
    ? `/api/execution/routing-profiles/${encodeURIComponent(workerId)}`
    : '/api/execution/routing-profiles';
  const payload = existing
    ? { ...base, expected_revision: existing.revision }
    : { ...base, schema_version: 1, worker_id: workerId };
  try {
    const profile = await apiFetchJson(url, {
      method: existing ? 'PUT' : 'POST',
      headers: authorizedHeaders(),
      body: JSON.stringify(payload),
    });
    setProfileStatus(`Saved profile revision ${profile.revision}.`, 'success');
    showToast(`Routing profile for ${workerId} saved.`, 'success');
    await refreshWorkers();
    populateProfileForm(workerId);
  } catch (error) {
    if (error?.response?.status === 409) {
      await refreshWorkers();
      populateProfileForm(workerId);
      setProfileStatus('Profile revision conflicted. Latest server state was reloaded.', 'error');
    } else {
      console.error('Failed to save routing profile', error);
      setProfileStatus('Profile could not be saved.', 'error');
    }
  }
}

async function resetProfileQuota() {
  const form = document.getElementById('routingProfileForm');
  const workerId = form?.elements.worker_id.value;
  const worker = brokerState.workers.find((item) => item.worker_id === workerId);
  if (!form || !worker?.profile) return;
  const remaining = Number(form.elements.quota_remaining_units.value);
  if (!window.confirm(`Reset ${workerId} quota to ${remaining} units?`)) return;
  try {
    const profile = await apiFetchJson(
      `/api/execution/routing-profiles/${encodeURIComponent(workerId)}/quota-reset`,
      {
        method: 'POST',
        headers: authorizedHeaders(),
        body: JSON.stringify({
          expected_revision: worker.profile.revision,
          quota_remaining_units: remaining,
          quota_reset_at: new Date().toISOString(),
        }),
      }
    );
    setProfileStatus(`Quota reset recorded at revision ${profile.revision}.`, 'success');
    await refreshWorkers();
    populateProfileForm(workerId);
  } catch (error) {
    if (error?.response?.status === 409) {
      await refreshWorkers();
      populateProfileForm(workerId);
      setProfileStatus('Quota reset conflicted. Latest profile was reloaded.', 'error');
    } else {
      console.error('Failed to reset routing quota', error);
    }
  }
}

async function mutateSelectedRequest(action) {
  const request = brokerState.selectedRequest;
  if (!request) return;
  let url;
  let body;
  let confirmMessage;
  if (action === 'approve' || action === 'approve-queue') {
    url = `/api/execution/work-orders/${request.work_order_id}/approve`;
    body = { queue: action === 'approve-queue' };
  } else if (action === 'queue') {
    url = `/api/execution/work-orders/${request.work_order_id}/queue`;
  } else if (action === 'cancel' || action === 'expire') {
    confirmMessage = `${formatLabel(action)} work order #${request.work_order_id}?`;
    url = `/api/execution/work-orders/${request.work_order_id}/${action}`;
    body = { reason: `operator_${action}` };
  } else if (action === 'publish') {
    confirmMessage = `Publish compact evidence for request #${request.request_id}? The GitHub head will be rechecked.`;
    url = `/api/execution/github/requests/${request.request_id}/publish`;
  }
  if (!url || (confirmMessage && !window.confirm(confirmMessage))) return;
  try {
    await apiFetchJson(url, {
      method: 'POST',
      headers: authorizedHeaders({ json: body !== undefined }),
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    showToast(`${formatLabel(action)} completed.`, 'success');
    await Promise.all([
      refreshSelectedRequest({ silent: true }),
      refreshHistory(),
      refreshOverview(),
      refreshWorkers(),
    ]);
  } catch (error) {
    console.error(`Failed request action ${action}`, error);
    if (error?.response?.status === 409) {
      setBrokerStatus('Lifecycle action conflicted. Latest request state was reloaded.', 'error');
      await refreshSelectedRequest({ silent: true });
    }
  }
}

function initBrokerEvents() {
  document.getElementById('refreshBroker')?.addEventListener('click', () => {
    refreshBrokerWorkspace({ announce: true });
  });
  document.getElementById('brokerWindow')?.addEventListener('change', refreshOverview);
  document.getElementById('validationRequestForm')?.addEventListener(
    'submit',
    handleValidationRequest
  );
  document.getElementById('routingProfileForm')?.addEventListener(
    'submit',
    handleProfileSubmit
  );
  document.getElementById('profileWorker')?.addEventListener('change', (event) => {
    if (event.currentTarget.value) populateProfileForm(event.currentTarget.value);
  });
  document.getElementById('resetProfileQuota')?.addEventListener('click', resetProfileQuota);
  document.getElementById('refreshRequest')?.addEventListener('click', () => {
    refreshSelectedRequest();
  });
  document.getElementById('brokerHistoryFilters')?.addEventListener('submit', (event) => {
    event.preventDefault();
    brokerState.historyOffset = 0;
    refreshHistory();
  });
  document.getElementById('historyPrevious')?.addEventListener('click', () => {
    brokerState.historyOffset = Math.max(0, brokerState.historyOffset - HISTORY_LIMIT);
    refreshHistory();
  });
  document.getElementById('historyNext')?.addEventListener('click', () => {
    brokerState.historyOffset += HISTORY_LIMIT;
    refreshHistory();
  });
  document.getElementById('validation-broker')?.addEventListener('click', (event) => {
    const selectButton = event.target.closest('[data-select-request]');
    if (selectButton) {
      selectRequest(Number(selectButton.dataset.selectRequest));
      return;
    }
    const editButton = event.target.closest('[data-profile-edit]');
    if (editButton) {
      populateProfileForm(editButton.dataset.profileEdit);
      document.getElementById('profileWorker')?.focus();
      return;
    }
    const actionButton = event.target.closest('[data-request-action]');
    if (actionButton && !actionButton.disabled) {
      mutateSelectedRequest(actionButton.dataset.requestAction);
    }
  });
  window.addEventListener('beforeunload', stopRequestPolling, { once: true });
}

function initializeBroker() {
  if (!document.getElementById('validation-broker')) return;
  initBrokerEvents();
  renderMetrics();
  renderWorkers();
  renderHistory();
  renderRequestDetail();
  refreshBrokerWorkspace();
}

document.addEventListener('DOMContentLoaded', initializeBroker);
