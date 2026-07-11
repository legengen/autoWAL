# autoWAL Go Client

Wails v2 desktop client for the existing Python XML-RPC server.

## Development

Requirements: Go 1.25+, Node.js 24+, Wails v2, and WebView2 on Windows.

```powershell
go install github.com/wailsapp/wails/v2/cmd/wails@v2.13.0
cd client-go
wails dev
```

The Vite frontend has a local preview data source, so its layout can also be
developed without a Wails runtime:

```powershell
cd client-go/frontend
npm install
npm run dev
```

## Build

```powershell
cd client-go
wails build -clean
```

The Windows executable is written to `client-go/build/bin/autoWAL-client.exe`.

## Test

```powershell
cd client-go
go test ./...
cd frontend
npm run build
```
