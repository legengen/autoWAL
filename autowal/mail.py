import os
import smtplib
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage

from .events import sanitize_text


class MailConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str
    use_tls: bool = True
    max_attempts: int = 5
    retry_delays: tuple = (60, 300, 900, 1800, 3600)

    @classmethod
    def from_env(cls, environ=None):
        environ = environ or os.environ
        required = ("AUTOWAL_SMTP_HOST", "AUTOWAL_SMTP_FROM", "AUTOWAL_SMTP_TO")
        missing = [name for name in required if not environ.get(name)]
        if missing:
            raise MailConfigurationError("missing SMTP settings: {}".format(", ".join(missing)))
        try:
            port = int(environ.get("AUTOWAL_SMTP_PORT", "587"))
            max_attempts = int(environ.get("AUTOWAL_SMTP_MAX_ATTEMPTS", "5"))
            retry_delays = tuple(
                int(value.strip())
                for value in environ.get("AUTOWAL_SMTP_RETRY_DELAYS", "60,300,900,1800,3600").split(",")
                if value.strip()
            )
        except ValueError as exc:
            raise MailConfigurationError("SMTP numeric settings are invalid") from exc
        if not 1 <= port <= 65535 or max_attempts < 1 or not retry_delays or min(retry_delays) < 0:
            raise MailConfigurationError("SMTP retry or port settings are invalid")
        use_tls = environ.get("AUTOWAL_SMTP_TLS", "true").strip().lower() in ("1", "true", "yes", "on")
        return cls(
            host=environ["AUTOWAL_SMTP_HOST"],
            port=port,
            username=environ.get("AUTOWAL_SMTP_USER", ""),
            password=environ.get("AUTOWAL_SMTP_PASSWORD", ""),
            sender=environ["AUTOWAL_SMTP_FROM"],
            recipient=environ["AUTOWAL_SMTP_TO"],
            use_tls=use_tls,
            max_attempts=max_attempts,
            retry_delays=retry_delays,
        )


class EmailSender:
    def __init__(self, store, config=None, smtp_factory=smtplib.SMTP, poll_interval=1.0):
        self.store = store
        self.smtp_factory = smtp_factory
        self.poll_interval = poll_interval
        self.stop_event = threading.Event()
        self.configuration_error = None
        if config is None:
            try:
                config = MailConfig.from_env()
            except MailConfigurationError as exc:
                self.configuration_error = str(exc)
        self.config = config
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="autowal-mail-sender", daemon=True)
        self._thread.start()

    def close(self):
        self.stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def process_once(self, now=None):
        now = now if now is not None else time.time()
        processed = 0
        for candidate in self.store.get_due_email_runs(now=now):
            record = self.store.claim_email(candidate["run_id"], claimed_at=now)
            if record is None:
                continue
            processed += 1
            if self.configuration_error is not None:
                self.store.complete_email(
                    record["run_id"],
                    False,
                    error=sanitize_text(self.configuration_error),
                    retry_at=None,
                    completed_at=now,
                )
                continue
            try:
                self._send(record)
            except Exception as exc:
                error = sanitize_text("{}: {}".format(type(exc).__name__, exc))
                retry_at = self._retry_at(record["email_attempts"], now)
                self.store.complete_email(
                    record["run_id"], False, error=error, retry_at=retry_at, completed_at=now
                )
            else:
                self.store.complete_email(record["run_id"], True, completed_at=now)
        return processed

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.process_once()
            except Exception:
                # A transient storage failure must not permanently stop delivery.
                pass
            self.stop_event.wait(self.poll_interval)

    def _retry_at(self, attempts, now):
        if attempts >= self.config.max_attempts:
            return None
        delay_index = min(max(attempts - 1, 0), len(self.config.retry_delays) - 1)
        return now + self.config.retry_delays[delay_index]

    def _send(self, record):
        message = self.compose_message(record)
        with self.smtp_factory(self.config.host, self.config.port, timeout=10) as smtp:
            if self.config.use_tls:
                smtp.starttls()
            if self.config.username:
                smtp.login(self.config.username, self.config.password)
            smtp.send_message(message)

    def compose_message(self, record):
        summary = record.get("summary") or {}
        options = record.get("options") or {}
        message = EmailMessage()
        message["From"] = self.config.sender
        message["To"] = self.config.recipient
        message["Message-ID"] = record["email_message_id"]
        message["Subject"] = "[autoWAL] {} {} - {}".format(
            record["run_number"], record["name"], record["status"]
        )
        lines = [
            "Run number: {}".format(record["run_number"]),
            "Run name: {}".format(record["name"]),
            "Purpose: {}".format(record.get("description") or "-"),
            "Final status: {}".format(record["status"]),
            "Created at: {}".format(record["created_at"]),
            "Started at: {}".format(record.get("started_at")),
            "Finished at: {}".format(record.get("finished_at")),
            "Threads: {}".format(options.get("threads", "-")),
            "Loops: {}".format(options.get("loops", "-")),
            "Succeeded/failed/cancelled/retries: {}/{}/{}/{}".format(
                summary.get("succeeded", 0),
                summary.get("failed", 0),
                summary.get("cancelled", 0),
                summary.get("retries", 0),
            ),
            "Duration: {} seconds".format(summary.get("duration_seconds", 0)),
            "Error: {}".format(sanitize_text(record.get("error")) or "-"),
        ]
        message.set_content("\n".join(lines))
        return message
