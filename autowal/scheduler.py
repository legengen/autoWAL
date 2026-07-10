import queue
import threading

from .control import RunSummary, TaskResult, build_tasks
from .worker import make_thread_rng, run_task


_STOP = object()


class ControlPlane:
    def __init__(self, survey, args, task_runner=run_task):
        self.survey = survey
        self.args = args
        self.task_runner = task_runner
        self.stop_event = threading.Event()
        self.result_queue = queue.Queue()
        self.task_queue = queue.Queue()
        self.threads = []

    def request_stop(self):
        self.stop_event.set()

    def _execute_with_retries(self, task, rng):
        current = task
        retries = getattr(self.args, "retries", 0)

        while not self.stop_event.is_set():
            try:
                result = self.task_runner(self.survey, self.args, rng, current)
            except Exception as exc:
                result = TaskResult(
                    task=current,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    worker_name=threading.current_thread().name,
                )

            if result.success or current.attempt > retries:
                return result

            current = current.next_attempt()
            print(
                f"[重试] 任务 {task.task_id} 将进行第 {current.attempt} 次尝试: "
                f"{result.error or 'unknown error'}"
            )

        return None

    def _worker_loop(self, worker_id):
        rng = make_thread_rng(self.args.seed, worker_id)
        has_completed_task = False

        while not self.stop_event.is_set():
            task = self.task_queue.get()
            try:
                if task is _STOP:
                    return

                if has_completed_task and self.args.loop_delay > 0:
                    print(
                        f"线程 {worker_id} 等待 {self.args.loop_delay:g} 秒后获取下一任务..."
                    )
                    if self.stop_event.wait(self.args.loop_delay):
                        return

                result = self._execute_with_retries(task, rng)
                if result is not None:
                    self.result_queue.put(result)
                has_completed_task = True
            finally:
                self.task_queue.task_done()

    def _start_workers(self, tasks):
        for task in tasks:
            self.task_queue.put(task)
        for _ in range(self.args.threads):
            self.task_queue.put(_STOP)

        for worker_id in range(1, self.args.threads + 1):
            thread = threading.Thread(
                target=self._worker_loop,
                args=(worker_id,),
                name=f"autowal-worker-{worker_id}",
            )
            thread.start()
            self.threads.append(thread)

    def _record_result(self, summary, result):
        summary.record(result)
        state = "成功" if result.success else "失败"
        print(
            f"[进度] {summary.completed}/{summary.total} "
            f"成功 {summary.succeeded} 失败 {summary.failed} | "
            f"任务 {result.task.task_id} {state} "
            f"({result.elapsed_seconds:.1f}s)"
        )

    def run(self):
        tasks = build_tasks(self.args.threads * self.args.loops)
        summary = RunSummary(total=len(tasks))
        self._start_workers(tasks)

        try:
            while summary.completed < summary.total:
                try:
                    result = self.result_queue.get(timeout=0.2)
                except queue.Empty:
                    if not any(thread.is_alive() for thread in self.threads):
                        break
                    continue

                self._record_result(summary, result)
        except KeyboardInterrupt:
            print("\n[控制] 收到中断请求，停止后续任务并等待当前任务关闭浏览器...")
            self.request_stop()
        finally:
            for thread in self.threads:
                thread.join()

            while True:
                try:
                    result = self.result_queue.get_nowait()
                except queue.Empty:
                    break
                self._record_result(summary, result)

            summary.finish(cancelled=summary.total - summary.completed)

        print(
            f"\n运行汇总: 总计 {summary.total}, 成功 {summary.succeeded}, "
            f"失败 {summary.failed}, 取消 {summary.cancelled}, "
            f"重试 {summary.retries}, 用时 {summary.duration_seconds:.1f}s"
        )
        return summary


def run_scheduler(survey, args):
    print(f"线程数: {args.threads}")
    print(f"任务倍数: {args.loops}")
    print(f"总填写次数: {args.threads * args.loops}")
    print(f"失败重试次数: {args.retries}\n")

    if args.interactive and args.threads > 1:
        print("[警告] 多线程模式下不建议使用 --interactive，多个线程可能同时等待输入。")

    return ControlPlane(survey, args).run()
