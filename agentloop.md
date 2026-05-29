# GitHub 开源项目中的 Agent Loop 运作机制总结（加入 Harness 与 OpenClaw）

作者：**Manus AI**  
日期：2026-05-29

## 摘要

**Agent Loop** 是自治 Agent 从用户目标出发，反复执行“构造上下文、调用模型、解释输出、执行工具、写回观察、判断是否继续”的控制结构。它不是简单的 `while True`，而是由**状态机、工具执行器、上下文管理器、权限系统、事件流与持久化层**共同组成的运行时。OpenAI 对 Codex agent loop 的解释强调：模型可能返回最终回复，也可能请求工具调用；当模型请求工具时，agent 执行工具并把输出追加回上下文，再次请求模型，直到模型停止发出工具调用并输出 assistant message。[1]

从 GitHub 开源项目看，Agent Loop 的经典形态大致分为四类。第一类是 **Codex / CLI coding agent**，以流式模型调用、工具路由、上下文压缩和 turn 生命周期为核心。第二类是 **minimal loop**，如 AlessandroAnnini/agent-loop，把循环写成清晰的“LLM → Tools → Loop Control → Repeat”。第三类是 **long-running coding loop**，如 Ralph，用 shell 脚本反复调用外部编码工具，并把长期状态外置到文件和 git。第四类是 **harness 化运行时**，如 OpenHarness 与 OpenClaw，把模型包在一整套工具、记忆、权限、会话、插件、队列、流式事件和多通道网关中，使 agent loop 从“单任务循环”升级为“可长期运行的生产级 agent 基础设施”。[2] [3] [4]

## 一、通用 Agent Loop 的核心结构

一个标准 Agent Loop 可以概括为：系统先把用户目标、系统规则、项目上下文、历史消息与可用工具定义合并成模型请求；模型随后输出自然语言、推理片段或工具调用；运行时验证工具调用并执行工具，把工具结果作为 observation 写回上下文；随后再次调用模型，让模型基于观察继续决策；当模型给出最终回复、达到轮次上限、出现重复行为、收到中断、发生超时、触发上下文压缩或遇到不可恢复错误时，循环结束。[1] [5]

> OpenClaw 官方文档把 agentic loop 定义为一次真实 agent run 的完整路径：**intake → context assembly → model inference → tool execution → streaming replies → persistence**。这一定义很好地概括了生产级 Agent Loop 不只是模型推理，还包括会话、事件、工具和持久化。[3]

```text
function agent_loop(user_input):
    session.append(user_input)
    while true:
        prompt = build_context(session, tools, memory, policy)
        response = call_model(prompt, stream=True)

        if response.has_tool_calls:
            for call in response.tool_calls:
                if policy.requires_approval(call):
                    approve_or_reject(call)
                result = execute_tool(call)
                session.append(tool_result(result))
            if should_compact_or_retry(session):
                compact_context(session)
            if should_stop_by_limit_or_repetition(session):
                break
            continue

        session.append(assistant_message(response.text))
        persist_session(session)
        break
```

这段伪代码表达的是最小闭环，但真实系统通常还会加入流式事件、工具并发、安全审批、沙箱、session queue、写锁、provider fallback、自动压缩、后台任务、子 Agent、外部通道回复和审计日志。

## 二、核心项目与机制对比

| 项目 | 主要定位 | Agent Loop 形态 | 状态保存方式 | 主要停止条件 | 关键特征 |
|---|---|---|---|---|---|
| [OpenAI Codex / codex-rs](https://github.com/openai/codex) | 本地软件工程 Agent | 异步 turn loop 与 task loop | 会话 history、turn context、工具输出、文件系统 diff | 无需 follow-up、用户中断、错误、上下文压缩后继续或停止 | 流式 Responses API、工具路由、并发/独占工具调度、自动压缩 |
| [AlessandroAnnini/agent-loop](https://github.com/AlessandroAnnini/agent-loop) | 命令行 AI Agent | LLM → tools → loop control → repeat | 当前消息、工具调用历史、迭代计数 | 最大迭代、重复工具模式、完成语义、用户选择停止 | 最小可读实现，适合学习基础循环 |
| [snarktank/ralph](https://github.com/snarktank/ralph) | 长时间自治编码循环 | shell 脚本反复调用 Amp 或 Claude Code | `prd.json`、`progress.txt`、git branch/history | `<promise>COMPLETE</promise>` 或最大迭代 | 每轮启动新上下文，把长期记忆外置到文件和 git |
| [verl Agent Loop](https://verl.readthedocs.io/en/latest/advance/agent_loop.html) | Agentic RL 多轮 rollout | 用户自定义 `AgentLoopBase.run()` | token id 轨迹、response mask、请求 ID | 用户 loop 返回最终 `AgentLoopOutput` | 强调训练轨迹、token 对齐、推理服务负载均衡 |
| [OpenHarness](https://github.com/HKUDS/OpenHarness) | 轻量 Agent Harness 基础设施 | streaming tool-call cycle + tools/skills/memory/permissions | session history、MEMORY.md、技能、插件、后台任务 | 任务完成、权限拒绝、工具错误、用户中断、上下文压缩 | 把 LLM 包装为具备“手、眼、记忆、安全边界”的 agent |
| [OpenClaw](https://github.com/openclaw/openclaw) | 本地优先的个人 AI 助手与多通道 Gateway | 单 session 序列化 run：intake → context → model → tools → stream → persist | Gateway session、workspace、transcript、skills snapshot、队列与写锁 | lifecycle end/error、timeout、AbortSignal、Gateway/RPC 断开 | 多通道入口、session lane、工具流、assistant 流、插件 hooks、sandbox |
| [LangChain Open SWE](https://github.com/langchain-ai/open-swe) | 异步软件工程 Agent 框架 | 基于 LangGraph 的 agent/reviewer/workflow | GitHub 工作流、沙箱、图状态 | 图执行完成、review 通过或需要反馈 | 将 loop 扩展为异步图工作流 |

## 三、Codex：工程化 Coding Agent Loop 的代表

Codex 的开源实现体现了生产级 Agent Loop 的复杂性。其核心思想是把一次用户请求封装为 turn，而 turn 内部又可能包含多次模型采样和工具执行。模型如果返回工具调用，运行时执行工具并把结果写回会话；如果返回 assistant message 且不需要 follow-up，turn 才算完成。[1]

| Codex 机制 | 作用 | 设计意义 |
|---|---|---|
| `run_turn` | 组织一个 turn 内的模型采样、工具调用和终止判断 | 把“模型—工具—模型”的迭代封装为可取消、可压缩、可恢复的 turn |
| `run_sampling_request` | 构建 prompt、工具路由、调用模型流式接口并处理事件 | 将模型 API、工具事件和 UI 事件解耦 |
| `needs_follow_up` | 标记工具调用或非终止输出后需要继续采样 | 是循环继续的核心布尔信号 |
| Auto compact | 上下文接近限制时压缩历史再继续 | 解决长任务中的上下文窗口耗尽问题 |
| pending input | 支持用户在模型运行中追加输入 | 使 loop 具备交互式协作能力 |

Codex 展示的关键经验是，coding agent loop 必须对**工具调用副作用**负责。它不仅要让模型“看见”工具结果，还要确保并发工具、独占工具、沙箱环境、输出清洗、上下文压缩、用户取消和历史持久化都保持一致。

## 四、最小循环与长循环：AlessandroAnnini/agent-loop 与 Ralph

`AlessandroAnnini/agent-loop` 适合理解基础控制流。它把主循环拆成 **LLM → Tools → Loop Control → Repeat**：每轮先请求模型，再执行工具，并通过完成检测、重复检测和最大迭代控制是否继续。其重复检测不是只看工具名，而是把工具名与参数 hash 组合成签名，从而区分“同一工具不同参数的合理调查”和“完全重复的死循环”。[5]

| 控制点 | 实现方式 | 价值 |
|---|---|---|
| 最大迭代次数 | 达到 `max_iterations` 时硬停止 | 防止无限循环和成本失控 |
| 完成检测 | 无工具调用且出现完成短语，或回复很短且不像提问 | 让 CLI 能自动判断任务结束 |
| 重复检测 | 工具名 + 参数 hash 的历史模式 | 防止模型反复执行相同无效动作 |
| Human-in-the-loop | 安全模式下工具执行前询问用户 | 降低危险命令或误操作风险 |

Ralph 代表另一种粗粒度但鲁棒的长循环。它用 shell 脚本反复调用外部编码工具，每轮让工具读取 PRD、修改代码、运行测试并更新进度。如果输出中出现 `<promise>COMPLETE</promise>`，脚本退出；否则等待后进入下一轮，直到达到最大迭代次数。Ralph 的长期记忆不依赖模型上下文，而依赖 `prd.json`、`progress.txt` 和 git 历史。这种设计牺牲了细粒度事件控制，但换来了极高的可审计性与恢复能力。[6]

## 五、verl：面向强化学习的 Agent Loop

verl 的 Agent Loop 面向 agentic reinforcement learning，而不是普通终端用户。它把 loop 抽象为用户自定义的 `AgentLoopBase.run()`：给定 prompt 后，用户在 loop 内调用 LLM generate API、工具或环境交互，最终返回 `AgentLoopOutput`。该输出包含 `prompt_ids`、`response_ids` 与 `response_mask`，其中 mask 用于区分哪些 token 来自模型生成，哪些 token 来自工具响应。[7]

| 普通 Coding Agent Loop | verl Agent Loop |
|---|---|
| 目标是完成用户任务、修改代码或输出回复 | 目标是生成可训练的多轮 rollout 轨迹 |
| 历史通常保存为消息、工具结果、文件 diff | 历史必须保存 token ids 与 response mask |
| 工具执行与权限是核心工程问题 | token 对齐、reward 计算和推理服务负载均衡更关键 |
| 完成后返回 assistant message 或外部产物 | 完成后返回 `AgentLoopOutput` 供训练流程使用 |

verl 的价值在于提醒我们：Agent Loop 不只是应用层结构，也可以是训练数据生成结构。对 RL 而言，loop 的“过程记录”与最终答案同样重要。

## 六、Harness：从“循环函数”到“Agent 运行时外壳”

**Harness** 可以理解为包裹 LLM 的完整 agent 运行时。OpenHarness 的 README 明确定义：Agent Harness 是包围 LLM、让它成为 functional agent 的完整基础设施；模型提供 intelligence，而 harness 提供 hands、eyes、memory 和 safety boundaries。[2]

| Harness 能力 | 在 Agent Loop 中的角色 | OpenHarness 示例 |
|---|---|---|
| Tools | 把模型意图转化为可执行动作 | file、shell、search、web、MCP 等 43+ tools |
| Skills | 按需加载领域知识和流程模板 | Markdown skill、Claude-style plugin layout |
| Memory | 保存跨轮、跨会话的长期信息 | `MEMORY.md`、session resume/history |
| Permissions | 在工具执行前进行治理 | 多级权限、路径规则、命令规则、交互式审批 |
| Hooks | 在模型、工具、安装、消息生命周期中插入逻辑 | PreToolUse、PostToolUse、plugin hooks |
| Streaming | 把模型增量、工具事件和状态变化暴露给 UI/调用方 | text/json/stream-json 输出 |
| Multi-agent | 将任务拆分给 worker 或 background task | subagent spawning、team registry、background lifecycle |
| Cost/Retry | 控制可靠性和成本 | API retry with exponential backoff、token counting、cost tracking |

Harness 化的关键变化在于，Agent Loop 不再只是“一个函数调用 LLM 和工具”，而是运行在一个有治理能力的外壳中。模型只负责生成意图，harness 负责把意图转化为安全、可恢复、可审计的环境操作。OpenHarness 还支持 headless automation 和 CI 场景，即通过 `--output-format json` 或 `stream-json` 把 agent loop 的运行过程接入脚本与自动化流水线。[2] [8]

## 七、OpenClaw：本地优先、多通道、可等待的 Agent Loop

OpenClaw 是更完整的个人 AI 助手与 Gateway 架构。其 agent loop 的入口包括 Gateway RPC 的 `agent`、`agent.wait` 和 CLI 的 `agent` 命令。`agent` RPC 会验证参数、解析 session、持久化 session metadata，并立即返回 `{ runId, acceptedAt }`；真正的运行由 `agentCommand` 与 `runEmbeddedAgent` 完成。`runEmbeddedAgent` 会通过 per-session queue 和可选 global queue 序列化 run，解析模型和认证 profile，构建 session，订阅 runtime 事件，流式发送 assistant/tool delta，并在超时后 abort。[3]

| OpenClaw 环节 | 主要动作 | Agent Loop 意义 |
|---|---|---|
| Intake | Gateway RPC 或 CLI 接收消息，解析 sessionKey/sessionId | 将多通道输入归一化为 session run |
| Queueing | per-session lane 与可选 global lane 序列化运行 | 防止同一 session 的工具与 transcript 竞态 |
| Context assembly | 加载 skills snapshot、bootstrap/context files、system prompt | 让模型获得稳定任务上下文 |
| Model inference | 解析 provider/model/auth/thinking/trace 默认值并调用 runtime | 支持不同模型与 thinking level |
| Tool execution | 发出 tool start/update/end 事件并清洗工具结果 | 使工具过程可观察、可审计 |
| Streaming replies | assistant deltas、tool events、lifecycle events 分流输出 | 支持聊天通道、UI 和 wait 语义 |
| Persistence | session transcript write lock 保护写入 | 保持跨进程、跨通道历史一致性 |
| Waiting | `agent.wait` 等待 lifecycle end/error | 支持同步调用方等待异步 run 完成 |

OpenClaw 的经典设计是**单 session 序列化 + 事件流桥接**。它把 runtime 内部事件映射为 `lifecycle`、`assistant` 与 `tool` 三类 stream：工具事件进入 `tool` stream，assistant 增量进入 `assistant` stream，开始、结束和错误进入 `lifecycle` stream。聊天通道会缓冲 assistant delta，并在 lifecycle end/error 时发出 final message。[3]

OpenClaw 还非常重视 session 一致性。它不仅使用 session lane 防止同一会话并发运行，还用 session transcript file write lock 保护 transcript 文件。这样，即使有绕过内存队列的外部进程写入，也能避免历史文件损坏。OpenClaw 文档还说明，`agent.wait` 的 timeout 只是等待超时，并不会停止底层 agent；真正会提前结束 run 的原因包括 agent timeout、AbortSignal、Gateway disconnect 或 RPC timeout。[3]

## 八、OpenClaw 的 Harness 插件机制：Codex 等 native runtime 如何接入

OpenClaw 的 Agent Harness 插件机制进一步区分了 **Core** 与 **Harness** 的职责。OpenClaw 文档将 agent harness 描述为“one prepared OpenClaw agent turn”的低层 executor：它不是 provider、不是 channel、不是 tool registry，而是用于那些模型家族拥有自己 native session runtime、普通 provider transport 不适合的场景，例如 native coding-agent server、需要流式 plan/reasoning/tool events 的 CLI 或 daemon、以及需要自己 resume id 的 runtime。[4]

| 责任域 | OpenClaw Core 负责 | Harness 负责 |
|---|---|---|
| 模型选择 | provider/model 解析、fallback、live switching policy | 不自行选择 provider，不静默切换 model |
| 会话与上下文 | transcript/session file、workspace、sandbox、context budget | 运行已准备好的 attempt |
| 权限与工具治理 | tool policy、approval、channel callbacks | 将 native runtime 的工具/事件映射回 OpenClaw 语义 |
| 用户可见历史 | OpenClaw transcript 与 channel-visible session history | 镜像 assistant/tool output 到 OpenClaw transcript |
| Runtime 特性 | 提供统一 Gateway、session、stream、hook 框架 | 保留 native thread id、resume、compaction、app-server execution 等特性 |

这个分工非常重要。它避免了“接入一个 native agent runtime 就绕开 OpenClaw 安全与历史系统”的问题。以 Codex harness 为例，Codex 可以保留自己的 native thread id、resume behavior、compaction 和 app-server execution；但 OpenClaw 仍拥有聊天通道、可见 transcript mirror、tool policy、approvals、media delivery 和 session selection。[4]

Harness 选择也遵循明确规则：model-scoped runtime policy 优先，其次 provider-scoped runtime policy；auto 模式下询问已注册 harness 是否支持 provider/model；没有匹配时回退到 embedded runtime。一旦 plugin harness claim 一个 run，OpenClaw 不会把同一 turn 通过另一个 runtime 重放，以避免工具副作用重复或认证/runtime 语义变化。[4]

## 九、共同设计模式：经典 Agent Loop 应该具备什么

综合 Codex、minimal loop、Ralph、verl、OpenHarness 与 OpenClaw，可以把经典 Agent Loop 的设计模式归纳为六层。

| 层次 | 主要职责 | 常见实现 |
|---|---|---|
| 输入与上下文层 | 整合用户目标、系统规则、项目文件、历史消息、技能和工具 schema | prompt builder、bootstrap context、project instructions、skills injection |
| 推理层 | 调用 LLM，接收文本、推理片段和工具调用 | Responses API、Chat Completion、streaming events、generate API |
| 工具层 | 解析、验证、执行工具，并把结果返回模型 | ToolRouter、ToolRegistry、MCP、shell/browser/file tools |
| 控制层 | 判断继续、停止、压缩、重试、等待或询问用户 | `needs_follow_up`、max iterations、completion signal、loop detection、timeout |
| 状态层 | 保存长期状态、任务轨迹和外部产物 | git、conversation history、transcript、token ids、progress log、MEMORY.md |
| 治理与运行时层 | 权限、安全、队列、锁、hook、事件流、沙箱和 provider 策略 | Harness、Gateway、session lane、write lock、approval、plugin hooks |

最核心的模式仍是**观察—行动闭环**。模型通过工具调用表达意图，运行时执行工具并返回观察，模型再依据观察继续推理。这个分离使系统能够插入权限控制、沙箱、审计、超时、重试和输出截断等保护。Harness 与 OpenClaw 的补充说明了更进一步的趋势：成熟 Agent Loop 必须把“能行动”与“能治理”绑定在一起，否则越强的工具能力就意味着越高的副作用风险。[2] [3]

第二个模式是**终止条件必须显式化**。自然语言的“我完成了”并不总可靠，因此实际系统会结合最大轮次、重复检测、工具调用状态、完成标记、生命周期事件、timeout、AbortSignal 和 session wait 语义。Ralph 用 `<promise>COMPLETE</promise>`，Alessandro 项目用完成短语和重复检测，Codex 用 follow-up 与 turn 状态，OpenClaw 用 lifecycle end/error 与 `agent.wait`，verl 则由用户实现的 `run()` 返回 `AgentLoopOutput`。[3] [5] [6] [7]

第三个模式是**状态应外置且可恢复**。长任务不能只依赖模型上下文。Codex 与 OpenClaw 保存 session history 和 transcript，Ralph 使用 PRD/progress/git，OpenHarness 使用 MEMORY.md 与 session resume，verl 保存 token 级轨迹。外置状态越清晰，Agent Loop 越容易调试、恢复、审计和迁移。[2] [3] [6] [7]

## 十、实现建议

如果要实现一个自己的 Agent Loop，可以从最小闭环开始，但应尽早加入停止条件、工具结果回填、错误处理和权限边界。对于单机 CLI 工具，AlessandroAnnini/agent-loop 的结构足够清晰；对于长时间编码任务，Ralph 的文件化长期记忆很值得借鉴；对于生产级 coding agent，应参考 Codex 的 turn loop、streaming、tool router、auto-compaction 与 pending input；如果目标是多通道、长期在线、可审计的个人助理或企业 Agent，则更应采用 OpenHarness/OpenClaw 这种 harness 化架构，把模型运行放在工具、记忆、队列、权限、hooks 与 session persistence 的外壳中。

| 目标场景 | 推荐借鉴机制 | 原因 |
|---|---|---|
| 学习或原型 | minimal LLM → tool → loop control | 结构清晰，调试成本低 |
| 本地编码助手 | Codex turn loop + tool router + auto compact | 适合文件系统、测试和长期代码修改 |
| 长时间批处理编码 | Ralph 式 PRD/progress/git 外置状态 | 上下文可重启，易审计 |
| RL 训练 | verl `AgentLoopBase` + token mask | 能生成可训练 rollout 轨迹 |
| 多通道个人助理 | OpenClaw Gateway + session lane + lifecycle stream | 能处理异步消息、等待、超时和持久化 |
| 通用 agent 基础设施 | OpenHarness tools/skills/memory/permissions | 将 LLM 包装成可治理、可扩展的 agent runtime |

## 参考文献

[1]: https://openai.com/index/unrolling-the-codex-agent-loop/ "OpenAI：Unrolling the Codex agent loop"  
[2]: https://github.com/HKUDS/OpenHarness "HKUDS/OpenHarness README"  
[3]: https://docs.openclaw.ai/concepts/agent-loop "OpenClaw Docs：Agent loop"  
[4]: https://docs.openclaw.ai/plugins/sdk-agent-harness "OpenClaw Docs：SDK Agent Harness"  
[5]: https://github.com/AlessandroAnnini/agent-loop "AlessandroAnnini/agent-loop"  
[6]: https://github.com/snarktank/ralph "snarktank/ralph"  
[7]: https://verl.readthedocs.io/en/latest/advance/agent_loop.html "verl Documentation：Agent Loop"  
[8]: https://github.com/HKUDS/OpenHarness/blob/main/docs/SHOWCASE.md "OpenHarness Showcase"  
[9]: https://github.com/openai/codex "OpenAI Codex GitHub Repository"  
[10]: https://github.com/langchain-ai/open-swe "LangChain Open SWE GitHub Repository"  
