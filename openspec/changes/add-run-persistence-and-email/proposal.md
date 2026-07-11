## Why

RPC 运行记录目前只保存在服务端内存中，服务重启后历史、错误和执行过程全部丢失，也无法可靠地识别、说明和追踪一次完整的多线程批次 Run。长时间运行的批次还需要在进入最终状态时主动通知用户，而不是依赖客户端持续在线查看。

## What Changes

- 使用 Python 标准库 SQLite 持久化每个完整批次 Run，并生成 UUID `run_id` 和服务端唯一的可读编号。
- 为 Run 增加必填名称和可选用途说明；Go 客户端可提交、显示和检索这些字段。
- 建立 `runs`、`run_logs`、`task_logs` 三张核心表，分别保存 Run 当前状态、生命周期日志和内部问卷填写日志。
- 由单一数据库写入线程串行处理状态命令和日志事件；Run 状态变化与对应生命周期日志在同一事务中提交。
- 服务启动时将遗留的活动 Run 恢复为 `interrupted`，保留历史并触发最终状态通知。
- 扩展 XML-RPC 接口，提供分页历史查询以及 Run/task 日志增量查询。
- 通过 SMTP 在每个 Run 首次进入 `completed`、`failed`、`stopped` 或 `interrupted` 时创建一份逻辑通知，并持久化发送、重试和失败状态。
- 邮件凭证仅从服务端环境变量读取，不写入数据库、日志或 RPC 响应。

## Non-goals

- 不持久化 Selenium 浏览器会话，也不在服务重启后继续执行中断的 Run。
- 不为 Run 内的单次问卷填写提供用户名称或单独邮件。
- 不提供多用户账号、权限控制、远程数据库、邮件模板编辑器或自动历史清理。
- SMTP 无法保证物理投递严格恰好一次；系统只保证每个 Run 创建一个逻辑通知并使用固定 Message-ID 重试。

## Capabilities

### New Capabilities

- `run-persistence`: Run 身份、名称、状态、统计结果、SQLite 事务、历史分页和重启恢复。
- `run-logging`: `run_logs` 与 `task_logs` 的结构化事件、单写入线程、顺序保证和增量查询。
- `run-email-notification`: Run 最终状态邮件的持久化 outbox 状态、SMTP 发送、重试和凭证管理。

### Modified Capabilities

无。

## Impact

- 服务端：`autowal.rpc`、调度器、worker/filler 日志路径、服务启动流程和配置。
- 客户端：Go RPC 模型、启动表单、历史列表、详情和日志查看。
- API：`start_run` 请求与 Run 响应增加元数据；列表和日志接口增加分页/游标参数。
- 数据：新增本地 SQLite 文件及 schema migration；不增加第三方 Python 数据库依赖。
- 运维：新增 SMTP 环境变量和数据库备份责任。
