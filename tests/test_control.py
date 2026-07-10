import unittest

from autowal.control import FillTask, RunSummary, TaskResult, build_tasks


class FillTaskTests(unittest.TestCase):
    def test_build_tasks_creates_flat_sequence(self):
        tasks = build_tasks(total_tasks=6)

        self.assertEqual(len(tasks), 6)
        self.assertEqual(
            [(task.task_id, task.total_tasks) for task in tasks],
            [(1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6)],
        )

    def test_retry_creates_next_attempt_without_mutating_task(self):
        task = FillTask(task_id=1, total_tasks=2)

        retried = task.next_attempt()

        self.assertEqual(task.attempt, 1)
        self.assertEqual(retried.attempt, 2)
        self.assertEqual(retried.task_id, task.task_id)


class RunSummaryTests(unittest.TestCase):
    def test_records_success_failure_retry_and_cancelled_counts(self):
        summary = RunSummary(total=3)
        task1 = FillTask(task_id=1, total_tasks=2)
        task2 = FillTask(task_id=2, total_tasks=2, attempt=2)

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
