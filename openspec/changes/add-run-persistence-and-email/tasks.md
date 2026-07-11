## 1. SQLite Schema and Repository

- [x] 1.1 Add data-directory configuration and resolve an absolute `autowal.db` path without logging secrets or environment values.
- [x] 1.2 Implement transactional schema initialization and `PRAGMA user_version` migration for `runs`, `run_logs`, `task_logs`, indexes, WAL, foreign keys, and busy timeout.
- [x] 1.3 Implement Run row serialization for options/summary JSON, timestamps, email fields, UUID identity, and atomic unique readable-number allocation.
- [x] 1.4 Add repository read methods for a Run, cursor-paginated Run history, Run logs, and filtered task logs using separate read connections.
- [x] 1.5 Add isolated SQLite tests for first startup, migration, unsupported newer schema, number uniqueness, pagination, and JSON/null round trips.

## 2. Single Database Writer

- [x] 2.1 Define typed persistence commands and result/error channels for create, transition, Run log, task log, email state, recovery, barrier, and shutdown operations.
- [x] 2.2 Implement the bounded FIFO persistence queue and one writer thread with batching for adjacent standalone log inserts and blocking backpressure.
- [x] 2.3 Implement conditional Run transitions that atomically update `runs` and insert the corresponding `run_logs` event.
- [x] 2.4 Implement barrier and graceful-shutdown semantics that confirm all earlier commands are committed before finalization or connection close.
- [x] 2.5 Add concurrency tests proving workers never write SQLite directly, events retain Run/task context, queue saturation does not drop logs, and failed lifecycle inserts roll back state changes.

## 3. Run Lifecycle Integration

- [ ] 3.1 Extend `start_run` request parsing with name/description metadata, legacy default naming, validation, and persistence-before-thread-start behavior.
- [ ] 3.2 Keep active `ControlPlane` references in memory while making SQLite the source of truth for public Run records and history.
- [ ] 3.3 Route pending, running, stopping, completed, failed, and stopped changes through expected-state persistence commands with summary/error timestamps.
- [ ] 3.4 Add startup recovery that transitions active records to `interrupted`, preserves final records, and recovers stale email `sending` states before accepting RPC.
- [ ] 3.5 Add lifecycle tests for persistence failure before start, stop/complete races, final-state immutability, restart interruption, and normal shutdown queue flushing.

## 4. Structured Run and Task Logging

- [ ] 4.1 Define stable lifecycle and task event types plus logging adapters that attach run ID, task ID, attempt, worker, component, level, error, and elapsed time.
- [ ] 4.2 Replace scheduler and worker execution `print()` paths with structured events while preserving useful console output through logging handlers.
- [ ] 4.3 Migrate filler operational output to structured task logging and gate DOM/high-volume diagnostic data behind the existing debug option.
- [ ] 4.4 Insert a persistence barrier before every final Run transition so all prior task logs are queryable when the final state becomes visible.
- [ ] 4.5 Add multi-Run/multi-worker tests for log attribution, retry attempt identity, event ordering, sensitive-value sanitization, and debug gating.

## 5. Final Email Notification

- [ ] 5.1 Add SMTP environment configuration parsing and validation for host, port, TLS, user/password, sender, recipient, retry count, and retry delays without exposing credentials.
- [ ] 5.2 Extend final Run transitions to atomically create one pending logical notification, deterministic Message-ID, and `email.queued` lifecycle event.
- [ ] 5.3 Implement the asynchronous mail sender claim/send/result loop using writer commands for `sending`, `sent`, `retry_wait`, and `failed` states.
- [ ] 5.4 Compose sanitized text email subjects and bodies containing Run identity, metadata, final state, options, summary, timestamps, duration, and error.
- [ ] 5.5 Add fake-SMTP tests for success, temporary retry, permanent failure, retry exhaustion, restart recovery, duplicate-finalization suppression, and no internal-task email.

## 6. XML-RPC and Go Client

- [ ] 6.1 Extend XML-RPC Run models and methods with number/name/description/email fields, bounded history pagination, Run log cursor queries, and task log filters.
- [ ] 6.2 Add Python RPC contract tests covering legacy start requests, named requests, persistent history after service recreation, cursors, invalid limits, and missing Runs.
- [ ] 6.3 Extend Go RPC models/client methods and XML-RPC compatibility fixtures for nullable persistent fields, pagination, and both log response types.
- [ ] 6.4 Add required Run-name and optional-purpose controls to the Wails start form and display number, metadata, email status, and delivery errors in history/detail views.
- [ ] 6.5 Add incremental Run/task log views with bounded polling, task/attempt filters, empty/loading/error states, and no log payload in the existing Run-list polling path.

## 7. Verification and Operations

- [ ] 7.1 Document database location, backup/rollback, SMTP environment variables, at-least-once delivery limitation, log privacy, and interrupted recovery behavior.
- [ ] 7.2 Run the full Python suite, Go tests, TypeScript production build, real Python-to-Go XML-RPC interoperability test, and Windows Wails package build.
- [ ] 7.3 Add CI checks that create a fresh database, exercise migration/recovery, run fake-SMTP integration tests, and verify no credentials appear in captured logs or RPC payloads.
