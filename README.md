# autoWAL

自动填写「网民网络安全感满意度调查活动」问卷的 Selenium 脚本。

## 环境要求

- Python 3.9+
- Google Chrome
- Selenium

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果是在 Linux 服务器：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 基础运行

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python .\auto_fill.py
```

Linux：

```bash
source .venv/bin/activate
python auto_fill.py
```

默认会打开 Chrome 无痕窗口，填写完成后关闭浏览器。默认不会自动提交，需要人工检查后提交。

## 项目结构

```text
auto_fill.py              兼容入口，转发到 autowal.cli
autowal/
  cli.py                  命令行参数解析
  control.py              任务、结果和运行汇总模型
  scheduler.py            主线程队列控制面
  worker.py               子线程单任务执行
  browser.py              Chrome / Selenium 初始化
  filler.py               各题型填写逻辑
  survey.py               问卷数据加载
  config.py               路径和问卷 URL 配置
survey_structured.json    结构化问卷题目数据
survey_raw.json           原始问卷接口数据
```

## 常用参数

```text
--headless      无头模式运行，不显示浏览器窗口
--auto-submit   填写完成后自动点击提交
--seed 123      固定随机种子，方便复现同一批随机结果
--loops 3       任务数量倍数，与 threads 相乘得到总任务数
--loop-delay 2  每轮之间等待 2 秒，默认 1 秒
--threads 2     最大并发 worker 数
--retries 1     单轮失败后最多重试 1 次，默认 0
--source-id 719419
                问卷链接中的 6 位 sourceID，默认 719419
--debug         保存调试截图
--interactive   每轮结束后等待按 Enter 再关闭浏览器
```

## 循环填写

循环填写 10 次：

```powershell
python .\auto_fill.py --headless --loops 10
```

每轮之间等待 3 秒：

```powershell
python .\auto_fill.py --headless --loops 10 --loop-delay 3
```

## 多线程填写

生成 15 个填写任务，最多同时由 3 个 worker 执行：

```powershell
python .\auto_fill.py --headless --threads 3 --loops 5
```

总填写次数为：

```text
threads * loops
```

例如 `--threads 3 --loops 5` 表示总共填写 15 次，但任务不会预先绑定线程。空闲 worker 会继续从共享队列获取下一个任务，因此每个 worker 实际处理的任务数可能不同。

## 控制平面

主线程现在只负责控制和观测，不直接填写问卷：

1. 根据 `threads * loops` 生成结构化任务。
2. 所有任务进入同一个共享工作队列。
3. 空闲 worker 从共享队列获取下一个任务，并上报成功、失败、耗时和错误。
4. 主线程持续输出完成进度，最后打印成功、失败、取消和重试汇总。

失败任务默认不重试。允许每轮失败后最多重试 2 次：

```powershell
python .\auto_fill.py --headless --threads 3 --loops 5 --retries 2
```

运行时按 `Ctrl+C`，控制面会停止后续任务，并等待当前轮次关闭浏览器后退出。

## 自定义 sourceID

默认问卷链接使用：

```text
sourceID=719419
```

运行时可以传入任意 6 位数字：

```powershell
python .\auto_fill.py --headless --source-id 123456
```

`source-id` 必须恰好为 6 位数字。它按字符串处理，因此像 `001234` 这样的前导零会被保留。

## 自动提交

填写完成后自动提交：

```powershell
python .\auto_fill.py --headless --auto-submit --loops 10
```

多线程自动提交：

```powershell
python .\auto_fill.py --headless --auto-submit --threads 3 --loops 5
```

## 固定随机种子

```powershell
python .\auto_fill.py --headless --seed 123 --threads 3 --loops 5
```

设置 `--seed` 后，每个任务根据 `seed + task_id` 使用独立随机序列，因此即使多线程领取顺序变化，同一任务的随机结果仍可复现。

## XML-RPC 接口

RPC 使用 Python 标准库实现，不需要安装额外依赖。启动服务：

```powershell
python .\rpc_server.py
```

服务默认监听 `127.0.0.1:8765`。如需指定地址和端口：

```powershell
python .\rpc_server.py --host 127.0.0.1 --port 8765
```

Python 客户端调用示例：

```python
from xmlrpc.client import ServerProxy

rpc = ServerProxy("http://127.0.0.1:8765", allow_none=True)

print(rpc.ping())

run = rpc.start_run({
    "threads": 2,
    "loops": 3,
    "headless": True,
    "auto_submit": False,
    "source_id": "719419",
})
run_id = run["run_id"]

print(rpc.get_run(run_id))
print(rpc.list_runs())
# rpc.stop_run(run_id)
```

提供以下接口：

```text
ping()              检查服务是否可用
start_run(options)  后台启动一次运行，返回 run_id
get_run(run_id)     查询运行状态和最终汇总
list_runs()         查询本进程中的全部运行记录
stop_run(run_id)    请求停止指定运行
```

`start_run` 支持 `threads`、`loops`、`loop_delay`、`retries`、`seed`、
`source_id`、`headless`、`auto_submit` 和 `debug`。未传参数时沿用命令行的安全默认值。
RPC 模式固定关闭 `interactive`，避免服务端等待终端输入。

RPC 当前没有身份认证，默认仅监听本机。不要直接将端口暴露到公网；远程调用建议通过 SSH
端口转发访问。

## Go 桌面客户端

`client-go/` 提供基于 Wails v2 的轻量桌面客户端。XML-RPC 请求由 Go 后端发送，前端不受
浏览器 CORS 限制。客户端支持连接服务器、启动任务、每 2 秒刷新运行列表、查看详情、
停止任务和操作日志。

开发运行：

```powershell
go install github.com/wailsapp/wails/v2/cmd/wails@v2.13.0
cd client-go
wails dev
```

构建 Windows 客户端：

```powershell
cd client-go
wails build -clean
```

产物位于 `client-go/build/bin/autoWAL-client.exe`。推送 `client-v*` 标签时，GitHub Actions
会构建 Windows、Linux 和 macOS 客户端并附加到 Release。

## 注意事项

- 脚本默认使用 Chrome 无痕模式。
- 职业身份题不会选择「其他」。
- 不建议在多线程模式下使用 `--interactive`，多个线程可能同时等待输入。
- 线程数越高，占用的 CPU、内存和浏览器实例越多，云服务器建议从 `--threads 2` 或 `--threads 3` 开始测试。
- 开发分支和提交规则见 `CONTRIBUTING.md`，禁止直接提交 `main` 和 `develop`。

## 仓库文件

需要提交到仓库的核心文件：

```text
auto_fill.py
autowal/
survey_structured.json
survey_raw.json
SELECTOR_GUIDE.md
requirements.txt
README.md
CONTRIBUTING.md
.gitignore
```

不需要提交：

```text
.venv/
drivers/
__pycache__/
debug_*.png
known-good-versions-with-downloads.json
latest-patch-versions-per-build-with-downloads.json
```
