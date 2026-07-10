import random
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from autowal.control import FillTask
from autowal.worker import run_once


def make_args():
    return SimpleNamespace(
        headless=True,
        debug=False,
        auto_submit=False,
        interactive=False,
    )


class WorkerTests(unittest.TestCase):
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
        task = FillTask(task_id=1, worker_id=1, round_no=1, total_rounds=1)

        result = run_once([], make_args(), random.Random(123), task)

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        fill_all.assert_called_once()
        driver.quit.assert_called_once_with()

    @patch("autowal.worker.time.sleep")
    @patch("autowal.worker.traceback.print_exc")
    @patch("autowal.worker.init_driver")
    def test_run_once_reports_driver_start_failure(self, init_driver, _traceback, _sleep):
        init_driver.side_effect = RuntimeError("driver unavailable")
        task = FillTask(task_id=1, worker_id=1, round_no=1, total_rounds=1)

        result = run_once([], make_args(), random.Random(123), task)

        self.assertFalse(result.success)
        self.assertIn("driver unavailable", result.error)


if __name__ == "__main__":
    unittest.main()
