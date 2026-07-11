## Context

当前 `RpcService` 用进程内 `_runs` 字典保存批次状态，`ControlPlane` 和 Selenium 填写链路主要使用 `print()` 输出。一个用户可见 Run 包含 `threads * loops` 个内部问卷任务，每个任务可能重试；多个 Run 和 worker 可以并发，因此全局 stdout 无法可靠归属日志。服务重启会丢失全部记录，也没有最终状态通知。

约束是保持单机、低运维复杂度和 Python 标准库优先，同时让现有 XML-RPC 调用可渐进兼容。SQLite 文件、SMTP 和 Go/Wails 客户端均属于同一部署边界。

## Goals / Non-Goals

**Goals:**

- 每个 Run 在执行前持久化身份、用户元数据和参数，并持久化全部状态变化、汇总和错误。
- 使用三张核心表区分 Run 当前状态、Run 生命周期日志和内部任务执行日志。
- 保证 Run 状态变化与对应生命周期日志原子提交，且 worker 不直接写 SQLite。
- 服务重启后保留历史，将未完成 Run 终结为 `interrupted`。
- 每个 Run 创建一个可重试的最终状态邮件逻辑通知。
- 让客户端命名 Run、分页查看历史，并增量查看日志和邮件状态。

**Non-Goals:**

- 不恢复 Selenium 会话或继续执行重启前的 Run。
- 不为单次问卷填写命名、发邮件或提供独立业务实体。
- 不提供远程数据库、多租户、权限系统、自动保留策略或严格一次 SMTP 物理投递。

## Decisions

### 1. SQLite 单文件与三张核心表

使用标准库 `sqlite3`，默认数据库位于服务端可配置数据目录下的 `autowal.db`。启用 WAL、foreign keys 和 busy timeout，并通过 `PRAGMA user_version` 管理 schema migration。

`runs` 保存 `run_id`、唯一 `run_number`、`name`、`description`、状态、JSON 参数/汇总、最终错误、邮件状态/尝试信息及时间戳。`run_logs` 保存 Run 生命周期事件；`task_logs` 保存 `(run_id, task_id, attempt)` 范围内的执行事件。JSON 用于低频且整体读取的参数和汇总，常用筛选字段保持独立列。

选择三表而不是增加 tasks/notifications 表，是因为内部任务只需日志身份，每个 Run 也只有一种最终邮件。若以后出现多种通知或任务级查询，再通过 migration 扩展。

### 2. 单一数据库写入线程处理持久化命令

所有生产者向有界 FIFO 队列提交 `CreateRun`、`TransitionRun`、`AppendRunLog`、`AppendTaskLog`、`MarkEmail*` 和 `Barrier` 命令。唯一 writer 持有写连接并返回需要确认的命令结果；RPC 查询使用独立只读连接。

worker 不直接执行 SQL。队列满时生产者阻塞而不是丢日志，因为日志完整性优先于吞吐。终态转换前提交并等待 `Barrier`，保证先前 task 日志已落盘。

### 3. 状态转换与生命周期日志原子化

`TransitionRun` 携带 expected status、new status、汇总/错误和生命周期事件。writer 在一个事务中条件更新 `runs` 并插入 `run_logs`；条件更新未命中时整个事务失败，防止停止与自然完成互相覆盖。

允许的主要转换为：

```text
pending  -> running | stopped | failed | interrupted
running  -> completed | failed | stopping | interrupted
stopping -> stopped | failed | interrupted
```

最终状态不可逆。进入最终状态的同一事务还会把 `email_status` 从 `none` 设置为 `pending`，生成确定性的 Message-ID，并插入 `email.queued`。

### 4. 结构化日志替代 stdout 捕获

使用标准库 `logging` 和上下文适配器，把 `run_id`、`task_id`、`attempt`、worker、component、event_type、level、message、error 和 elapsed time 转换为队列命令。禁止通过 `redirect_stdout` 捕获，因为并发 Run 会混合输出。默认持久化操作日志；可能包含 DOM 或敏感内容的详细诊断仅在 debug 模式记录。

日志表使用自增 `log_id` 作为稳定游标。RPC 查询接受 `after_log_id` 和有限 `limit`，不把日志嵌入每两秒轮询的 Run 记录。

### 5. Run 身份和客户端元数据

`run_id` 使用 UUID 作为不可变主键；`run_number` 由服务端按日期和序列生成，例如 `20260711-000001`，并设唯一约束。名称必填、说明选填，两者都不是唯一键。

`start_run` 在保持原扁平 options 字典兼容的前提下接受 `name` 和 `description`，服务端先剥离元数据再构建 scheduler 参数。新客户端必须提交名称，并显示编号、名称、说明和邮件状态。

### 6. runs 表承担单通知 outbox

邮件线程只查询 `email_status in (pending, retry_wait)` 的终态 Run，并通过 writer 原子声明为 `sending`。成功后提交 `sent` 和 `email.sent`；失败后增加 attempts，提交 `retry_wait`/`failed` 和对应日志。采用有上限的指数退避，具体次数和间隔可配置。

同一 Run 始终使用确定性 Message-ID，因此所有重试属于同一个逻辑通知。SMTP 的确认与数据库提交无法构成分布式事务，崩溃窗口仍可能造成物理重复，这是接受的权衡。

SMTP host、port、user、password、from、to 和 TLS 设置从环境变量读取。凭证不得写入数据库、日志、异常详情或 RPC。

### 7. 启动恢复和关闭顺序

启动时在接受 RPC 前启动 writer、运行 migration，并在一个或多个受控事务中把 `pending/running/stopping` 变为 `interrupted`，写入 `run.interrupted`，同时排队最终邮件。遗留 `sending` 邮件变为 `retry_wait`；`sent` 不变。

正常关闭时先停止接受新 Run，再请求活动 Run 停止，刷新持久化队列，最后关闭邮件线程和数据库 writer。

## Risks / Trade-offs

- [SQLite 或磁盘不可写导致任务无法启动] -> `CreateRun` 成功前不启动线程，RPC 返回明确错误并提供数据目录配置。
- [高频日志产生背压] -> 使用有界队列和批量插入，但绝不静默丢弃；避免默认记录 DOM 等高体积内容。
- [SMTP 发送成功后、标记 sent 前崩溃造成重复] -> 固定 Message-ID、恢复后重试并在文档声明至少一次语义。
- [持久历史使 list_runs 无界增长] -> API 强制 limit/cursor，客户端分页；第一版不自动删除。
- [旧客户端不提供名称] -> 服务端为兼容调用生成默认名称；新客户端 UI 将名称设为必填。
- [数据库 schema 演进] -> 启动时事务化 migration，升级前建议备份数据库文件。

## Migration Plan

1. 新增存储模块、schema migration 和隔离测试；空数据库自动创建三表及索引。
2. 接入 RpcService 的 Run 创建/状态查询，暂时保留现有内存中的活动 control plane 引用。
3. 接入结构化日志队列和 scheduler/worker/filler 上下文，验证并发归属和顺序。
4. 增加恢复流程、邮件 outbox 和 SMTP 集成测试。
5. 扩展 XML-RPC 与 Go 客户端，完成历史、名称、日志和邮件状态 UI。
6. 部署前备份现有数据目录；旧版本没有可迁移的内存历史。

回滚到旧版本前停止服务并备份 `autowal.db`。旧版本会忽略数据库，但不会删除它；再次升级后可继续读取历史。

## Open Questions

- 邮件最大重试次数和退避时间采用什么默认值（建议 5 次，1/5/15/30/60 分钟）。
- 默认数据目录是项目目录下 `data/`，还是由部署环境强制提供绝对路径。
- 第一版客户端是否只显示合并时间线，还是分别提供 Run 日志和内部任务日志标签页。
