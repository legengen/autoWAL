import os
import tempfile
import unittest

from autowal.mail import EmailSender, MailConfig, MailConfigurationError
from autowal.storage import RunStore, TransitionConflict


class FakeSMTP:
    messages = []
    failures = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def starttls(self):
        return None

    def login(self, username, password):
        return None

    def send_message(self, message):
        if self.failures:
            raise self.failures.pop(0)
        self.messages.append(message)


class EmailSenderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = RunStore(os.path.join(self.temp_dir.name, "autowal.db"))
        self.config = MailConfig(
            host="smtp.example.test",
            port=587,
            username="mailer",
            password="secret-value",
            sender="from@example.test",
            recipient="to@example.test",
            max_attempts=2,
            retry_delays=(10,),
        )
        FakeSMTP.messages = []
        FakeSMTP.failures = []

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def final_run(self, run_id="run-a"):
        self.store.create_run(
            "Nightly survey", "regression", {"threads": 2, "loops": 3},
            created_at=10, run_id=run_id,
        )
        return self.store.transition_run(
            run_id, ("pending",), "completed", "run.completed", "completed",
            updates={
                "finished_at": 20,
                "summary_json": {"succeeded": 6, "failed": 0, "duration_seconds": 10},
            },
        )

    def sender(self):
        return EmailSender(self.store, self.config, smtp_factory=FakeSMTP)

    def test_parses_environment_without_exposing_password(self):
        config = MailConfig.from_env({
            "AUTOWAL_SMTP_HOST": "smtp.example.test",
            "AUTOWAL_SMTP_PORT": "465",
            "AUTOWAL_SMTP_FROM": "from@example.test",
            "AUTOWAL_SMTP_TO": "to@example.test",
            "AUTOWAL_SMTP_PASSWORD": "private",
            "AUTOWAL_SMTP_TLS": "false",
            "AUTOWAL_SMTP_RETRY_DELAYS": "1,5",
        })
        self.assertEqual(465, config.port)
        self.assertFalse(config.use_tls)
        self.assertEqual((1, 5), config.retry_delays)
        with self.assertRaises(MailConfigurationError):
            MailConfig.from_env({})

    def test_final_transition_queues_and_success_sends_once(self):
        record = self.final_run()
        self.assertEqual("pending", record["email_status"])
        self.assertEqual("<run-run-a@autowal.local>", record["email_message_id"])

        self.assertEqual(1, self.sender().process_once(now=30))
        sent = self.store.get_run("run-a")
        self.assertEqual("sent", sent["email_status"])
        self.assertEqual(1, sent["email_attempts"])
        self.assertEqual(1, len(FakeSMTP.messages))
        self.assertEqual(sent["email_message_id"], FakeSMTP.messages[0]["Message-ID"])
        self.assertIn("Nightly survey", FakeSMTP.messages[0].get_content())
        self.assertEqual(0, self.sender().process_once(now=31))

    def test_temporary_failure_retries_then_exhausts(self):
        self.final_run()
        FakeSMTP.failures = [RuntimeError("password=secret-value unavailable")]
        sender = self.sender()
        sender.process_once(now=30)
        waiting = self.store.get_run("run-a")
        self.assertEqual("retry_wait", waiting["email_status"])
        self.assertEqual(40, waiting["email_next_attempt_at"])
        self.assertNotIn("secret-value", waiting["email_last_error"])
        self.assertEqual(0, sender.process_once(now=39))

        FakeSMTP.failures = [RuntimeError("still unavailable")]
        sender.process_once(now=40)
        failed = self.store.get_run("run-a")
        self.assertEqual("failed", failed["email_status"])
        self.assertEqual(2, failed["email_attempts"])

    def test_missing_configuration_is_recorded_as_failure(self):
        self.final_run()
        sender = EmailSender(self.store, config=None, smtp_factory=FakeSMTP)
        sender.configuration_error = "missing SMTP settings"
        sender.process_once(now=30)
        self.assertEqual("failed", self.store.get_run("run-a")["email_status"])

    def test_stale_sending_is_recovered_for_retry(self):
        self.final_run()
        self.store.claim_email("run-a", claimed_at=30)
        self.store.recover_interrupted_runs(recovered_at=40)
        recovered = self.store.get_run("run-a")
        self.assertEqual("retry_wait", recovered["email_status"])
        self.assertEqual(40, recovered["email_next_attempt_at"])

    def test_duplicate_finalization_and_task_logs_do_not_queue_extra_email(self):
        self.final_run()
        with self.assertRaises(TransitionConflict):
            self.store.transition_run(
                "run-a", ("pending",), "failed", "run.failed", "failed"
            )
        self.store.append_task_log("run-a", 1, 1, "task.completed", "done")
        self.store.barrier()
        queued = [
            row for row in self.store.get_run_logs("run-a")["items"]
            if row["event_type"] == "email.queued"
        ]
        self.assertEqual(1, len(queued))


if __name__ == "__main__":
    unittest.main()
