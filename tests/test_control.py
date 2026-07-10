import unittest

from autowal.control import FillTask, RunSummary, TaskResult, build_tasks


class FillTaskTests(unittest.TestCase):
    def test_build_tasks_preserves_worker_and_round_layout(self):
        tasks = build_tasks(thread_count=2, loops=3)

        self.assertEqual(len(tasks), 6)
        self.assertEqual(
            [(task.task_id, task.worker_id, task.round_no) for task in tasks],
            [
                (1, 1, 1),
                (2, 1, 2),
                (3, 1, 3),
                (4, 2, 1),
                (5, 2, 2),
                (6, 2, 3),
            ],
        )

    def test_retry_creates_next_attempt_without_mutating_task(self):
        task = FillTask(task_id=1, worker_id=1, round_no=1, total_rounds=2)

        retried = task.next_attempt()

        self.assertEqual(task.attempt, 1)
        self.assertEqual(retried.attempt, 2)
        self.assertEqual(retried.task_id, task.task_id)


class RunSummaryTests(unittest.TestCase):
    def test_records_success_failure_retry_and_cancelled_counts(self):
        summary = RunSummary(total=3)
        task1 = FillTask(task_id=1, worker_id=1, round_no=1, total_rounds=2)
        task2 = FillTask(task_id=2, worker_id=1, round_no=2, total_rounds=2, attempt=2)

        summary.record(TaskResult(task=task1, success=True))
        summary.record(TaskResult(task=task2, success=False, error="failed"))
        summary.finish(cancelled=1)

        self.assertEqual(summary.completed, 2)
        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.retries, 1)
        self.assertEqual(summary.cancelled, 1)
        self.assertEqual(summary.exit_code, 1)


if __name__ == "__main__":
    unittest.main()
