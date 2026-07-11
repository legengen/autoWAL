package rpcclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/kolo/xmlrpc"
)

const requestTimeout = 8 * time.Second

var ErrNotConnected = errors.New("尚未连接到服务器")

type timeoutTransport struct {
	base    http.RoundTripper
	timeout time.Duration
}

func (t timeoutTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	ctx, cancel := context.WithTimeout(req.Context(), t.timeout)
	response, err := t.base.RoundTrip(req.WithContext(ctx))
	if err != nil {
		cancel()
		return nil, err
	}
	response.Body = &cancelReadCloser{ReadCloser: response.Body, cancel: cancel}
	return response, nil
}

type cancelReadCloser struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (c *cancelReadCloser) Close() error {
	err := c.ReadCloser.Close()
	c.cancel()
	return err
}

type Client struct {
	mu     sync.RWMutex
	client *xmlrpc.Client
	url    string
}

func New() *Client {
	return &Client{}
}

func NormalizeURL(raw string) (string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", errors.New("请输入服务器地址")
	}
	if !strings.Contains(raw, "://") {
		raw = "http://" + raw
	}

	parsed, err := url.Parse(raw)
	if err != nil || parsed.Host == "" {
		return "", errors.New("服务器地址格式不正确")
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return "", errors.New("服务器地址仅支持 HTTP 或 HTTPS")
	}
	parsed.Fragment = ""
	return strings.TrimRight(parsed.String(), "/"), nil
}

func (c *Client) Connect(rawURL string) (PingResponse, error) {
	normalized, err := NormalizeURL(rawURL)
	if err != nil {
		return PingResponse{}, err
	}

	transport := timeoutTransport{
		base: &http.Transport{
			Proxy:                 http.ProxyFromEnvironment,
			DialContext:           (&net.Dialer{Timeout: 4 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
			TLSHandshakeTimeout:   4 * time.Second,
			ResponseHeaderTimeout: 6 * time.Second,
		},
		timeout: requestTimeout,
	}
	client, err := xmlrpc.NewClient(normalized, transport)
	if err != nil {
		return PingResponse{}, fmt.Errorf("创建 RPC 客户端失败: %w", err)
	}

	var response PingResponse
	if err := client.Call("ping", nil, &response); err != nil {
		client.Close()
		return PingResponse{}, fmt.Errorf("连接失败: %w", err)
	}
	if !response.OK {
		client.Close()
		return PingResponse{}, errors.New("服务器未返回有效的 ping 响应")
	}

	c.mu.Lock()
	previous := c.client
	c.client = client
	c.url = normalized
	c.mu.Unlock()
	if previous != nil {
		previous.Close()
	}
	return response, nil
}

func (c *Client) URL() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.url
}

func (c *Client) StartRun(options StartOptions) (StartResponse, error) {
	params := map[string]interface{}{
		"threads": options.Threads, "loops": options.Loops,
		"source_id": options.SourceID, "headless": options.Headless,
		"auto_submit": options.AutoSubmit, "debug": options.Debug,
		"retries": options.Retries, "loop_delay": options.LoopDelay,
	}
	if options.Seed != nil {
		params["seed"] = *options.Seed
	}
	var response StartResponse
	return response, c.call("start_run", params, &response)
}

func (c *Client) GetRun(runID string) (RunRecord, error) {
	var raw map[string]interface{}
	if err := c.call("get_run", runID, &raw); err != nil {
		return RunRecord{}, err
	}
	response, err := decodeRecord(raw)
	if err == nil && response.OK != nil && !*response.OK {
		return response, errors.New(valueOr(response.Error, "查询任务失败"))
	}
	return response, err
}

func (c *Client) ListRuns() ([]RunRecord, error) {
	var raw []map[string]interface{}
	if err := c.call("list_runs", nil, &raw); err != nil {
		return nil, err
	}
	response := make([]RunRecord, 0, len(raw))
	for _, item := range raw {
		record, err := decodeRecord(item)
		if err != nil {
			return nil, err
		}
		response = append(response, record)
	}
	return response, nil
}

func (c *Client) StopRun(runID string) (StopResponse, error) {
	var response StopResponse
	err := c.call("stop_run", runID, &response)
	if err == nil && !response.OK {
		return response, errors.New(response.Error)
	}
	return response, err
}

func (c *Client) call(method string, params interface{}, target interface{}) error {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.client == nil {
		return ErrNotConnected
	}
	if err := c.client.Call(method, params, target); err != nil {
		return fmt.Errorf("RPC %s 调用失败: %w", method, err)
	}
	return nil
}

func valueOr(value *string, fallback string) string {
	if value == nil || *value == "" {
		return fallback
	}
	return *value
}

func decodeRecord(raw map[string]interface{}) (RunRecord, error) {
	encoded, err := json.Marshal(raw)
	if err != nil {
		return RunRecord{}, fmt.Errorf("编码运行记录失败: %w", err)
	}
	var record RunRecord
	if err := json.Unmarshal(encoded, &record); err != nil {
		return RunRecord{}, fmt.Errorf("解析运行记录失败: %w", err)
	}
	return record, nil
}
