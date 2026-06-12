# vLLM 核心原理与使用指南

vLLM 是一个由加州大学伯克利分校 Sky Computing Lab 开发的高吞吐量、高内存利用率的大语言模型（LLM）推理和在线服务引擎 [1]。它支持众多开源模型，以卓越的推理速度、PagedAttention 内存管理技术和与 OpenAI API 协议的无缝兼容性而闻名。

本文将详细介绍 vLLM 的推理原理、使用方式、启动方法、常用参数配置以及监控 API。

## 1. 核心推理原理

vLLM 之所以能在 LLM 推理领域取得显著的性能提升，主要归功于其底层创新的架构和内存管理机制，其中最核心的即为 **PagedAttention** 和 **Continuous Batching（连续批处理）**。

### 1.1 PagedAttention 机制

在传统的 LLM 推理中，自回归生成的每个 token 都依赖于前面所有 token 的注意力键和值（Key 和 Value，简称 KV cache）。传统的内存管理通常为每个请求预先分配一块连续的 GPU 显存用于存放 KV cache。由于生成的序列长度不可预测，这种方式会导致严重的内存碎片化和浪费，显存利用率通常只有 20% 到 40% [1]。

**PagedAttention** 的灵感来源于操作系统的虚拟内存和分页技术 [2]：
* **分页存储**：它将连续的 KV cache 划分为固定大小的“块（Blocks）”，每个块可以包含一定数量 token 的 KV cache。
* **按需分配**：在生成过程中，KV cache 块并不需要在物理显存中连续存放。通过一个类似页表的映射机制（Block Table），逻辑上连续的 token KV cache 可以被映射到物理显存中不连续的块中。
* **消除碎片**：这种方式彻底消除了外部内存碎片，将内存浪费降低到 4% 以下。由于显存利用率大幅提高，vLLM 可以在同一个 batch 中容纳更多的请求，从而极大提升了系统的吞吐量 [2]。
* **内存共享**：PagedAttention 还天然支持内存共享。对于具有相同前缀（Prompt）的请求（如并行采样、束搜索等），它们可以共享同一份物理 KV cache 块，进一步节省内存并提升速度。

### 1.2 连续批处理（Continuous Batching）

传统的静态批处理（Static Batching）要求一个 batch 中的所有请求同时开始和结束。由于不同请求的生成长度不同，较早结束的请求必须等待较晚结束的请求，导致 GPU 计算资源的严重浪费 [3]。

vLLM 采用了**迭代级别的调度（Iteration-level scheduling）**或称为**连续批处理（Continuous Batching）** [3]：
* 系统在每次生成一个 token（即一个 iteration）后，都会检查并剔除已经完成的请求。
* 随后，系统会立即将等待队列中的新请求加入到当前 batch 中，充分利用 GPU 的计算能力。
* 这种细粒度的调度策略使得 GPU 始终保持高负载状态，避免了因请求长度不一导致的计算资源闲置。

## 2. 架构概览

vLLM V1 采用了多进程架构，以分离关注点并最大化吞吐量 [4]。其核心进程包括：
* **API Server 进程**：处理 HTTP 请求（例如兼容 OpenAI 的 API），执行输入处理（如 Tokenization），并将结果流式返回给客户端。
* **Engine Core 进程**：运行调度器，管理 KV cache，并协调 GPU Worker 上的模型执行。每个数据并行（DP）节点有一个 Engine Core 进程。
* **GPU Worker 进程**：负责加载模型权重、执行前向传播和管理 GPU 显存。每个 GPU 对应一个 Worker 进程。

## 3. 安装与使用方式

### 3.1 安装 vLLM

vLLM 支持 NVIDIA CUDA、AMD ROCm、Intel XPU 和 Apple Silicon (vLLM-Metal) 等多种硬件平台 [5]。最推荐的安装方式是使用 `pip` 或 `uv` 在全新的 Python 环境中进行安装：

```bash
# 推荐使用 uv 创建环境
uv venv --python 3.12 --seed --managed-python
source .venv/bin/activate

# 使用 pip 安装 vLLM（默认编译支持 CUDA 12.1 及以上）
pip install vllm
```

如果希望使用 Docker 部署，vLLM 官方提供了镜像 `vllm/vllm-openai`：
```bash
docker run --runtime nvidia --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -p 8000:8000 \
    --ipc=host \
    vllm/vllm-openai:latest \
    --model Qwen/Qwen2.5-7B-Instruct
```

### 3.2 离线批量推理 (Offline Inference)

对于不需要在线服务的批量处理任务，可以直接使用 Python API 中的 `LLM` 类：

```python
from vllm import LLM, SamplingParams

# 定义输入提示词
prompts = [
    "Hello, my name is",
    "The capital of France is",
]

# 定义采样参数
sampling_params = SamplingParams(temperature=0.8, top_p=0.95, max_tokens=100)

# 初始化 LLM 引擎
llm = LLM(model="Qwen/Qwen2.5-7B-Instruct", tensor_parallel_size=1)

# 生成输出
outputs = llm.generate(prompts, sampling_params)

for output in outputs:
    prompt = output.prompt
    generated_text = output.outputs[0].text
    print(f"Prompt: {prompt!r}, Generated text: {generated_text!r}")
```

### 3.3 在线服务 (Online Serving)

vLLM 提供了一个与 OpenAI API 完全兼容的 HTTP 服务器。你可以将其作为 OpenAI API 的直接替代品。

**启动服务命令：**
```bash
vllm serve Qwen/Qwen2.5-7B-Instruct --host 0.0.0.0 --port 8000 --tensor-parallel-size 1
```

启动后，你可以使用与 OpenAI 相同的客户端或 curl 命令发起请求：
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [
      {"role": "user", "content": "请介绍一下量子力学。"}
    ]
  }'
```

## 4. 常用参数设置

vLLM 提供了丰富的参数用于控制引擎行为、模型加载、并行策略和生成采样 [6] [7]。

### 4.1 引擎与启动参数 (Engine & Serve Args)

启动 `vllm serve` 时，常用的核心参数包括：

| 参数名称 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `--model` | Hugging Face 模型名称或本地路径。 | 无 |
| `--host` | API 服务器绑定的主机地址。 | `0.0.0.0` |
| `--port` | API 服务器绑定的端口号。 | `8000` |
| `--tensor-parallel-size` (`-tp`) | 张量并行大小，即使用的 GPU 数量。对于大模型，可设置为 2, 4, 8 等以切分模型权重。 | `1` |
| `--gpu-memory-utilization` | vLLM 实例占用的 GPU 显存比例。0.92 表示占用 92% 的显存。如果多实例共用 GPU，需调低此值。 | `0.92` |
| `--max-model-len` | 模型的最大上下文长度（Prompt + Output）。如果不指定，将自动从模型配置中推导。如果显存不足，可以手动将其调小（如 `8192`）。 | `auto` |
| `--quantization` (`-q`) | 权重加载的量化方法，如 `awq`, `gptq`, `fp8` 等。如果不指定，将自动根据模型配置判断。 | `None` |
| `--dtype` | 模型权重和激活的数据类型，可选 `auto`, `half` (FP16), `bfloat16`, `float`。 | `auto` |
| `--enforce-eager` | 是否强制使用 eager 模式。默认 False 时，vLLM 会编译 CUDA Graphs 以提升小 batch 的性能；开启可节省显存但可能降低速度。 | `False` |
| `--enable-prefix-caching` | 是否开启自动前缀缓存（Automatic Prefix Caching）。开启后，系统会缓存并复用相同前缀的 KV cache，非常适合多轮对话和长文档问答场景。 | `False` |
| `--trust-remote-code` | 下载和加载模型时是否信任 Hugging Face 上的远程代码。 | `False` |
| `--api-key` | 为 API 服务设置访问密钥，客户端请求需在 Header 中携带此 Key。 | 无 |

### 4.2 采样参数 (SamplingParams)

在生成文本时，可以通过 `SamplingParams`（或 API 请求中的对应字段）控制生成行为 [7]：

* `temperature`: 控制采样的随机性。值越低（接近 0），输出越确定（贪婪采样）；值越高，输出越随机。默认 `1.0`。
* `top_p`: 控制累计概率采样（Nucleus Sampling）。取值 `(0, 1]`。例如 `0.9` 表示只从累计概率达到 90% 的候选 token 中采样。
* `top_k`: 整数，控制仅从概率最高的 K 个 token 中采样。设置为 `-1` 表示考虑所有 token。
* `max_tokens`: 每条序列生成的最大 token 数量。默认 `16`。
* `stop`: 字符串或字符串列表，当生成这些字符串时立即停止生成。
* `presence_penalty` / `frequency_penalty`: 惩罚因子，用于减少重复词的生成。

## 5. 监控 API 与 Metrics 含义

vLLM 提供了一个 `/metrics` 端点（默认 `http://localhost:8000/metrics`），以 Prometheus 格式暴露系统的实时运行状态和健康指标 [8]。这对于生产环境中的容量规划和告警至关重要。

常用的监控指标包括：

### 5.1 队列与请求状态 (Gauges)
* `vllm:num_requests_running`: 当前正在 GPU 上执行（处于模型前向传播批处理中）的请求数量。
* `vllm:num_requests_waiting`: 当前在等待队列中、尚未开始处理的请求数量。如果此值持续大于 0，说明系统负载已满，可能需要扩容。
* `vllm:kv_cache_usage_perc`: KV Cache 的使用百分比（0.0 到 1.0）。接近 1.0 表示显存中的 KV Cache 块已满。

### 5.2 吞吐量与 Token 统计 (Counters)
* `vllm:prompt_tokens`: 系统处理的 Prefill（输入提示词）Token 总数。
* `vllm:generation_tokens`: 系统生成的 Output Token 总数。
* `vllm:request_success`: 成功处理完毕的请求总数。
* `vllm:prefix_cache_hits` / `vllm:prefix_cache_queries`: 前缀缓存的命中次数和查询次数，用于监控开启 Prefix Caching 后的缓存效率。

### 5.3 延迟与耗时 (Histograms)
* `vllm:time_to_first_token_seconds` (TTFT): 首字延迟，即从收到请求到生成第一个 Token 所花费的时间。主要反映 Prefill 阶段的计算耗时和排队时间。
* `vllm:inter_token_latency_seconds` (ITL): 词间延迟，即生成每个后续 Token 之间的平均时间间隔。主要反映 Decode 阶段的推理速度。
* `vllm:e2e_request_latency_seconds`: 端到端请求延迟，即从收到请求到完全生成结束的总时间。

---

## References

[1] vLLM Documentation: Welcome to vLLM. https://docs.vllm.ai/en/latest/
[2] vLLM Blog: vLLM: Easy, Fast, and Cheap LLM Serving with PagedAttention. https://blog.vllm.ai/2023/06/20/vllm.html
[3] Anyscale Blog: How continuous batching enables 23x throughput in LLM inference. https://www.anyscale.com/blog/continuous-batching-llm-inference
[4] vLLM Documentation: Architecture Overview. https://docs.vllm.ai/en/latest/design/arch_overview/
[5] vLLM Documentation: Installation. https://docs.vllm.ai/en/stable/getting_started/installation/gpu/
[6] vLLM Documentation: vllm serve CLI Reference. https://docs.vllm.ai/en/stable/cli/serve/
[7] vLLM Documentation: Sampling Parameters. https://docs.vllm.ai/en/v0.6.4/dev/sampling_params.html
[8] vLLM Documentation: Production Metrics. https://docs.vllm.ai/en/stable/usage/metrics/
