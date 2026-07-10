import threading
import unittest

from autowal.control import RunSummary
from autowal.rpc import RpcService


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
        self.service = RpcService(
            survey_loader=lambda _path: [],
            control_plane_factory=FakeControlPlane,
        )

    def tearDown(self):
        FakeControlPlane.release.set()

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

    def test_unknown_run_returns_error(self):
        self.assertFalse(self.service.get_run("missing")["ok"])
        self.assertFalse(self.service.stop_run("missing")["ok"])

    def _wait_until_finished(self, run_id):
        for _ in range(100):
            record = self.service.get_run(run_id)
            if record["status"] in ("completed", "failed", "stopped"):
                return record
            threading.Event().wait(0.01)
        self.fail("run did not finish")


if __name__ == "__main__":
    unittest.main()
