import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing

from autowal.storage import RunStore, StorageError, TransitionConflict


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "autowal.db")
        self.store = RunStore(self.database_path, queue_size=8)

    def tearDown(self):
        if self.store is not None:
            self.store.close()
        self.temp_dir.cleanup()

    def test_creates_schema_and_round_trips_run(self):
        record = self.store.create_run(
            name="批次一",
            description="用途",
            options={"threads": 2, "seed": None},
            created_at=1720000000.0,
            run_id="run-a",
        )
        self.assertEqual("20240703-000001", record["run_number"])
        self.assertEqual("批次一", record["name"])
        self.assertEqual({"threads": 2, "seed": None}, record["options"])
        self.assertEqual("pending", record["status"])
        self.assertEqual("run.created", self.store.get_run_logs("run-a")["items"][0]["event_type"])

        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(1, connection.execute("PRAGMA user_version").fetchone()[0])
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"runs", "run_logs", "task_logs"}.issubset(tables))

    def test_allocates_unique_readable_numbers(self):
        first = self.store.create_run("one", "", {}, created_at=1720000000, run_id="run-1")
        second = self.store.create_run("two", "", {}, created_at=1720000001, run_id="run-2")
        self.assertEqual("20240703-000001", first["run_number"])
        self.assertEqual("20240703-000002", second["run_number"])

    def test_paginates_runs_and_logs(self):
        for index in range(3):
            self.store.create_run(str(index), "", {}, created_at=100 + index, run_id="run-{}".format(index))
        first = self.store.list_runs(limit=2)
        second = self.store.list_runs(limit=2, cursor=first["next_cursor"])
        self.assertEqual(["run-2", "run-1"], [item["run_id"] for item in first["items"]])
        self.assertEqual(["run-0"], [item["run_id"] for item in second["items"]])

        self.store.append_task_log("run-2", 1, 1, "task.started", "start")
        self.store.append_task_log("run-2", 1, 1, "task.completed", "done", elapsed_seconds=1.2)
        self.store.barrier()
        logs = self.store.get_task_logs("run-2", limit=1)
        later = self.store.get_task_logs("run-2", after_log_id=logs["next_after_log_id"])
        self.assertEqual("task.started", logs["items"][0]["event_type"])
        self.assertEqual("task.completed", later["items"][0]["event_type"])

    def test_transition_and_log_are_atomic(self):
        self.store.create_run("one", "", {}, run_id="run-a")
        record = self.store.transition_run(
            "run-a", ("pending",), "running", "run.started", "started",
            updates={"started_at": 10.0},
        )
        self.assertEqual("running", record["status"])
        self.assertEqual(10.0, record["started_at"])
        with self.assertRaises(TransitionConflict):
            self.store.transition_run("run-a", ("pending",), "failed", "run.failed", "failed")
        self.assertEqual("running", self.store.get_run("run-a")["status"])

    def test_failed_lifecycle_insert_rolls_back_transition(self):
        self.store.create_run("one", "", {}, run_id="run-a")
        self.store.barrier()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_failed_log BEFORE INSERT ON run_logs "
                "WHEN NEW.event_type = 'run.failed' BEGIN SELECT RAISE(ABORT, 'rejected'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.transition_run("run-a", ("pending",), "failed", "run.failed", "failed")
        self.assertEqual("pending", self.store.get_run("run-a")["status"])

    def test_concurrent_producers_retain_context_and_barrier(self):
        self.store.create_run("one", "", {}, run_id="run-a")

        def produce(task_id):
            for attempt in range(1, 6):
                self.store.append_task_log(
                    "run-a", task_id, attempt, "task.event", "event",
                    worker="worker-{}".format(task_id),
                )

        threads = [threading.Thread(target=produce, args=(task_id,)) for task_id in range(1, 5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.store.barrier()
        rows = self.store.get_task_logs("run-a", limit=100)["items"]
        self.assertEqual(20, len(rows))
        self.assertEqual({1, 2, 3, 4}, {row["task_id"] for row in rows})
        self.assertEqual(list(range(1, 21)), [row["log_id"] for row in rows])

    def test_barrier_reports_asynchronous_log_failure(self):
        self.store.append_run_log("missing", "event", "cannot persist")
        with self.assertRaises(StorageError):
            self.store.barrier()

    def test_rejects_newer_schema(self):
        self.store.close()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("PRAGMA user_version = 999")
        with self.assertRaises(StorageError):
            RunStore(self.database_path)

    def test_close_flushes_pending_logs(self):
        self.store.create_run("one", "", {}, run_id="run-a")
        for index in range(10):
            self.store.append_run_log("run-a", "event", str(index))
        self.store.close()
        self.store = None
        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM run_logs WHERE run_id='run-a'").fetchone()[0]
        self.assertEqual(11, count)


if __name__ == "__main__":
    unittest.main()
