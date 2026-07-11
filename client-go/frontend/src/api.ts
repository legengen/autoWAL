export interface StartOptions {
  name: string
  description: string
  threads: number
  loops: number
  source_id: string
  headless: boolean
  auto_submit: boolean
  debug: boolean
  retries: number
  loop_delay: number
  seed: number | null
}

export interface RunSummary {
  total: number
  completed: number
  succeeded: number
  failed: number
  cancelled: number
  retries: number
  duration_seconds: number
  exit_code: number
}

export interface RunRecord {
  ok?: boolean
  error: string | null
  run_id: string
  run_number: string
  name: string
  description: string
  status: string
  email_status: string
  email_attempts: number
  email_last_error: string | null
  email_message_id: string | null
  email_next_attempt_at: number | null
  email_sent_at: number | null
  created_at: number
  started_at: number | null
  finished_at: number | null
  options: StartOptions & { interactive?: boolean }
  summary: RunSummary | null
}

export interface RunLog {
  log_id: number; run_id: string; timestamp: number; level: string
  component: string; event_type: string; message: string; error: string | null
}

export interface TaskLog extends RunLog {
  task_id: number; attempt: number; worker: string | null; elapsed_seconds: number | null
}

export interface RunPage { items: RunRecord[]; next_cursor: string | null }
export interface RunLogPage { items: RunLog[]; next_after_log_id: number | null }
export interface TaskLogPage { items: TaskLog[]; next_after_log_id: number | null }

interface AppBindings {
  Connect(url: string): Promise<{ ok: boolean; service: string; url: string }>
  StartRun(options: StartOptions): Promise<{ run_id: string; run_number: string; name: string; status: string }>
  GetRun(runID: string): Promise<RunRecord>
  ListRuns(): Promise<RunRecord[]>
  ListRunsPage(limit: number, cursor: string): Promise<RunPage>
  GetRunLogs(runID: string, afterLogID: number, limit: number): Promise<RunLogPage>
  GetTaskLogs(runID: string, afterLogID: number, limit: number, taskID: number | null, attempt: number | null): Promise<TaskLogPage>
  StopRun(runID: string): Promise<{ ok: boolean; run_id: string; status: string; error: string }>
}

declare global {
  interface Window {
    go?: { main?: { App?: AppBindings } }
  }
}

const demoRuns: RunRecord[] = [
  {
    run_id: '6d79d691d3fa4b0ea2b4b9f1a9527e01', run_number: '20260711-000002', name: '夜间回归', description: '检查正式问卷流程', status: 'running', error: null,
    email_status: 'none', email_attempts: 0, email_last_error: null, email_message_id: null, email_next_attempt_at: null, email_sent_at: null,
    created_at: Date.now() / 1000 - 32, started_at: Date.now() / 1000 - 31, finished_at: null,
    options: { name: '夜间回归', description: '检查正式问卷流程', threads: 2, loops: 4, source_id: '719419', headless: true, auto_submit: false, debug: false, retries: 1, loop_delay: 1, seed: null },
    summary: null,
  },
  {
    run_id: '8a42f81d073542dc927250b57eedb714', run_number: '20260711-000001', name: '发布前验证', description: '版本验收', status: 'completed', error: null,
    email_status: 'sent', email_attempts: 1, email_last_error: null, email_message_id: '<demo@autowal.local>', email_next_attempt_at: null, email_sent_at: Date.now() / 1000 - 80,
    created_at: Date.now() / 1000 - 380, started_at: Date.now() / 1000 - 378, finished_at: Date.now() / 1000 - 82,
    options: { name: '发布前验证', description: '版本验收', threads: 1, loops: 3, source_id: '719419', headless: true, auto_submit: true, debug: false, retries: 0, loop_delay: 1, seed: 42 },
    summary: { total: 3, completed: 3, succeeded: 3, failed: 0, cancelled: 0, retries: 0, duration_seconds: 296, exit_code: 0 },
  },
]

const demoAPI: AppBindings = {
  async Connect(url) { return { ok: true, service: 'autoWAL (预览)', url: url.startsWith('http') ? url : `http://${url}` } },
  async StartRun(options) {
    const run_id = crypto.randomUUID().replaceAll('-', '')
    const run_number = `20260711-${String(demoRuns.length + 1).padStart(6, '0')}`
    demoRuns.unshift({ run_id, run_number, name: options.name, description: options.description, status: 'pending', error: null, email_status: 'none', email_attempts: 0, email_last_error: null, email_message_id: null, email_next_attempt_at: null, email_sent_at: null, created_at: Date.now() / 1000, started_at: null, finished_at: null, options, summary: null })
    return { run_id, run_number, name: options.name, status: 'pending' }
  },
  async GetRun(runID) { return demoRuns.find((run) => run.run_id === runID) ?? Promise.reject(new Error('任务不存在')) },
  async ListRuns() { return demoRuns },
  async ListRunsPage(limit, cursor) { return { items: cursor ? [] : demoRuns.slice(0, limit), next_cursor: null } },
  async GetRunLogs(runID, afterLogID) { return { items: afterLogID ? [] : [{ log_id: 1, run_id: runID, timestamp: Date.now() / 1000, level: 'INFO', component: 'rpc', event_type: 'run.created', message: 'Run created', error: null }], next_after_log_id: 1 } },
  async GetTaskLogs(runID, afterLogID, _limit, taskID, attempt) { return { items: afterLogID ? [] : [{ log_id: 1, run_id: runID, timestamp: Date.now() / 1000, level: 'INFO', component: 'worker', event_type: 'task.completed', message: 'Task completed', error: null, task_id: taskID ?? 1, attempt: attempt ?? 1, worker: 'worker-1', elapsed_seconds: 2.4 }], next_after_log_id: 1 } },
  async StopRun(runID) {
    const run = demoRuns.find((item) => item.run_id === runID)
    if (!run) throw new Error('任务不存在')
    run.status = 'stopping'
    return { ok: true, run_id: runID, status: 'stopping', error: '' }
  },
}

function bindings(): AppBindings {
  const app = window.go?.main?.App
  if (app) return app
  if (import.meta.env.DEV) return demoAPI
  throw new Error('Wails 运行时尚未就绪')
}

export const api: AppBindings = {
  Connect: (url) => bindings().Connect(url),
  StartRun: (options) => bindings().StartRun(options),
  GetRun: (runID) => bindings().GetRun(runID),
  ListRuns: () => bindings().ListRuns(),
  ListRunsPage: (limit, cursor) => bindings().ListRunsPage(limit, cursor),
  GetRunLogs: (runID, afterLogID, limit) => bindings().GetRunLogs(runID, afterLogID, limit),
  GetTaskLogs: (runID, afterLogID, limit, taskID, attempt) => bindings().GetTaskLogs(runID, afterLogID, limit, taskID, attempt),
  StopRun: (runID) => bindings().StopRun(runID),
}
