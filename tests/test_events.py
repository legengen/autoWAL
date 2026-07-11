import os
import tempfile
import threading
import unittest

from autowal.control import FillTask
from autowal.events import EventLogger, bind_task_logger, emit_task_output, reset_task_logger, sanitize_text
from autowal.storage import RunStore


class EventLoggerTests(unittest.TestCase):
    def test_sanitizes_common_credentials(self):
        text = sanitize_text("password=hunter2 authorization:BearerValue normal=value")
        self.assertNotIn("hunter2", text)
        self.assertNotIn("BearerValue", text)
        self.assertIn("normal=value", text)

    def test_bound_filler_output_keeps_task_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RunStore(os.path.join(temp_dir, "test.db"))
            store.create_run("one", "", {}, run_id="run-a")
            logger = EventLogger(store, "run-a", console=False)
            task = FillTask(task_id=3, total_tasks=5, attempt=2)
            token = bind_task_logger(logger, task, worker="worker-x")
            try:
                emit_task_output("filler detail")
            finally:
                reset_task_logger(token)
            store.barrier()
            rows = store.get_task_logs("run-a")["items"]
            store.close()
        self.assertEqual(3, rows[0]["task_id"])
        self.assertEqual(2, rows[0]["attempt"])
        self.assertEqual("worker-x", rows[0]["worker"])
        self.assertEqual("filler", rows[0]["component"])

    def test_concurrent_run_loggers_do_not_mix_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RunStore(os.path.join(temp_dir, "test.db"))
            store.create_run("one", "", {}, run_id="run-a")
            store.create_run("two", "", {}, run_id="run-b")
            loggers = [EventLogger(store, run_id, console=False) for run_id in ("run-a", "run-b")]

            def emit(logger, task_id):
                task = FillTask(task_id=task_id, total_tasks=2)
                for _ in range(5):
                    logger.task(task, "task.event", "event")

            threads = [threading.Thread(target=emit, args=(logger, index + 1)) for index, logger in enumerate(loggers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            store.barrier()
            first = store.get_task_logs("run-a")["items"]
            second = store.get_task_logs("run-b")["items"]
            store.close()
        self.assertEqual({1}, {row["task_id"] for row in first})
        self.assertEqual({2}, {row["task_id"] for row in second})


if __name__ == "__main__":
    unittest.main()
