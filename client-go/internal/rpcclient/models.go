package rpcclient

type PingResponse struct {
	OK      bool   `xmlrpc:"ok" json:"ok"`
	Service string `xmlrpc:"service" json:"service"`
}

type StartOptions struct {
	Name        string  `json:"name"`
	Description string  `json:"description"`
	Threads     int     `json:"threads"`
	Loops       int     `json:"loops"`
	SourceID    string  `json:"source_id"`
	Headless    bool    `json:"headless"`
	AutoSubmit  bool    `json:"auto_submit"`
	Debug       bool    `json:"debug"`
	Retries     int     `json:"retries"`
	LoopDelay   float64 `json:"loop_delay"`
	Seed        *int    `json:"seed"`
}

type StartResponse struct {
	RunID     string `xmlrpc:"run_id" json:"run_id"`
	RunNumber string `xmlrpc:"run_number" json:"run_number"`
	Name      string `xmlrpc:"name" json:"name"`
	Status    string `xmlrpc:"status" json:"status"`
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
	OK                 *bool       `xmlrpc:"ok" json:"ok,omitempty"`
	Error              *string     `xmlrpc:"error" json:"error"`
	RunID              string      `xmlrpc:"run_id" json:"run_id"`
	RunNumber          string      `xmlrpc:"run_number" json:"run_number"`
	Name               string      `xmlrpc:"name" json:"name"`
	Description        string      `xmlrpc:"description" json:"description"`
	Status             string      `xmlrpc:"status" json:"status"`
	EmailStatus        string      `xmlrpc:"email_status" json:"email_status"`
	EmailAttempts      int         `xmlrpc:"email_attempts" json:"email_attempts"`
	EmailLastError     *string     `xmlrpc:"email_last_error" json:"email_last_error"`
	EmailMessageID     *string     `xmlrpc:"email_message_id" json:"email_message_id"`
	EmailNextAttemptAt *float64    `xmlrpc:"email_next_attempt_at" json:"email_next_attempt_at"`
	EmailSentAt        *float64    `xmlrpc:"email_sent_at" json:"email_sent_at"`
	CreatedAt          float64     `xmlrpc:"created_at" json:"created_at"`
	StartedAt          *float64    `xmlrpc:"started_at" json:"started_at"`
	FinishedAt         *float64    `xmlrpc:"finished_at" json:"finished_at"`
	Options            RunOptions  `xmlrpc:"options" json:"options"`
	Summary            *RunSummary `xmlrpc:"summary" json:"summary"`
}

type RunPage struct {
	Items      []RunRecord `json:"items"`
	NextCursor *string     `json:"next_cursor"`
}

type RunLog struct {
	LogID     int64   `json:"log_id"`
	RunID     string  `json:"run_id"`
	Timestamp float64 `json:"timestamp"`
	Level     string  `json:"level"`
	Component string  `json:"component"`
	EventType string  `json:"event_type"`
	Message   string  `json:"message"`
	Error     *string `json:"error"`
}

type TaskLog struct {
	RunLog
	TaskID         int      `json:"task_id"`
	Attempt        int      `json:"attempt"`
	Worker         *string  `json:"worker"`
	ElapsedSeconds *float64 `json:"elapsed_seconds"`
}

type RunLogPage struct {
	OK             *bool    `json:"ok,omitempty"`
	Error          *string  `json:"error,omitempty"`
	Items          []RunLog `json:"items"`
	NextAfterLogID *int64   `json:"next_after_log_id"`
}

type TaskLogPage struct {
	OK             *bool     `json:"ok,omitempty"`
	Error          *string   `json:"error,omitempty"`
	Items          []TaskLog `json:"items"`
	NextAfterLogID *int64    `json:"next_after_log_id"`
}
