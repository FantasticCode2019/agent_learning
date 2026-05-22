# Agent 异步架构原理、应用场景与优缺点详解
## 摘要

Agent 系统并不是一次性调用大模型后直接返回结果的简单程序。一个真实可用的 Agent 往往会经历**理解用户意图、规划任务、拆分子任务、并发调用工具或大模型、等待异步结果、检查依赖、汇总上下文、生成最终答复**等多个阶段。由于大模型调用、搜索、浏览器操作、代码执行、文件处理、数据库查询、第三方 API 调用都可能耗时较长，Agent 架构天然需要异步化。

Agent 异步架构的核心不是简单地“开线程”或“用回调”，而是把一次用户请求建模为一个可恢复的 **Agent Run**，把每个可执行步骤建模为一个带状态的 **Job**，再通过 **Job Store** 保存事实，通过 **Event Bus** 传播完成事件，通过 **Orchestrator** 推进 agent-loop。换言之，Agent 异步架构的关键原则是：**状态存储负责事实，事件通知负责触发，调度器负责决策，大模型和工具运行时负责执行**。

> **核心结论**：同进程 Agent 可以使用 Future、Promise、callback、async/await 等机制实现异步通知；分布式 Agent 则应使用任务状态存储、消息队列、事件总线、Webhook、SSE/WebSocket、工作流引擎等机制组合实现。生产级 Agent 不应只依赖内存回调，而应采用“状态可查询 + 事件可通知 + 失败可恢复”的架构。

## 1. Agent 异步架构要解决的问题

Agent-loop 是一个持续决策过程。每一轮循环通常会读取当前上下文，判断下一步动作，调用模型或工具，接收结果，再更新上下文并决定是否继续。这个过程之所以需要异步架构，是因为每一步的耗时、成功率和依赖关系都不可控。

| 问题 | 具体表现 | 异步架构的作用 |
| --- | --- | --- |
| 长耗时调用 | 大模型、网页抓取、代码执行、文件解析可能持续数秒到数分钟 | 避免阻塞主请求线程，让任务在后台继续运行 |
| 多任务并发 | 一个用户请求可能拆成多个并行子任务 | 提高吞吐和响应速度，允许多个 Job 同时执行 |
| 依赖编排 | 某些任务必须等多个前置任务完成后才能开始 | 使用 DAG、状态机或工作流引擎表达依赖 |
| 失败恢复 | 模型超时、工具失败、网络异常、worker 宕机 | 通过持久化状态、重试、补偿和死信恢复 |
| 用户体验 | 用户需要看到进度，而不是长时间无响应 | 通过状态接口、SSE 或 WebSocket 推送进度 |
| 系统扩展 | 单进程无法承载大量并发 Agent Run | 使用队列、worker pool 和分布式调度扩展执行能力 |

HTTP 长任务 API 常见的异步请求-回复模式会在接收请求后快速返回 `202 Accepted`，并通过 `Location` 暴露状态资源，让调用者后续查询进度或结果。[1] 这个思想同样适用于 Agent：用户请求创建后，系统可以返回一个 `run_id`，后续通过状态接口或事件流获取执行进度。

## 2. Agent 异步架构的核心组件

一个完整的 Agent 异步架构通常至少包含七类组件。它们不一定都是独立服务，在小型系统中可以位于同一进程；但在大型系统中，通常会拆分为多个服务和存储系统。

| 组件 | 职责 | 典型实现 |
| --- | --- | --- |
| API / Session Service | 接收用户请求，维护会话，返回 `run_id` 或最终答复 | HTTP API、WebSocket Gateway、会话服务 |
| Planner | 将用户目标拆解为任务计划或 DAG | LLM planner、规则引擎、模板化计划器 |
| Orchestrator | 推进 agent-loop，派发 Job，检查依赖，处理事件 | 自研调度器、工作流引擎、状态机 |
| Job Store | 保存每个子任务的状态、输入、输出引用、错误和重试次数 | PostgreSQL、MySQL、Redis、MongoDB、DynamoDB |
| Queue / Event Bus | 分发待执行任务和完成事件 | Kafka、RabbitMQ、Redis Stream、NATS、云 Pub/Sub |
| Worker / Tool Runtime | 执行 LLM 调用、工具调用、浏览器操作、代码运行、文件处理 | 线程池、进程池、容器、serverless worker |
| Result / Context Store | 保存中间结果、证据、文件、模型输出和最终报告 | 数据库、对象存储、向量库、上下文存储 |

这些组件之间的关系可以抽象为如下架构图：

```text
User
  |
  v
API / Session Service
  |
  v
Agent Orchestrator  <------ Event Bus <------ Worker / Tool Runtime
  |                       ^                       |
  |                       |                       v
  v                       |              LLM / Search / Browser / Code
Run Store / Job Store ----+                       |
  |                                               v
  +------------------ Result Store <-------------+
```

在这个架构中，**Orchestrator** 是 Agent-loop 的大脑，但它不应该亲自执行所有耗时任务。它负责决定“下一步做什么”，然后把具体执行交给 worker。worker 完成后把结果写入 Result Store，并通过 Event Bus 发布 `JobCompleted` 或 `JobFailed` 事件。Orchestrator 消费事件后继续推进后续任务。

## 3. Agent Run 与 Job 的状态模型

要理解 Agent 异步架构，必须区分两个层次的状态：**Agent Run 状态**和**Job 状态**。Agent Run 表示一次用户请求的整体生命周期；Job 表示其中一个可执行子任务。

| Agent Run 状态 | 含义 | 典型触发条件 |
| --- | --- | --- |
| `created` | 用户请求已创建，但尚未开始规划 | API 接收到请求并创建 run 记录 |
| `planning` | 正在调用模型或规则生成任务计划 | Planner 开始执行 |
| `executing` | 子任务正在并发执行 | 至少一个 Job 已派发 |
| `waiting` | 等待外部工具、用户确认、长任务或定时器 | 需要人工输入或外部回调 |
| `aggregating` | 正在汇总多个子任务结果 | 关键依赖全部完成 |
| `responding` | 正在生成最终答复 | 汇总结果已准备完成 |
| `completed` | 整体任务成功完成 | 最终结果已写入会话或结果存储 |
| `failed` | 整体任务不可恢复失败 | 达到最大重试次数或关键步骤失败 |
| `cancelled` | 用户或系统取消任务 | 用户取消、超时策略或资源回收 |

| Job 状态 | 含义 | 典型处理 |
| --- | --- | --- |
| `pending` | Job 已创建，尚未执行 | 等待依赖满足或等待调度 |
| `queued` | Job 已进入队列 | 等待 worker 领取 |
| `leased` | Job 已被某个 worker 领取 | 设置租约和心跳，避免重复执行 |
| `running` | Job 正在执行 | 记录开始时间、worker ID、进度 |
| `succeeded` | Job 成功完成 | 写入结果引用并发布完成事件 |
| `failed` | Job 执行失败 | 记录错误，判断是否重试 |
| `retrying` | Job 等待下一次重试 | 使用退避策略重新入队 |
| `dead_lettered` | 多次失败后进入死信 | 等待人工排查或补偿处理 |
| `cancelled` | Job 被取消 | 停止后续依赖任务或进入补偿流程 |

这种状态建模使 Agent 能够从异常中恢复。比如 worker 执行到一半崩溃，Job Store 中的任务会长时间处于 `leased` 或 `running` 状态，调度器可以通过心跳超时把它重新置为 `queued` 或 `retrying`。如果只依赖内存回调，一旦进程退出，系统就无法可靠判断任务是否完成。

## 4. Agent 异步调用的完整过程

下面以“用户要求 Agent 调研 5 个竞品并生成对比报告”为例，说明 Agent 内部如何异步执行。

用户输入如下：

> “帮我调研 Notion、Airtable、Coda、ClickUp、Monday 这 5 个产品，比较它们的定位、功能、价格和优缺点，最后生成一份 Markdown 报告。”

Planner 可以把任务拆成如下 DAG：

| 任务 ID | 任务名称 | 是否可并发 | 依赖关系 |
| --- | --- | --- | --- |
| `T0` | 理解需求并生成计划 | 否 | 无 |
| `T1` | 调研 Notion | 是 | `T0` |
| `T2` | 调研 Airtable | 是 | `T0` |
| `T3` | 调研 Coda | 是 | `T0` |
| `T4` | 调研 ClickUp | 是 | `T0` |
| `T5` | 调研 Monday | 是 | `T0` |
| `T6` | 汇总竞品信息 | 否 | `T1` 至 `T5` 全部成功或可接受地完成 |
| `T7` | 生成最终 Markdown 报告 | 否 | `T6` |

执行过程可以表示为如下事件时间线：

| 时间 | 事件 | 说明 |
| --- | --- | --- |
| `10:00:00` | `RunCreated` | API 创建 `agent_run_id` 并返回给前端 |
| `10:00:01` | `PlanningStarted` | Orchestrator 调用 Planner |
| `10:00:05` | `PlanningCompleted` | Planner 生成任务 DAG |
| `10:00:06` | `JobQueued(T1..T5)` | 五个竞品调研任务并发入队 |
| `10:00:08` | `JobStarted(T1)` | Worker A 开始调研 Notion |
| `10:00:08` | `JobStarted(T2)` | Worker B 开始调研 Airtable |
| `10:00:09` | `JobStarted(T3)` | Worker C 开始调研 Coda |
| `10:00:20` | `JobCompleted(T2)` | Airtable 调研完成，结果写入 Result Store |
| `10:00:23` | `JobFailed(T3)` | Coda 页面抓取失败，准备重试 |
| `10:00:30` | `JobRetrying(T3)` | 使用备用搜索源重试 |
| `10:00:42` | `JobCompleted(T3)` | Coda 重试成功 |
| `10:00:52` | `JobCompleted(T5)` | 最后一个竞品调研任务完成 |
| `10:00:53` | `DependenciesSatisfied(T6)` | Orchestrator 检测到汇总任务依赖满足 |
| `10:00:54` | `JobStarted(T6)` | 汇总结构化竞品信息 |
| `10:01:05` | `JobCompleted(T6)` | 汇总完成 |
| `10:01:06` | `JobStarted(T7)` | 调用大模型生成最终报告 |
| `10:01:20` | `RunCompleted` | 最终报告写入会话，通知用户 |

这个例子体现了 Agent 异步架构的本质：多个子任务并行执行，任何一个子任务完成后都会产生事件，但只有当依赖条件满足时，Orchestrator 才会启动下游任务。异步事件不是直接替代控制流，而是驱动状态机继续前进。

## 5. 同进程 Agent 的异步实现方式

小型 Agent、单机工具或开发阶段的 Agent 通常可以采用同进程异步架构。此时任务、调度器和结果都在同一个运行时内，可以使用 Future、Promise、callback、async/await、线程池或协程队列。

| 机制 | 原理 | 适用场景 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| Future / Promise | 提交任务后返回未来结果对象，完成后可查询或回调 | 线程池、进程池、并发模型调用 | 抽象清晰，支持结果、异常、取消和超时 | 进程重启后状态丢失，不适合长期任务 |
| Callback | 任务完成后执行注册函数 | 简单工具调用、UI 回调、轻量事件 | 实时性好，实现简单 | 回调线程不明确，异常处理和生命周期管理复杂 |
| async/await | 协程挂起等待异步结果，完成后恢复执行 | 高并发 I/O、API 调用、流式响应 | 代码结构清晰，资源占用低 | 阻塞代码会卡住事件循环 |
| Condition/Event | 线程等待共享条件变化，完成后被唤醒 | 底层并发控制、线程同步 | 控制精细，性能高 | 容易出现死锁、虚假唤醒、丢通知 |
| Blocking Queue/Channel | worker 完成后把结果放入队列，调度器消费 | 多任务结果收集、生产者消费者 | 适合流式消费和背压 | 需要额外维护任务 ID 与结果映射 |

Python 的 `concurrent.futures.Future` 封装了异步 callable 的执行，支持 `done()`、`result(timeout)` 和 `add_done_callback()` 等能力。[2] 这类机制非常适合同进程 Agent，但它们只是进程内状态对象，不应该作为分布式 Agent 的唯一事实来源。

一个同进程 Agent 的伪代码如下：

```python
class AgentOrchestrator:
    def __init__(self, executor):
        self.executor = executor
        self.jobs = {}
        self.dependencies = {"T6": ["T1", "T2", "T3", "T4", "T5"]}

    def submit_research_jobs(self):
        products = {
            "T1": "Notion",
            "T2": "Airtable",
            "T3": "Coda",
            "T4": "ClickUp",
            "T5": "Monday",
        }
        for job_id, product in products.items():
            self.jobs[job_id] = {"status": "running", "result": None}
            future = self.executor.submit(self.research_product, product)
            future.add_done_callback(lambda f, jid=job_id: self.on_job_done(jid, f))

    def on_job_done(self, job_id, future):
        try:
            self.jobs[job_id]["result"] = future.result()
            self.jobs[job_id]["status"] = "succeeded"
            self.on_event({"type": "JobCompleted", "job_id": job_id})
        except Exception as e:
            self.jobs[job_id]["status"] = "failed"
            self.jobs[job_id]["error"] = str(e)
            self.on_event({"type": "JobFailed", "job_id": job_id})

    def on_event(self, event):
        if self.can_start("T6"):
            self.aggregate()

    def can_start(self, job_id):
        return all(self.jobs[d]["status"] == "succeeded" for d in self.dependencies[job_id])
```

这段逻辑中，`add_done_callback` 只是把 Future 完成转换成 `JobCompleted` 事件。真正推进 agent-loop 的，是 `on_event()` 中的依赖检查和后续任务派发。

## 6. 分布式 Agent 的异步实现方式

当 Agent 需要支持多用户、高并发、长任务、跨机器执行、可恢复运行和多工具调用时，同进程 Future 就不够了。分布式 Agent 应将任务状态、事件和结果全部外部化。

| 架构能力 | 同进程 Agent | 分布式 Agent |
| --- | --- | --- |
| 状态保存 | 内存对象 | 数据库、Redis、工作流状态存储 |
| 完成通知 | callback、Future、Event | 消息队列、事件总线、Webhook、数据库 outbox |
| 执行资源 | 本地线程池或协程 | 多 worker、多容器、serverless、Kubernetes job |
| 失败恢复 | 依赖进程存活 | 可通过状态表、租约、重试和死信恢复 |
| 扩展性 | 受单机资源限制 | 可水平扩展 worker 和队列 |
| 适用范围 | demo、插件、本地自动化、小规模服务 | 生产级 Agent 平台、多用户 SaaS、企业自动化 |

分布式 Agent 的事件通常采用结构化格式，例如：

```json
{
  "event_id": "evt_001",
  "event_type": "JobCompleted",
  "agent_run_id": "run_20260522_001",
  "job_id": "T1",
  "job_type": "research_product",
  "status": "succeeded",
  "result_ref": "s3://agent-results/run_20260522_001/T1.json",
  "attempt": 1,
  "created_at": "2026-05-22T10:00:00+08:00"
}
```

这里的 `result_ref` 非常关键。Agent 的中间结果往往包含网页文本、模型输出、结构化表格、文件路径和证据片段，体积可能很大。如果把完整结果直接放进事件消息，会造成队列负载过高、重复传输和消息大小限制。因此，事件只携带结果引用，由消费者按需读取 Result Store。

## 7. Agent 中的几种完成通知机制

Agent 的“事件完成通知”并不只有一种实现方式。不同部署边界和实时性要求决定了不同机制。

| 通知机制 | 原理 | 适用场景 | 优点 | 缺点 |
| --- | --- | --- | --- | --- |
| Future callback | 同进程任务完成后触发回调 | 单机 Agent、开发原型、本地自动化 | 简单直接，延迟低 | 进程崩溃后丢失，不适合分布式 |
| 状态轮询 | 调用方通过 `run_id` 或 `job_id` 查询状态 | HTTP 长任务、前端刷新恢复、外部客户端 | 简单可靠，兼容性强 | 实时性差，可能产生轮询压力 |
| 消息队列事件 | worker 完成后发布 `JobCompleted` 消息 | 微服务内部、生产级 Agent 平台 | 可持久化、可重试、可削峰 | 引入 broker 运维复杂度 |
| Webhook | Agent 完成后调用外部系统 URL | 第三方集成、企业系统回调 | 外部系统可被动接收通知 | 需要签名、重试、防重放和幂等 |
| SSE/WebSocket | 后端把执行进度推给前端 | 用户实时查看 Agent 执行过程 | 用户体验好，适合进度流 | 连接管理和扩缩容较复杂 |
| 工作流信号 | 工作流实例等待外部事件或活动完成 | 多步骤长事务、复杂 Agent 编排 | 状态恢复和重试能力强 | 平台复杂度和学习成本较高 |

轮询与回调并不是非此即彼。很多长任务 API 会同时提供状态查询和通知机制。状态查询提供可靠兜底，通知机制提供实时性。异步 REST API 的常见模式也建议通过状态资源、轮询和 Webhook 组合管理长耗时任务。[3]

## 8. Agent 异步架构的应用场景

Agent 异步架构适用于所有“一个用户目标需要多个步骤、多次模型调用或多个工具协同完成”的场景。它在以下业务中尤其重要。

| 应用场景 | 异步特点 | 推荐架构 |
| --- | --- | --- |
| 深度研究报告 | 需要并发搜索、阅读多个网页、抽取事实、汇总引用 | DAG 调度 + 搜索 worker + LLM summarizer + Result Store |
| 数据分析 Agent | 需要上传文件、清洗数据、运行代码、生成图表 | Job Store + 代码执行沙箱 + 文件结果存储 |
| 浏览器自动化 Agent | 页面加载、登录、点击、下载均可能长时间等待 | Orchestrator + 浏览器 worker + 状态事件流 |
| 企业流程自动化 | 涉及审批、CRM、ERP、邮件、表单等多个系统 | 工作流引擎 + Webhook + 消息队列 |
| 软件开发 Agent | 需要读代码、改文件、运行测试、修复错误 | 任务 DAG + shell/code worker + 测试事件反馈 |
| 多 Agent 协作 | Planner、Researcher、Coder、Reviewer 各自执行任务 | 多角色 Job + Event Bus + Shared Context Store |
| 实时客服 Agent | 需要低延迟响应，同时异步查询知识库和工单系统 | async/await + 缓存 + 后台补全任务 |
| 长时间运行 Agent | 任务可能持续数小时或跨天 | 持久化状态 + 工作流引擎 + 定时器 + 恢复机制 |

这些场景的共同点是：任务之间存在依赖，执行时间不可预测，调用可能失败，用户希望看到进度，系统需要在失败后恢复。异步架构正是为了解决这些问题。

## 9. Agent 异步架构的优点

Agent 异步架构最大的价值是把“长时间、不确定、多步骤”的智能任务变成可管理的状态机。它使系统能够并发执行、渐进反馈、失败重试和横向扩展。

| 优点 | 说明 |
| --- | --- |
| 提升吞吐和响应速度 | 多个独立子任务可以并发执行，用户无需等待每一步串行完成 |
| 支持长任务 | API 请求可以快速返回 `run_id`，后台继续执行，避免 HTTP 超时 |
| 提高可靠性 | 状态持久化后，即使 worker 或调度器重启，也能恢复执行 |
| 更好的用户体验 | 前端可以展示计划、进度、阶段性结果和最终输出 |
| 便于扩展 | worker 可以按任务类型水平扩展，例如搜索 worker、代码 worker、浏览器 worker |
| 支持复杂编排 | DAG、状态机和工作流可以表达依赖、重试、补偿和人工确认 |
| 便于观测和审计 | 每个 Job 的输入、输出、耗时、错误和重试次数都可记录 |
| 降低耦合 | Orchestrator 只负责决策，Worker 只负责执行，事件总线负责通信 |

对于生产级 Agent 平台，这些优点通常是必须具备的。没有异步架构，Agent 很容易在长任务、并发用户、工具失败和进程重启时表现不稳定。

## 10. Agent 异步架构的缺点与挑战

异步架构也会显著提高系统复杂度。它把一次简单函数调用变成多个状态、事件、存储和 worker 之间的协作，因此需要更严格的工程治理。

| 挑战 | 具体风险 | 应对策略 |
| --- | --- | --- |
| 状态复杂 | Run 和 Job 状态可能不一致 | 定义明确状态机，所有状态迁移集中管理 |
| 事件重复 | 消息队列通常是至少一次投递 | 使用 `event_id`、`job_id + version` 做幂等 |
| 事件乱序 | 后发事件可能先到 | 在事件中携带版本号和时间戳，消费端校验状态迁移 |
| 结果丢失 | 事件到了但结果尚未落库，或结果引用失效 | 先写结果，再发布事件；使用事务 outbox 或最终一致机制 |
| 调试困难 | 异步链路跨多个组件 | 建立 trace_id、run_id、job_id 全链路日志 |
| 资源泄露 | 长任务、长连接、临时文件可能未清理 | 设置 TTL、心跳、租约和清理任务 |
| 成本上升 | 并发 worker 和模型调用可能快速放大成本 | 配额、限流、优先级队列、模型路由和缓存 |
| 用户取消复杂 | 已派发任务可能仍在执行 | 支持取消信号、协作式取消和结果忽略策略 |

Agent 系统还面临大模型特有的不确定性。模型可能输出不稳定计划，工具调用可能需要重试，某些任务失败后还可以改计划继续执行。因此，Agent Orchestrator 不仅要像传统任务调度器一样处理状态，还要能根据失败原因重新调用模型进行反思或重规划。

## 11. 可靠性设计：为什么“状态 + 事件”要同时存在

很多人会问：既然有事件通知，为什么还需要状态表？或者既然可以轮询状态，为什么还需要事件？答案是二者解决的问题不同。

| 机制 | 回答的问题 | 可靠性角色 |
| --- | --- | --- |
| 状态存储 | “现在事实是什么？” | 事实来源，可恢复，可查询，可审计 |
| 事件通知 | “刚刚发生了什么变化？” | 触发调度，降低延迟，驱动下游处理 |
| 轮询查询 | “如果通知丢了，我如何知道结果？” | 兜底机制，适合外部客户端 |
| 回调推送 | “我如何尽快收到结果？” | 实时体验增强，适合前端或第三方集成 |

生产级 Agent 应遵循以下顺序：worker 先把结果和状态写入持久化存储，然后再发布事件。这样即使事件消费者收到通知后立刻查询，也能读到结果。如果需要强一致性，可以使用事务 outbox：在同一个数据库事务中写入业务状态和待发布事件，再由 outbox relay 异步投递事件。

## 12. 前端如何感知 Agent 进度

Agent 后端的异步架构最终需要被用户感知。常见方式有三种：状态轮询、SSE 和 WebSocket。

| 方式 | 原理 | 适用情况 | 优缺点 |
| --- | --- | --- | --- |
| 状态轮询 | 前端定时请求 `GET /agent-runs/{run_id}` | 简单页面、低频任务、兼容性优先 | 实现简单，但实时性差，可能浪费请求 |
| SSE | 浏览器建立单向事件流，后端推送进度 | 任务进度、日志流、阶段性结果 | 比 WebSocket 简单，适合服务端到客户端推送 |
| WebSocket | 前后端建立双向长连接 | 实时交互、多轮控制、协作场景 | 功能强，但连接管理和扩容更复杂 |

推荐做法是：前端打开页面时先调用状态接口获取当前事实，再建立 SSE 或 WebSocket 接收后续事件。这样即使用户刷新页面或网络短暂断开，也可以从 `run_id` 恢复当前状态。

## 13. Agent 异步架构的落地建议

对于不同成熟度的系统，可以采用不同复杂度的实现。不要一开始就引入所有组件，而应根据任务时长、并发量、可靠性要求和团队能力逐步演进。

| 阶段 | 适用系统 | 推荐实现 |
| --- | --- | --- |
| 原型阶段 | 单用户、本地工具、demo Agent | async/await、Future、内存队列、简单状态对象 |
| 小型服务 | 少量用户、任务较短、可接受重启丢失部分进度 | 数据库存 run/job 状态，后台线程池执行，前端轮询 |
| 生产服务 | 多用户、任务数较多、需要恢复和重试 | Job Store + Queue + Worker Pool + Event Bus + Result Store |
| 企业平台 | 长任务、跨系统、审计要求高、流程复杂 | 工作流引擎 + 消息总线 + 权限系统 + 全链路观测 |
| 多 Agent 平台 | 多角色协作、任务图动态变化、上下文复杂 | DAG Orchestrator + Shared Context + Agent Registry + Policy Engine |

一个务实的演进路径是：先实现 `run_id` 和状态查询，再把耗时任务放入后台队列，然后增加完成事件和前端进度推送，最后在任务复杂度上升时引入工作流引擎或更完整的 DAG 调度器。

## 14. 推荐的数据模型

以下是一个简化的 Agent Run 和 Job 数据模型，适合多数生产系统作为起点。

| 表/集合 | 字段 | 说明 |
| --- | --- | --- |
| `agent_runs` | `run_id` | 一次用户请求的唯一 ID |
| `agent_runs` | `user_id` | 所属用户或租户 |
| `agent_runs` | `status` | 整体状态，例如 `planning`、`executing`、`completed` |
| `agent_runs` | `goal` | 用户原始目标或规范化目标 |
| `agent_runs` | `plan_ref` | 任务 DAG 或计划的存储引用 |
| `agent_runs` | `created_at / updated_at` | 创建和更新时间 |
| `agent_jobs` | `job_id` | 子任务唯一 ID |
| `agent_jobs` | `run_id` | 所属 Agent Run |
| `agent_jobs` | `status` | Job 状态 |
| `agent_jobs` | `job_type` | 任务类型，例如 search、llm、browser、code |
| `agent_jobs` | `input_ref` | 输入数据引用 |
| `agent_jobs` | `result_ref` | 输出结果引用 |
| `agent_jobs` | `attempt` | 当前重试次数 |
| `agent_jobs` | `depends_on` | 前置依赖 Job 列表 |
| `agent_events` | `event_id` | 事件唯一 ID，用于幂等 |
| `agent_events` | `event_type` | 事件类型，例如 `JobCompleted` |
| `agent_events` | `payload` | 事件载荷 |
| `agent_events` | `published_at` | 发布时间 |

这个模型的重点是：不要把所有内容都塞在一张表里。状态字段应该轻量、可索引；大文本、大文件和中间证据应放在 Result Store 中，并通过引用关联。

## 15. 最佳实践总结

Agent 异步架构的最佳实践可以浓缩为几个原则。第一，任何长耗时任务都应有唯一 ID 和明确状态。第二，任务结果应先持久化，再发布完成事件。第三，事件消费者必须幂等，因为重复事件是分布式系统的常态。第四，前端实时通知必须有状态查询兜底。第五，worker 执行任务时要有超时、心跳、租约和重试策略。第六，所有日志和事件都应携带 `run_id`、`job_id` 和 `trace_id`，否则异步链路很难排查。

| 原则 | 推荐做法 |
| --- | --- |
| 可恢复 | Run、Job、Result、Event 都要有持久化记录 |
| 可观察 | 记录每个 Job 的耗时、token、成本、错误、重试次数 |
| 可取消 | 支持用户取消 run，并向 worker 传播取消信号 |
| 可限流 | 对用户、租户、模型、工具和队列分别设置限流 |
| 可降级 | 模型失败时可切换模型，工具失败时可使用备用工具 |
| 可审计 | 保存关键输入、输出、工具调用和决策事件 |
| 可扩展 | 按任务类型拆分 worker pool，避免互相阻塞 |
| 可治理 | 对工具权限、网络访问、文件访问和外部调用做策略控制 |

## 16. 结论

Agent 异步架构是把智能体从“单次模型调用”升级为“可执行、可恢复、可观测、可扩展任务系统”的关键。它的本质是事件驱动的任务状态机：Planner 负责拆解目标，Orchestrator 负责编排执行，Worker 负责调用模型和工具，Job Store 保存事实，Event Bus 通知变化，Result Store 保存上下文和结果，前端通过轮询、SSE 或 WebSocket 感知进度。

如果是同进程 Agent，可以从 Future、callback 和 async/await 开始；如果是生产级分布式 Agent，应尽早引入持久化 Job Store、队列、事件总线、结果存储和幂等机制。最终推荐的设计不是单纯轮询，也不是单纯回调，而是：**状态可查询、事件可通知、结果可恢复、失败可重试、执行可观测**。

> **一句话总结**：Agent 的异步架构应以 `Agent Run + Job DAG + 状态存储 + 事件总线 + Worker Pool + 结果存储` 为核心，通过事件驱动 agent-loop 持续推进，并通过持久化状态保证系统在失败、重启和网络异常后仍能恢复。

## References

[1]: https://learn.microsoft.com/en-us/azure/architecture/patterns/asynchronous-request-reply "Microsoft Azure Architecture Center: Asynchronous Request-Reply Pattern"

[2]: https://docs.python.org/3/library/concurrent.futures.html "Python Documentation: concurrent.futures — Launching parallel tasks"

[3]: https://zuplo.com/learning-center/asynchronous-operations-in-rest-apis-managing-long-running-tasks/ "Zuplo: Asynchronous Operations in REST APIs: Managing Long-Running Tasks"
