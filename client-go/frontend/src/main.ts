import { createIcons, Link, ListRestart, Play, RefreshCw, Square, Terminal, Unplug, Wifi } from 'lucide'
import { api, type RunLog, type RunRecord, type StartOptions, type TaskLog } from './api'
import './style.css'

const app = document.querySelector<HTMLDivElement>('#app')!

app.innerHTML = `
  <header class="app-header">
    <div class="brand-mark">AW</div>
    <div>
      <h1>autoWAL 控制台</h1>
      <p>远程任务调度</p>
    </div>
    <div class="connection-state disconnected" id="connection-state">
      <span class="state-dot"></span><span id="connection-label">未连接</span>
    </div>
  </header>

  <section class="connection-bar" aria-label="服务器连接">
    <div class="input-with-icon">
      <i data-lucide="link"></i>
      <input id="server-url" aria-label="服务器地址" value="${localStorage.getItem('autowal.server') ?? 'http://127.0.0.1:8765'}" spellcheck="false" />
    </div>
    <button id="connect-button" class="button secondary"><i data-lucide="wifi"></i><span>连接</span></button>
  </section>

  <main class="workspace">
    <aside class="run-form-panel">
      <div class="section-heading">
        <div><span class="eyebrow">新建运行</span><h2>任务参数</h2></div>
      </div>
      <form id="run-form">
        <label>任务名称<input name="name" maxlength="120" placeholder="例如：发布前全量验证" required /></label>
        <label>用途说明 <span class="optional">可选</span><textarea name="description" maxlength="1000" rows="2" placeholder="说明本次完整填写流程的用途"></textarea></label>
        <div class="field-pair">
          <label>线程数<input name="threads" type="number" value="1" min="1" step="1" required /></label>
          <label>循环数<input name="loops" type="number" value="1" min="1" step="1" required /></label>
        </div>
        <label>来源编号<input name="source_id" value="719419" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required /></label>
        <div class="field-pair">
          <label>重试次数<input name="retries" type="number" value="0" min="0" step="1" required /></label>
          <label>循环间隔<input name="loop_delay" type="number" value="1" min="0" step="0.1" required /><span class="unit">秒</span></label>
        </div>
        <label>随机种子 <span class="optional">可选</span><input name="seed" type="number" step="1" placeholder="不固定" /></label>

        <div class="switch-group">
          <label class="switch-row"><span><strong>无头模式</strong><small>后台运行浏览器</small></span><input name="headless" type="checkbox" checked /><span class="switch"></span></label>
          <label class="switch-row"><span><strong>自动提交</strong><small>填写完成后直接提交</small></span><input name="auto_submit" type="checkbox" /><span class="switch"></span></label>
          <label class="switch-row"><span><strong>调试记录</strong><small>保存页面诊断截图</small></span><input name="debug" type="checkbox" /><span class="switch"></span></label>
        </div>

        <button class="button primary full" type="submit" id="start-button"><i data-lucide="play"></i><span>启动任务</span></button>
      </form>
    </aside>

    <section class="runs-panel">
      <div class="section-heading runs-heading">
        <div><span class="eyebrow">服务器队列</span><h2>运行记录</h2></div>
        <button id="refresh-button" class="icon-button" title="刷新运行记录" aria-label="刷新运行记录"><i data-lucide="refresh-cw"></i></button>
      </div>

      <div class="table-wrap">
        <table>
          <thead><tr><th>任务</th><th>状态</th><th>进度</th><th>已运行</th></tr></thead>
          <tbody id="runs-body"><tr class="empty-row"><td colspan="4">连接服务器后显示运行记录</td></tr></tbody>
        </table>
      </div>
      <button id="load-more" class="button secondary load-more" type="button" hidden>加载更多</button>

      <section class="detail-panel" id="detail-panel">
        <div class="detail-empty"><i data-lucide="list-restart"></i><span>选择一条运行记录查看详情</span></div>
      </section>
    </section>
  </main>

  <section class="log-panel">
    <div class="log-title"><i data-lucide="terminal"></i><span>操作日志</span><button id="clear-log" type="button">清空</button></div>
    <div class="log-lines" id="log-lines"><div><time>--:--:--</time><span>等待连接服务器</span></div></div>
  </section>

  <div class="toast-region" id="toast-region" aria-live="polite"></div>
`

const appIcons = { Link, ListRestart, Play, RefreshCw, Square, Terminal, Unplug, Wifi }
renderIcons()

const serverInput = byID<HTMLInputElement>('server-url')
const connectButton = byID<HTMLButtonElement>('connect-button')
const refreshButton = byID<HTMLButtonElement>('refresh-button')
const loadMoreButton = byID<HTMLButtonElement>('load-more')
const startButton = byID<HTMLButtonElement>('start-button')
const runForm = byID<HTMLFormElement>('run-form')
const runsBody = byID<HTMLTableSectionElement>('runs-body')
const detailPanel = byID<HTMLElement>('detail-panel')
const logLines = byID<HTMLDivElement>('log-lines')
const connectionState = byID<HTMLDivElement>('connection-state')
const connectionLabel = byID<HTMLSpanElement>('connection-label')

let connected = false
let selectedRunID: string | null = null
let runs: RunRecord[] = []
let nextCursor: string | null = null
let activeDetailTab: 'overview' | 'run-logs' | 'task-logs' = 'overview'
let runLogs: RunLog[] = []
let taskLogs: TaskLog[] = []
let runLogCursor = 0
let taskLogCursor = 0
let taskFilter: number | null = null
let attemptFilter: number | null = null
let loadingDetailLogs = false
let refreshing = false
let pollTimer: number | null = null

connectButton.addEventListener('click', connect)
serverInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') void connect() })
refreshButton.addEventListener('click', () => void refreshRuns(true))
loadMoreButton.addEventListener('click', () => void loadMoreRuns())
runForm.addEventListener('submit', startRun)
byID<HTMLButtonElement>('clear-log').addEventListener('click', () => { logLines.innerHTML = '' })

async function connect() {
  setBusy(connectButton, true)
  try {
    const result = await api.Connect(serverInput.value)
    connected = true
    serverInput.value = result.url
    localStorage.setItem('autowal.server', result.url)
    connectionState.className = 'connection-state connected'
    connectionLabel.textContent = `已连接 · ${result.service}`
    addLog(`已连接 ${result.url}`, 'success')
    toast('服务器连接成功', 'success')
    startPolling()
    await refreshRuns(false)
  } catch (error) {
    markDisconnected()
    reportError('连接失败', error)
  } finally {
    setBusy(connectButton, false)
  }
}

async function startRun(event: SubmitEvent) {
  event.preventDefault()
  if (!connected) return toast('请先连接服务器', 'warning')
  if (!runForm.reportValidity()) return

  const data = new FormData(runForm)
  const seedText = String(data.get('seed') ?? '').trim()
  const options: StartOptions = {
    name: String(data.get('name') ?? '').trim(),
    description: String(data.get('description') ?? '').trim(),
    threads: Number(data.get('threads')),
    loops: Number(data.get('loops')),
    source_id: String(data.get('source_id')),
    headless: data.has('headless'),
    auto_submit: data.has('auto_submit'),
    debug: data.has('debug'),
    retries: Number(data.get('retries')),
    loop_delay: Number(data.get('loop_delay')),
    seed: seedText === '' ? null : Number(seedText),
  }

  setBusy(startButton, true)
  try {
    const result = await api.StartRun(options)
    selectedRunID = result.run_id
    addLog(`任务 ${shortID(result.run_id)} 已进入队列`, 'success')
    toast('任务已启动', 'success')
    await refreshRuns(false)
  } catch (error) {
    reportError('启动失败', error)
  } finally {
    setBusy(startButton, false)
  }
}

async function refreshRuns(notify = false) {
  if (!connected || refreshing) return
  refreshing = true
  refreshButton.classList.add('spinning')
  try {
    const page = await api.ListRunsPage(100, '')
    runs = page.items
    nextCursor = page.next_cursor
    loadMoreButton.hidden = !nextCursor
    renderRuns()
    renderDetail()
    if (activeDetailTab !== 'overview') void loadSelectedLogs(false)
    if (notify) toast('运行记录已刷新', 'success')
  } catch (error) {
    markDisconnected()
    reportError('刷新失败', error)
  } finally {
    refreshing = false
    refreshButton.classList.remove('spinning')
  }
}

async function loadMoreRuns() {
  if (!nextCursor) return
  setBusy(loadMoreButton, true)
  try {
    const page = await api.ListRunsPage(100, nextCursor)
    runs.push(...page.items)
    nextCursor = page.next_cursor
    loadMoreButton.hidden = !nextCursor
    renderRuns()
  } catch (error) {
    reportError('加载历史失败', error)
  } finally {
    setBusy(loadMoreButton, false)
  }
}

function renderRuns() {
  if (runs.length === 0) {
    runsBody.innerHTML = '<tr class="empty-row"><td colspan="4">当前没有运行记录</td></tr>'
    return
  }
  runsBody.innerHTML = runs.map((run) => {
    const progress = run.summary ? `${run.summary.completed}/${run.summary.total}` : run.status === 'running' ? '执行中' : '—'
    const state = safeStatus(run.status)
    return `<tr data-run-id="${escapeHTML(run.run_id)}" class="${run.run_id === selectedRunID ? 'selected' : ''}">
      <td><strong class="run-name">${escapeHTML(run.name)}</strong><small>${escapeHTML(run.run_number)} · ${formatDate(run.created_at)}</small></td>
      <td><span class="status ${state.className}"><span></span>${state.label}</span></td>
      <td>${progress}</td><td>${formatDuration(run)}</td>
    </tr>`
  }).join('')
  runsBody.querySelectorAll<HTMLTableRowElement>('tr[data-run-id]').forEach((row) => {
    row.addEventListener('click', () => {
      selectedRunID = row.dataset.runId ?? null
      activeDetailTab = 'overview'
      runLogs = []; taskLogs = []; runLogCursor = 0; taskLogCursor = 0
      renderRuns()
      renderDetail()
    })
  })
}

function renderDetail() {
  const run = runs.find((item) => item.run_id === selectedRunID)
  if (!run) {
    detailPanel.innerHTML = '<div class="detail-empty"><i data-lucide="list-restart"></i><span>选择一条运行记录查看详情</span></div>'
    renderIcons()
    return
  }
  const summary = run.summary
  const canStop = ['pending', 'running', 'stopping'].includes(run.status)
  const state = safeStatus(run.status)
  detailPanel.innerHTML = `
    <div class="detail-header"><div><span class="status ${state.className}"><span></span>${state.label}</span><h3>${escapeHTML(run.name)}</h3><p class="run-meta">${escapeHTML(run.run_number)} · ${escapeHTML(run.description || '无用途说明')}</p></div>
      ${canStop ? '<button id="stop-button" class="button danger"><i data-lucide="square"></i><span>停止任务</span></button>' : ''}
    </div>
    <div class="detail-tabs" role="tablist">
      <button data-tab="overview" class="${activeDetailTab === 'overview' ? 'active' : ''}">概览</button>
      <button data-tab="run-logs" class="${activeDetailTab === 'run-logs' ? 'active' : ''}">Run 日志</button>
      <button data-tab="task-logs" class="${activeDetailTab === 'task-logs' ? 'active' : ''}">任务日志</button>
    </div>
    <div id="detail-tab-content">${renderTabContent(run)}</div>
  `
  renderIcons()
  detailPanel.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach((button) => button.addEventListener('click', () => {
    activeDetailTab = button.dataset.tab as typeof activeDetailTab
    renderDetail()
    if (activeDetailTab !== 'overview') void loadSelectedLogs(false)
  }))
  document.querySelector<HTMLButtonElement>('#stop-button')?.addEventListener('click', () => void stopRun(run.run_id))
  document.querySelector<HTMLButtonElement>('#refresh-detail-logs')?.addEventListener('click', () => void loadSelectedLogs(true))
  document.querySelector<HTMLInputElement>('#task-filter')?.addEventListener('change', (event) => { taskFilter = inputNumber(event); void loadSelectedLogs(true) })
  document.querySelector<HTMLInputElement>('#attempt-filter')?.addEventListener('change', (event) => { attemptFilter = inputNumber(event); void loadSelectedLogs(true) })
}

function renderTabContent(run: RunRecord) {
  if (activeDetailTab !== 'overview') {
    const logs = activeDetailTab === 'run-logs' ? runLogs : taskLogs
    return `<div class="detail-log-toolbar">
      ${activeDetailTab === 'task-logs' ? `<input id="task-filter" type="number" min="1" value="${taskFilter ?? ''}" placeholder="任务 ID"><input id="attempt-filter" type="number" min="1" value="${attemptFilter ?? ''}" placeholder="尝试次数">` : ''}
      <button id="refresh-detail-logs" class="button secondary" type="button">刷新日志</button>
    </div><div class="detail-logs">${logs.length ? logs.map(renderPersistedLog).join('') : '<div class="logs-empty">暂无日志</div>'}</div>`
  }
  const summary = run.summary
  return `
    <div class="metrics">
      <div><span>成功</span><strong>${summary?.succeeded ?? '—'}</strong></div>
      <div><span>失败</span><strong>${summary?.failed ?? '—'}</strong></div>
      <div><span>取消</span><strong>${summary?.cancelled ?? '—'}</strong></div>
      <div><span>重试</span><strong>${summary?.retries ?? '—'}</strong></div>
      <div><span>总耗时</span><strong>${summary ? formatSeconds(summary.duration_seconds) : formatDuration(run)}</strong></div>
    </div>
    <dl class="options-list">
      <div><dt>并发 / 循环</dt><dd>${run.options.threads} / ${run.options.loops}</dd></div>
      <div><dt>来源编号</dt><dd>${escapeHTML(run.options.source_id)}</dd></div>
      <div><dt>循环间隔</dt><dd>${run.options.loop_delay} 秒</dd></div>
      <div><dt>随机种子</dt><dd>${run.options.seed ?? '未设置'}</dd></div>
      <div><dt>运行模式</dt><dd>${[run.options.headless && '无头', run.options.auto_submit && '自动提交', run.options.debug && '调试'].filter(Boolean).join(' · ') || '标准'}</dd></div>
    </dl>
    <dl class="options-list email-detail">
      <div><dt>邮件状态</dt><dd>${escapeHTML(emailStatus(run.email_status))}</dd></div>
      <div><dt>发送次数</dt><dd>${run.email_attempts}</dd></div>
      <div><dt>发送时间</dt><dd>${run.email_sent_at ? formatDate(run.email_sent_at) : '—'}</dd></div>
    </dl>
    ${run.email_last_error ? `<div class="error-message">邮件发送失败：${escapeHTML(run.email_last_error)}</div>` : ''}
    ${run.error ? `<div class="error-message">${escapeHTML(run.error)}</div>` : ''}
  `
}

function renderPersistedLog(log: RunLog | TaskLog) {
  const task = 'task_id' in log ? `<b>#${log.task_id} / ${log.attempt}</b>` : ''
  return `<div class="persisted-log"><time>${formatDate(log.timestamp)}</time>${task}<span class="log-level">${escapeHTML(log.level)}</span><code>${escapeHTML(log.event_type)}</code><span>${escapeHTML(log.message)}</span>${log.error ? `<em>${escapeHTML(log.error)}</em>` : ''}</div>`
}

async function loadSelectedLogs(reset: boolean) {
  if (!selectedRunID || loadingDetailLogs) return
  loadingDetailLogs = true
  try {
    if (activeDetailTab === 'run-logs') {
      if (reset) { runLogs = []; runLogCursor = 0 }
      const page = await api.GetRunLogs(selectedRunID, runLogCursor, 200)
      runLogs.push(...page.items); runLogCursor = page.next_after_log_id ?? runLogCursor
    } else if (activeDetailTab === 'task-logs') {
      if (reset) { taskLogs = []; taskLogCursor = 0 }
      const page = await api.GetTaskLogs(selectedRunID, taskLogCursor, 200, taskFilter, attemptFilter)
      taskLogs.push(...page.items); taskLogCursor = page.next_after_log_id ?? taskLogCursor
    }
    renderDetail()
  } catch (error) { reportError('加载日志失败', error) } finally { loadingDetailLogs = false }
}

function inputNumber(event: Event) { const value = (event.target as HTMLInputElement).value; return value ? Number(value) : null }
function emailStatus(status: string) { return ({ none: '未进入终态', pending: '等待发送', sending: '发送中', retry_wait: '等待重试', sent: '已发送', failed: '发送失败' } as Record<string, string>)[status] ?? status }

async function stopRun(runID: string) {
  const button = document.querySelector<HTMLButtonElement>('#stop-button')
  if (button) setBusy(button, true)
  try {
    await api.StopRun(runID)
    addLog(`已请求停止任务 ${shortID(runID)}`, 'warning')
    toast('停止请求已发送', 'warning')
    await refreshRuns(false)
  } catch (error) {
    reportError('停止失败', error)
  } finally {
    if (button) setBusy(button, false)
  }
}

function startPolling() {
  if (pollTimer !== null) window.clearInterval(pollTimer)
  pollTimer = window.setInterval(() => void refreshRuns(false), 2000)
}

function markDisconnected() {
  connected = false
  connectionState.className = 'connection-state disconnected'
  connectionLabel.textContent = '未连接'
  if (pollTimer !== null) window.clearInterval(pollTimer)
  pollTimer = null
}

function setBusy(button: HTMLButtonElement, busy: boolean) {
  button.disabled = busy
  button.classList.toggle('busy', busy)
}

function reportError(prefix: string, error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  addLog(`${prefix}: ${message}`, 'error')
  toast(`${prefix}: ${message}`, 'error')
}

function addLog(message: string, level: string) {
  if (logLines.textContent?.includes('等待连接服务器')) logLines.innerHTML = ''
  const line = document.createElement('div')
  line.className = level
  line.innerHTML = `<time>${new Date().toLocaleTimeString('zh-CN', { hour12: false })}</time><span>${escapeHTML(message)}</span>`
  logLines.prepend(line)
}

function toast(message: string, type: string) {
  const element = document.createElement('div')
  element.className = `toast ${type}`
  element.textContent = message
  byID<HTMLDivElement>('toast-region').append(element)
  window.setTimeout(() => element.remove(), 3500)
}

function formatDuration(run: RunRecord) {
  if (!run.started_at) return '—'
  return formatSeconds((run.finished_at ?? Date.now() / 1000) - run.started_at)
}

function formatSeconds(seconds: number) {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} 秒`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}分 ${Math.round(seconds % 60)}秒`
}

function formatDate(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}

function safeStatus(status: string) {
  const states: Record<string, { className: string; label: string }> = {
    pending: { className: 'pending', label: '等待中' },
    running: { className: 'running', label: '运行中' },
    completed: { className: 'completed', label: '已完成' },
    failed: { className: 'failed', label: '失败' },
    stopping: { className: 'stopping', label: '停止中' },
    stopped: { className: 'stopped', label: '已停止' },
    interrupted: { className: 'failed', label: '服务重启中断' },
  }
  return states[status] ?? { className: 'unknown', label: '未知状态' }
}

function renderIcons() {
  createIcons({ icons: appIcons })
  document.querySelectorAll('svg[data-lucide]').forEach((icon) => icon.removeAttribute('data-lucide'))
}

function shortID(id: string) { return id.slice(0, 10) }
function byID<T extends HTMLElement>(id: string) { return document.getElementById(id) as T }
function escapeHTML(value: unknown) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]!)
}
