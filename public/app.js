/**
 * Aegis Scraper Dashboard Client Script
 * Handles real-time SSE stream telemetry, live data rendering,
 * architecture modals, tab switching, dual theme toggling (Dark Default), and job ingestion controls.
 */

// State
let eventSource = null;
let currentJobs = [];
let isExecuting = false;
let currentRunId = null;
let activeLogFilter = 'all';

// DOM Elements
const terminalConsole = document.getElementById('terminalConsole');
const jobsTableBody = document.getElementById('jobsTableBody');
const proxyTableBody = document.getElementById('proxyTableBody');
const autoScrollCheck = document.getElementById('autoScrollCheck');
const jobSearchInput = document.getElementById('jobSearchInput');
const scrapeForm = document.getElementById('scrapeForm');
const sourceSelect = document.getElementById('sourceSelect');
const runScraperBtn = document.getElementById('runScraperBtn');
const resultsCount = document.getElementById('resultsCount');

// Stat Counters
const statTotalJobs = document.getElementById('statTotalJobs');
const statEvaded = document.getElementById('statEvaded');
const statRecoveries = document.getElementById('statRecoveries');
const statCircuitState = document.getElementById('statCircuitState');
const headerCircuitStatus = document.getElementById('headerCircuitStatus');
const headerProxyHealth = document.getElementById('headerProxyHealth');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initSSE();
  fetchInitialStatus();
  setupEventListeners();
  setupFilterChips();
  setupKeyboardShortcuts();
  setupWorkspaceTabs();
  setupThemeToggle();
});

// Theme Toggle Handler (Default Dark Mode)
function setupThemeToggle() {
  const toggleBtn = document.getElementById('themeToggleBtn');
  const toggleText = document.getElementById('themeToggleText');
  if (!toggleBtn) return;

  const savedTheme = localStorage.getItem('aegis-theme');
  if (savedTheme === 'light') {
    document.body.classList.remove('dark-theme');
    if (toggleText) toggleText.textContent = 'Dark Mode';
  } else {
    // Default to Dark Mode
    document.body.classList.add('dark-theme');
    if (toggleText) toggleText.textContent = 'Light Mode';
  }

  toggleBtn.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-theme');
    if (isDark) {
      localStorage.setItem('aegis-theme', 'dark');
      if (toggleText) toggleText.textContent = 'Light Mode';
    } else {
      localStorage.setItem('aegis-theme', 'light');
      if (toggleText) toggleText.textContent = 'Dark Mode';
    }
  });
}

// SSE Connection
function initSSE() {
  if (eventSource) eventSource.close();

  eventSource = new EventSource('/api/stream');

  eventSource.onopen = () => {
    const statusText = document.getElementById('sseStatusText');
    const statusPill = document.getElementById('sseStatusPill');
    if (statusText) statusText.textContent = 'Telemetry Live';
    if (statusPill) statusPill.classList.add('live-pill');
  };

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleTelemetryEvent(data);
    } catch (err) {
      console.error('SSE JSON parse error:', err);
    }
  };

  eventSource.onerror = () => {
    const statusText = document.getElementById('sseStatusText');
    const statusPill = document.getElementById('sseStatusPill');
    if (statusText) statusText.textContent = 'Reconnecting...';
    if (statusPill) statusPill.classList.remove('live-pill');
  };
}

// Telemetry Event Handler
function handleTelemetryEvent(evt) {
  appendTerminalLog(evt);

  if (evt.type === 'INGESTION_COMPLETED') {
    fetchInitialStatus();
  }
}

// Append Line to Terminal Console
function appendTerminalLog(evt) {
  if (!terminalConsole) return;

  const line = document.createElement('div');
  line.className = 'terminal-line';

  const time = evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

  let tagClass = 'tag-sys';
  let tagText = 'SYS';
  let message = '';

  switch (evt.type) {
    case 'CONNECTED':
      tagClass = 'tag-sys';
      tagText = 'INIT';
      message = evt.message;
      break;

    case 'INGESTION_START':
      tagClass = 'tag-req';
      tagText = 'START';
      message = `Initiating stealth ingestion vector: [${evt.sourceName}] (Run ID: ${evt.runId})`;
      break;

    case 'REQUEST_START':
      tagClass = 'tag-req';
      tagText = 'HTTP';
      message = `[${evt.proxy}] GET ${evt.url} | Morph Profile: ${evt.profileName} | Jitter: ${evt.jitterDelay}ms`;
      break;

    case 'REQUEST_SUCCESS':
      tagClass = 'tag-ok';
      tagText = '200 OK';
      message = `Response received in ${evt.duration}ms (${(evt.bodyLength / 1024).toFixed(1)} KB payload).`;
      break;

    case 'CHALLENGE_DETECTED':
    case 'CHALLENGE_INJECTED':
      tagClass = 'tag-warn';
      tagText = 'BOT-BLOCK';
      message = `${evt.challenge?.message || evt.challenge}. Initiating session morph & proxy failover.`;
      break;

    case 'PROXY_QUARANTINED':
      tagClass = 'tag-warn';
      tagText = 'PROXY';
      message = `${evt.note}`;
      break;

    case 'FAILOVER_SUCCESS':
      tagClass = 'tag-failover';
      tagText = 'RECOVERY';
      message = `Schema Drift Recovery: ${evt.note}`;
      break;

    case 'CIRCUIT_TRIPPED':
      tagClass = 'tag-err';
      tagText = 'CIRCUIT';
      message = `Circuit Breaker TRIPPED: ${evt.note}`;
      break;

    case 'INGESTION_COMPLETED':
      tagClass = 'tag-ok';
      tagText = 'DONE';
      message = `Ingestion complete. Successfully parsed ${evt.jobsExtracted} jobs via ${evt.strategyUsed} (Quality: ${evt.quality?.confidence}% ${evt.quality?.status}).`;
      break;

    case 'INGESTION_ERROR':
      tagClass = 'tag-err';
      tagText = 'ERROR';
      message = `Ingestion failed: ${evt.error}`;
      break;

    default:
      tagClass = 'tag-sys';
      tagText = 'EVENT';
      message = evt.note || evt.message || JSON.stringify(evt);
  }

  line.setAttribute('data-tag', tagText);
  line.innerHTML = `
    <span class="log-time">[${time}]</span>
    <span class="log-tag ${tagClass}">${tagText}</span>
    <span class="log-msg">${escapeHtml(message)}</span>
  `;

  // Apply active log filter
  if (activeLogFilter !== 'all' && tagText !== activeLogFilter) {
    line.style.display = 'none';
  }

  terminalConsole.appendChild(line);

  // Maintain max 250 logs
  while (terminalConsole.children.length > 250) {
    terminalConsole.removeChild(terminalConsole.firstChild);
  }

  if (autoScrollCheck && autoScrollCheck.checked) {
    terminalConsole.scrollTop = terminalConsole.scrollHeight;
  }
}

// Workspace Tab Switching
function setupWorkspaceTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-tab');
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      tab.classList.add('active');
      const content = document.getElementById(`tab-${target}`);
      if (content) content.classList.add('active');
    });
  });
}

// Terminal Filter Chips Handler
function setupFilterChips() {
  const container = document.getElementById('terminalFilters');
  if (!container) return;

  container.addEventListener('click', (e) => {
    const btn = e.target.closest('.filter-chip');
    if (!btn) return;

    container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');

    activeLogFilter = btn.getAttribute('data-filter');

    if (!terminalConsole) return;
    const lines = terminalConsole.querySelectorAll('.terminal-line');
    lines.forEach(line => {
      const tag = line.getAttribute('data-tag');
      if (activeLogFilter === 'all' || tag === activeLogFilter) {
        line.style.display = 'flex';
      } else {
        line.style.display = 'none';
      }
    });

    if (autoScrollCheck && autoScrollCheck.checked) {
      terminalConsole.scrollTop = terminalConsole.scrollHeight;
    }
  });
}

// Global Keyboard Shortcuts
function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== jobSearchInput && document.activeElement.tagName !== 'SELECT') {
      e.preventDefault();
      if (jobSearchInput) jobSearchInput.focus();
    }
  });
}

// Fetch Initial Status & Metrics
async function fetchInitialStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    // Update Metrics
    if (statTotalJobs) statTotalJobs.textContent = data.stats?.totalJobsExtracted || 0;
    if (statEvaded) statEvaded.textContent = data.stats?.challengesEvaded || 0;
    if (statRecoveries) statRecoveries.textContent = data.stats?.schemaFallbacksRecovered || 0;
    
    // Check circuit breaker status
    const breakers = Object.values(data.circuitBreakers || {});
    const isAnyOpen = breakers.some(b => b.state === 'OPEN');
    const isAnyHalf = breakers.some(b => b.state === 'HALF_OPEN');

    if (isAnyOpen) {
      if (statCircuitState) {
        statCircuitState.textContent = 'OPEN (Quarantine)';
        statCircuitState.className = 'kpi-value text-amber';
      }
      if (headerCircuitStatus) {
        headerCircuitStatus.textContent = 'OPEN (Quarantine)';
        headerCircuitStatus.className = 'text-amber';
      }
    } else if (isAnyHalf) {
      if (statCircuitState) {
        statCircuitState.textContent = 'HALF_OPEN (Probing)';
        statCircuitState.className = 'kpi-value text-amber';
      }
      if (headerCircuitStatus) {
        headerCircuitStatus.textContent = 'HALF_OPEN';
        headerCircuitStatus.className = 'text-amber';
      }
    } else {
      if (statCircuitState) {
        statCircuitState.textContent = 'CLOSED';
        statCircuitState.className = 'kpi-value text-amber';
      }
      if (headerCircuitStatus) {
        headerCircuitStatus.textContent = 'CLOSED (100%)';
        headerCircuitStatus.className = 'text-emerald';
      }
    }

    // Update Token Matrix
    if (data.rateLimiter) {
      const rl = data.rateLimiter;
      const matrixBudget = document.getElementById('matrixTokenBudget');
      if (matrixBudget) matrixBudget.textContent = `${rl.tokensRemaining}/${rl.maxTokens} Tokens Available`;
    }

    // Render Proxies Table
    if (data.proxies) {
      renderProxyTable(data.proxies);
      const healthyCount = data.proxies.filter(p => p.health > 50).length;
      if (headerProxyHealth) headerProxyHealth.textContent = `${healthyCount}/${data.proxies.length} Active`;
    }

    // Fetch history
    fetchHistory();

  } catch (err) {
    console.error('Failed to fetch status:', err);
  }
}

function renderProxyTable(proxies) {
  if (!proxyTableBody) return;
  proxyTableBody.innerHTML = proxies.map(p => {
    let healthClass = 'text-emerald';
    if (p.health < 40) healthClass = 'text-amber';
    else if (p.health < 80) healthClass = 'text-indigo';

    return `
      <tr>
        <td><strong>${escapeHtml(p.id)}</strong></td>
        <td class="text-muted">${escapeHtml(p.region)}</td>
        <td class="${healthClass}"><strong>${p.health}%</strong></td>
        <td class="text-indigo"><strong>${p.requests}</strong></td>
      </tr>
    `;
  }).join('');
}

async function fetchHistory() {
  try {
    const res = await fetch('/api/history');
    const history = await res.json();
    if (history.length > 0 && currentJobs.length === 0) {
      currentRunId = history[0].runId;
      currentJobs = history[0].jobs || [];
      renderJobsTable(currentJobs);
    }
  } catch (err) {
    // Non-fatal
  }
}

// Render Extracted Jobs Table
function renderJobsTable(jobs) {
  if (!jobsTableBody) return;
  const filter = jobSearchInput ? jobSearchInput.value.toLowerCase().trim() : '';
  const filtered = jobs.filter(j => {
    if (!filter) return true;
    const hay = `${j.title} ${j.company} ${j.location} ${(j.tags || []).join(' ')} ${j.source}`.toLowerCase();
    return hay.includes(filter);
  });

  if (resultsCount) {
    resultsCount.textContent = `${filtered.length} listings displayed (${jobs.length} total in buffer).`;
  }

  if (filtered.length === 0) {
    jobsTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-state">
          <div class="empty-wrap">
            <div class="empty-badge">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
            </div>
            <h4 class="empty-heading">No matching listings</h4>
            <p class="empty-sub">No job listings match your current search filter "${escapeHtml(filter)}".</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  jobsTableBody.innerHTML = filtered.map(j => {
    let tierBadge = 'badge-emerald';
    if (j.tier === 'TIER_2_JSON_LD') tierBadge = 'badge-indigo';
    else if (j.tier === 'TIER_3_HEURISTIC') tierBadge = 'badge-amber';

    const tagsHtml = (j.tags || []).slice(0, 3).map(t => `<span class="badge badge-indigo">${escapeHtml(t)}</span>`).join(' ');

    return `
      <tr>
        <td class="job-title-cell">
          <div><strong>${escapeHtml(j.title)}</strong></div>
          <div class="tags-wrapper" style="margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap;">${tagsHtml}</div>
        </td>
        <td><strong>${escapeHtml(j.company)}</strong></td>
        <td><span class="text-muted">${escapeHtml(j.location || 'Remote')}</span></td>
        <td><span class="text-emerald"><strong>${escapeHtml(j.salary || 'Competitive')}</strong></span></td>
        <td><span class="badge ${tierBadge}">${j.tier || 'TIER_0'}</span></td>
        <td><span class="text-indigo"><strong>${escapeHtml(j.source || 'Live')}</strong></span></td>
        <td class="text-right">
          ${j.url ? `<a href="${escapeHtml(j.url)}" target="_blank" rel="noreferrer" class="btn btn-indigo-outline btn-xs">View Listing</a>` : '<span class="text-muted">N/A</span>'}
        </td>
      </tr>
    `;
  }).join('');
}

// Scrape Dispatch Form
function setupEventListeners() {
  if (scrapeForm) {
    scrapeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (isExecuting) return;

      const val = sourceSelect.value;
      const limit = parseInt(document.getElementById('batchLimitSelect').value, 10) || 25;
      let sourceId = val;
      let scenario = null;

      if (val.startsWith('simulator:')) {
        sourceId = 'simulator';
        scenario = val.split(':')[1];
      }

      isExecuting = true;
      runScraperBtn.disabled = true;
      runScraperBtn.innerHTML = `
        <svg class="pulse-ring" style="display:inline-block; margin-right:8px;"></svg>
        <span>Ingesting (${limit} Targets)...</span>
      `;

      try {
        const res = await fetch('/api/scrape', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sourceId, scenario, limit })
        });

        const data = await res.json();
        if (data.success && data.jobs) {
          currentRunId = data.runId;
          currentJobs = data.jobs;
          renderJobsTable(currentJobs);
        } else if (!data.success) {
          alert(`Ingestion error: ${data.error}`);
        }
      } catch (err) {
        alert(`Network error: ${err.message}`);
      } finally {
        isExecuting = false;
        runScraperBtn.disabled = false;
        runScraperBtn.innerHTML = `
          <svg class="btn-svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          <span>Execute Ingestion Pipeline</span>
        `;
        fetchInitialStatus();
      }
    });
  }

  // Search Filter
  if (jobSearchInput) {
    jobSearchInput.addEventListener('input', () => {
      renderJobsTable(currentJobs);
    });
  }

  // Clear Logs
  const clearLogsBtn = document.getElementById('clearLogsBtn');
  if (clearLogsBtn) {
    clearLogsBtn.addEventListener('click', () => {
      if (!terminalConsole) return;
      terminalConsole.innerHTML = `
        <div class="terminal-line log-sys">
          <span class="log-time">[${new Date().toLocaleTimeString()}]</span>
          <span class="log-tag tag-sys">SYS</span>
          <span class="log-msg">Terminal logs cleared.</span>
        </div>
      `;
    });
  }

  // Export Buttons
  const exportCsvBtn = document.getElementById('exportCsvBtn');
  if (exportCsvBtn) {
    exportCsvBtn.addEventListener('click', () => exportData('csv'));
  }

  const exportJsonBtn = document.getElementById('exportJsonBtn');
  if (exportJsonBtn) {
    exportJsonBtn.addEventListener('click', () => exportData('json'));
  }
}

function exportData(format) {
  if (currentJobs && currentJobs.length > 0) {
    const runId = currentRunId || `export-${Date.now()}`;
    if (format === 'csv') {
      const headers = ['ID', 'Title', 'Company', 'Location', 'Salary', 'URL', 'Source', 'Tier'];
      const rows = currentJobs.map(j => [
        `"${String(j.id || '').replace(/"/g, '""')}"`,
        `"${String(j.title || '').replace(/"/g, '""')}"`,
        `"${String(j.company || '').replace(/"/g, '""')}"`,
        `"${String(j.location || '').replace(/"/g, '""')}"`,
        `"${String(j.salary || '').replace(/"/g, '""')}"`,
        `"${String(j.url || '').replace(/"/g, '""')}"`,
        `"${String(j.source || '').replace(/"/g, '""')}"`,
        `"${String(j.tier || '').replace(/"/g, '""')}"`
      ]);
      const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\r\n');
      downloadFile(csvContent, `jobs-${runId}.csv`, 'text/csv;charset=utf-8;');
    } else {
      const jsonContent = JSON.stringify(currentJobs, null, 2);
      downloadFile(jsonContent, `jobs-${runId}.json`, 'application/json;charset=utf-8;');
    }
    return;
  }

  // If client buffer is empty, attempt backend export fallback
  const run = currentRunId || 'latest';
  window.open(`/api/export/${run}?format=${format}`, '_blank');
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
