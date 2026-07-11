package main

import "github.com/autowal/client/internal/rpcclient"

type App struct {
	rpc *rpcclient.Client
}

type ConnectionResult struct {
	OK      bool   `json:"ok"`
	Service string `json:"service"`
	URL     string `json:"url"`
}

func NewApp() *App {
	return &App{rpc: rpcclient.New()}
}

func (a *App) Connect(serverURL string) (ConnectionResult, error) {
	ping, err := a.rpc.Connect(serverURL)
	if err != nil {
		return ConnectionResult{}, err
	}
	return ConnectionResult{OK: true, Service: ping.Service, URL: a.rpc.URL()}, nil
}

func (a *App) StartRun(options rpcclient.StartOptions) (rpcclient.StartResponse, error) {
	return a.rpc.StartRun(options)
}

func (a *App) GetRun(runID string) (rpcclient.RunRecord, error) {
	return a.rpc.GetRun(runID)
}

func (a *App) ListRuns() ([]rpcclient.RunRecord, error) {
	return a.rpc.ListRuns()
}

func (a *App) ListRunsPage(limit int, cursor string) (rpcclient.RunPage, error) {
	return a.rpc.ListRunsPage(limit, cursor)
}

func (a *App) GetRunLogs(runID string, afterLogID int64, limit int) (rpcclient.RunLogPage, error) {
	return a.rpc.GetRunLogs(runID, afterLogID, limit)
}

func (a *App) GetTaskLogs(runID string, afterLogID int64, limit int, taskID, attempt *int) (rpcclient.TaskLogPage, error) {
	return a.rpc.GetTaskLogs(runID, afterLogID, limit, taskID, attempt)
}

func (a *App) StopRun(runID string) (rpcclient.StopResponse, error) {
	return a.rpc.StopRun(runID)
}
