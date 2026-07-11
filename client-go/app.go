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

func (a *App) StopRun(runID string) (rpcclient.StopResponse, error) {
	return a.rpc.StopRun(runID)
}
