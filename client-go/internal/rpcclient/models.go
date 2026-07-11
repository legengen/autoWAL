package rpcclient

type PingResponse struct {
	OK      bool   `xmlrpc:"ok" json:"ok"`
	Service string `xmlrpc:"service" json:"service"`
}

type StartOptions struct {
	Threads    int     `json:"threads"`
	Loops      int     `json:"loops"`
	SourceID   string  `json:"source_id"`
	Headless   bool    `json:"headless"`
	AutoSubmit bool    `json:"auto_submit"`
	Debug      bool    `json:"debug"`
	Retries    int     `json:"retries"`
	LoopDelay  float64 `json:"loop_delay"`
	Seed       *int    `json:"seed"`
}

type StartResponse struct {
	RunID  string `xmlrpc:"run_id" json:"run_id"`
	Status string `xmlrpc:"status" json:"status"`
}

type StopResponse struct {
	OK     bool   `xmlrpc:"ok" json:"ok"`
	RunID  string `xmlrpc:"run_id" json:"run_id"`
	Status string `xmlrpc:"status" json:"status"`
	Error  string `xmlrpc:"error" json:"error"`
}

type RunOptions struct {
	Headless    bool    `xmlrpc:"headless" json:"headless"`
	AutoSubmit  bool    `xmlrpc:"auto_submit" json:"auto_submit"`
	Debug       bool    `xmlrpc:"debug" json:"debug"`
	Seed        *int    `xmlrpc:"seed" json:"seed"`
	Loops       int     `xmlrpc:"loops" json:"loops"`
	LoopDelay   float64 `xmlrpc:"loop_delay" json:"loop_delay"`
	Threads     int     `xmlrpc:"threads" json:"threads"`
	Retries     int     `xmlrpc:"retries" json:"retries"`
	SourceID    string  `xmlrpc:"source_id" json:"source_id"`
	Interactive bool    `xmlrpc:"interactive" json:"interactive"`
}

type RunSummary struct {
	Total           int     `xmlrpc:"total" json:"total"`
	Completed       int     `xmlrpc:"completed" json:"completed"`
	Succeeded       int     `xmlrpc:"succeeded" json:"succeeded"`
	Failed          int     `xmlrpc:"failed" json:"failed"`
	Cancelled       int     `xmlrpc:"cancelled" json:"cancelled"`
	Retries         int     `xmlrpc:"retries" json:"retries"`
	DurationSeconds float64 `xmlrpc:"duration_seconds" json:"duration_seconds"`
	ExitCode        int     `xmlrpc:"exit_code" json:"exit_code"`
}

type RunRecord struct {
	OK         *bool       `xmlrpc:"ok" json:"ok,omitempty"`
	Error      *string     `xmlrpc:"error" json:"error"`
	RunID      string      `xmlrpc:"run_id" json:"run_id"`
	Status     string      `xmlrpc:"status" json:"status"`
	CreatedAt  float64     `xmlrpc:"created_at" json:"created_at"`
	StartedAt  *float64    `xmlrpc:"started_at" json:"started_at"`
	FinishedAt *float64    `xmlrpc:"finished_at" json:"finished_at"`
	Options    RunOptions  `xmlrpc:"options" json:"options"`
	Summary    *RunSummary `xmlrpc:"summary" json:"summary"`
}
