## ADDED Requirements

### Requirement: Persist a Run before execution
The service SHALL persist every complete batch Run in SQLite before starting its scheduler thread. The persisted Run SHALL have an immutable UUID `run_id`, a unique server-generated readable `run_number`, a name, an optional description, execution options, status, result summary, final error, email status, and lifecycle timestamps.

#### Scenario: Named Run starts successfully
- **WHEN** a client starts a Run with a valid name, description, and execution options
- **THEN** the service persists a `pending` Run before starting execution and returns its `run_id` and `run_number`

#### Scenario: Persistence fails before startup
- **WHEN** the service cannot persist a new Run
- **THEN** it rejects `start_run` and does not start a scheduler thread

#### Scenario: Legacy client omits a name
- **WHEN** a compatible legacy RPC client starts a Run without a name
- **THEN** the service assigns a deterministic default display name while preserving the normal Run identity

### Requirement: Enforce valid Run state transitions
The service SHALL update Run state through conditional transitions and SHALL treat `completed`, `failed`, `stopped`, and `interrupted` as immutable final states.

#### Scenario: Running Run completes
- **WHEN** a `running` Run finishes all internal tasks
- **THEN** the service persists `completed`, its summary, and its finish time

#### Scenario: Competing final transition
- **WHEN** two actors attempt incompatible transitions from the same expected state
- **THEN** only the first valid transition commits and the other receives a transition conflict

### Requirement: Recover interrupted Runs on startup
The service SHALL recover persisted active Runs before accepting RPC requests and SHALL not attempt to resume their Selenium execution.

#### Scenario: Server restarts during execution
- **WHEN** startup finds a Run in `pending`, `running`, or `stopping`
- **THEN** it transitions the Run to `interrupted`, records a finish time and interruption error, and makes it eligible for final notification

#### Scenario: Server restarts after completion
- **WHEN** startup finds a Run already in a final state
- **THEN** it preserves that state and result unchanged

### Requirement: Query persistent Run history
The service SHALL serve Run history from SQLite after process restarts and SHALL support bounded pagination ordered by creation time and a stable tie-breaker.

#### Scenario: Client lists recent history
- **WHEN** a client requests a page with a supported limit and cursor
- **THEN** the service returns that bounded page and a cursor for any following page

#### Scenario: Client opens an old Run
- **WHEN** a client requests a persisted `run_id` created by a previous server process
- **THEN** the service returns its metadata, options, status, summary, error, timestamps, and email status

### Requirement: Manage the SQLite schema safely
The service SHALL create and migrate the SQLite schema transactionally using a recorded schema version and SHALL enable settings required for local concurrent reads and serialized writes.

#### Scenario: First server startup
- **WHEN** no database exists in the configured data directory
- **THEN** the service creates `runs`, `run_logs`, `task_logs`, required indexes, and the initial schema version

#### Scenario: Unsupported newer schema
- **WHEN** the database schema version is newer than the running service supports
- **THEN** startup fails without modifying the database

### Requirement: Client supplies and displays Run metadata
The Go client SHALL require a Run name, allow an optional purpose description, and display the server-generated number, name, description, persistent state, and email status in history and detail views.

#### Scenario: User starts a named batch
- **WHEN** the user enters a valid name and starts a batch
- **THEN** the client sends the name and optional description with the existing execution parameters

#### Scenario: User omits the Run name
- **WHEN** the user attempts to submit the new-client form without a name
- **THEN** the client prevents submission and identifies the missing field
