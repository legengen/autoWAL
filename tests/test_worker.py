import random
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from autowal.control import FillTask
from autowal.worker import make_task_rng, run_once


def make_args(**overrides):
    values = dict(
        headless=True,
        debug=False,
        auto_submit=False,
        interactive=False,
        source_id="719419",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class WorkerTests(unittest.TestCase):
    def test_task_rng_is_stable_and_independent_of_worker_scheduling(self):
        first = make_task_rng(123, task_id=2).randint(1, 100000)
        repeated = make_task_rng(123, task_id=2).randint(1, 100000)
        another_task = make_task_rng(123, task_id=3).randint(1, 100000)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, another_task)

    @patch("autowal.worker.time.sleep")
    @patch("autowal.worker.fill_all")
    @patch("autowal.worker.WebDriverWait")
    @patch("autowal.worker.init_driver")
    def test_run_once_returns_success_and_closes_driver(
        self,
        init_driver,
        webdriver_wait,
        fill_all,
        _sleep,
    ):
        driver = Mock()
        init_driver.return_value = driver
        webdriver_wait.return_value.until.return_value = object()
        task = FillTask(task_id=1, total_tasks=1)

        result = run_once(
            [],
            make_args(source_id="123456"),
            random.Random(123),
            task,
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        fill_all.assert_called_once()
        driver.get.assert_called_once_with(
            "https://myd.iscn.org.cn/#/s/yCWFPyRr?sourceID=123456"
        )
        driver.quit.assert_called_once_with()

    @patch("autowal.worker.time.sleep")
    @patch("autowal.worker.traceback.print_exc")
    @patch("autowal.worker.init_driver")
    def test_run_once_reports_driver_start_failure(self, init_driver, _traceback, _sleep):
        init_driver.side_effect = RuntimeError("driver unavailable")
        task = FillTask(task_id=1, total_tasks=1)

        result = run_once([], make_args(), random.Random(123), task)

        self.assertFalse(result.success)
        self.assertIn("driver unavailable", result.error)


if __name__ == "__main__":
    unittest.main()
