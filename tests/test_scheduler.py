import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from autowal.control import TaskResult
from autowal.scheduler import ControlPlane


def make_args(**overrides):
    values = {
        "threads": 2,
        "loops": 3,
        "loop_delay": 0,
        "seed": 123,
        "interactive": False,
        "retries": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ControlPlaneTests(unittest.TestCase):
    def test_uses_one_shared_task_queue(self):
        plane = ControlPlane([], make_args())

        self.assertTrue(hasattr(plane, "task_queue"))
        self.assertFalse(hasattr(plane, "task_queues"))

    @patch("builtins.print")
    def test_dispatches_all_tasks_and_aggregates_success(self, _print):
        seen = []
        seen_lock = threading.Lock()

        def runner(_survey, _args, _rng, task):
            with seen_lock:
                seen.append(task.task_id)
            return TaskResult(task=task, success=True, elapsed_seconds=0.01)

        summary = ControlPlane([], make_args(), task_runner=runner).run()

        self.assertEqual(summary.total, 6)
        self.assertEqual(summary.succeeded, 6)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(summary.cancelled, 0)
        self.assertEqual(sorted(seen), [1, 2, 3, 4, 5, 6])

    @patch("builtins.print")
    def test_retries_failed_task_and_records_retry(self, _print):
        attempts = []

        def runner(_survey, _args, _rng, task):
            attempts.append(task.attempt)
            return TaskResult(
                task=task,
                success=task.attempt == 2,
                error=None if task.attempt == 2 else "temporary failure",
            )

        summary = ControlPlane(
            [],
            make_args(threads=1, loops=1, retries=1),
            task_runner=runner,
        ).run()

        self.assertEqual(attempts, [1, 2])
        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(summary.retries, 1)

    @patch("builtins.print")
    def test_pre_requested_stop_marks_tasks_cancelled(self, _print):
        plane = ControlPlane([], make_args(threads=2, loops=2))
        plane.request_stop()

        summary = plane.run()

        self.assertEqual(summary.completed, 0)
        self.assertEqual(summary.cancelled, 4)


if __name__ == "__main__":
    unittest.main()
