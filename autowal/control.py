import time
from dataclasses import dataclass, field, replace
from typing import List, Optional


@dataclass(frozen=True)
class FillTask:
    task_id: int
    worker_id: int
    round_no: int
    total_rounds: int
    attempt: int = 1

    @property
    def label(self):
        return f"线程 {self.worker_id} 第 {self.round_no}/{self.total_rounds} 轮"

    def next_attempt(self):
        return replace(self, attempt=self.attempt + 1)


@dataclass(frozen=True)
class TaskResult:
    task: FillTask
    success: bool
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
    worker_name: str = ""


@dataclass
class RunSummary:
    total: int
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    retries: int = 0
    started_at: float = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None

    @property
    def completed(self):
        return self.succeeded + self.failed

    @property
    def duration_seconds(self):
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return max(0.0, end - self.started_at)

    @property
    def exit_code(self):
        return 0 if self.failed == 0 and self.cancelled == 0 else 1

    def record(self, result):
        if result.success:
            self.succeeded += 1
        else:
            self.failed += 1
        self.retries += max(0, result.task.attempt - 1)

    def finish(self, cancelled=0):
        self.cancelled = max(0, cancelled)
        self.finished_at = time.monotonic()
        return self


def build_tasks(thread_count, loops):
    if thread_count < 1:
        raise ValueError("thread_count must be at least 1")
    if loops < 1:
        raise ValueError("loops must be at least 1")

    tasks: List[FillTask] = []
    task_id = 1
    for worker_id in range(1, thread_count + 1):
        for round_no in range(1, loops + 1):
            tasks.append(
                FillTask(
                    task_id=task_id,
                    worker_id=worker_id,
                    round_no=round_no,
                    total_rounds=loops,
                )
            )
            task_id += 1
    return tasks
