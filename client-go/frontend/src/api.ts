export interface StartOptions {
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
  status: string
  created_at: number
  started_at: number | null
  finished_at: number | null
  options: StartOptions & { interactive?: boolean }
  summary: RunSummary | null
}

interface AppBindings {
  Connect(url: string): Promise<{ ok: boolean; service: string; url: string }>
  StartRun(options: StartOptions): Promise<{ run_id: string; status: string }>
  GetRun(runID: string): Promise<RunRecord>
  ListRuns(): Promise<RunRecord[]>
  StopRun(runID: string): Promise<{ ok: boolean; run_id: string; status: string; error: string }>
}

declare global {
  interface Window {
    go?: { main?: { App?: AppBindings } }
  }
}

const demoRuns: RunRecord[] = [
  {
    run_id: '6d79d691d3fa4b0ea2b4b9f1a9527e01', status: 'running', error: null,
    created_at: Date.now() / 1000 - 32, started_at: Date.now() / 1000 - 31, finished_at: null,
    options: { threads: 2, loops: 4, source_id: '719419', headless: true, auto_submit: false, debug: false, retries: 1, loop_delay: 1, seed: null },
    summary: null,
  },
  {
    run_id: '8a42f81d073542dc927250b57eedb714', status: 'completed', error: null,
    created_at: Date.now() / 1000 - 380, started_at: Date.now() / 1000 - 378, finished_at: Date.now() / 1000 - 82,
    options: { threads: 1, loops: 3, source_id: '719419', headless: true, auto_submit: true, debug: false, retries: 0, loop_delay: 1, seed: 42 },
    summary: { total: 3, completed: 3, succeeded: 3, failed: 0, cancelled: 0, retries: 0, duration_seconds: 296, exit_code: 0 },
  },
]

const demoAPI: AppBindings = {
  async Connect(url) { return { ok: true, service: 'autoWAL (预览)', url: url.startsWith('http') ? url : `http://${url}` } },
  async StartRun(options) {
    const run_id = crypto.randomUUID().replaceAll('-', '')
    demoRuns.unshift({ run_id, status: 'pending', error: null, created_at: Date.now() / 1000, started_at: null, finished_at: null, options, summary: null })
    return { run_id, status: 'pending' }
  },
  async GetRun(runID) { return demoRuns.find((run) => run.run_id === runID) ?? Promise.reject(new Error('任务不存在')) },
  async ListRuns() { return demoRuns },
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
  StopRun: (runID) => bindings().StopRun(runID),
}
