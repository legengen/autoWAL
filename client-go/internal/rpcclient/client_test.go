package rpcclient

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return f(request)
}

func TestNormalizeURL(t *testing.T) {
	got, err := NormalizeURL(" 127.0.0.1:8765/ ")
	if err != nil || got != "http://127.0.0.1:8765" {
		t.Fatalf("NormalizeURL() = %q, %v", got, err)
	}
	if _, err := NormalizeURL("ftp://example.com"); err == nil {
		t.Fatal("expected unsupported scheme error")
	}
}

func TestTimeoutTransportKeepsContextUntilBodyClose(t *testing.T) {
	var requestContext context.Context
	transport := timeoutTransport{
		timeout: time.Second,
		base: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			requestContext = request.Context()
			return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader("ok"))}, nil
		}),
	}
	request, _ := http.NewRequest(http.MethodGet, "http://example.test", nil)
	response, err := transport.RoundTrip(request)
	if err != nil {
		t.Fatalf("RoundTrip() error: %v", err)
	}
	select {
	case <-requestContext.Done():
		t.Fatal("request context was cancelled before response body was consumed")
	default:
	}
	if err := response.Body.Close(); err != nil {
		t.Fatalf("Body.Close() error: %v", err)
	}
	select {
	case <-requestContext.Done():
	default:
		t.Fatal("request context was not cancelled when response body closed")
	}
}

func TestTimeoutTransportCancelsContextOnError(t *testing.T) {
	var requestContext context.Context
	transport := timeoutTransport{
		timeout: time.Second,
		base: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			requestContext = request.Context()
			return nil, errors.New("network error")
		}),
	}
	request, _ := http.NewRequest(http.MethodGet, "http://example.test", nil)
	if _, err := transport.RoundTrip(request); err == nil {
		t.Fatal("expected transport error")
	}
	select {
	case <-requestContext.Done():
	default:
		t.Fatal("request context was not cancelled after transport error")
	}
}

func TestPythonServerIntegration(t *testing.T) {
	serverURL := os.Getenv("AUTOWAL_RPC_URL")
	if serverURL == "" {
		t.Skip("AUTOWAL_RPC_URL is not set")
	}
	client := New()
	ping, err := client.Connect(serverURL)
	if err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	if !ping.OK || ping.Service != "autoWAL" {
		t.Fatalf("unexpected ping response: %#v", ping)
	}
	if _, err := client.ListRuns(); err != nil {
		t.Fatalf("ListRuns() error: %v", err)
	}
	if _, err := client.ListRunsPage(20, ""); err != nil {
		t.Fatalf("ListRunsPage() error: %v", err)
	}
	if _, err := client.GetRunLogs("missing", 0, 20); err == nil {
		t.Fatal("GetRunLogs() should report a missing Run")
	}
}

func TestClientInteroperabilityAndNilFields(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "text/xml")
		switch {
		case strings.Contains(string(body), "<methodName>ping</methodName>"):
			io.WriteString(w, response(`<struct><member><name>ok</name><value><boolean>1</boolean></value></member><member><name>service</name><value><string>autoWAL</string></value></member></struct>`))
		case strings.Contains(string(body), "<methodName>list_runs</methodName>"):
			io.WriteString(w, response(`<array><data><value><struct>
				<member><name>run_id</name><value><string>abc123</string></value></member>
				<member><name>status</name><value><string>pending</string></value></member>
				<member><name>created_at</name><value><double>100.5</double></value></member>
				<member><name>started_at</name><value><nil/></value></member>
				<member><name>finished_at</name><value><nil/></value></member>
				<member><name>options</name><value><struct><member><name>seed</name><value><nil/></value></member></struct></value></member>
				<member><name>summary</name><value><nil/></value></member>
				<member><name>error</name><value><nil/></value></member>
			</struct></value></data></array>`))
		default:
			t.Fatalf("unexpected request: %s", body)
		}
	}))
	defer server.Close()

	client := New()
	if _, err := client.Connect(server.URL); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	runs, err := client.ListRuns()
	if err != nil {
		t.Fatalf("ListRuns() error: %v", err)
	}
	if len(runs) != 1 || runs[0].RunID != "abc123" || runs[0].StartedAt != nil || runs[0].Summary != nil {
		t.Fatalf("unexpected decoded record: %#v", runs)
	}
}

func TestPersistentRunAndLogFixtures(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		request := string(body)
		w.Header().Set("Content-Type", "text/xml")
		switch {
		case strings.Contains(request, "<methodName>ping</methodName>"):
			io.WriteString(w, response(`<struct><member><name>ok</name><value><boolean>1</boolean></value></member><member><name>service</name><value><string>autoWAL</string></value></member></struct>`))
		case strings.Contains(request, "<methodName>list_runs</methodName>"):
			io.WriteString(w, response(`<struct>
				<member><name>items</name><value><array><data><value><struct>
					<member><name>run_id</name><value><string>run-a</string></value></member>
					<member><name>run_number</name><value><string>20260711-000001</string></value></member>
					<member><name>name</name><value><string>Nightly</string></value></member>
					<member><name>description</name><value><string>Regression</string></value></member>
					<member><name>status</name><value><string>completed</string></value></member>
					<member><name>email_status</name><value><string>sent</string></value></member>
					<member><name>email_attempts</name><value><int>1</int></value></member>
					<member><name>email_last_error</name><value><nil/></value></member>
					<member><name>email_sent_at</name><value><double>200</double></value></member>
					<member><name>created_at</name><value><double>100</double></value></member>
					<member><name>started_at</name><value><nil/></value></member>
					<member><name>finished_at</name><value><double>199</double></value></member>
					<member><name>options</name><value><struct></struct></value></member>
					<member><name>summary</name><value><nil/></value></member>
					<member><name>error</name><value><nil/></value></member>
				</struct></value></data></array></value></member>
				<member><name>next_cursor</name><value><string>100|run-a</string></value></member>
			</struct>`))
		case strings.Contains(request, "<methodName>get_run_logs</methodName>"):
			io.WriteString(w, response(logPageXML(false)))
		case strings.Contains(request, "<methodName>get_task_logs</methodName>"):
			io.WriteString(w, response(logPageXML(true)))
		default:
			t.Fatalf("unexpected request: %s", body)
		}
	}))
	defer server.Close()

	client := New()
	if _, err := client.Connect(server.URL); err != nil {
		t.Fatal(err)
	}
	page, err := client.ListRunsPage(20, "")
	if err != nil || len(page.Items) != 1 || page.Items[0].EmailSentAt == nil {
		t.Fatalf("unexpected run page: %#v, %v", page, err)
	}
	runLogs, err := client.GetRunLogs("run-a", 0, 20)
	if err != nil || len(runLogs.Items) != 1 || runLogs.Items[0].EventType != "run.completed" {
		t.Fatalf("unexpected run logs: %#v, %v", runLogs, err)
	}
	taskID, attempt := 7, 2
	taskLogs, err := client.GetTaskLogs("run-a", 0, 20, &taskID, &attempt)
	if err != nil || len(taskLogs.Items) != 1 || taskLogs.Items[0].TaskID != 7 {
		t.Fatalf("unexpected task logs: %#v, %v", taskLogs, err)
	}
}

func logPageXML(task bool) string {
	extra := ""
	event := "run.completed"
	if task {
		event = "task.completed"
		extra = `<member><name>task_id</name><value><int>7</int></value></member><member><name>attempt</name><value><int>2</int></value></member><member><name>worker</name><value><string>worker-1</string></value></member><member><name>elapsed_seconds</name><value><double>1.25</double></value></member>`
	}
	return `<struct><member><name>items</name><value><array><data><value><struct>` +
		`<member><name>log_id</name><value><int>3</int></value></member>` +
		`<member><name>run_id</name><value><string>run-a</string></value></member>` + extra +
		`<member><name>timestamp</name><value><double>100</double></value></member>` +
		`<member><name>level</name><value><string>INFO</string></value></member>` +
		`<member><name>component</name><value><string>runtime</string></value></member>` +
		`<member><name>event_type</name><value><string>` + event + `</string></value></member>` +
		`<member><name>message</name><value><string>done</string></value></member>` +
		`<member><name>error</name><value><nil/></value></member>` +
		`</struct></value></data></array></value></member><member><name>next_after_log_id</name><value><int>3</int></value></member></struct>`
}

func response(value string) string {
	return `<?xml version="1.0"?><methodResponse><params><param><value>` + value + `</value></param></params></methodResponse>`
}
