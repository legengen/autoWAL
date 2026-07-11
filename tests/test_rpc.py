import threading
import os
import tempfile
import unittest
from unittest.mock import patch

from autowal.control import RunSummary
from autowal.rpc import RpcService
from autowal.storage import RunStore, StorageError


class FakeControlPlane:
    started = threading.Event()
    release = threading.Event()

    def __init__(self, _survey, args):
        self.args = args
        self.stopped = False

    def request_stop(self):
        self.stopped = True
        self.release.set()

    def run(self):
        self.started.set()
        self.release.wait(timeout=2)
        total = self.args.threads * self.args.loops
        return RunSummary(total=total).finish(cancelled=total if self.stopped else 0)


class RpcServiceTests(unittest.TestCase):
    def setUp(self):
        FakeControlPlane.started.clear()
        FakeControlPlane.release.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = RunStore(os.path.join(self.temp_dir.name, "test.db"))
        self.service = RpcService(
            survey_loader=lambda _path: [],
            control_plane_factory=FakeControlPlane,
            store=self.store,
            start_mailer=False,
        )

    def tearDown(self):
        FakeControlPlane.release.set()
        self.store.close()
        self.temp_dir.cleanup()

    def test_start_run_accepts_simple_options_and_completes(self):
        result = self.service.start_run(
            {"threads": 2, "loops": 3, "source_id": "001234"}
        )
        self.assertTrue(FakeControlPlane.started.wait(timeout=1))
        FakeControlPlane.release.set()

        record = self._wait_until_finished(result["run_id"])
        self.assertEqual("completed", record["status"])
        self.assertEqual(6, record["summary"]["total"])
        self.assertEqual("001234", record["options"]["source_id"])

    def test_named_run_is_persisted(self):
        result = self.service.start_run({"name": "测试批次", "description": "用途"})
        self.assertTrue(FakeControlPlane.started.wait(timeout=1))
        record = self.service.get_run(result["run_id"])
        self.assertEqual("测试批次", record["name"])
        self.assertEqual("用途", record["description"])
        self.assertRegex(record["run_number"], r"^\d{8}-\d{6}$")
        FakeControlPlane.release.set()

    def test_persistence_failure_does_not_start_control_plane(self):
        with patch.object(self.store, "create_run", side_effect=StorageError("disk unavailable")):
            with self.assertRaises(StorageError):
                self.service.start_run({"name": "cannot start"})
        self.assertFalse(FakeControlPlane.started.is_set())

    def test_stop_run_requests_control_plane_stop(self):
        result = self.service.start_run({})
        self.assertTrue(FakeControlPlane.started.wait(timeout=1))
        stopped = self.service.stop_run(result["run_id"])
        self.assertTrue(stopped["ok"])

        record = self._wait_until_finished(result["run_id"])
        self.assertEqual("stopped", record["status"])
        self.assertEqual(1, record["summary"]["cancelled"])

    def test_rejects_unknown_or_invalid_options(self):
        with self.assertRaises(ValueError):
            self.service.start_run({"workers": 2})
        with self.assertRaises(ValueError):
            self.service.start_run({"threads": 0})
        with self.assertRaises(ValueError):
            self.service.start_run({"source_id": "12345"})
        with self.assertRaises(ValueError):
            self.service.start_run({"headless": "yes"})
        with self.assertRaises(ValueError):
            self.service.start_run({"name": " "})

    def test_unknown_run_returns_error(self):
        self.assertFalse(self.service.get_run("missing")["ok"])
        self.assertFalse(self.service.stop_run("missing")["ok"])
        self.assertFalse(self.service.get_run_logs({"run_id": "missing"})["ok"])
        self.assertFalse(self.service.get_task_logs({"run_id": "missing"})["ok"])

    def test_history_and_logs_are_cursor_paginated(self):
        first = self.store.create_run("first", "", {}, created_at=10, run_id="run-1")
        second = self.store.create_run("second", "purpose", {}, created_at=20, run_id="run-2")
        page = self.service.list_runs({"limit": 1})
        self.assertEqual([second["run_id"]], [item["run_id"] for item in page["items"]])
        later = self.service.list_runs({"limit": 1, "cursor": page["next_cursor"]})
        self.assertEqual([first["run_id"]], [item["run_id"] for item in later["items"]])

        self.store.append_run_log("run-2", "custom.event", "lifecycle")
        self.store.append_task_log("run-2", 7, 2, "task.failed", "failure")
        self.store.barrier()
        run_logs = self.service.get_run_logs({"run_id": "run-2", "limit": 1})
        next_logs = self.service.get_run_logs({
            "run_id": "run-2", "after_log_id": run_logs["next_after_log_id"], "limit": 10,
        })
        task_logs = self.service.get_task_logs({
            "run_id": "run-2", "task_id": 7, "attempt": 2, "limit": 10,
        })
        self.assertEqual("custom.event", next_logs["items"][0]["event_type"])
        self.assertEqual("task.failed", task_logs["items"][0]["event_type"])

    def test_legacy_list_and_start_remain_compatible(self):
        result = self.service.start_run({})
        self.assertTrue(result["name"])
        self.assertIsInstance(self.service.list_runs(), list)
        FakeControlPlane.release.set()

    def test_rejects_invalid_history_and_log_queries(self):
        self.store.create_run("one", "", {}, run_id="run-a")
        with self.assertRaises(ValueError):
            self.service.list_runs({"limit": 0})
        with self.assertRaises(ValueError):
            self.service.list_runs({"unexpected": True})
        with self.assertRaises(ValueError):
            self.service.get_run_logs({"limit": 10})
        with self.assertRaises(ValueError):
            self.service.get_task_logs({"run_id": "run-a", "limit": 501})

    def test_history_survives_service_recreation(self):
        self.store.create_run("persistent", "purpose", {}, run_id="run-persisted")
        recreated = RpcService(
            survey_loader=lambda _path: [],
            control_plane_factory=FakeControlPlane,
            store=self.store,
            start_mailer=False,
        )
        try:
            page = recreated.list_runs({"limit": 10})
            self.assertIn("run-persisted", [item["run_id"] for item in page["items"]])
        finally:
            recreated.close()

    def _wait_until_finished(self, run_id):
        for _ in range(100):
            record = self.service.get_run(run_id)
            if record["status"] in ("completed", "failed", "stopped"):
                return record
            threading.Event().wait(0.01)
        self.fail("run did not finish")


if __name__ == "__main__":
    unittest.main()
