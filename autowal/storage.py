import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime


SCHEMA_VERSION = 1
FINAL_STATUSES = frozenset(("completed", "failed", "stopped", "interrupted"))
ACTIVE_STATUSES = frozenset(("pending", "running", "stopping"))


class StorageError(RuntimeError):
    pass


class TransitionConflict(StorageError):
    pass


@dataclass
class PersistenceCommand:
    kind: str
    payload: dict
    result_queue: object = None


class RunStore:
    def __init__(self, database_path, queue_size=2000):
        self.database_path = os.path.abspath(database_path)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        self._initialize_schema()
        self._commands = queue.Queue(maxsize=queue_size)
        self._error_lock = threading.Lock()
        self._async_error = None
        self._thread = threading.Thread(
            target=self._writer_loop,
            name="autowal-database-writer",
            daemon=True,
        )
        self._closed = False
        self._thread.start()

    def create_run(self, name, description, options, created_at=None, run_id=None):
        return self._submit(
            "create_run",
            {
                "run_id": run_id or uuid.uuid4().hex,
                "name": name,
                "description": description,
                "options": options,
                "created_at": created_at if created_at is not None else time.time(),
            },
            wait=True,
        )

    def transition_run(
        self,
        run_id,
        expected_statuses,
        new_status,
        event_type,
        message,
        updates=None,
        level="INFO",
        component="rpc",
        error=None,
    ):
        return self._submit(
            "transition_run",
            {
                "run_id": run_id,
                "expected_statuses": tuple(expected_statuses),
                "new_status": new_status,
                "event": {
                    "timestamp": time.time(),
                    "level": level,
                    "component": component,
                    "event_type": event_type,
                    "message": message,
                    "error": error,
                },
                "updates": updates or {},
            },
            wait=True,
        )

    def append_run_log(self, run_id, event_type, message, level="INFO", component="runtime", error=None):
        self._submit(
            "append_run_log",
            {
                "run_id": run_id,
                "timestamp": time.time(),
                "level": level,
                "component": component,
                "event_type": event_type,
                "message": message,
                "error": error,
            },
            wait=False,
        )

    def append_task_log(
        self,
        run_id,
        task_id,
        attempt,
        event_type,
        message,
        level="INFO",
        worker=None,
        component="worker",
        error=None,
        elapsed_seconds=None,
    ):
        self._submit(
            "append_task_log",
            {
                "run_id": run_id,
                "task_id": task_id,
                "attempt": attempt,
                "timestamp": time.time(),
                "worker": worker,
                "component": component,
                "event_type": event_type,
                "level": level,
                "message": message,
                "error": error,
                "elapsed_seconds": elapsed_seconds,
            },
            wait=False,
        )

    def barrier(self):
        return self._submit("barrier", {}, wait=True)

    def recover_interrupted_runs(self, recovered_at=None):
        return self._submit(
            "recover_interrupted_runs",
            {"recovered_at": recovered_at if recovered_at is not None else time.time()},
            wait=True,
        )

    def claim_email(self, run_id, claimed_at=None):
        return self._submit(
            "claim_email",
            {"run_id": run_id, "claimed_at": claimed_at if claimed_at is not None else time.time()},
            wait=True,
        )

    def complete_email(self, run_id, success, error=None, retry_at=None, completed_at=None):
        return self._submit(
            "complete_email",
            {
                "run_id": run_id,
                "success": bool(success),
                "error": error,
                "retry_at": retry_at,
                "completed_at": completed_at if completed_at is not None else time.time(),
            },
            wait=True,
        )

    def get_due_email_runs(self, now=None, limit=20):
        limit = self._validate_limit(limit)
        now = now if now is not None else time.time()
        with closing(self._read_connection()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM runs
                WHERE status IN ('completed', 'failed', 'stopped', 'interrupted')
                  AND (email_status = 'pending'
                       OR (email_status = 'retry_wait' AND email_next_attempt_at <= ?))
                ORDER BY finished_at ASC, run_id ASC LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [self._decode_run(row) for row in rows]

    def close(self):
        if self._closed:
            return
        self._submit("shutdown", {}, wait=True)
        self._thread.join(timeout=5)
        self._closed = True

    def get_run(self, run_id):
        with closing(self._read_connection()) as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._decode_run(row) if row is not None else None

    def list_runs(self, limit=100, cursor=None):
        limit = self._validate_limit(limit)
        params = []
        where = ""
        if cursor:
            try:
                cursor_time, cursor_id = cursor.split("|", 1)
                cursor_time = float(cursor_time)
            except (TypeError, ValueError):
                raise ValueError("invalid run cursor")
            where = "WHERE created_at < ? OR (created_at = ? AND run_id < ?)"
            params.extend((cursor_time, cursor_time, cursor_id))
        params.append(limit)
        sql = "SELECT * FROM runs {} ORDER BY created_at DESC, run_id DESC LIMIT ?".format(where)
        with closing(self._read_connection()) as connection:
            rows = connection.execute(sql, params).fetchall()
        items = [self._decode_run(row) for row in rows]
        next_cursor = None
        if len(rows) == limit:
            last = rows[-1]
            next_cursor = "{}|{}".format(last["created_at"], last["run_id"])
        return {"items": items, "next_cursor": next_cursor}

    def get_run_logs(self, run_id, after_log_id=0, limit=200):
        return self._get_logs("run_logs", run_id, after_log_id, limit)

    def get_task_logs(self, run_id, after_log_id=0, limit=200, task_id=None, attempt=None):
        limit = self._validate_limit(limit)
        clauses = ["run_id = ?", "log_id > ?"]
        params = [run_id, int(after_log_id)]
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(int(task_id))
        if attempt is not None:
            clauses.append("attempt = ?")
            params.append(int(attempt))
        params.append(limit)
        sql = "SELECT * FROM task_logs WHERE {} ORDER BY log_id ASC LIMIT ?".format(
            " AND ".join(clauses)
        )
        with closing(self._read_connection()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return self._log_page(rows)

    def _get_logs(self, table, run_id, after_log_id, limit):
        limit = self._validate_limit(limit)
        sql = "SELECT * FROM {} WHERE run_id = ? AND log_id > ? ORDER BY log_id ASC LIMIT ?".format(table)
        with closing(self._read_connection()) as connection:
            rows = connection.execute(sql, (run_id, int(after_log_id), limit)).fetchall()
        return self._log_page(rows)

    @staticmethod
    def _log_page(rows):
        items = [dict(row) for row in rows]
        return {
            "items": items,
            "next_after_log_id": items[-1]["log_id"] if items else None,
        }

    @staticmethod
    def _validate_limit(limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500")
        return limit

    def _submit(self, kind, payload, wait):
        if self._closed:
            raise StorageError("run store is closed")
        result_queue = queue.Queue(maxsize=1) if wait else None
        command = PersistenceCommand(kind=kind, payload=payload, result_queue=result_queue)
        self._commands.put(command)
        if not wait:
            return None
        result = result_queue.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _writer_loop(self):
        connection = self._connect()
        pending = None
        try:
            while True:
                command = pending or self._commands.get()
                pending = None
                if command.kind in ("append_run_log", "append_task_log"):
                    batch = [command]
                    while len(batch) < 100:
                        try:
                            candidate = self._commands.get_nowait()
                        except queue.Empty:
                            break
                        if candidate.kind not in ("append_run_log", "append_task_log"):
                            pending = candidate
                            break
                        batch.append(candidate)
                    try:
                        self._execute_log_batch(connection, batch)
                        batch_result = None
                    except Exception as exc:
                        batch_result = exc
                        with self._error_lock:
                            if self._async_error is None:
                                self._async_error = exc
                    for item in batch:
                        self._complete(item, batch_result)
                        self._commands.task_done()
                    continue

                try:
                    result = self._execute_command(connection, command)
                except Exception as exc:
                    result = exc
                self._complete(command, result)
                self._commands.task_done()
                if command.kind == "shutdown":
                    break
        finally:
            connection.close()

    @staticmethod
    def _complete(command, result):
        if command.result_queue is not None:
            command.result_queue.put(result)

    def _execute_command(self, connection, command):
        if command.kind == "create_run":
            return self._create_run(connection, command.payload)
        if command.kind == "transition_run":
            return self._transition_run(connection, command.payload)
        if command.kind == "recover_interrupted_runs":
            return self._recover_interrupted_runs(connection, command.payload["recovered_at"])
        if command.kind == "claim_email":
            return self._claim_email(connection, command.payload)
        if command.kind == "complete_email":
            return self._complete_email(connection, command.payload)
        if command.kind in ("barrier", "shutdown"):
            with self._error_lock:
                async_error = self._async_error
                self._async_error = None
            if async_error is not None:
                raise StorageError("asynchronous log persistence failed: {}".format(async_error))
            return True
        raise StorageError("unknown persistence command: {}".format(command.kind))

    def _create_run(self, connection, payload):
        with connection:
            run_number = self._next_run_number(connection, payload["created_at"])
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, run_number, name, description, status, options_json,
                    summary_json, final_error, email_status, email_attempts,
                    created_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, NULL, NULL, 'none', 0, ?, NULL, NULL)
                """,
                (
                    payload["run_id"],
                    run_number,
                    payload["name"],
                    payload["description"],
                    json.dumps(payload["options"], ensure_ascii=False, separators=(",", ":")),
                    payload["created_at"],
                ),
            )
            self._insert_run_log(
                connection,
                {
                    "run_id": payload["run_id"],
                    "timestamp": payload["created_at"],
                    "level": "INFO",
                    "component": "rpc",
                    "event_type": "run.created",
                    "message": "Run created",
                    "error": None,
                },
            )
        return self.get_run(payload["run_id"])

    def _recover_interrupted_runs(self, connection, recovered_at):
        recovered = []
        with connection:
            rows = connection.execute(
                "SELECT run_id, status FROM runs WHERE status IN ('pending', 'running', 'stopping')"
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE runs SET status = 'interrupted', finished_at = ?, final_error = ?,
                        email_status = 'pending', email_message_id = ?
                    WHERE run_id = ?
                    """,
                    (
                        recovered_at,
                        "server restarted before Run completed",
                        self._message_id(row["run_id"]),
                        row["run_id"],
                    ),
                )
                self._insert_run_log(
                    connection,
                    {
                        "run_id": row["run_id"],
                        "timestamp": recovered_at,
                        "level": "ERROR",
                        "component": "recovery",
                        "event_type": "run.interrupted",
                        "message": "Run interrupted by server restart",
                        "error": "previous status: {}".format(row["status"]),
                    },
                )
                self._insert_run_log(
                    connection,
                    {
                        "run_id": row["run_id"],
                        "timestamp": recovered_at,
                        "level": "INFO",
                        "component": "mail",
                        "event_type": "email.queued",
                        "message": "Final Run email queued after recovery",
                        "error": None,
                    },
                )
                recovered.append(row["run_id"])
            stale = connection.execute(
                "SELECT run_id FROM runs WHERE email_status = 'sending'"
            ).fetchall()
            for row in stale:
                connection.execute(
                    "UPDATE runs SET email_status = 'retry_wait', email_next_attempt_at = ? WHERE run_id = ?",
                    (recovered_at, row["run_id"]),
                )
                self._insert_run_log(
                    connection,
                    {
                        "run_id": row["run_id"],
                        "timestamp": recovered_at,
                        "level": "WARNING",
                        "component": "mail",
                        "event_type": "email.retry_scheduled",
                        "message": "Stale sending email scheduled for retry",
                        "error": None,
                    },
                )
        return recovered

    def _claim_email(self, connection, payload):
        with connection:
            cursor = connection.execute(
                """
                UPDATE runs SET email_status = 'sending', email_attempts = email_attempts + 1,
                    email_next_attempt_at = NULL
                WHERE run_id = ? AND email_status IN ('pending', 'retry_wait')
                """,
                (payload["run_id"],),
            )
            if cursor.rowcount != 1:
                return None
            self._insert_run_log(
                connection,
                {
                    "run_id": payload["run_id"],
                    "timestamp": payload["claimed_at"],
                    "level": "INFO",
                    "component": "mail",
                    "event_type": "email.sending",
                    "message": "Sending final Run email",
                    "error": None,
                },
            )
        return self.get_run(payload["run_id"])

    def _complete_email(self, connection, payload):
        event_type = "email.sent" if payload["success"] else "email.failed"
        status = "sent" if payload["success"] else ("retry_wait" if payload["retry_at"] is not None else "failed")
        with connection:
            cursor = connection.execute(
                """
                UPDATE runs SET email_status = ?, email_last_error = ?,
                    email_next_attempt_at = ?, email_sent_at = ?
                WHERE run_id = ? AND email_status = 'sending'
                """,
                (
                    status,
                    payload["error"],
                    payload["retry_at"],
                    payload["completed_at"] if payload["success"] else None,
                    payload["run_id"],
                ),
            )
            if cursor.rowcount != 1:
                raise TransitionConflict("email state changed before result could commit")
            self._insert_run_log(
                connection,
                {
                    "run_id": payload["run_id"],
                    "timestamp": payload["completed_at"],
                    "level": "INFO" if payload["success"] else "ERROR",
                    "component": "mail",
                    "event_type": event_type,
                    "message": "Final Run email sent" if payload["success"] else "Final Run email delivery failed",
                    "error": payload["error"],
                },
            )
        return self.get_run(payload["run_id"])

    @staticmethod
    def _message_id(run_id):
        return "<run-{}@autowal.local>".format(run_id)

    @staticmethod
    def _next_run_number(connection, created_at):
        prefix = datetime.fromtimestamp(created_at).strftime("%Y%m%d")
        row = connection.execute(
            "SELECT run_number FROM runs WHERE run_number LIKE ? ORDER BY run_number DESC LIMIT 1",
            (prefix + "-%",),
        ).fetchone()
        sequence = int(row["run_number"].rsplit("-", 1)[1]) + 1 if row else 1
        return "{}-{:06d}".format(prefix, sequence)

    def _transition_run(self, connection, payload):
        updates = dict(payload["updates"])
        allowed = {
            "started_at", "finished_at", "summary_json", "final_error",
            "email_status", "email_attempts", "email_last_error",
            "email_message_id", "email_next_attempt_at", "email_sent_at",
        }
        unknown = set(updates) - allowed
        if unknown:
            raise StorageError("unsupported run update fields: {}".format(", ".join(sorted(unknown))))
        if "summary_json" in updates and updates["summary_json"] is not None and not isinstance(updates["summary_json"], str):
            updates["summary_json"] = json.dumps(updates["summary_json"], ensure_ascii=False, separators=(",", ":"))
        expected = tuple(payload["expected_statuses"])
        if not expected:
            raise StorageError("expected statuses cannot be empty")
        assignments = ["status = ?"]
        values = [payload["new_status"]]
        for name, value in updates.items():
            assignments.append("{} = ?".format(name))
            values.append(value)
        queues_email = payload["new_status"] in FINAL_STATUSES
        if queues_email:
            assignments.extend(("email_status = 'pending'", "email_message_id = ?"))
            values.append(self._message_id(payload["run_id"]))
        placeholders = ",".join("?" for _ in expected)
        values.extend((payload["run_id"],) + expected)
        with connection:
            cursor = connection.execute(
                "UPDATE runs SET {} WHERE run_id = ? AND status IN ({})".format(
                    ", ".join(assignments), placeholders
                ),
                values,
            )
            if cursor.rowcount != 1:
                raise TransitionConflict("Run state changed before transition could commit")
            event = dict(payload["event"])
            event["run_id"] = payload["run_id"]
            self._insert_run_log(connection, event)
            if queues_email:
                self._insert_run_log(
                    connection,
                    {
                        "run_id": payload["run_id"],
                        "timestamp": event["timestamp"],
                        "level": "INFO",
                        "component": "mail",
                        "event_type": "email.queued",
                        "message": "Final Run email queued",
                        "error": None,
                    },
                )
        return self.get_run(payload["run_id"])

    def _execute_log_batch(self, connection, commands):
        try:
            with connection:
                for command in commands:
                    if command.kind == "append_run_log":
                        self._insert_run_log(connection, command.payload)
                    else:
                        self._insert_task_log(connection, command.payload)
        except Exception:
            raise

    @staticmethod
    def _insert_run_log(connection, payload):
        connection.execute(
            """
            INSERT INTO run_logs (run_id, timestamp, level, component, event_type, message, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["run_id"], payload["timestamp"], payload["level"],
                payload["component"], payload["event_type"], payload["message"],
                payload.get("error"),
            ),
        )

    @staticmethod
    def _insert_task_log(connection, payload):
        connection.execute(
            """
            INSERT INTO task_logs (
                run_id, task_id, attempt, timestamp, worker, component,
                event_type, level, message, error, elapsed_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["run_id"], payload["task_id"], payload["attempt"],
                payload["timestamp"], payload.get("worker"), payload["component"],
                payload["event_type"], payload["level"], payload["message"],
                payload.get("error"), payload.get("elapsed_seconds"),
            ),
        )

    def _initialize_schema(self):
        connection = self._connect()
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise StorageError(
                    "database schema version {} is newer than supported version {}".format(
                        version, SCHEMA_VERSION
                    )
                )
            if version == 0:
                with connection:
                    connection.executescript(
                        """
                        CREATE TABLE runs (
                            run_id TEXT PRIMARY KEY,
                            run_number TEXT NOT NULL UNIQUE,
                            name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL,
                            options_json TEXT NOT NULL,
                            summary_json TEXT,
                            final_error TEXT,
                            email_status TEXT NOT NULL DEFAULT 'none',
                            email_attempts INTEGER NOT NULL DEFAULT 0,
                            email_last_error TEXT,
                            email_message_id TEXT,
                            email_next_attempt_at REAL,
                            email_sent_at REAL,
                            created_at REAL NOT NULL,
                            started_at REAL,
                            finished_at REAL
                        );
                        CREATE TABLE run_logs (
                            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            timestamp REAL NOT NULL,
                            level TEXT NOT NULL,
                            component TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            message TEXT NOT NULL,
                            error TEXT
                        );
                        CREATE TABLE task_logs (
                            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            task_id INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            timestamp REAL NOT NULL,
                            worker TEXT,
                            component TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            level TEXT NOT NULL,
                            message TEXT NOT NULL,
                            error TEXT,
                            elapsed_seconds REAL
                        );
                        CREATE INDEX idx_runs_status_created ON runs(status, created_at DESC);
                        CREATE INDEX idx_runs_email_status ON runs(email_status);
                        CREATE INDEX idx_run_logs_run_cursor ON run_logs(run_id, log_id);
                        CREATE INDEX idx_run_logs_run_event ON run_logs(run_id, event_type);
                        CREATE INDEX idx_task_logs_run_cursor ON task_logs(run_id, log_id);
                        CREATE INDEX idx_task_logs_identity ON task_logs(run_id, task_id, attempt);
                        PRAGMA user_version = 1;
                        """
                    )
        finally:
            connection.close()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=5, check_same_thread=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _read_connection(self):
        return self._connect()

    @staticmethod
    def _decode_run(row):
        record = dict(row)
        record["options"] = json.loads(record.pop("options_json"))
        summary = record.pop("summary_json")
        record["summary"] = json.loads(summary) if summary is not None else None
        record["error"] = record.pop("final_error")
        return record
