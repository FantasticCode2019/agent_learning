# SGLang：高性能结构化大语言模型推理框架详细指南

SGLang (Structured Generation Language) 是由 LMSYS 组织（由 UC Berkeley、Stanford 等高校成员组成）开源的一个高性能的大语言模型（LLM）和多模态模型（VLM）推理和服务框架。它专为生产级服务设计，旨在提供低延迟和高吞吐量的推理能力，支持从单 GPU 到大规模分布式集群的多种硬件配置 [1]。

本文将详细介绍 SGLang 的推理原理、技术架构、使用方法、启动参数以及相关的监控和推理 API。

---

## 1. 核心推理原理与技术架构

SGLang 并非仅仅是一个推理引擎，它创新性地将前端编程语言（DSL）和后端运行时系统（Runtime）进行了协同设计，以解决现代复杂 LLM 工作流中的低效问题 [2]。

### 1.1 RadixAttention：自动 KV Cache 复用
在复杂的 LLM 应用（如 Agent 多轮对话、Tree-of-Thought 推理、Few-shot 提示）中，经常会出现多个请求共享相同前缀的情况。传统的推理引擎在每个请求结束后会丢弃 KV Cache，导致重复计算。

SGLang 提出了 **RadixAttention** 技术。它将提示词和生成结果的 KV Cache 作为一个整体资源，存储在一个**基数树（Radix Tree）**数据结构中。
- **自动匹配与复用**：当新请求到达时，系统自动在基数树中进行前缀匹配。如果找到匹配的前缀，直接复用其 KV Cache，无需重复计算。
- **LRU 驱逐策略**：当 GPU 显存达到上限时，系统采用最近最少使用（LRU）策略递归地驱逐叶子节点。
- **缓存感知调度（Cache-Aware Scheduling）**：在分布式部署中，SGLang 的路由器（sgl-router）能够预测各 Worker 上的 KV Cache 命中率，并将请求智能路由到命中率最高的节点，从而大幅提升吞吐量 [3]。

### 1.2 零开销批处理调度（Zero-Overhead Batch Scheduler）
LLM 推理虽然在 GPU 上运行，但 CPU 同样需要处理批处理调度、内存分配和前缀匹配等任务，这可能带来显著的开销。
SGLang v0.4 引入了**零开销调度器**，通过重叠 CPU 调度和 GPU 计算，使得调度器提前一个批次运行并准备元数据。这确保了 GPU 始终保持忙碌状态，隐藏了 CPU 的调度开销，使吞吐量提升了 1.1 倍 [3]。

### 1.3 压缩有限状态机（Compressed Finite State Machine）与结构化解码
对于需要输出特定格式（如 JSON）的任务，传统的系统通常通过在每一步解码时屏蔽非法 Token 的概率来实现，这导致每次只能解码一个 Token。
SGLang 分析约束的有限状态机（FSM），将多 Token 路径压缩为单步路径。当只有唯一合法路径时，可以在一次前向传播中解码多个 Token，这使得 JSON 解码速度最高可提升 10 倍（结合 xgrammar 后端）[3] [4]。

### 1.4 DeepSeek 模型的 DP Attention
针对 DeepSeek 模型（使用 MLA 架构，只有一个 KV 头），传统的张量并行（TP）会导致 KV Cache 冗余和内存浪费。SGLang 实现了数据并行（DP）注意力机制，显著减少了 KV Cache 占用，支持更大的 Batch Size，使 DeepSeek 模型的解码吞吐量提升了 1.9 倍 [3]。

---

## 2. 安装与使用方法

### 2.1 安装 SGLang
SGLang 支持通过 pip 安装。建议在干净的虚拟环境或 Conda 环境中进行：

```bash
# 安装最新版 SGLang
pip install -U sglang

# 验证安装
python -c "import sglang; print('SGLang import OK')"
```

### 2.2 启动服务器
SGLang 提供了一个与 OpenAI 兼容的 HTTP 服务器。最简单的启动方式如下：

```bash
python3 -m sglang.launch_server \
  --model-path qwen/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 \
  --port 30000
```

### 2.3 发送请求
启动服务器后，您可以使用 OpenAI 的 Python 客户端或标准的 HTTP 客户端进行调用：

**使用 OpenAI Python 客户端：**
```python
import openai

client = openai.Client(
    base_url="http://127.0.0.1:30000/v1",
    api_key="EMPTY"
)

response = client.chat.completions.create(
    model="qwen/Qwen2.5-7B-Instruct",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain RadixAttention in SGLang."}
    ],
    temperature=0.7,
    max_tokens=256,
)

print(response.choices[0].message.content)
```

---

## 3. 常用服务器启动参数设置

SGLang 提供了丰富的启动参数以优化不同场景下的性能。以下是核心参数说明 [5]：

### 基础模型与网络配置
| 参数 | 说明 |
|------|------|
| `--model-path` | 模型在本地的路径或 HuggingFace 模型 ID。 |
| `--host` | 绑定的主机地址（默认：`127.0.0.1`）。 |
| `--port` | 绑定的端口号（默认：`30000`）。 |
| `--api-key` | 设置 API 访问密钥。 |

### 并行与硬件调度
| 参数 | 说明 |
|------|------|
| `--tp-size` | 张量并行（Tensor Parallelism）的 GPU 数量（默认：`1`）。 |
| `--dp-size` | 数据并行（Data Parallelism）的 GPU 数量（默认：`1`）。配合 `sgl-router` 使用可实现多节点负载均衡。 |
| `--device` | 运行设备，支持 `cuda`, `xpu`, `npu`, `cpu` 等。未指定时自动检测。 |

### 内存与调度优化
| 参数 | 说明 |
|------|------|
| `--mem-fraction-static` | 用于静态分配（模型权重和 KV Cache 池）的显存比例。若出现 OOM，可适当调小（如 `0.8`）。 |
| `--chunked-prefill-size` | Chunked Prefill 的 Chunk 大小。设为 `-1` 则禁用。 |
| `--max-running-requests` | 服务器同时处理的最大并发请求数。 |
| `--disable-radix-cache` | 禁用 RadixAttention KV Cache 复用（通常不建议禁用）。 |
| `--schedule-policy` | 请求调度策略，默认为 `fcfs`（先到先得）。 |

### 高级优化与功能
| 参数 | 说明 |
|------|------|
| `--grammar-backend` | 结构化生成的后端。建议使用 `--grammar-backend xgrammar` 获得极致的 JSON 解码速度。 |
| `--enable-dp-attention` | 针对 DeepSeek MLA 架构模型，开启数据并行 Attention 以节省显存。 |
| `--enable-metrics` | 开启 Prometheus 监控指标导出。 |
| `--quantization` | 权重加载时的量化方式，如 `fp8`, `awq`, `gptq` 等。 |

---

## 4. API 含义与监控介绍

SGLang 完全兼容 OpenAI 的 API 规范，同时提供了丰富的内部状态和监控接口 [6] [7]。

### 4.1 核心推理 API (OpenAI 兼容)
- `POST /v1/chat/completions`：聊天补全接口，支持多轮对话、流式输出（`stream: true`）、JSON Schema 结构化输出等。
- `POST /v1/completions`：标准文本续写接口。
- `POST /v1/embeddings`：文本向量化接口（当加载 Embedding 模型时）。
- `GET /v1/models`：列出当前服务器加载的所有模型及 LoRA 适配器。

**SGLang 独有扩展参数（在 `/v1/chat/completions` 中使用）：**
- `regex`：在 `extra_body` 中传入正则表达式，强制模型输出匹配该正则的内容。
- `return_cached_tokens_details`：在 `extra_body` 中设为 `True`，可在返回的 `usage` 中查看 KV Cache 命中统计。

### 4.2 服务器监控与检测 API
这些 API 用于监控 SGLang 的运行状态、健康度以及底层硬件负载：

- **`GET /health`**：
  健康检查端点。返回 `200 OK` 表示服务器正常运行。该端点通过实际在后台生成一个极小的 Token 任务来验证引擎是否真正可用，而非仅仅检查 HTTP 进程。
  
- **`GET /model_info`**：
  获取当前加载模型的详细配置信息，包括模型路径、是否支持视觉/音频、最大上下文长度等。

- **`GET /server_info`**：
  获取服务器的全局配置参数和每个数据并行（DP）Worker 的内部状态，包括调度器状态、版本号等。

- **`GET /v1/loads`** (替代已废弃的 `/get_load`)：
  获取实时的负载指标。返回包含正在运行的请求数、排队请求数、已使用的 Token 数和待处理的 Token 数。非常适合用于自动扩缩容（Auto-scaling）决策。

- **`GET /metrics`** (需启动时加 `--enable-metrics`)：
  导出标准的 Prometheus 监控指标。SGLang 导出了极其详细的性能数据，包括：
  - 首字延迟（TTFT）与字间延迟（TPOT）直方图。
  - KV Cache 命中率和内存池使用率。
  - Token 生成吞吐量。
  - 投机解码（Speculative Decoding）的接受率统计。

  官方在 GitHub 的 `examples/monitoring` 目录下提供了完整的 Grafana Dashboard 模板，可直接导入以实现可视化监控。

---

## 参考文献
[1] SGLang Documentation: Welcome to SGLang. https://sgl-project.github.io/
[2] SGLang: Efficient Execution of Structured Language Model Programs. https://arxiv.org/abs/2312.07104
[3] SGLang v0.4: Zero-Overhead Batch Scheduler, Cache-Aware Load Balancer, Faster Structured Outputs. https://lmsys.org/blog/2024-12-04-sglang-v0-4/
[4] Fast and Expressive LLM Inference with RadixAttention and SGLang. https://lmsys.org/blog/2024-01-17-sglang/
[5] SGLang Server Arguments Source Code. https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/server_args.py
[6] SGLang OpenAI Compatible API Documentation. https://sgl-project-sglang-93.mintlify.app/backend/openai-compatible-api
[7] SGLang HTTP Server Source Code. https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/entrypoints/http_server.py
