import threading
import time
import uuid
import os
from types import SimpleNamespace
from xmlrpc.server import SimpleXMLRPCServer
from socketserver import ThreadingMixIn

from .config import DEFAULT_SOURCE_ID, SURVEY_JSON, resolve_data_dir, validate_source_id
from .events import EventLogger
from .scheduler import ControlPlane
from .storage import ACTIVE_STATUSES, FINAL_STATUSES, RunStore, TransitionConflict
from .survey import load_survey


DEFAULT_RUN_OPTIONS = {
    "headless": True,
    "auto_submit": False,
    "debug": False,
    "seed": None,
    "loops": 1,
    "loop_delay": 1.0,
    "threads": 1,
    "retries": 0,
    "source_id": DEFAULT_SOURCE_ID,
    "interactive": False,
}


class ThreadingXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    daemon_threads = True


class RpcService:
    def __init__(self, survey_loader=load_survey, control_plane_factory=ControlPlane, store=None, data_dir=None):
        self._survey_loader = survey_loader
        self._control_plane_factory = control_plane_factory
        self._store = store or RunStore(os.path.join(resolve_data_dir(data_dir), "autowal.db"))
        self._owns_store = store is None
        self._planes = {}
        self._lock = threading.Lock()
        self._store.recover_interrupted_runs()

    def ping(self):
        return {"ok": True, "service": "autoWAL"}

    def start_run(self, options=None):
        request = dict(options or {})
        name = request.pop("name", None)
        description = request.pop("description", "")
        args = self._build_args(request)
        if name is None:
            name = "未命名任务"
        name = self._validate_text(name, "name", required=True, maximum=120)
        description = self._validate_text(description, "description", required=False, maximum=1000)
        record = self._store.create_run(name, description, vars(args).copy())
        run_id = record["run_id"]
        with self._lock:
            self._planes[run_id] = None

        thread = threading.Thread(
            target=self._execute_run,
            args=(run_id, args),
            name=f"autowal-rpc-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return {
            "run_id": run_id,
            "run_number": record["run_number"],
            "name": record["name"],
            "status": "pending",
        }

    def get_run(self, run_id):
        record = self._store.get_run(run_id)
        return record if record is not None else {"ok": False, "error": "run not found"}

    def list_runs(self):
        return self._store.list_runs(limit=100)["items"]

    def stop_run(self, run_id):
        record = self._store.get_run(run_id)
        if record is None:
            return {"ok": False, "error": "run not found"}
        if record["status"] in FINAL_STATUSES:
            return {"ok": False, "error": "run already finished"}
        try:
            self._store.transition_run(
                run_id,
                ("pending", "running"),
                "stopping",
                "run.stop_requested",
                "Run stop requested",
                component="rpc",
            )
        except TransitionConflict:
            record = self._store.get_run(run_id)
            if record is None or record["status"] != "stopping":
                return {"ok": False, "error": "run state changed"}
        with self._lock:
            plane = self._planes.get(run_id)

        if plane is not None:
            plane.request_stop()
        return {"ok": True, "run_id": run_id, "status": "stopping"}

    def _execute_run(self, run_id, args):
        try:
            survey = self._survey_loader(SURVEY_JSON)
            args.event_logger = EventLogger(self._store, run_id)
            plane = self._control_plane_factory(survey, args)
            with self._lock:
                self._planes[run_id] = plane
            record = self._store.get_run(run_id)
            if record["status"] == "stopping":
                plane.request_stop()
            else:
                self._store.transition_run(
                    run_id,
                    ("pending",),
                    "running",
                    "run.started",
                    "Run started",
                    updates={"started_at": time.time()},
                    component="rpc",
                )

            summary = plane.run()
            self._store.barrier()
            record = self._store.get_run(run_id)
            stopped = summary.cancelled or record["status"] == "stopping"
            final_status = "stopped" if stopped else "completed"
            self._store.transition_run(
                run_id,
                ("running", "stopping"),
                final_status,
                "run." + final_status,
                "Run {}".format(final_status),
                updates={
                    "summary_json": self._summary_dict(summary),
                    "finished_at": time.time(),
                },
                component="rpc",
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            record = self._store.get_run(run_id)
            if record is not None and record["status"] in ACTIVE_STATUSES:
                try:
                    self._store.barrier()
                    self._store.transition_run(
                        run_id,
                        tuple(ACTIVE_STATUSES),
                        "failed",
                        "run.failed",
                        "Run failed",
                        updates={"final_error": error, "finished_at": time.time()},
                        level="ERROR",
                        component="rpc",
                        error=error,
                    )
                except Exception:
                    pass
        finally:
            with self._lock:
                self._planes.pop(run_id, None)

    def close(self):
        if self._owns_store:
            self._store.close()

    @staticmethod
    def _build_args(options):
        if not isinstance(options, dict):
            raise ValueError("options must be a struct")
        unknown = set(options) - set(DEFAULT_RUN_OPTIONS)
        if unknown:
            raise ValueError(f"unknown options: {', '.join(sorted(unknown))}")

        values = {**DEFAULT_RUN_OPTIONS, **options}
        for name in ("headless", "auto_submit", "debug"):
            if not isinstance(values[name], bool):
                raise ValueError(f"{name} must be a boolean")
        if values["seed"] is not None and (
            isinstance(values["seed"], bool) or not isinstance(values["seed"], int)
        ):
            raise ValueError("seed must be an integer or null")
        for name in ("loops", "threads"):
            if isinstance(values[name], bool) or not isinstance(values[name], int) or values[name] < 1:
                raise ValueError(f"{name} must be an integer greater than or equal to 1")
        if isinstance(values["retries"], bool) or not isinstance(values["retries"], int) or values["retries"] < 0:
            raise ValueError("retries must be a non-negative integer")
        if isinstance(values["loop_delay"], bool) or not isinstance(values["loop_delay"], (int, float)) or values["loop_delay"] < 0:
            raise ValueError("loop_delay must be a non-negative number")
        values["source_id"] = validate_source_id(values["source_id"])
        values["loop_delay"] = float(values["loop_delay"])
        values["interactive"] = False
        return SimpleNamespace(**values)

    @staticmethod
    def _summary_dict(summary):
        return {
            "total": summary.total,
            "completed": summary.completed,
            "succeeded": summary.succeeded,
            "failed": summary.failed,
            "cancelled": summary.cancelled,
            "retries": summary.retries,
            "duration_seconds": summary.duration_seconds,
            "exit_code": summary.exit_code,
        }

    @staticmethod
    def _validate_text(value, name, required, maximum):
        if not isinstance(value, str):
            raise ValueError("{} must be a string".format(name))
        value = value.strip()
        if required and not value:
            raise ValueError("{} is required".format(name))
        if len(value) > maximum:
            raise ValueError("{} must not exceed {} characters".format(name, maximum))
        return value


def serve(host="127.0.0.1", port=8765, data_dir=None):
    service = RpcService(data_dir=data_dir)
    try:
        with ThreadingXMLRPCServer(
            (host, port), allow_none=True, logRequests=True
        ) as server:
            server.register_introspection_functions()
            server.register_instance(service)
            print(f"autoWAL RPC listening on http://{host}:{port}")
            server.serve_forever()
    finally:
        service.close()
