import threading
import time
import uuid
from types import SimpleNamespace
from xmlrpc.server import SimpleXMLRPCServer
from socketserver import ThreadingMixIn

from .config import DEFAULT_SOURCE_ID, SURVEY_JSON, validate_source_id
from .scheduler import ControlPlane
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
    def __init__(self, survey_loader=load_survey, control_plane_factory=ControlPlane):
        self._survey_loader = survey_loader
        self._control_plane_factory = control_plane_factory
        self._runs = {}
        self._lock = threading.Lock()

    def ping(self):
        return {"ok": True, "service": "autoWAL"}

    def start_run(self, options=None):
        args = self._build_args(options or {})
        run_id = uuid.uuid4().hex
        record = {
            "run_id": run_id,
            "status": "pending",
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "options": vars(args).copy(),
            "summary": None,
            "error": None,
            "plane": None,
        }
        with self._lock:
            self._runs[run_id] = record

        thread = threading.Thread(
            target=self._execute_run,
            args=(run_id, args),
            name=f"autowal-rpc-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return {"run_id": run_id, "status": "pending"}

    def get_run(self, run_id):
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return {"ok": False, "error": "run not found"}
            return self._public_record(record)

    def list_runs(self):
        with self._lock:
            records = sorted(
                self._runs.values(), key=lambda item: item["created_at"], reverse=True
            )
            return [self._public_record(record) for record in records]

    def stop_run(self, run_id):
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return {"ok": False, "error": "run not found"}
            if record["status"] in ("completed", "failed", "stopped"):
                return {"ok": False, "error": "run already finished"}
            plane = record["plane"]
            record["status"] = "stopping"

        if plane is not None:
            plane.request_stop()
        return {"ok": True, "run_id": run_id, "status": "stopping"}

    def _execute_run(self, run_id, args):
        try:
            survey = self._survey_loader(SURVEY_JSON)
            plane = self._control_plane_factory(survey, args)
            with self._lock:
                record = self._runs[run_id]
                record["plane"] = plane
                record["started_at"] = time.time()
                if record["status"] == "stopping":
                    plane.request_stop()
                else:
                    record["status"] = "running"

            summary = plane.run()
            with self._lock:
                record = self._runs[run_id]
                record["summary"] = self._summary_dict(summary)
                record["status"] = "stopped" if summary.cancelled else "completed"
        except Exception as exc:
            with self._lock:
                record = self._runs[run_id]
                record["status"] = "failed"
                record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                record = self._runs[run_id]
                record["finished_at"] = time.time()
                record["plane"] = None

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
    def _public_record(record):
        return {
            key: value
            for key, value in record.items()
            if key != "plane"
        }


def serve(host="127.0.0.1", port=8765):
    service = RpcService()
    with ThreadingXMLRPCServer(
        (host, port), allow_none=True, logRequests=True
    ) as server:
        server.register_introspection_functions()
        server.register_instance(service)
        print(f"autoWAL RPC listening on http://{host}:{port}")
        server.serve_forever()
