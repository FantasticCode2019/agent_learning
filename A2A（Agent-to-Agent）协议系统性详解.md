# A2A（Agent-to-Agent）协议系统性详解

> **文档版本**：基于 A2A Protocol Specification v1.0.0 及 a2a-python SDK 编写
>
> **参考资料**：[官方规范][spec] | [官方介绍][what-is-a2a] | [a2a-python SDK][sdk] | [LiteLLM A2A 文档][litellm] | [ADK A2A 介绍][adk]

[spec]: https://a2a-protocol.org/latest/specification/
[what-is-a2a]: https://a2a-protocol.org/latest/topics/what-is-a2a/
[sdk]: https://github.com/a2aproject/a2a-python
[litellm]: https://docs.litellm.com.cn/docs/a2a
[adk]: https://adk.dev/a2a/intro/

---

## 目录

1. [什么是 A2A 协议](#1-什么是-a2a-协议)
2. [核心设计原则](#2-核心设计原则)
3. [规范分层架构](#3-规范分层架构)
4. [核心数据模型](#4-核心数据模型)
5. [任务状态机与生命周期](#5-任务状态机与生命周期)
6. [核心操作](#6-核心操作)
7. [任务更新传递机制](#7-任务更新传递机制)
8. [Agent Card 与服务发现](#8-agent-card-与服务发现)
9. [认证与授权](#9-认证与授权)
10. [协议绑定](#10-协议绑定)
11. [扩展机制](#11-扩展机制)
12. [Python SDK 实践：a2a-python](#12-python-sdk-实践a2a-python)
13. [完整示例：构建一个 Hello World Agent](#13-完整示例构建一个-hello-world-agent)
14. [常见工作流与交互模式](#14-常见工作流与交互模式)
15. [错误处理](#15-错误处理)
16. [参考资料](#16-参考资料)

---

## 1. 什么是 A2A 协议

**A2A（Agent-to-Agent）协议**是一个开放标准，旨在促进独立、可能不透明的 AI Agent 系统之间的通信和互操作性。在一个 Agent 可能由不同框架、语言构建或由不同供应商提供的生态系统中，A2A 提供了一种通用的语言和交互模型 [1]。

A2A 的核心价值在于：**不同 Agent 之间可以相互协作，而无需了解彼此的内部实现**。一个基于 LangChain 构建的 Agent 可以无缝地调用一个基于 ADK 构建的 Agent，反之亦然，只要双方都遵循 A2A 协议。

A2A 协议的主要目标如下：

| 目标 | 说明 |
|---|---|
| **互操作性** | 弥合不同 Agentic 系统之间的通信鸿沟 |
| **协作** | 使 Agent 能够委派任务、交换上下文并协同工作 |
| **发现** | 允许 Agent 动态发现和理解其他 Agent 的能力 |
| **灵活性** | 支持同步、流式、异步推送等多种交互模式 |
| **安全性** | 基于标准 Web 安全实践，适用于企业环境 |
| **异步优先** | 原生支持长时间运行任务和人在回路（Human-in-the-loop）场景 |

---

## 2. 核心设计原则

A2A 协议的设计遵循以下指导原则 [1]：

**简单性**：复用现有的、被广泛理解的标准（HTTP、JSON-RPC 2.0、Server-Sent Events），而非发明新的底层协议。

**企业就绪**：通过与已建立的企业实践保持一致，解决认证、授权、安全、隐私、追踪和监控问题。

**异步优先**：专为可能非常长时间运行的任务和人在回路交互而设计。

**模态无关**：支持交换多种内容类型，包括文本、音视频（通过文件引用）、结构化数据/表单，以及潜在的嵌入式 UI 组件。

**不透明执行（Opaque Execution）**：Agent 之间基于声明的能力和交换的信息进行协作，**无需共享内部想法、计划或工具实现**。这是 A2A 与 MCP（Model Context Protocol）的重要区别——MCP 关注的是 Agent 与工具/资源的连接，而 A2A 关注的是 Agent 与 Agent 之间的互操作。

---

## 3. 规范分层架构

A2A 规范采用了清晰的三层架构，确保核心语义在所有协议绑定中保持一致 [1]：

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 1: 规范数据模型                     │
│   Task  Message  AgentCard  Part  Artifact  Extension       │
│   (基于 Protocol Buffers 定义，协议无关的规范数据结构)         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Layer 2: 抽象操作                         │
│  SendMessage  GetTask  ListTasks  CancelTask  SubscribeToTask│
│   (定义基本能力和行为，独立于具体协议绑定)                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Layer 3: 协议绑定                         │
│   JSON-RPC Methods  │  gRPC RPCs  │  HTTP/REST Endpoints    │
│   (将抽象操作映射到具体的网络协议)                             │
└─────────────────────────────────────────────────────────────┘
```

这种分层方法确保了：核心语义在所有协议绑定中保持一致；可以添加新的协议绑定而无需改变基本数据模型；开发者可以独立于绑定细节来理解 A2A 操作。

---

## 4. 核心数据模型

A2A 的数据模型以 Protocol Buffers 为规范定义，所有协议绑定都必须提供功能等效的表示。

### 4.1. Task（任务）

Task 是 A2A 中最核心的概念，是工作的基本单元。

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 任务的唯一标识符（如 UUID），由服务器生成 |
| `contextId` | string | 否 | 上下文集合的唯一标识符，用于关联多个相关任务 |
| `status` | TaskStatus | 是 | 任务的当前状态，包含状态枚举和可选消息 |
| `artifacts` | Artifact[] | 否 | 任务生成的输出产物集合 |
| `history` | Message[] | 否 | 任务执行过程中的交互历史 |
| `metadata` | object | 否 | 自定义元数据键值对 |

### 4.2. Message（消息）

Message 是客户端和 Agent 之间的一个通信回合。

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| `messageId` | string | 是 | 消息的唯一标识符，由消息创建者生成 |
| `role` | Role | 是 | 消息发送方：`ROLE_USER`（客户端）或 `ROLE_AGENT`（服务端） |
| `parts` | Part[] | 是 | 消息内容的容器，可包含多个 Part |
| `contextId` | string | 否 | 关联的上下文 ID |
| `taskId` | string | 否 | 关联的任务 ID |
| `referenceTaskIds` | string[] | 否 | 此消息引用的相关任务 ID 列表 |
| `extensions` | string[] | 否 | 此消息使用的扩展 URI 列表 |

> **重要区分**：消息（Message）用于通信，而产物（Artifact）用于传递任务输出。"Messages SHOULD NOT be used to deliver task outputs. Results SHOULD BE returned using Artifacts associated with a Task." [1]

### 4.3. Part（内容部分）

Part 是 Message 或 Artifact 中的最小内容单元，采用 OneOf 模式，每个 Part 必须且只能包含以下之一：

| 类型 | 字段 | 说明 |
|---|---|---|
| 文本 | `text` | 字符串文本内容 |
| 原始字节 | `raw` | 文件的原始字节（JSON 中 base64 编码） |
| URL 引用 | `url` | 指向文件内容的 URL |
| 结构化数据 | `data` | 任意 JSON 值（对象、数组、字符串、数字等） |

此外，Part 还有 `metadata`、`filename`、`mediaType` 等可选字段。

### 4.4. Artifact（产物）

Artifact 代表任务的输出结果。

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| `artifactId` | string | 是 | 产物的唯一标识符（在任务内唯一） |
| `name` | string | 否 | 产物的人类可读名称 |
| `parts` | Part[] | 是 | 产物内容，至少包含一个 Part |
| `description` | string | 否 | 产物的描述 |
| `extensions` | string[] | 否 | 使用的扩展 URI 列表 |

### 4.5. 流式事件（Streaming Events）

在流式传输模式下，服务端会推送以下两种事件：

**TaskStatusUpdateEvent**：通知客户端任务状态变化。

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| `taskId` | string | 是 | 发生变化的任务 ID |
| `contextId` | string | 是 | 任务所属的上下文 ID |
| `status` | TaskStatus | 是 | 任务的新状态 |

**TaskArtifactUpdateEvent**：通知客户端有新的产物生成或产物块追加。

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| `taskId` | string | 是 | 任务 ID |
| `contextId` | string | 是 | 上下文 ID |
| `artifact` | Artifact | 是 | 生成或更新的产物 |
| `append` | boolean | 否 | 若为 true，表示此内容追加到同 ID 的先前产物 |
| `lastChunk` | boolean | 否 | 若为 true，表示这是产物的最后一个块 |

---

## 5. 任务状态机与生命周期

A2A 任务遵循严格的状态机，`TaskState` 定义了所有可能的状态 [1]：

```
                    ┌─────────────────┐
                    │   新建消息发送   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  TASK_STATE_    │
                    │   SUBMITTED     │  ← 已提交，等待处理
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  TASK_STATE_    │
                    │    WORKING      │  ← 处理中
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ INPUT_       │ │ AUTH_        │ │  COMPLETED   │ ← 终态
    │ REQUIRED     │ │ REQUIRED     │ │  FAILED      │ ← 终态
    │ (中断状态)   │ │ (中断状态)   │ │  CANCELED    │ ← 终态
    └──────┬───────┘ └──────┬───────┘ │  REJECTED    │ ← 终态
           │                │         └──────────────┘
           │ 客户端补充输入  │ 客户端提供凭证
           └────────────────┘
                   │
                   ▼
             (继续处理...)
```

| 状态 | 类型 | 说明 |
|---|---|---|
| `TASK_STATE_SUBMITTED` | 正常 | 任务已成功提交并确认 |
| `TASK_STATE_WORKING` | 正常 | 任务正在被 Agent 积极处理 |
| `TASK_STATE_COMPLETED` | **终态** | 任务已成功完成 |
| `TASK_STATE_FAILED` | **终态** | 任务以错误结束 |
| `TASK_STATE_CANCELED` | **终态** | 任务在完成前被取消 |
| `TASK_STATE_REJECTED` | **终态** | Agent 决定不执行该任务 |
| `TASK_STATE_INPUT_REQUIRED` | 中断 | Agent 需要额外的用户输入才能继续 |
| `TASK_STATE_AUTH_REQUIRED` | 中断 | 需要认证授权才能继续 |

终态任务不接受进一步的消息。中断状态的任务可以通过客户端发送带有相同 `taskId` 的新消息来恢复。

---

## 6. 核心操作

### 6.1. Send Message（发送消息）

这是启动 Agent 交互的主要操作。客户端发送消息，Agent 返回一个跟踪处理过程的 Task，或者针对简单交互直接返回 Message 响应。

**输入**：`SendMessageRequest`（包含 message、configuration、metadata）

**输出**：`Task` 或 `Message`

`SendMessageConfiguration` 中的关键配置项：

| 配置项 | 说明 |
|---|---|
| `returnImmediately` | 若为 true，服务器立即返回 `TASK_STATE_SUBMITTED` 状态的任务，不等待完成 |
| `acceptedOutputModes` | 客户端接受的输出媒体类型列表 |
| `historyLength` | 返回的历史消息最大数量 |
| `taskPushNotificationConfig` | 随请求一起设置的推送通知配置 |

### 6.2. Send Streaming Message（发送流式消息）

与 Send Message 类似，但建立流式连接以实时接收更新。流式响应遵循以下模式之一：

- **纯消息流**：若 Agent 返回 Message，流中只包含一个 Message 对象然后立即关闭。
- **任务生命周期流**：若 Agent 返回 Task，流以 Task 对象开始，随后是零个或多个 `TaskStatusUpdateEvent` 或 `TaskArtifactUpdateEvent`，当任务到达终态时流关闭。

### 6.3. Get Task（获取任务）

获取先前启动的任务的当前状态，通常用于轮询或在流结束/推送通知后获取最终状态。

### 6.4. List Tasks（列出任务）

获取任务列表，支持按 `contextId`、`status`、`statusTimestampAfter` 过滤，以及基于游标的分页（`pageToken`/`nextPageToken`）。任务按最后更新时间降序排列。

### 6.5. Cancel Task（取消任务）

请求取消正在进行的任务。取消不保证成功（任务可能已完成或处于不可取消的阶段）。

### 6.6. Subscribe to Task（订阅任务）

为**已存在**的任务建立流式连接以接收实时更新。流的第一个事件必须是当前任务状态的 Task 对象，以防止 `GetTask` 和 `SubscribeToTask` 之间的信息丢失。

### 6.7. Push Notification Config（推送通知配置）

管理任务的 Webhook 推送通知配置（创建、获取、列出、删除）。

### 6.8. Get Extended Agent Card（获取扩展 Agent Card）

在客户端认证后获取更详细的 Agent Card，可能包含公开 Card 中不存在的额外技能或配置信息。

---

## 7. 任务更新传递机制

A2A 提供了三种互补的机制，供客户端接收任务进度和完成情况的更新 [1]：

| 机制 | 操作 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| **轮询（Polling）** | Get Task | 实现简单，适用于所有绑定 | 延迟高，可能产生不必要的请求 | 简单集成、更新不频繁、客户端在防火墙后 |
| **流式传输（Streaming）** | Send Streaming Message / Subscribe to Task | 低延迟，实时更新 | 需要持久连接支持 | 交互式应用、实时仪表板、进度监控 |
| **推送通知（Push Notifications）** | 推送通知配置 CRUD | 无需持久连接，异步交付 | 客户端需可通过 HTTP 访问 | 服务器间集成、长时间运行任务、事件驱动架构 |

**推送通知的工作原理**：客户端注册 Webhook URL 后，当任务状态发生变化时，Agent 服务器会向该 URL 发送 HTTP POST 请求，payload 为 `StreamResponse` 格式的 JSON，并在 header 中携带 `X-A2A-Notification-Token` 用于验证。

---

## 8. Agent Card 与服务发现

### 8.1. Agent Card 结构

Agent Card 是 A2A 服务发现的基础，是一个 JSON 元数据文档，描述了 Agent 的身份、能力、技能和认证要求 [1]。

以下是一个完整的 Agent Card 示例：

```json
{
  "name": "GeoSpatial Route Planner Agent",
  "description": "Provides advanced route planning, traffic analysis, and custom map generation services.",
  "version": "1.2.0",
  "provider": {
    "organization": "Example Geo Services Inc.",
    "url": "https://www.examplegeoservices.com"
  },
  "supportedInterfaces": [
    {
      "url": "https://georoute-agent.example.com/a2a/v1",
      "protocolBinding": "JSONRPC",
      "protocolVersion": "1.0"
    },
    {
      "url": "https://georoute-agent.example.com/a2a/grpc",
      "protocolBinding": "GRPC",
      "protocolVersion": "1.0"
    },
    {
      "url": "https://georoute-agent.example.com/a2a/json",
      "protocolBinding": "HTTP+JSON",
      "protocolVersion": "1.0"
    }
  ],
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "extendedAgentCard": true
  },
  "securitySchemes": {
    "google": {
      "openIdConnectSecurityScheme": {
        "openIdConnectUrl": "https://accounts.google.com/.well-known/openid-configuration"
      }
    }
  },
  "security": [{ "google": ["openid", "profile", "email"] }],
  "defaultInputModes": ["application/json", "text/plain"],
  "defaultOutputModes": ["application/json", "image/png"],
  "skills": [
    {
      "id": "route-optimizer-traffic",
      "name": "Traffic-Aware Route Optimizer",
      "description": "Calculates the optimal driving route considering real-time traffic.",
      "tags": ["maps", "routing", "navigation", "traffic"],
      "examples": [
        "Plan a route from Mountain View to SFO avoiding tolls."
      ],
      "inputModes": ["application/json", "text/plain"],
      "outputModes": ["application/json", "text/html"]
    }
  ]
}
```

### 8.2. 服务发现机制

客户端可以通过以下方式找到 Agent Card [1]：

1. **Well-Known URI**：访问 `https://{server_domain}/.well-known/agent-card.json`（最常用）
2. **注册表/目录**：查询 Agent 的策划目录
3. **直接配置**：预配置的 Agent Card URL 或内容

### 8.3. 协议选择规则

客户端在获取 Agent Card 后，必须遵循以下规则选择协议 [1]：

- 解析 `supportedInterfaces` 列表，选择第一个本地支持的传输协议。
- `supportedInterfaces` 中越靠前的条目优先级越高（代表 Agent 的偏好）。
- 使用所选传输协议对应的 URL。
- 若 `AgentInterface` 中设置了 `tenant` 字段，客户端必须在所有请求消息的 `tenant` 字段中包含该值。

### 8.4. Agent Card 签名

Agent Card 可以使用 JSON Web Signature (JWS, RFC 7515) 进行数字签名，以确保真实性和完整性。签名前需使用 JSON Canonicalization Scheme (JCS, RFC 8785) 对 Card 进行规范化处理 [1]。

---

## 9. 认证与授权

A2A 将 Agent 视为标准的企业应用，依赖已建立的 Web 安全实践。身份信息在协议层处理，而非在 A2A 语义内处理 [1]。

### 9.1. 支持的安全方案

| 安全方案 | 说明 |
|---|---|
| `APIKeySecurityScheme` | API 密钥认证（通过 query、header 或 cookie 传递） |
| `HTTPAuthSecurityScheme` | HTTP 认证（如 Bearer Token） |
| `OAuth2SecurityScheme` | OAuth 2.0（支持 Authorization Code、Client Credentials、Device Code 等流程） |
| `OpenIdConnectSecurityScheme` | OpenID Connect |
| `MutualTlsSecurityScheme` | 双向 TLS 认证 |

### 9.2. 客户端认证流程

1. **发现要求**：客户端通过 Agent Card 的 `securitySchemes` 字段发现服务器要求的认证方案。
2. **凭证获取（带外）**：客户端通过特定于所需认证方案的带外流程获取必要凭证。
3. **凭证传输**：客户端在每个 A2A 请求的协议特定 header 或元数据中包含这些凭证。

### 9.3. 任务内授权（In-Task Authorization）

在执行任务过程中，Agent 可能需要授权才能执行某些操作（如调用外部 API、执行破坏性操作前需人工审批）。A2A 提供了 `TASK_STATE_AUTH_REQUIRED` 状态来处理这种情况 [1]：

- Agent 将任务状态转换为 `TASK_STATE_AUTH_REQUIRED`，并在状态消息中说明所需的授权。
- 客户端收到此状态后，需要通过带外方式或扩展协商的带内方式提供凭证。
- 如果客户端本身也是一个 A2A Agent，它可以进一步将授权请求委托给其自己的客户端，形成授权请求链。

---

## 10. 协议绑定

A2A 官方支持三种核心协议绑定，所有绑定在功能上等效 [1]。

### 10.1. 方法映射参考

| 功能 | JSON-RPC 方法 | gRPC 方法 | REST 端点 |
|---|---|---|---|
| 发送消息 | `SendMessage` | `SendMessage` | `POST /message:send` |
| 发送流式消息 | `SendStreamingMessage` | `SendStreamingMessage` | `POST /message:stream` |
| 获取任务 | `GetTask` | `GetTask` | `GET /tasks/{id}` |
| 列出任务 | `ListTasks` | `ListTasks` | `GET /tasks` |
| 取消任务 | `CancelTask` | `CancelTask` | `POST /tasks/{id}:cancel` |
| 订阅任务 | `SubscribeToTask` | `SubscribeToTask` | `POST /tasks/{id}:subscribe` |
| 创建推送配置 | `CreateTaskPushNotificationConfig` | 同左 | `POST /tasks/{id}/pushNotificationConfigs` |
| 获取扩展 Card | `GetExtendedAgentCard` | `GetExtendedAgentCard` | `GET /extendedAgentCard` |

### 10.2. JSON-RPC 绑定

- **协议**：JSON-RPC 2.0 over HTTP(S)
- **Content-Type**：`application/json`
- **流式传输**：Server-Sent Events (`text/event-stream`)
- **服务参数传递**：通过 HTTP 请求 header（如 `A2A-Version`、`A2A-Extensions`）

```json
// 请求示例
POST /rpc HTTP/1.1
Content-Type: application/json
A2A-Version: 1.0

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "SendMessage",
  "params": {
    "message": {
      "role": "ROLE_USER",
      "messageId": "msg-uuid",
      "parts": [{"text": "What is the weather today?"}]
    }
  }
}

// 响应示例
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "task": {
      "id": "task-uuid",
      "contextId": "context-uuid",
      "status": {"state": "TASK_STATE_COMPLETED"}
    }
  }
}
```

### 10.3. gRPC 绑定

- **协议**：gRPC over HTTP/2 with TLS
- **序列化**：Protocol Buffers v3
- **服务定义**：实现 `A2AService` gRPC 服务
- **服务参数传递**：通过 gRPC metadata（header）
- **流式传输**：原生 gRPC server streaming RPC

### 10.4. HTTP+JSON/REST 绑定

- **协议**：HTTP(S) with JSON payloads
- **Content-Type**：`application/a2a+json`
- **流式传输**：Server-Sent Events
- **服务参数传递**：通过 HTTP 请求 header

```
// 流式响应示例 (SSE)
HTTP/1.1 200 OK
Content-Type: text/event-stream

data: {"task": {"id": "task-uuid", "status": {"state": "TASK_STATE_WORKING"}}}

data: {"artifactUpdate": {"taskId": "task-uuid", "artifact": {"parts": [{"text": "# Report\n\n"}]}}}

data: {"statusUpdate": {"taskId": "task-uuid", "status": {"state": "TASK_STATE_COMPLETED"}}}
```

### 10.5. 版本协商

客户端必须在每个请求中发送 `A2A-Version` header（如 `A2A-Version: 1.0`）。服务器必须使用请求版本的语义处理请求，若不支持则返回 `VersionNotSupportedError` [1]。

---

## 11. 扩展机制

A2A 协议支持扩展，以提供超出核心规范的附加功能，同时保持向后兼容性 [1]。

Agent 在 Agent Card 的 `capabilities.extensions` 数组中声明支持的扩展：

```json
{
  "capabilities": {
    "extensions": [
      {
        "uri": "https://standards.org/extensions/citations/v1",
        "description": "Provides citation formatting and source verification",
        "required": false
      }
    ]
  }
}
```

客户端通过绑定特定机制（如 HTTP header `A2A-Extensions`）表明希望使用的扩展，并在 Message 的 `metadata` 字段中传递扩展特定的数据：

```json
// HTTP 请求 header
A2A-Extensions: https://example.com/extensions/geolocation/v1

// Message 中的扩展数据
{
  "message": {
    "extensions": ["https://example.com/extensions/geolocation/v1"],
    "metadata": {
      "https://example.com/extensions/geolocation/v1": {
        "latitude": 37.7749,
        "longitude": -122.4194
      }
    }
  }
}
```

---

## 12. Python SDK 实践：a2a-python

`a2a-python` SDK 提供了对 A2A 协议的完整 Python 实现，涵盖客户端和服务器端，并支持 JSON-RPC、HTTP+JSON 和 gRPC 三种传输层。

### 12.1. SDK 架构概览

```
a2a-python/
├── src/a2a/
│   ├── client/                    # 客户端实现
│   │   ├── client.py              # A2AClient 核心类
│   │   ├── client_factory.py      # 协议协商与客户端工厂
│   │   └── card_resolver.py       # Agent Card 解析与发现
│   ├── server/
│   │   ├── agent_execution/       # Agent 执行层
│   │   │   ├── agent_executor.py  # AgentExecutor 抽象接口
│   │   │   ├── active_task.py     # ActiveTask 生命周期管理
│   │   │   └── context.py         # RequestContext 请求上下文
│   │   ├── request_handlers/      # 请求处理层
│   │   │   └── default_request_handler_v2.py
│   │   ├── routes/                # 协议绑定路由层
│   │   │   ├── rest_dispatcher.py # HTTP+JSON 绑定
│   │   │   └── jsonrpc_dispatcher.py # JSON-RPC 绑定
│   │   └── tasks/                 # 任务状态管理层
│   │       ├── task_manager.py    # 任务状态归约与持久化
│   │       ├── task_updater.py    # Agent 发布更新的辅助类
│   │       └── inmemory_task_store.py
│   └── types/                     # Proto 生成的数据类型
│       └── a2a_pb2.pyi
└── samples/
    ├── hello_world_agent.py       # 完整服务端示例
    └── cli.py                     # 完整客户端示例
```

### 12.2. 服务端核心组件

**`AgentExecutor`（抽象接口）**

这是开发者需要实现的核心接口，只需实现 `execute` 和 `cancel` 两个方法：

```python
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue

class AgentExecutor(ABC):
    @abstractmethod
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """执行 Agent 逻辑，通过 event_queue 发布事件"""
        ...

    @abstractmethod
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """处理任务取消请求"""
        ...
```

**`RequestContext`（请求上下文）**

封装了当前请求的所有上下文信息：

```python
context.message          # 当前用户消息 (Message)
context.task_id          # 任务 ID（若为新任务则自动生成）
context.context_id       # 上下文 ID
context.current_task     # 当前任务对象（若为继续任务则已有值）
context.get_user_input() # 从消息 Parts 中提取纯文本输入
context.requested_extensions  # 客户端请求的扩展 URI 列表
```

**`TaskUpdater`（任务更新辅助类）**

简化了向 `EventQueue` 发送符合规范事件的过程：

```python
from a2a.server.tasks.task_updater import TaskUpdater

updater = TaskUpdater(
    event_queue=event_queue,
    task_id=task_id,
    context_id=context_id,
)

# 状态更新
await updater.start_work(message=updater.new_agent_message([Part(text='Processing...')]))
await updater.requires_input(message=updater.new_agent_message([Part(text='Please provide more details')]))
await updater.requires_auth(message=updater.new_agent_message([Part(text='Auth required')]))
await updater.complete()
await updater.failed()
await updater.cancel()

# 产物更新（支持流式分块）
await updater.add_artifact(
    parts=[Part(text='First chunk...')],
    artifact_id='report-001',
    name='report',
    append=False,    # 首块
    last_chunk=False
)
await updater.add_artifact(
    parts=[Part(text='...last chunk')],
    artifact_id='report-001',
    append=True,     # 追加
    last_chunk=True  # 最后一块
)
```

**`ActiveTask` 与 `EventConsumer`（内部核心）**

`ActiveTask` 是 SDK 服务端的核心执行引擎，采用生产者-消费者模式管理任务生命周期 [2]：

- **Producer**（`_run_producer`）：监听请求队列，调用 `AgentExecutor.execute()`，并将生命周期事件（`_RequestStarted`、`_RequestCompleted`）和异常放入内部事件队列。
- **Consumer**（`EventConsumer`）：消费内部事件队列，更新任务状态并持久化到 `TaskManager`，将相关更新传播给所有订阅者，并处理异常（将任务状态更新为 `TASK_STATE_FAILED`）。
- **Subscribers**（`subscribe()`）：通过 tap 队列机制，允许多个客户端并发订阅同一任务的事件流。

`EventConsumer` 严格执行 A2A 协议的事件流规则：

```python
# 来自 active_task.py 的关键验证逻辑
def _handle_message_event(self, event: Message) -> None:
    if self.task_mode is True:
        raise InvalidAgentResponseError(
            'Received Message object in task mode. '
            'Use TaskStatusUpdateEvent or TaskArtifactUpdateEvent instead.'
        )
    if self.task_mode is False:
        raise InvalidAgentResponseError('Multiple Message objects received.')
    self.task_mode = False  # 进入纯消息模式

async def _handle_task_event(self, event):
    if self.task_mode is False:
        raise InvalidAgentResponseError(
            f'Received {type(event).__name__} in message mode. '
            'Use Task with TaskStatusUpdateEvent and TaskArtifactUpdateEvent instead.'
        )
    self.task_mode = True  # 进入任务模式
```

**`DefaultRequestHandlerV2`（请求处理器）**

处理所有传入请求的核心类，协调 `AgentExecutor`、`TaskStore`、`PushNotificationSender` 等组件：

```python
# 来自 default_request_handler_v2.py 的 on_message_send 核心逻辑
async def on_message_send(self, params: SendMessageRequest, context: ServerCallContext) -> Message | Task:
    active_task, request_context = await self._setup_active_task(params, context)
    task_id = cast('str', request_context.task_id)
    result = None

    async for raw_event in active_task.subscribe(
        request=request_context,
        include_initial_task=False,
        replace_status_update_with_task=True,
    ):
        if isinstance(event, Task) and (
            params.configuration.return_immediately  # 非阻塞模式
            or event.status.state in (TERMINAL_TASK_STATES | INTERRUPTED_TASK_STATES)
        ):
            result = event
            break  # 立即返回，AgentExecutor 在后台继续运行

        if isinstance(event, Message):
            result = event
            # 不 break，等待流结束

    return apply_history_length(result, params.configuration)
```

### 12.3. 客户端核心组件

**`A2ACardResolver`（Agent Card 解析器）**

```python
from a2a.client import A2ACardResolver
import httpx

async with httpx.AsyncClient() as httpx_client:
    resolver = A2ACardResolver(httpx_client, base_url='http://127.0.0.1:41241')
    card = await resolver.get_agent_card()
    # card 是一个 AgentCard protobuf 对象
```

**`create_client`（客户端工厂）**

根据 Agent Card 中声明的 `supportedInterfaces` 和本地配置，自动选择最合适的传输层：

```python
from a2a.client import ClientConfig, create_client
import grpc

config = ClientConfig(
    grpc_channel_factory=grpc.aio.insecure_channel,
    # 可以指定偏好的传输协议
    # supported_protocol_bindings=['GRPC']  # 或 'JSONRPC', 'HTTP+JSON'
)

client = await create_client(card, client_config=config)
# client 会自动选择 gRPC、JSON-RPC 或 HTTP+JSON 传输层
```

**发送消息与处理流**

```python
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
import uuid

# 构建消息
message = Message(
    role=Role.ROLE_USER,
    message_id=str(uuid.uuid4()),
    parts=[Part(text='Hello, Agent!')],
    task_id=current_task_id,      # 继续已有任务时传入
    context_id=current_context_id,
)

request = SendMessageRequest(message=message)

# 发送并处理流式响应
async for event in client.send_message(request):
    if event.HasField('message'):
        # 直接消息响应（无任务模式）
        print('Direct reply:', event.message.parts[0].text)

    elif event.HasField('task'):
        # 任务创建事件
        current_task_id = event.task.id
        print(f'Task created: {event.task.id}')

    elif event.HasField('status_update'):
        state = TaskState.Name(event.status_update.status.state)
        print(f'Status: {state}')

    elif event.HasField('artifact_update'):
        print(f'Artifact: {event.artifact_update.artifact.name}')

# 也可以直接获取任务状态
from a2a.types import GetTaskRequest
task = await client.get_task(request=GetTaskRequest(id=task_id))
```

---

## 13. 完整示例：构建一个 Hello World Agent

以下是基于 `a2a-python` SDK 构建一个完整 A2A Agent 服务的示例，同时支持 JSON-RPC、HTTP+JSON 和 gRPC 三种传输协议。

### 13.1. 服务端实现

```python
# hello_world_agent.py
import asyncio
import logging
import grpc
import uvicorn
from fastapi import FastAPI

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler, GrpcHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCapabilities, AgentCard, AgentInterface,
    AgentProvider, AgentSkill, Part, Task,
    TaskState, TaskStatus, a2a_pb2_grpc,
)


class HelloWorldAgentExecutor(AgentExecutor):
    """实现 AgentExecutor 接口，包含核心 Agent 逻辑"""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id
        context_id = context.context_id

        # Step 1: 发布初始 Task 事件（SUBMITTED 状态）
        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                history=[context.message],  # 将用户消息加入历史
            )
        )

        # Step 2: 使用 TaskUpdater 简化后续状态更新
        updater = TaskUpdater(event_queue, task_id, context_id)

        # 更新为 WORKING 状态
        await updater.start_work(
            message=updater.new_agent_message([Part(text='Processing your request...')])
        )

        # Step 3: 执行 Agent 逻辑
        user_input = context.get_user_input()
        reply = f"Hello! You said: '{user_input}'"

        # Step 4: 发布 Artifact（任务输出）
        await updater.add_artifact(
            parts=[Part(text=reply)],
            name='response',
            last_chunk=True,
        )

        # Step 5: 标记任务完成
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id or '', context.context_id or '')
        await updater.cancel()


async def serve(host: str = '127.0.0.1', port: int = 41241, grpc_port: int = 50051):
    # 定义 Agent Card
    agent_card = AgentCard(
        name='Hello World Agent',
        description='A simple hello world agent.',
        provider=AgentProvider(organization='Example', url='https://example.com'),
        version='1.0.0',
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=['text/plain'],
        default_output_modes=['text/plain'],
        skills=[
            AgentSkill(
                id='hello',
                name='Hello World',
                description='Greets the user.',
                tags=['greeting'],
                examples=['Hello!'],
            )
        ],
        supported_interfaces=[
            AgentInterface(protocol_binding='GRPC', protocol_version='1.0', url=f'{host}:{grpc_port}'),
            AgentInterface(protocol_binding='JSONRPC', protocol_version='1.0', url=f'http://{host}:{port}/a2a/jsonrpc'),
            AgentInterface(protocol_binding='HTTP+JSON', protocol_version='1.0', url=f'http://{host}:{port}/a2a/rest'),
        ],
    )

    # 组装服务端组件
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=HelloWorldAgentExecutor(),
        task_store=task_store,
        agent_card=agent_card,
    )

    # 创建 FastAPI 应用并挂载 A2A 路由
    app = FastAPI()
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card=agent_card),
        jsonrpc_routes=create_jsonrpc_routes(request_handler=request_handler, rpc_url='/a2a/jsonrpc'),
        rest_routes=create_rest_routes(request_handler=request_handler, path_prefix='/a2a/rest'),
    )

    # 启动 gRPC 服务器
    grpc_server = grpc.aio.server()
    grpc_server.add_insecure_port(f'{host}:{grpc_port}')
    a2a_pb2_grpc.add_A2AServiceServicer_to_server(GrpcHandler(request_handler), grpc_server)

    # 并发启动 HTTP 和 gRPC 服务器
    await asyncio.gather(
        grpc_server.start(),
        uvicorn.Server(uvicorn.Config(app, host=host, port=port)).serve(),
    )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
```

### 13.2. 客户端实现

```python
# client_example.py
import asyncio
import uuid
import httpx
import grpc

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState


async def main():
    agent_url = 'http://127.0.0.1:41241'

    # Step 1: 发现 Agent Card
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(httpx_client, agent_url)
        card = await resolver.get_agent_card()
        print(f'Connected to: {card.name}')

    # Step 2: 创建客户端（自动选择传输层）
    config = ClientConfig(grpc_channel_factory=grpc.aio.insecure_channel)
    client = await create_client(card, client_config=config)

    # Step 3: 发送消息
    context_id = str(uuid.uuid4())
    current_task_id = None

    message = Message(
        role=Role.ROLE_USER,
        message_id=str(uuid.uuid4()),
        parts=[Part(text='Hello, World!')],
        context_id=context_id,
    )

    # Step 4: 处理流式响应
    async for event in client.send_message(SendMessageRequest(message=message)):
        if event.HasField('task'):
            current_task_id = event.task.id
            print(f'Task created: {current_task_id}')

        elif event.HasField('status_update'):
            state = TaskState.Name(event.status_update.status.state)
            print(f'Status: {state}')
            if event.status_update.status.HasField('message'):
                text = event.status_update.status.message.parts[0].text
                print(f'  Message: {text}')

        elif event.HasField('artifact_update'):
            artifact = event.artifact_update.artifact
            print(f'Artifact [{artifact.name}]: {artifact.parts[0].text}')

    await client.close()


if __name__ == '__main__':
    asyncio.run(main())
```

---

## 14. 常见工作流与交互模式

### 14.1. 基础任务执行（阻塞模式）

```
客户端                              Agent 服务器
  │                                      │
  │── POST /message:send ──────────────>│
  │   {"message": {"role": "ROLE_USER", │
  │    "parts": [{"text": "..."}]}}      │
  │                                      │── 执行 Agent 逻辑
  │                                      │
  │<── {"task": {"id": "task-uuid",     │
  │     "status": {"state":             │
  │      "TASK_STATE_COMPLETED"},        │
  │     "artifacts": [...]}} ───────────│
```

### 14.2. 流式任务执行

```
客户端                              Agent 服务器
  │                                      │
  │── POST /message:stream ────────────>│
  │                                      │
  │<── data: {"task": {..., "status":   │
  │     {"state": "TASK_STATE_WORKING"}}}│
  │                                      │
  │<── data: {"artifactUpdate":         │
  │     {"artifact": {"parts": [        │
  │      {"text": "First chunk..."}]}}} │
  │                                      │
  │<── data: {"statusUpdate":           │
  │     {"status": {"state":            │
  │      "TASK_STATE_COMPLETED"}}} ─────│
  │                                      │
  │  (SSE 流关闭)                        │
```

### 14.3. 多轮交互（Input Required）

```
客户端                              Agent 服务器
  │                                      │
  │── POST /message:send ──────────────>│
  │   {"message": {"parts":             │
  │    [{"text": "Book me a flight"}]}} │
  │                                      │
  │<── {"task": {"id": "task-uuid",     │
  │     "status": {                     │
  │      "state": "TASK_STATE_INPUT_    │
  │       REQUIRED",                    │
  │      "message": {"parts": [{"text": │
  │       "Where to fly from/to?"}]}}}} │
  │                                      │
  │── POST /message:send ──────────────>│
  │   {"message": {                     │
  │    "taskId": "task-uuid",           │  ← 带上 taskId 继续任务
  │    "parts": [{"text": "SFO to JFK"}]}}
  │                                      │
  │<── {"task": {"status":              │
  │     {"state": "TASK_STATE_COMPLETED"}}}
```

### 14.4. 推送通知工作流

```
客户端                              Agent 服务器
  │                                      │
  │── POST /message:send ──────────────>│
  │   {"configuration":                 │
  │    {"returnImmediately": true,      │  ← 立即返回，不等待完成
  │     "taskPushNotificationConfig":   │
  │     {"url": "https://client/hook"}}}│
  │                                      │
  │<── {"task": {"status":             │
  │     {"state": "TASK_STATE_SUBMITTED"}}}
  │                                      │
  │  (稍后，Agent 完成任务)               │
  │                                      │
  │<── POST https://client/hook ────────│  ← Agent 主动推送
  │    {"statusUpdate": {"status":      │
  │     {"state": "TASK_STATE_COMPLETED"}}}
```

---

## 15. 错误处理

A2A 定义了一套标准的错误类型，并在各协议绑定中有对应的错误码映射 [1]：

| A2A 错误类型 | JSON-RPC 错误码 | gRPC 状态码 | HTTP 状态码 | 说明 |
|---|---|---|---|---|
| `TaskNotFoundError` | -32001 | NOT_FOUND | 404 | 任务 ID 不存在或不可访问 |
| `TaskNotCancelableError` | -32002 | FAILED_PRECONDITION | 400 | 任务不处于可取消状态 |
| `PushNotificationNotSupportedError` | -32003 | FAILED_PRECONDITION | 400 | Agent 不支持推送通知 |
| `UnsupportedOperationError` | -32004 | FAILED_PRECONDITION | 400 | 操作不被支持（如对终态任务发送消息） |
| `ContentTypeNotSupportedError` | -32005 | INVALID_ARGUMENT | 400 | 不支持的媒体类型 |
| `InvalidAgentResponseError` | -32006 | INTERNAL | 500 | Agent 响应格式无效 |
| `ExtendedAgentCardNotConfiguredError` | -32007 | FAILED_PRECONDITION | 400 | 未配置扩展 Agent Card |
| `VersionNotSupportedError` | -32009 | FAILED_PRECONDITION | 400 | 不支持的协议版本 |

**HTTP+JSON 错误响应示例**：

```json
HTTP/1.1 404 Not Found
Content-Type: application/a2a+json

{
  "error": {
    "code": 404,
    "status": "NOT_FOUND",
    "message": "The specified task ID does not exist or is not accessible",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "TASK_NOT_FOUND",
        "domain": "a2a-protocol.org",
        "metadata": {
          "taskId": "task-123"
        }
      }
    ]
  }
}
```

**JSON-RPC 错误响应示例**：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32001,
    "message": "Task not found",
    "data": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "TASK_NOT_FOUND",
        "domain": "a2a-protocol.org"
      }
    ]
  }
}
```

---

## 16. 参考资料

[1] A2A Protocol Specification v1.0.0. https://a2a-protocol.org/latest/specification/

[2] a2a-python SDK — active_task.py 源码注释. https://github.com/a2aproject/a2a-python/blob/main/src/a2a/server/agent_execution/active_task.py

[3] What is A2A? — A2A Protocol Official Documentation. https://a2a-protocol.org/latest/topics/what-is-a2a/

[4] LiteLLM A2A Documentation. https://docs.litellm.com.cn/docs/a2a

[5] ADK A2A Introduction. https://adk.dev/a2a/intro/

[6] a2a-python SDK — hello_world_agent.py 示例. https://github.com/a2aproject/a2a-python/blob/main/samples/hello_world_agent.py

[7] a2a-python SDK — cli.py 客户端示例. https://github.com/a2aproject/a2a-python/blob/main/samples/cli.py
