## 摘要

vLLM、Ollama 与 llama.cpp 都常被用于大语言模型推理，但它们解决的问题层级并不完全相同。**vLLM** 更接近面向生产服务的高吞吐 GPU 推理引擎，核心优势在于 PagedAttention、连续批处理、KV Cache 高效管理和 OpenAI 兼容服务接口。**Ollama** 更接近本地模型运行、模型分发和应用集成平台，它通过简单 CLI、REST API、Modelfile、模型仓库和运行时调度降低本地 LLM 使用门槛。**llama.cpp** 则是底层 C/C++ 推理运行时和 GGUF/量化生态的核心项目，强调轻量、跨平台、低依赖、CPU/GPU 混合推理和极广硬件覆盖。

> vLLM 官方博客将其定位为“fast LLM inference and serving”开源库，并指出其核心是 **PagedAttention**，用于高效管理 attention keys and values，即 KV Cache。[1]

从工程选型看，如果目标是多用户、高并发、GPU 集群或线上 API 服务，vLLM 通常是首选；如果目标是个人电脑、工作站或小团队快速运行开源模型并接入桌面应用、聊天 UI、IDE 插件或 RAG 工具，Ollama 的体验最好；如果目标是嵌入式、本地低资源、移动端、边缘设备、量化实验或对底层推理参数有强控制需求，llama.cpp 更合适。三者并非严格替代关系，Ollama 的 README 明确列出其支持的后端包括 llama.cpp，因此 Ollama 在相当多场景中可以视为对 llama.cpp 等后端的上层封装。[6]

## 一、三者定位概览

三类工具最容易混淆的原因在于它们都能“跑模型”，但实际关注点不同。vLLM 的目标是将 LLM 作为在线服务高效提供，重点解决 GPU 显存利用率、调度与吞吐问题；Ollama 的目标是让用户用极少命令完成模型下载、运行、管理、定制和 API 调用；llama.cpp 的目标是用 C/C++ 在尽可能多的硬件上以低依赖方式运行 LLM，并形成 GGUF 与量化模型生态。[1] [4] [6] [10]

| 维度     | vLLM                                | Ollama                                 | llama.cpp                                 |
| ------ | ----------------------------------- | -------------------------------------- | ----------------------------------------- |
| 核心定位   | 高吞吐 LLM 推理与服务框架                     | 本地模型运行、管理与应用集成平台                       | C/C++ 本地 LLM 推理运行时与量化生态                   |
| 主要用户   | 后端工程师、MLOps、平台团队、GPU 服务团队           | 个人开发者、应用开发者、桌面用户、小团队                   | 系统工程师、边缘端开发者、量化/本地推理爱好者                   |
| 典型场景   | OpenAI 兼容 API 服务、批量推理、高并发在线推理       | 本地聊天、Agent/IDE 集成、RAG 原型、模型快速体验        | CPU/Metal/CUDA/Vulkan 推理、GGUF 量化、嵌入式与本地服务 |
| 关键优势   | PagedAttention、连续批处理、GPU 利用率、分布式扩展  | 安装简单、模型库、Modelfile、REST API、OpenAI 兼容  | 低依赖、跨平台、量化强、硬件覆盖广、可嵌入                     |
| 主要模型格式 | Hugging Face/Safetensors 等，支持多种量化后端 | Ollama 模型包，支持 Safetensors/GGUF 导入      | GGUF 为核心，支持量化模型                           |
| 服务接口   | Python API、OpenAI 兼容 HTTP 服务        | CLI、REST API、OpenAI 兼容 API、Python/JS 库 | CLI、C API、`llama-server` OpenAI 兼容服务      |

## 二、vLLM：面向高吞吐服务的 GPU 推理引擎

vLLM 的官方文档提供两类主要入口：一类是 Python 中的 `LLM` 类，用于离线批量推理；另一类是 `vllm serve <model>`，用于启动在线服务。vLLM 的在线服务实现 OpenAI 兼容接口，默认可作为许多使用 OpenAI API 的应用的替代后端。[2] [3]

### 2.1 使用方法

在离线批推理场景中，vLLM 使用 `LLM` 和 `SamplingParams`。用户指定模型名、采样参数和 prompt 列表，随后调用 `llm.generate()` 生成输出。官方快速开始示例中，`LLM` 是运行 vLLM engine 的主类，而 `SamplingParams` 用于指定 temperature、top_p 等采样参数。[3]

```python
from vllm import LLM, SamplingParams

prompts = [
    "Hello, my name is",
    "The capital of France is",
]
sampling_params = SamplingParams(temperature=0.8, top_p=0.95)
llm = LLM(model="facebook/opt-125m")
outputs = llm.generate(prompts, sampling_params)
```

在线服务通常使用如下命令启动，服务可暴露 OpenAI 兼容接口。新版本文档推荐使用 `vllm serve`，而历史上常见的 `python -m vllm.entrypoints.openai.api_server --model <model>` 已被文档标注为可能废弃的直接入口。[2]

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct
```

启动后，应用可以以 OpenAI API 的方式访问 `/v1/chat/completions`、`/v1/completions` 等接口。vLLM 也支持 Docker、Kubernetes、Ray、多 GPU、张量并行、数据并行、LoRA、结构化输出、投机解码、自动前缀缓存等生产相关能力，这使其更适合服务化与平台化部署。[2] [3]

### 2.2 核心原理

vLLM 的核心技术是 **PagedAttention**。LLM 自回归生成时，每个 token 的 key/value 张量需要保存在 GPU 显存中，以便后续 token 计算注意力时复用，这就是 KV Cache。KV Cache 具有三个困难特征：体积大、随序列长度动态增长、不同请求长度差异极大。因此传统连续内存分配或预留式分配会产生显著碎片与浪费。[1] [4]

PagedAttention 借鉴操作系统虚拟内存分页思想，将每个序列的 KV Cache 分成固定大小的 block。逻辑上，一个序列仍然拥有连续的逻辑 block；物理上，这些 block 可以映射到非连续显存块。vLLM 通过 block table 维护逻辑块到物理块的映射，并在生成新 token 时按需分配物理块。[1] [4]

> vLLM 博客指出，在传统系统中 KV Cache 管理可能因碎片和过度预留浪费 **60%–80%** 的显存；PagedAttention 将浪费限制在序列最后一个 block 内，实践中浪费可低于 **4%**。[1]

该机制直接提升批处理能力。显存不再被大量碎片占据，同一张 GPU 可以同时容纳更多请求，使连续批处理的有效 batch size 增大，从而提升吞吐。此外，PagedAttention 还天然支持类似操作系统 copy-on-write 的 KV Cache 共享。当多个输出共享同一 prompt，例如 parallel sampling 或 beam search，多个序列可以共享 prompt 部分的物理块，只有发生分叉写入时才复制。[1]

vLLM 的架构也围绕高吞吐服务设计。官方架构文档描述了 V1 多进程模型：API Server 处理 HTTP 请求、输入处理和流式返回；Engine Core 负责调度、KV Cache 管理和协调模型执行；GPU Worker 加载权重并执行 forward；启用数据并行时还会有 DP Coordinator 负责跨 data-parallel rank 的负载均衡与协调。[2]

| vLLM 组件        | 主要职责                              | 对性能的意义           |
| -------------- | --------------------------------- | ---------------- |
| API Server     | HTTP 请求、tokenization、多模态数据加载、流式响应 | 将网络与输入处理从推理核心中解耦 |
| Engine Core    | 调度、KV Cache 管理、协调 GPU Worker      | 决定批处理效率与显存利用率    |
| GPU Worker     | 加载模型权重、执行 forward、管理 GPU 显存       | 承担主要计算负载         |
| DP Coordinator | 数据并行负载均衡与 MoE 同步协调                | 面向多 GPU/多副本扩展    |

## 三、Ollama：面向本地开发体验的模型运行平台

Ollama 的核心价值不在于提出新的底层 attention 算法，而在于把模型下载、模型管理、模型运行、Prompt 模板、参数配置、API 服务和外部应用集成统一到一个非常简单的用户体验中。官方快速开始文档显示，用户安装后可以直接运行 `ollama` 打开交互菜单，也可以使用 `ollama run gemma3` 运行模型。[5] [8]

### 3.1 使用方法

Ollama 的日常使用主要围绕 CLI 与 API。最简单的聊天方式如下：[5] [8]

```bash
ollama run gemma3
```

如果作为服务集成到应用中，默认 REST API 地址为 `http://localhost:11434/api`，例如调用 `/api/chat`：[5] [7]

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "gemma3",
  "messages": [{"role": "user", "content": "Hello!"}]
}'
```

Ollama 还提供 OpenAI API 兼容能力，应用可以将 OpenAI SDK 的 `base_url` 指向 `http://localhost:11434/v1/`，并使用任意占位 API key。官方文档示例展示了通过 OpenAI Python SDK 调用 `/v1/chat/completions` 和 `/v1/responses` 的方式。[9]

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1/",
    api_key="ollama",
)

response = client.chat.completions.create(
    model="gpt-oss:20b",
    messages=[{"role": "user", "content": "Say this is a test"}],
)
print(response.choices[0].message.content)
```

Ollama 的差异化功能是 **Modelfile**。Modelfile 类似模型运行蓝图，支持 `FROM` 指定基础模型，`PARAMETER` 设置运行参数，`TEMPLATE` 定义 prompt 模板，`SYSTEM` 定义系统提示，`ADAPTER` 加载 LoRA/Q LoRA 适配器，`LICENSE` 和 `MESSAGE` 用于模型元信息与消息历史。[7]

```dockerfile
FROM llama3.2
PARAMETER temperature 0.7
PARAMETER num_ctx 4096
SYSTEM """你是一个严谨的中文技术助手。"""
```

创建和运行自定义模型通常如下：[7] [8]

```bash
ollama create my-assistant -f ./Modelfile
ollama run my-assistant
```

Ollama 也支持从 Safetensors、GGUF 文件以及 LoRA/QLoRA adapter 导入模型。对于 FP16/FP32 模型，`ollama create --quantize` 可以执行量化，例如 `q4_K_M` 或 `q8_0`。[10]

### 3.2 核心原理

Ollama 可以理解为“模型运行编排层”。它负责模型包管理、下载、缓存、导入、量化、参数封装、模板封装、运行时服务和 API 适配。Ollama README 明确列出其 supported backends 包括 llama.cpp，这说明它在许多本地推理场景中依赖或复用 llama.cpp 生态能力。[6]

Ollama 的运行机制还包括模型常驻与调度。FAQ 显示，默认模型在内存中保留 5 分钟后卸载，用户可以通过 API 的 `keep_alive` 参数控制模型保留时间，使用空请求预加载模型，或使用 `ollama stop` 主动卸载模型。[12]

Ollama 的硬件支持覆盖 NVIDIA、AMD ROCm、Apple Metal 与 Vulkan。它可以通过 `ollama ps` 显示模型当前加载在 GPU、CPU，还是 CPU/GPU 混合状态。硬件文档还提到 Ollama scheduler 会利用 GPU 库报告的可用 VRAM 数据做调度决策；如果 Vulkan 无法提供可用 VRAM，Ollama 会根据模型近似大小进行尽力调度。[11] [12]

| Ollama 能力 | 说明 | 对用户的价值 |
| --- | --- | --- |
| 模型库与 `ollama pull/run` | 下载并运行模型 | 降低模型获取与启动成本 |
| Modelfile | 封装基础模型、参数、模板、系统提示和 adapter | 便于复现实验与分发定制模型 |
| REST API 与 OpenAI 兼容 API | 默认本地 API 与 `/v1` 兼容接口 | 易接入 LangChain、Open WebUI、IDE 插件等应用 |
| 模型导入与量化 | 支持 Safetensors、GGUF、adapter 与量化 | 降低自定义模型落地难度 |
| 本地运行与模型保留 | 支持 preload、keep_alive、stop | 改善本地交互延迟与资源控制 |

## 四、llama.cpp：轻量 C/C++ 本地推理运行时与 GGUF 生态

llama.cpp 的 README 将项目描述为 **LLM inference in C/C++**，其目标是在本地和云端以最少设置和高性能运行大语言模型。它采用低依赖 C/C++ 实现，并针对 Apple Silicon、x86 AVX/AVX2/AVX512/AMX、RISC-V、CUDA、HIP、Vulkan、SYCL 等硬件与后端做优化。[13]

### 4.1 使用方法

llama.cpp 的使用方式可以分为 CLI、本地服务器、库集成和模型转换量化。最简单的 CLI 运行方式是直接指定 GGUF 文件：[13]

```bash
llama-cli -m ./models/my_model.gguf
```

也可以直接从 Hugging Face 下载并运行 GGUF 模型：[13]

```bash
llama-cli -hf ggml-org/gemma-3-1b-it-GGUF
```

服务化运行可使用 `llama-server`。官方 README 示例显示，可以用如下命令启动 OpenAI 兼容 API 服务：[13]

```bash
llama-server -hf ggml-org/gemma-3-1b-it-GGUF
```

`tools/server` 文档显示，`llama-server` 是一个基于 httplib、nlohmann::json 和 llama.cpp 的快速轻量 C/C++ HTTP 服务，支持 OpenAI 兼容 chat completions、responses、embeddings，支持 Anthropic Messages API 兼容接口，并提供 continuous batching、并行解码、多用户、多模态、监控、结构化 JSON 输出、函数调用和投机解码等功能。[14]

构建方面，llama.cpp 通过 CMake 支持 CPU、BLAS、Metal、CUDA、HIP、Vulkan、SYCL、OpenCL 等后端。CPU 构建通常如下：[15]

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --config Release
```

如果需要 NVIDIA CUDA 加速，可使用：[15]

```bash
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release
```

### 4.2 核心原理

llama.cpp 的基础是 ggml/gguf 生态。GGUF 是当前本地 LLM 社区常见的模型文件格式，适合保存量化权重、tokenizer、模型元数据等。llama.cpp 的一个关键能力是将 Hugging Face 模型转换为 GGUF，再进行低比特量化，以显著降低内存与存储需求。[16]

量化工具 `llama-quantize` 接收高精度 GGUF，例如 F32、BF16 或 F16，将权重转换为 Q4、Q5、Q8、IQ 等低比特格式。官方量化文档说明，量化会降低权重精度，例如从 32-bit float 降为 4-bit integer，从而缩小模型体积并可能加速推理，但会带来一定精度损失，可通过 perplexity 或 KL divergence 衡量。[16]

| 示例模型           | 原始大小       | Q4_K_M 量化后大小 | 压缩效果      |
| -------------- | ---------- | ------------ | --------- |
| Llama 3.1 8B   | 32.1 GB    | 4.9 GB       | 约 6.6 倍缩小 |
| Llama 3.1 70B  | 280.9 GB   | 43.1 GB      | 约 6.5 倍缩小 |
| Llama 3.1 405B | 1,625.1 GB | 249.1 GB     | 约 6.5 倍缩小 |
|                |            |              |           |

llama.cpp 的推理优势来自几个方面。第一，模型文件可通过 mmap 映射，降低加载与内存复制成本。第二，量化格式使模型能在较小内存中运行。第三，它支持 CPU 与 GPU 混合推理，例如通过 `--n-gpu-layers` 将部分层 offload 到 GPU。第四，`llama-server` 层面已支持 continuous batching、KV Cache 类型配置、KV offload、Flash Attention、speculative decoding 等提升服务能力的机制。[14] [15] [16]

## 五、差异性比较

从系统层级看，vLLM 更像“高并发推理服务引擎”，Ollama 更像“本地模型产品化运行平台”，llama.cpp 更像“底层推理内核与量化运行时”。这一区分是选型时最重要的出发点。

| 比较项    | vLLM                                  | Ollama                     | llama.cpp                               |
| ------ | ------------------------------------- | -------------------------- | --------------------------------------- |
| 抽象层级   | 服务引擎层                                 | 产品化运行与模型管理层                | 底层运行时/内核层                               |
| 性能优化核心 | PagedAttention、KV Cache 分页、连续批处理、并行扩展 | 模型加载/保留、硬件调度、后端封装与易用性      | GGUF 量化、低依赖 C/C++、多硬件后端、CPU/GPU offload |
| 并发服务能力 | 很强，面向多用户高吞吐服务                         | 中等，适合本地与轻量服务               | 已支持 continuous batching 与多用户，但更多需要手动调参  |
| 易用性    | 中等，需要 Python/GPU/部署知识                 | 很高，安装后 `ollama run` 即可     | 中等偏低，常涉及构建、GGUF、量化和参数调优                 |
| 资源需求   | 主要面向 GPU，尤其适合 NVIDIA 数据中心 GPU         | 可在个人电脑/工作站/服务器运行           | 资源适应性最强，从 CPU 到 GPU、移动端和边缘设备            |
| 模型管理   | 依赖 HF 等外部模型源和部署配置                     | 内置模型库、pull/run/create/push | 主要围绕 GGUF 文件与 HF GGUF repo              |
| 定制方式   | 启动参数、服务参数、LoRA、模型配置                   | Modelfile、参数、模板、adapter    | CLI 参数、C API、GGUF 转换与量化、LoRA 参数         |
| 生产部署   | 强，适合 Kubernetes、Ray、多 GPU、多副本         | 适合小规模服务与本地应用，不是典型高并发服务平台   | 可生产化，但需要更多工程封装                          |
| 最佳使用者  | 平台工程团队                                | 应用开发者与本地用户                 | 系统工程师和本地推理专家                            |

### 5.1 性能与吞吐

vLLM 的性能优势主要来自显存管理与调度。PagedAttention 使 KV Cache 几乎按需分配，并通过 block table 避免连续显存要求，允许更大 batch 和更多并发请求。官方博客声称 vLLM 相比 Hugging Face Transformers 最高可达 24 倍吞吐提升，相比 TGI 最高可达 3.5 倍吞吐提升；论文摘要则报告相对 FasterTransformer 和 Orca 在相同延迟水平下吞吐提升 2–4 倍。[1] [4]

llama.cpp 的性能优势主要体现在本地资源约束下的可运行性与效率。它的量化模型能将 8B、70B 甚至更大模型压缩到更适合消费级硬件的大小；同时，Metal、CUDA、Vulkan、HIP 等后端支持让其能利用本地 GPU。对于单机低并发或边缘设备，它往往比复杂服务框架更轻。[13] [16]

Ollama 的性能很大程度上取决于其底层后端、模型量化格式、硬件和调度策略。它不以极限吞吐为首要目标，而是以本地易用、模型管理和应用集成为首要目标。对于单用户或小并发本地应用，Ollama 的性能通常足够；对于高并发线上服务，vLLM 更有针对性。[6] [11] [12]

### 5.2 模型格式与生态

vLLM 与 Hugging Face 模型生态结合紧密，适合直接加载主流 Transformer 模型，并支持多种量化和推理优化机制。Ollama 通过自己的模型包与 Modelfile 管理模型，同时支持 Safetensors 与 GGUF 导入。llama.cpp 以 GGUF 为中心，拥有最强的本地量化生态。[3] [7] [10] [13] [16]

| 模型生命周期环节 | vLLM | Ollama | llama.cpp |
| --- | --- | --- | --- |
| 获取模型 | Hugging Face、ModelScope 等 | `ollama pull`、Ollama library、导入本地模型 | 本地 GGUF、Hugging Face GGUF repo、转换脚本 |
| 转换模型 | 通常不作为主要功能 | 支持 Safetensors/GGUF 导入 | 强，提供 HF 到 GGUF、LoRA 到 GGUF 等工具 |
| 量化 | 支持多种量化方案，但不是 GGUF 量化生态中心 | `ollama create --quantize` | 强，`llama-quantize` 支持大量量化类型 |
| 分发模型 | 依赖外部模型仓库与部署系统 | 可 push 到 ollama.com | 通常通过 GGUF 文件或 HF repo 分发 |

### 5.3 运维复杂度

vLLM 部署复杂度较高，但生产能力强。它涉及 GPU 驱动、CUDA/PyTorch、模型权重、服务参数、并行策略、显存控制和监控。Ollama 运维复杂度最低，安装后默认在本地 `11434` 端口提供服务，环境变量可配置 host、模型目录、上下文长度等。llama.cpp 位于两者之间，预编译二进制可以快速使用，但若要充分发挥硬件性能，常需要从源码构建并选择合适后端。[3] [8] [12] [15]

| 部署情境                        | 推荐工具               | 理由                             |
| --------------------------- | ------------------ | ------------------------------ |
| 单人 Mac/Windows/Linux 上快速试模型 | Ollama             | 安装简单，模型库与 CLI 体验最好             |
| 消费级显卡运行 GGUF 量化模型           | llama.cpp 或 Ollama | llama.cpp 控制更细；Ollama 更易用      |
| 公司内部高并发 OpenAI 兼容服务         | vLLM               | 更好的批处理、KV Cache 管理和 GPU 吞吐     |
| 嵌入式、移动端、边缘设备                | llama.cpp          | C/C++、低依赖、硬件覆盖广                |
| RAG/Agent 原型接本地模型           | Ollama             | API 与工具生态友好                    |
| 研究推理性能、量化格式、底层算子            | llama.cpp 或 vLLM   | llama.cpp 适合本地量化，vLLM 适合服务调度研究 |

## 六、选型建议

如果团队拥有专门 GPU 服务器，希望构建对外或对内的统一推理服务，并且关注吞吐、并发、延迟、显存利用率和 OpenAI 兼容 API，那么应优先选择 **vLLM**。它的 PagedAttention 和多进程调度架构是为生产服务设计的，对多请求批处理和长上下文场景尤其有价值。[1] [2] [4]

如果目标是在开发机或小型服务器上快速使用开源模型，并与 IDE、聊天 UI、Agent 框架或本地 RAG 应用集成，那么应优先选择 **Ollama**。它把模型下载、模型运行、API 服务、模板、参数和适配器封装为统一体验，学习成本最低。[5] [7] [8] [9]

如果目标是最大程度控制推理运行时、在低资源设备上运行模型、使用 GGUF 量化模型、研究量化效果，或需要把 LLM 推理嵌入 C/C++/移动端/边缘端应用，那么应优先选择 **llama.cpp**。它是三者中最底层、最轻量、硬件适配最广的方案。[13] [15] [16]

在实际工程中，三者也可以组合使用。个人开发者可以用 Ollama 做本地原型；当需求转向大规模服务时，将模型部署到 vLLM；当模型需要在客户端、边缘设备或消费级机器上离线运行时，则使用 llama.cpp/GGUF 量化方案。Ollama 与 llama.cpp 的关系尤其密切，因为 Ollama 的本地运行体验在很大程度上受益于 llama.cpp 生态，而 llama.cpp 则提供了更底层、更可调的能力。[6] [13]

## 七、结论

vLLM、Ollama 和 llama.cpp 的差异不是简单的“谁更好”，而是“解决哪一层问题”。vLLM 解决的是 **服务端高吞吐推理**；Ollama 解决的是 **本地模型使用与应用集成体验**；llama.cpp 解决的是 **跨平台低依赖本地推理与量化运行时**。如果用一句话概括：**生产高并发选 vLLM，本地易用选 Ollama，底层轻量与量化选 llama.cpp**。

## References

[1]: https://vllm.ai/blog/2023-06-20-vllm "vLLM: Easy, Fast, and Cheap LLM Serving with PagedAttention"
[2]: https://docs.vllm.ai/en/latest/design/arch_overview/ "vLLM Architecture Overview"
[3]: https://docs.vllm.ai/en/stable/getting_started/quickstart/ "vLLM Quickstart"
[4]: https://arxiv.org/abs/2309.06180 "Efficient Memory Management for Large Language Model Serving with PagedAttention"
[5]: https://docs.ollama.com/quickstart "Ollama Quickstart"
[6]: https://github.com/ollama/ollama/blob/main/README.md "Ollama GitHub README"
[7]: https://docs.ollama.com/modelfile "Ollama Modelfile Reference"
[8]: https://docs.ollama.com/cli "Ollama CLI Reference"
[9]: https://docs.ollama.com/api/openai-compatibility "Ollama OpenAI compatibility"
[10]: https://docs.ollama.com/import "Ollama Importing a Model"
[11]: https://docs.ollama.com/gpu "Ollama Hardware support"
[12]: https://docs.ollama.com/faq "Ollama FAQ"
[13]: https://github.com/ggml-org/llama.cpp "llama.cpp GitHub README"
[14]: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp HTTP Server README"
[15]: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md "Build llama.cpp locally"
[16]: https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md "llama.cpp quantize README"
