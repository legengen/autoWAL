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

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import SURVEY_JSON
from .filler import set_debug
from .survey import load_survey
from .worker import run_worker


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
