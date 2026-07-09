#!/usr/bin/env python3
"""
自动填写「网民网络安全感满意度调查活动」问卷
依赖: selenium, chromedriver (Chrome 浏览器)
用法: python auto_fill.py [--debug] [--headless] [--auto-submit] [--seed 123] [--loops 3] [--threads 2]

  --debug       每步截图 + 打印详细 DOM 信息
  --headless    无头模式
  --auto-submit 填完自动点击提交
  --seed 123    固定随机种子
  --loops 3     循环填写 3 次，每次都会重启浏览器打开新页面
  --threads 2   同时启动 2 个线程，每个线程执行 loops 次
"""

import random
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from .browser import init_driver
from .config import SURVEY_JSON, SURVEY_URL
from .survey import load_survey

from .filler import debug_screenshot, fill_all, set_debug


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


def main():
    parser = argparse.ArgumentParser(description="自动填写网民网络安全感满意度调查问卷")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--auto-submit", action="store_true")
    parser.add_argument("--debug", action="store_true", help="每步截图 + DOM 探测")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--loops", type=int, default=1, help="循环填写次数，默认 1")
    parser.add_argument("--loop-delay", type=float, default=1.0, help="每轮结束后的等待秒数，默认 1")
    parser.add_argument("--threads", type=int, default=1, help="同时运行的线程数，默认 1")
    parser.add_argument("--interactive", action="store_true",
                        help="填写完成后等待按 Enter 才关闭浏览器（默认不等待）")
    args = parser.parse_args()

    if args.loops < 1:
        parser.error("--loops 必须大于等于 1")
    if args.threads < 1:
        parser.error("--threads 必须大于等于 1")
    if args.loop_delay < 0:
        parser.error("--loop-delay 不能小于 0")

    set_debug(args.debug)

    if args.seed is not None:
        print(f"随机种子: {args.seed}")

    print(f"加载问卷: {SURVEY_JSON}")
    survey = load_survey(SURVEY_JSON)
    print(f"共 {len(survey)} 个表单项")
    print(f"线程数: {args.threads}")
    print(f"每线程循环次数: {args.loops}")
    print(f"总填写次数: {args.threads * args.loops}\n")

    if args.threads == 1:
        run_worker(survey, args, thread_no=1)
        return

    if args.interactive:
        print("⚠ 多线程模式下不建议使用 --interactive，多个线程可能同时等待输入。")

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = [
            executor.submit(run_worker, survey, args, thread_no)
            for thread_no in range(1, args.threads + 1)
        ]
        for future in as_completed(futures):
            thread_no = future.result()
            print(f"线程 {thread_no} 全部循环完成")


if __name__ == "__main__":
    main()
