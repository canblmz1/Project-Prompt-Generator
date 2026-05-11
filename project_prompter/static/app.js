/* Local Project Prompt Generator — Web UI JavaScript */

'use strict';

let currentScanId = null;
let pollInterval = null;
let scanResults = {};

// Mode defaults (synced with backend mode_config.py)
const MODE_DEFAULTS = {
  fast:     { max_files: 40, max_chars_per_file: 3000 },
  balanced: { max_files: 50, max_chars_per_file: 4000 },
  deep:     { max_files: 80, max_chars_per_file: 6000 },
};

// ---------------------------------------------------------------------------
// Tab management
// ---------------------------------------------------------------------------

function showTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

  const tab = document.getElementById('tab-' + name);
  if (tab) tab.classList.add('active');

  const btns = document.querySelectorAll('.tab-btn');
  btns.forEach(btn => {
    if (btn.getAttribute('onclick') === `showTab('${name}')`) {
      btn.classList.add('active');
    }
  });
}

// ---------------------------------------------------------------------------
// Mode selection — auto-update limits
// ---------------------------------------------------------------------------

document.querySelectorAll('input[name="analysisMode"]').forEach(radio => {
  radio.addEventListener('change', function () {
    const mode = this.value;
    const defaults = MODE_DEFAULTS[mode];
    if (defaults) {
      document.getElementById('maxFiles').value = defaults.max_files;
      document.getElementById('maxChars').value = defaults.max_chars_per_file;
    }
    // Fast mode disables Ollama
    if (mode === 'fast') {
      document.getElementById('useOllama').checked = false;
      document.getElementById('ollamaSettings').style.display = 'none';
    }
  });
});

// ---------------------------------------------------------------------------
// Ollama status check
// ---------------------------------------------------------------------------

async function checkOllama() {
  const url = document.getElementById('ollamaUrl').value.trim();
  const statusEl = document.getElementById('ollamaStatus');
  statusEl.textContent = 'Checking...';
  statusEl.style.color = 'var(--text-muted)';

  try {
    const resp = await fetch(`/api/ollama-models?ollama_url=${encodeURIComponent(url)}`);
    const data = await resp.json();

    if (data.available) {
      // Populate model dropdown
      const modelSelect = document.getElementById('ollamaModel');
      modelSelect.innerHTML = '';
      data.models.forEach(model => {
        const opt = document.createElement('option');
        opt.value = model;
        opt.textContent = model;
        if (model === data.default) opt.selected = true;
        modelSelect.appendChild(opt);
      });

      const modelList = data.models.length > 0
        ? data.models.slice(0, 5).join(', ')
        : 'No models found';
      statusEl.textContent = `✓ Ollama available. Models: ${modelList}`;
      statusEl.style.color = 'var(--success)';
    } else {
      statusEl.textContent = `✗ ${data.error || 'Ollama not available'}`;
      statusEl.style.color = 'var(--danger)';
    }
  } catch (e) {
    statusEl.textContent = `✗ Could not reach Ollama: ${e.message}`;
    statusEl.style.color = 'var(--danger)';
  }
}

// ---------------------------------------------------------------------------
// Ollama toggle
// ---------------------------------------------------------------------------

document.getElementById('useOllama').addEventListener('change', function () {
  document.getElementById('ollamaSettings').style.display = this.checked ? 'block' : 'none';
  if (this.checked) {
    checkOllama();
  }
});

// ---------------------------------------------------------------------------
// Start scan
// ---------------------------------------------------------------------------

async function startScan() {
  const projectPath = document.getElementById('projectPath').value.trim();
  if (!projectPath) {
    logStatus('✗ Please enter a project path.', 'error');
    return;
  }

  // Prevent duplicate polling intervals
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }

  const btn = document.getElementById('scanBtn');
  btn.disabled = true;
  btn.textContent = 'Scanning...';

  clearResults();
  setProgress(true);
  logStatus('Starting scan...', 'info');

  // Get selected mode
  const modeRadio = document.querySelector('input[name="analysisMode"]:checked');
  const mode = modeRadio ? modeRadio.value : 'fast';

  const useOllama = document.getElementById('useOllama').checked;
  const modelSelect = document.getElementById('ollamaModel');
  const model = modelSelect.value || 'qwen2.5-coder:1.5b';

  const payload = {
    project_path: projectPath,
    output_path: './output',
    mode: mode,
    model: model,
    ollama_url: document.getElementById('ollamaUrl').value.trim() || 'http://localhost:11434',
    max_files: parseInt(document.getElementById('maxFiles').value) || null,
    max_chars_per_file: parseInt(document.getElementById('maxChars').value) || null,
    use_ollama: useOllama,
    target_model: document.getElementById('targetModel').value,
    use_cache: document.getElementById('useCache').checked,
    clear_cache: document.getElementById('clearCache').checked,
  };

  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json();
      // Show readable validation errors if present
      if (err.errors && Array.isArray(err.errors)) {
        const msgs = err.errors.map(e => `${e.field}: ${e.message}`).join('; ');
        throw new Error(`${err.detail} — ${msgs}`);
      }
      throw new Error(err.detail || `HTTP ${resp.status}: Failed to start scan`);
    }

    const data = await resp.json();
    currentScanId = data.scan_id;
    logStatus(`Scan started (ID: ${currentScanId}, mode: ${mode})`, 'success');

    // Start polling
    pollInterval = setInterval(() => pollResults(currentScanId), 1500);

  } catch (e) {
    logStatus(`✗ Error: ${e.message}`, 'error');
    btn.disabled = false;
    btn.textContent = 'Start Scan';
    setProgress(false);
  }
}

// ---------------------------------------------------------------------------
// Poll for results
// ---------------------------------------------------------------------------

async function pollResults(scanId) {
  try {
    const resp = await fetch(`/api/results/${scanId}`);
    if (!resp.ok) return;

    const data = await resp.json();

    // Update progress log
    if (data.progress && data.progress.length > 0) {
      const statusArea = document.getElementById('statusArea');
      statusArea.innerHTML = data.progress
        .map(line => {
          let cls = 'log-line';
          if (line.includes('✓') || line.includes('complete')) cls += ' log-success';
          else if (line.includes('⚠') || line.includes('Warning')) cls += ' log-warning';
          else if (line.includes('✗') || line.includes('Error') || line.includes('failed')) cls += ' log-error';
          return `<span class="${cls}">${escapeHtml(line)}</span>`;
        })
        .join('\n');
      statusArea.scrollTop = statusArea.scrollHeight;
    }

    if (data.status === 'completed') {
      clearInterval(pollInterval);
      pollInterval = null;
      setProgress(false);
      document.getElementById('scanBtn').disabled = false;
      document.getElementById('scanBtn').textContent = 'Start Scan';
      logStatus('✓ Scan completed!', 'success');
      if (data.preview_truncated) {
        logStatus('⚠ Note: Some previews were truncated due to size limits. Download files for full content.', 'warning');
      }
      scanResults = data;
      renderResults(data);
    } else if (data.status === 'failed') {
      clearInterval(pollInterval);
      pollInterval = null;
      setProgress(false);
      document.getElementById('scanBtn').disabled = false;
      document.getElementById('scanBtn').textContent = 'Start Scan';
      logStatus(`✗ Scan failed: ${data.error || 'Unknown error'}`, 'error');
    }

  } catch (e) {
    // Ignore transient errors during polling
  }
}

// ---------------------------------------------------------------------------
// Render results
// ---------------------------------------------------------------------------

function renderResults(data) {
  const contents = data.file_contents || {};

  // Summary
  const summaryMd = contents['project_summary.md'] || '';
  if (summaryMd) {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('summaryContent').style.display = 'block';
    document.getElementById('summaryText').textContent = summaryMd;
  }

  // Tech Stack
  renderTechStack(data.tech_stack || {}, contents['tech_stack.md'] || '');

  // File Tree
  const fileTreeMd = contents['file_tree.md'] || '';
  if (fileTreeMd) {
    document.getElementById('fileTreeContent').innerHTML =
      `<div class="content-block">${escapeHtml(fileTreeMd)}</div>`;
  }

  // Risks
  const risksMd = contents['risk_notes.md'] || '';
  if (risksMd) {
    document.getElementById('risksContent').innerHTML =
      `<div class="content-block markdown">${escapeHtml(risksMd)}</div>`;
  }

  // Prompts
  const promptModels = ['chatgpt', 'claude', 'gemini', 'minimax', 'generic'];
  promptModels.forEach(model => {
    const key = `prompts/${model}_prompt.md`;
    const content = contents[key] || '';
    const inner = document.getElementById(`${model}-inner`);
    const actions = document.getElementById(`${model}-actions`);
    if (content && inner) {
      inner.innerHTML = `<div class="content-block">${escapeHtml(content)}</div>`;
      if (actions) actions.style.display = 'flex';
    }
  });

  // Scan Report
  const scanReportJson = contents['scan_report.json'] || '';
  if (scanReportJson) {
    document.getElementById('scanReportContent').innerHTML =
      `<div class="content-block">${escapeHtml(scanReportJson)}</div>`;
  }

  // Redaction Report
  const redactionMd = contents['redaction_report.md'] || '';
  if (redactionMd) {
    document.getElementById('redactionContent').innerHTML =
      `<div class="content-block markdown">${escapeHtml(redactionMd)}</div>`;
  }

  // Download links
  renderDownloadLinks(data);

  // Show actions section
  document.getElementById('actionsSection').style.display = 'block';

  // Switch to summary tab
  showTab('summary');

  // Save to local history
  saveToHistory(data);
}

function renderTechStack(stack, rawMd) {
  const el = document.getElementById('techStackContent');
  if (!stack || Object.keys(stack).length === 0) return;

  let html = '<div style="padding:4px 0">';

  const categories = [
    { key: 'languages', label: 'Languages', cls: 'lang' },
    { key: 'frameworks', label: 'Frameworks', cls: 'framework' },
    { key: 'databases', label: 'Databases / ORM', cls: 'db' },
    { key: 'tools', label: 'Tools', cls: '' },
    { key: 'package_managers', label: 'Package Managers', cls: '' },
    { key: 'testing_tools', label: 'Testing', cls: 'test' },
  ];

  categories.forEach(({ key, label, cls }) => {
    const items = stack[key] || [];
    if (items.length === 0) return;
    html += `<div style="margin-bottom:16px">`;
    html += `<div class="section-title" style="margin-bottom:8px">${label}</div>`;
    html += `<div class="chip-list">`;
    items.forEach(item => {
      html += `<span class="chip ${cls}">${escapeHtml(item)}</span>`;
    });
    html += `</div></div>`;
  });

  html += '</div>';

  if (rawMd) {
    html += `<div class="divider" style="margin:16px 0"></div>`;
    html += `<div class="content-block markdown" style="margin-top:8px">${escapeHtml(rawMd)}</div>`;
  }

  el.innerHTML = html;
}

function renderDownloadLinks(data) {
  const outputs = data.outputs || {};
  const scanId = data.scan_id;
  const container = document.getElementById('downloadLinks');
  container.innerHTML = '';

  const priority = [
    'project_summary.md',
    'tech_stack.md',
    'file_tree.md',
    'risk_notes.md',
    'redaction_report.md',
    'scan_report.json',
    'prompts/chatgpt_prompt.md',
    'prompts/claude_prompt.md',
    'prompts/gemini_prompt.md',
    'prompts/minimax_prompt.md',
    'prompts/generic_prompt.md',
  ];

  const available = Object.keys(outputs);
  const ordered = [
    ...priority.filter(f => available.includes(f)),
    ...available.filter(f => !priority.includes(f)),
  ];

  ordered.forEach(filename => {
    const btn = document.createElement('a');
    btn.href = `/api/download/${scanId}/${filename}`;
    btn.download = filename.split('/').pop();
    btn.className = 'btn btn-secondary btn-sm';
    btn.style.textDecoration = 'none';
    btn.textContent = `⬇ ${filename.split('/').pop()}`;
    container.appendChild(btn);
  });
}

// ---------------------------------------------------------------------------
// Copy prompt to clipboard
// ---------------------------------------------------------------------------

async function copyPrompt(model) {
  const inner = document.getElementById(`${model}-inner`);
  if (!inner) return;

  const block = inner.querySelector('.content-block');
  if (!block) return;

  const text = block.textContent;
  try {
    await navigator.clipboard.writeText(text);
    showToast(`${model} prompt copied to clipboard!`);
  } catch (e) {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(`${model} prompt copied!`);
  }
}

function downloadPrompt(model) {
  if (!currentScanId) return;
  const link = document.createElement('a');
  link.href = `/api/download/${currentScanId}/prompts/${model}_prompt.md`;
  link.download = `${model}_prompt.md`;
  link.click();
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function logStatus(msg, type) {
  const area = document.getElementById('statusArea');
  const cls = type === 'error' ? 'log-error' : type === 'success' ? 'log-success' : type === 'warning' ? 'log-warning' : 'log-line';
  area.innerHTML += `<span class="${cls}">${escapeHtml(msg)}</span>\n`;
  area.scrollTop = area.scrollHeight;
}

function clearResults() {
  currentScanId = null;
  scanResults = {};
  document.getElementById('emptyState').style.display = 'flex';
  document.getElementById('summaryContent').style.display = 'none';
  document.getElementById('summaryText').textContent = '';
  document.getElementById('techStackContent').innerHTML = '<div class="empty-state"><div class="icon">🛠</div><h3>No tech stack detected yet</h3><p>Run a scan to detect the technology stack.</p></div>';
  document.getElementById('fileTreeContent').innerHTML = '<div class="empty-state"><div class="icon">📂</div><h3>No file tree yet</h3><p>Run a scan to generate the file tree.</p></div>';
  document.getElementById('risksContent').innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><h3>No risk notes yet</h3><p>Run a scan to generate risk notes.</p></div>';
  document.getElementById('scanReportContent').innerHTML = '<div class="empty-state"><div class="icon">📊</div><h3>No scan report yet</h3><p>Run a scan to generate the report.</p></div>';
  document.getElementById('redactionContent').innerHTML = '<div class="empty-state"><div class="icon">🔒</div><h3>No redaction report yet</h3><p>Run a scan to see what secrets were detected and redacted.</p></div>';
  document.getElementById('downloadLinks').innerHTML = '';
  document.getElementById('actionsSection').style.display = 'none';
  document.getElementById('statusArea').textContent = '';

  ['chatgpt', 'claude', 'gemini', 'minimax', 'generic'].forEach(model => {
    const inner = document.getElementById(`${model}-inner`);
    const actions = document.getElementById(`${model}-actions`);
    if (inner) inner.innerHTML = `<div class="empty-state"><div class="icon">📝</div><h3>${model} prompt not generated yet</h3><p>Run a scan to generate this prompt.</p></div>`;
    if (actions) actions.style.display = 'none';
  });
}

function setProgress(active) {
  const fill = document.getElementById('progressFill');
  if (active) {
    fill.classList.add('indeterminate');
  } else {
    fill.classList.remove('indeterminate');
    fill.style.width = '0%';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showToast(msg) {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed; bottom: 24px; right: 24px;
    background: var(--success); color: #fff;
    padding: 10px 18px; border-radius: 6px;
    font-size: 0.82rem; font-weight: 600;
    z-index: 9999; box-shadow: var(--shadow);
    animation: fadeIn 0.2s ease;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

// ---------------------------------------------------------------------------
// Scan History (localStorage)
// ---------------------------------------------------------------------------

const HISTORY_KEY = 'project_prompter_history';
const HISTORY_MAX = 20;

function saveToHistory(data) {
  if (!data || !data.scan_id) return;
  try {
    let history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    history = history.filter(h => h.scan_id !== data.scan_id);
    const entry = {
      scan_id: data.scan_id,
      project_path: data.project_path,
      mode: data.mode,
      scanned_at: data.completed_at || new Date().toISOString(),
      redaction_count: data.redaction_count || 0,
      files_scanned: data.files_scanned || 0,
      tech_summary: (data.tech_stack && data.tech_stack.languages)
        ? data.tech_stack.languages.slice(0, 3).join(', ')
        : '',
    };
    history.unshift(entry);
    if (history.length > HISTORY_MAX) history = history.slice(0, HISTORY_MAX);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    renderHistory();
  } catch (e) {
    // localStorage may be disabled or full; silently ignore
  }
}

function renderHistory() {
  const container = document.getElementById('historyList');
  if (!container) return;
  container.innerHTML = '';
  try {
    const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    if (history.length === 0) {
      container.innerHTML = '<div style="font-size:0.75rem;color:var(--text-dim);padding:4px 0;">No history yet.</div>';
      return;
    }
    history.forEach(entry => {
      const item = document.createElement('button');
      item.className = 'btn btn-secondary btn-sm';
      item.style.cssText = 'justify-content:flex-start;text-align:left;';
      const meta = `${entry.mode} • ${entry.files_scanned} files${entry.redaction_count ? ' • ' + entry.redaction_count + ' secrets' : ''}`;
      item.innerHTML = `<div style="line-height:1.4"><div style="font-weight:600;font-size:0.78rem">${escapeHtml(entry.project_path || 'Unknown')}</div><div style="font-size:0.65rem;color:var(--text-muted)">${escapeHtml(meta)}</div></div>`;
      item.title = 'Click to restore project path and mode';
      item.onclick = () => loadHistoryEntry(entry);
      container.appendChild(item);
    });
  } catch (e) {
    container.innerHTML = '<div style="font-size:0.75rem;color:var(--text-dim)">Unable to load history.</div>';
  }
}

function loadHistoryEntry(entry) {
  logStatus(`Loaded history entry: ${entry.project_path} (${entry.mode})`, 'info');
  document.getElementById('projectPath').value = entry.project_path || '';
  if (entry.mode && MODE_DEFAULTS[entry.mode]) {
    const radio = document.querySelector(`input[name="analysisMode"][value="${entry.mode}"]`);
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event('change'));
    }
  }
  document.getElementById('projectPath').focus();
}

function clearHistory() {
  try {
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
    showToast('History cleared');
  } catch (e) {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Export Results
// ---------------------------------------------------------------------------

function exportResults() {
  if (!scanResults || !scanResults.scan_id) {
    showToast('No results to export. Run a scan first.');
    return;
  }
  try {
    const blob = new Blob([JSON.stringify(scanResults, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `scan-${scanResults.scan_id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Results exported');
  } catch (e) {
    showToast('Export failed');
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

renderHistory();
// UI is ready by default; no auto-check needed.
