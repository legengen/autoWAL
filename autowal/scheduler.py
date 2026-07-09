from concurrent.futures import ThreadPoolExecutor, as_completed

from .worker import run_worker


def run_scheduler(survey, args):
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
