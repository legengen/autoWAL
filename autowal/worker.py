import random
import threading
import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from .browser import init_driver
from .config import SURVEY_URL
from .control import FillTask, TaskResult
from .filler import debug_screenshot, fill_all


def run_once(survey, args, rng, task):
    started_at = time.monotonic()
    driver = None
    success = False
    error = None

    try:
        driver = init_driver(headless=args.headless)
        print(f"\n{'='*50}")
        print(task.label)
        print(f"打开页面: {SURVEY_URL}")
        driver.get(SURVEY_URL)

        print("等待渲染...")
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".el-form-item, .el-radio, .el-checkbox, .el-cascader, .form-item-component, [class*='form-item']")
            )
        )
        time.sleep(2)
        print("就绪，开始填写\n")

        if args.debug:
            debug_screenshot(driver, "page_loaded")

        fill_all(driver, survey, rng, auto_submit=args.auto_submit)

        if args.interactive:
            print("\n按 Enter 关闭浏览器...")
            try:
                input()
            except EOFError:
                print("(非交互模式，自动关闭)")
                time.sleep(3)

        success = True

    except TimeoutException:
        print("[警告] 加载超时，强制尝试...")
        try:
            fill_all(driver, survey, rng, auto_submit=False)
            time.sleep(3)
            success = True
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(f"[错误] 超时后的填写尝试失败: {error}")
            traceback.print_exc()
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print(f"[错误] 异常: {error}")
        traceback.print_exc()
        time.sleep(3)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                if success:
                    success = False
                    error = f"driver quit failed: {exc}"
                print(f"[警告] 关闭浏览器失败: {exc}")
        print(f"{task.label} 已关闭浏览器")

    return TaskResult(
        task=task,
        success=success,
        elapsed_seconds=time.monotonic() - started_at,
        error=error,
        worker_name=threading.current_thread().name,
    )


def run_task(survey, args, rng, task):
    return run_once(survey, args, rng, task)


def make_thread_rng(seed, thread_no):
    if seed is None:
        return random.Random()
    return random.Random(seed + thread_no - 1)


def run_worker(survey, args, thread_no):
    rng = make_thread_rng(args.seed, thread_no)
    for round_no in range(1, args.loops + 1):
        task = FillTask(
            task_id=(thread_no - 1) * args.loops + round_no,
            worker_id=thread_no,
            round_no=round_no,
            total_rounds=args.loops,
        )
        run_task(
            survey,
            args,
            rng,
            task,
        )
        if round_no < args.loops and args.loop_delay > 0:
            print(f"线程 {thread_no} 等待 {args.loop_delay:g} 秒后开始下一轮...")
            time.sleep(args.loop_delay)
    return thread_no
