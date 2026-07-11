## ADDED Requirements

### Requirement: Create one logical final notification per Run
The service SHALL create exactly one logical final status email notification when a Run first enters `completed`, `failed`, `stopped`, or `interrupted`. Internal questionnaire tasks SHALL NOT create email notifications.

#### Scenario: Run completes
- **WHEN** a non-final Run transitions to `completed`
- **THEN** the same transaction sets `email_status` to `pending`, assigns a deterministic Message-ID, and records `email.queued`

#### Scenario: Final transition is replayed
- **WHEN** the service receives a duplicate request to finalize an already-final Run
- **THEN** it does not create or reset another logical notification

#### Scenario: Internal task completes
- **WHEN** one questionnaire task inside an active Run succeeds or fails
- **THEN** no email notification is created for that internal task

### Requirement: Deliver final email asynchronously
The mail sender SHALL claim pending notifications through the database writer and SHALL not block the scheduler or worker on SMTP network operations.

#### Scenario: Pending email sends successfully
- **WHEN** SMTP accepts a pending final notification
- **THEN** the service marks it `sent`, records `email_sent_at`, and writes an `email.sent` lifecycle event

#### Scenario: SMTP send fails temporarily
- **WHEN** SMTP returns a retryable error
- **THEN** the service increments attempts, records a sanitized `email.failed` event, and schedules the same logical notification for retry

#### Scenario: Retry limit is reached
- **WHEN** the configured maximum attempts are exhausted
- **THEN** the service marks the notification `failed` and preserves the last sanitized error for operators and clients

### Requirement: Recover incomplete email delivery
The service SHALL recover unfinished email states after restart without re-queuing notifications already marked `sent`.

#### Scenario: Server restarts while email is sending
- **WHEN** startup finds a final Run with `email_status` equal to `sending`
- **THEN** it moves the same logical notification to a retryable state and retains its deterministic Message-ID

#### Scenario: Server restarts after email was recorded sent
- **WHEN** startup finds `email_status` equal to `sent`
- **THEN** it does not send or queue another notification

### Requirement: Include useful Run outcome information
The final email SHALL include the Run number, name, description, final state, timestamps, execution options, success/failure/cancel/retry counts, duration, and sanitized final error when present.

#### Scenario: Failed Run email is composed
- **WHEN** a failed Run is delivered by the mail sender
- **THEN** the subject identifies its Run number, name, and failed state, and the body contains its persisted outcome summary and error

### Requirement: Keep SMTP credentials outside persistent data
The service SHALL obtain SMTP endpoint, authentication, sender, recipient, and TLS settings from server-side environment configuration and MUST NOT expose credentials through SQLite, logs, or XML-RPC.

#### Scenario: SMTP password is configured
- **WHEN** the service initializes the mail sender from its environment
- **THEN** it uses the password for authentication without writing it to any persistent record or RPC response

#### Scenario: Required SMTP configuration is missing
- **WHEN** a final notification is pending but required SMTP settings are absent
- **THEN** the service retains a failed or retryable email state with a sanitized configuration error and leaves the completed Run itself intact

### Requirement: Display email delivery status
The Go client SHALL display the persisted final email status and any sanitized delivery error without requiring the client to remain connected while the Run executes.

#### Scenario: User returns after server restart
- **WHEN** the client later opens a persisted Run
- **THEN** it displays whether the final notification is pending, sending, sent, retrying, or failed
