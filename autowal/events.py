import contextvars
import re
import threading


_CURRENT_TASK_CONTEXT = contextvars.ContextVar("autowal_task_event_context", default=None)
_SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(password|authorization|bearer|token|secret|api[_-]?key)\b\s*[:=]\s*([^\s,;]+)"
)


def sanitize_text(value):
    if value is None:
        return None
    return _SENSITIVE_PATTERN.sub(lambda match: "{}=<redacted>".format(match.group(1)), str(value))


class EventLogger:
    def __init__(self, store=None, run_id=None, console=True):
        self.store = store
        self.run_id = run_id
        self.console = console

    def run(self, event_type, message, level="INFO", component="runtime", error=None):
        message = sanitize_text(message)
        error = sanitize_text(error)
        if self.console:
            print(message)
        if self.store is not None and self.run_id is not None:
            self.store.append_run_log(
                self.run_id,
                event_type,
                message,
                level=level,
                component=component,
                error=error,
            )

    def task(
        self,
        task,
        event_type,
        message,
        level="INFO",
        worker=None,
        component="worker",
        error=None,
        elapsed_seconds=None,
    ):
        message = sanitize_text(message)
        error = sanitize_text(error)
        if self.console:
            print(message)
        if self.store is not None and self.run_id is not None:
            self.store.append_task_log(
                self.run_id,
                task.task_id,
                task.attempt,
                event_type,
                message,
                level=level,
                worker=worker or threading.current_thread().name,
                component=component,
                error=error,
                elapsed_seconds=elapsed_seconds,
            )

    def barrier(self):
        if self.store is not None:
            self.store.barrier()


def bind_task_logger(logger, task, worker=None):
    return _CURRENT_TASK_CONTEXT.set((logger, task, worker or threading.current_thread().name))


def reset_task_logger(token):
    _CURRENT_TASK_CONTEXT.reset(token)


def emit_task_output(*values, **kwargs):
    separator = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    message = separator.join(str(value) for value in values) + ("" if end == "\n" else end)
    context = _CURRENT_TASK_CONTEXT.get()
    if context is None:
        print(*values, **kwargs)
        return
    logger, task, worker = context
    logger.task(task, "filler.output", message, worker=worker, component="filler")
