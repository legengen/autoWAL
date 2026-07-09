import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from .browser import init_driver
from .config import SURVEY_URL
from .filler import debug_screenshot, fill_all


def run_once(survey, args, rng, thread_no=1, round_no=1, total_rounds=1):
    driver = init_driver(headless=args.headless)
    try:
        print(f"\n{'='*50}")
        print(f"线程 {thread_no} 第 {round_no}/{total_rounds} 轮")
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

    except TimeoutException:
        print("⚠ 加载超时，强制尝试...")
        fill_all(driver, survey, rng, auto_submit=False)
        time.sleep(3)
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        time.sleep(3)
    finally:
        driver.quit()
        print(f"线程 {thread_no} 第 {round_no}/{total_rounds} 轮已关闭浏览器")


def make_thread_rng(seed, thread_no):
    if seed is None:
        return random.Random()
    return random.Random(seed + thread_no - 1)


def run_worker(survey, args, thread_no):
    rng = make_thread_rng(args.seed, thread_no)
    for round_no in range(1, args.loops + 1):
        run_once(
            survey,
            args,
            rng,
            thread_no=thread_no,
            round_no=round_no,
            total_rounds=args.loops,
        )
        if round_no < args.loops and args.loop_delay > 0:
            print(f"线程 {thread_no} 等待 {args.loop_delay:g} 秒后开始下一轮...")
            time.sleep(args.loop_delay)
    return thread_no
