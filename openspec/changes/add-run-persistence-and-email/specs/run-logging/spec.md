## ADDED Requirements

### Requirement: Separate Run and internal task logs
The service SHALL persist Run lifecycle events in `run_logs` and internal questionnaire execution events in `task_logs` without treating an internal task as a user-named Run.

#### Scenario: Run lifecycle event is recorded
- **WHEN** a Run is created, started, stopped, completed, failed, interrupted, or changes final email state
- **THEN** the service writes a structured `run_logs` row with run identity, timestamp, level, component, event type, message, and optional error

#### Scenario: Internal task attempt is recorded
- **WHEN** an internal questionnaire task starts, retries, succeeds, or fails
- **THEN** the service writes structured `task_logs` rows associated with `run_id`, `task_id`, and `attempt`, including available worker, component, event type, level, error, and elapsed time

### Requirement: Serialize all database writes
The service SHALL route Run state commands, Run logs, and task logs through one database writer thread. Scheduler, worker, filler, and mail threads MUST NOT execute SQLite writes directly.

#### Scenario: Multiple workers emit logs concurrently
- **WHEN** multiple workers from one or more Runs emit log events at the same time
- **THEN** the events enter a bounded queue and the writer persists them serially without mixing their Run/task context

#### Scenario: Persistence queue is full
- **WHEN** a producer tries to emit a required log while the bounded queue is full
- **THEN** the producer applies backpressure rather than silently dropping the event

### Requirement: Atomically record Run transitions
The database writer SHALL update `runs` and insert the corresponding lifecycle `run_logs` event in one SQLite transaction.

#### Scenario: Final state commits
- **WHEN** a valid Run transition to a final state is processed
- **THEN** both the final `runs` state and its lifecycle event become visible together after commit

#### Scenario: Lifecycle log insert fails
- **WHEN** the lifecycle log cannot be inserted during a Run transition
- **THEN** the transaction rolls back the Run state update

### Requirement: Preserve log ordering before finalization
The persistence queue SHALL support a barrier that confirms all earlier task log commands are committed before a Run final transition is committed.

#### Scenario: Last worker finishes
- **WHEN** the scheduler is ready to finalize a Run
- **THEN** it waits for the persistence barrier before submitting the final state transition

### Requirement: Query logs incrementally
The service SHALL expose bounded XML-RPC queries for Run and task logs using monotonic `log_id` cursors.

#### Scenario: Client polls new Run logs
- **WHEN** a client requests Run logs with `after_log_id` and `limit`
- **THEN** the service returns only later log rows up to the limit and the next cursor

#### Scenario: Client filters task logs
- **WHEN** a client requests task logs for a Run and optionally a `task_id` or `attempt`
- **THEN** the service returns matching rows in ascending `log_id` order

### Requirement: Protect sensitive diagnostic content
The service SHALL omit credentials from all logs and SHALL persist DOM-level or other high-volume diagnostic details only when the Run has debug logging enabled.

#### Scenario: SMTP authentication fails
- **WHEN** the mail sender reports an authentication error
- **THEN** the persisted log contains a sanitized error without the SMTP password or authorization material

#### Scenario: Normal Run records filler activity
- **WHEN** debug mode is disabled
- **THEN** operational task events are persisted without raw DOM dumps
