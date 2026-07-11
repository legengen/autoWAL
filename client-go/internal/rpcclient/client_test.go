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

func response(value string) string {
	return `<?xml version="1.0"?><methodResponse><params><param><value>` + value + `</value></param></params></methodResponse>`
}
