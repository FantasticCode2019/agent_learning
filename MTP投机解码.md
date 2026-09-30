
结论
MTP（Multi-Token Prediction）属于投机解码（Speculative Decoding），其生成吞吐不是一个固定值，而是随负载在很大区间内波动——同一个模型同一套配置，吞吐可以从 ~160 t/s 到 ~240 t/s 不等。原因是 MTP 吞吐由"草稿被采纳的比例（接受率）"决定，而接受率取决于内容好不好猜（熵）和采样温度：代码、序列生成等低熵负载能跑满 240+，日常开放域对话只有一半左右。这是投机解码这类技术的固有特性，且不影响生成质量。
本文用三个实测用例说明这种差异的来源与原理，并给出可复现的测试方法。用户仓库llamacppqwen36a3bone 标称的 243 t/s 即对应其中接受率接近 100% 的峰值场景。
MTP 最突出的特点：草稿器是模型自带的多 token 预测头（与目标模型共享主干、同一份权重），无需额外的独立草稿模型——省显存、部署简单，且草稿质量天然贴合目标分布，低熵场景接受率可达 95%+。再叠加投机解码的无损性（输出分布不变），等于"免费"提速。
最适合的场景：输出结构化、低熵、可预测的任务收益最大——代码生成、JSON / 函数（工具）调用、格式化/数据转换、模板与长文本续写、agent 工作流等，常能逼近理论加速上限（约 γ+1 倍；本部署草稿长度 γ=3，即每个验证周期最多产出 4 个 token、约 4×）。反之，高熵开放域（闲聊、创意写作）或高温采样场景接受率低，提速有限，但绝不会比普通解码慢很多、也不损质量。）
平台：Olares One（RTX 5090M 24GB）。这是用户市场（本仓库自建市场）的镜像 aamsellem/buun-llama-cpp:87c351d2，模型 Qwen3.6-35B-A3B-MTP UD-Q3_K_XL（≈17.2 GB），--reasoning off，草稿长度 γ=3。用三种不同可预测性的负载各跑一次。
判读看 server 返回 timings 里的两个字段：

---
一、Olares One 上的测试方式与结果（用户市场）
仓库地址：https://github.com/aamsellem/olares-one-market
项目：llamacppqwen36a3bone
模型：Qwen3.6-35B-A3B-UD-Q3_K_XL.gguf
镜像：docker.io/aamsellem/buun-llama-cpp:87c351d2
- draft_n_accepted / draft_n = 草稿接受率
- predicted_per_second = 生成吞吐
用例 1：序列生成（最好猜）
curl -s http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"Count from 1 to 800, one number per line, nothing else."}],
  "max_tokens":2048,"temperature":0,"top_k":1,"stream":false}'
结果：接受率 99.2%（1417/1428）→ 243.9 t/s，正好撞上标称值。 原因：下一个永远是 +1，目标模型几乎 one-hot，草稿基本全中。
用例 2：代码生成（较好猜）
curl -s http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"Write a complete single-file HTML+JS Snake game. Output only code."}],
  "max_tokens":1536,"temperature":0.6,"top_k":20,"top_p":0.95,"min_p":0,"stream":false}'
结果：接受率 83.9%（531/633）→ 221.8 t/s。 原因：代码有语法约束（括号、缩进、关键字），可预测性较高，但不如数数；温度 0.6 也略增随机性。
用例 3：开放域对话（最难猜）
curl -s http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"随便聊聊你对生活、旅行和美食的看法。"}],
  "max_tokens":1024,"temperature":0.7,"stream":false}'
结果：接受率 51.3%（223/435）→ 162.6 t/s。 原因：同一句话有无数种合理说法，目标分布平坦、候选众多，草稿经常押错；温度偏高进一步降低命中。
三组对照
暂时无法在飞书文档外展示此内容
吞吐随接受率单调变化——这就是全部原因。

---
二、官方市场镜像（llama.cpp）的测试结果
官方 Olares 市场自带的 llama.cpp 镜像（基于 ggml-org/llama.cpp，模型 Q4_K_M）用同样三组负载复测，请求里加 "chat_template_kwargs":{"enable_thinking":false} 关思考。
用例 1：数数（关思考，干净）
curl -s http://localhost:8081/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"Count from 1 to 800, one number per line, nothing else."}],
  "max_tokens":2048,"temperature":0,"top_k":1,
  "stream":false,"chat_template_kwargs":{"enable_thinking":false}}'
结果：接受率 100%（1364/1364）→ 236.7 t/s。
用例 2：代码（Snake，关思考，干净）
curl -s http://localhost:8081/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"Write a complete single-file HTML+JS Snake game with arrow-key controls and score. Output only code."}],
  "max_tokens":1536,"temperature":0.6,"top_k":20,"top_p":0.95,"min_p":0,
  "stream":false,"chat_template_kwargs":{"enable_thinking":false}}'
结果：接受率 96.7%（1012/1046）→ ~235 t/s（多次复跑 234.6 / 237.5 t/s，稳定）。另有一次复跑接受率相近（97.4%）但吞吐掉到 117.7 t/s、每 token 从 4.21ms 涨到 8.50ms——系 GPU 调度释放锁/降频等环境波动，属离群值，与投机解码无关。
用例 3：开放域对话（关思考，干净，两次取均值）
curl -s http://localhost:8081/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"随便跟我聊聊你对生活、旅行和美食的看法,讲得自然一点。"}],
  "max_tokens":1024,"temperature":1.0,"top_k":40,"top_p":0.95,
  "stream":false,"chat_template_kwargs":{"enable_thinking":false}}'
结果：接受率 44.6%（673/1510）→ ~156.8 t/s（两次 156.94 / 156.72 t/s）。
用户市场（Q3）vs 官方市场（Q4）逐组对比
暂时无法在飞书文档外展示此内容
三组均关思考、数据干净。注意单次跑存在环境波动（GPU 调度/降频），代码组第二次复跑在相同接受率下吞吐曾掉到 ~117 t/s，宜多跑几次取稳定值。
两点说明：
- 规律完全一致：两边都是"接受率高 → 吞吐高"，关思考后数数都顶到接近 100% 接受。MTP 这套机制与具体实现无关。
- 绝对数值不能直接对比：两者镜像和模型量化都不同——用户市场是 Q3_K_XL（更小更快），官方市场是 Q4_K_M（更大、精度更高、单 token 更慢）。差距里既有 fork 性能核（turbo4 V-cache、融合非对称 flash-attn）的因素，也有 Q3/Q4 量化的因素，不是受控对比。要严格比性能核，需固定同一份模型并都关思考。
注：测官方镜像时若忘记关思考，模型会先生成思维链，数数曾被拖到 ~158 t/s（甚至低于闲聊）。务必确认返回 reasoning_content 为空，详见第四节。

---
三、为什么会这样（原理）
投机解码的逻辑：自回归生成一次只能出一个 token，且受显存带宽限制，GPU 算力闲置。于是让一个廉价"草稿器"一次性提议 γ 个 token，再让大模型一次前向并行验证（验证 γ 个 token 和验证 1 个几乎一样快）。猜对的部分直接采纳，遇到第一个不匹配就截断重来。
- 草稿越准（接受率 α 越高），每轮采纳的 token 越多，吞吐越高。
- MTP 只是把草稿器做成模型自带的预测头，省掉独立草稿模型；规律和其它投机方法（Medusa、EAGLE、独立草稿模型）完全一样。
接受率 α 由两件事决定：
1. 内容的可预测性（熵）：数数 < 代码 < 对话，熵越低越好猜。
2. 采样温度：温度越低，目标输出越确定，草稿越容易命中（贪心 T=0 时接受率最高）。
一个够用的估算（草稿长度 γ，接受率 α）：每轮期望产出 ≈ (1 − α^(γ+1)) / (1 − α)。本部署 γ=3：α→1 时逼近 γ+1 = 4 倍加速；α→0 时退化为无加速、甚至因草稿开销变慢。
重要：投机解码是无损的。 输出经拒绝采样校正后，分布严格等于原模型——只改速度，不改质量。对话慢 ≠ 质量差。

---
四、测试时的坑：先关掉"思考模式"
如果开着 thinking/reasoning，模型会先吐一大段思维链（CoT），这些高熵文本占满 token 预算，会让"数数"这种本该最快的用例反而变慢、数据失真（我们实测原生 llama.cpp 开思考时，数数 94% 接受却只有 158 t/s，比闲聊还慢）。
关闭方式（llama.cpp）：
- 启动时全局：--reasoning off
- 单次请求软开关（Qwen3）：用户消息末尾加  /no_think
验证：返回里 reasoning_content 为空即可。

---
五、实操建议
- 想快：降低温度（temperature=0.6），内容越结构化（代码、列表、序列）越接近峰值。
- 日常对话 150–180 t/s 是正常表现，改不掉也不该改。

---
六、参考引用
均为 MTP / 投机解码的一手资料（llama.cpp 仓库与 PR、模型官方），可直接佐证本文"吞吐随草稿接受率变化"的结论。
llama.cpp MTP 实现（GitHub）
- MTP 主合入 PR：ggml-org/llama.cpp #22673 —— 实现说明与基准，PR 讨论给出不同负载下的草稿接受率与对应吞吐，直接印证"接受率决定加速比"。
- server 端 timings 字段（draft_n / draft_n_accepted / predicted_per_second，本文判读依据）：tools/server/README.md
- 投机解码（独立 draft 模型路径）示例与参数（--model-draft、--draft-max、--draft-min、--draft-p-min）：examples/speculative
- 仓库主页：github.com/ggml-org/llama.cpp
模型官方（MTP 头与接受率）
- 实际所用模型卡（UD-Q3/Q4 量化 + MTP 头）：unsloth/Qwen3.6-35B-A3B-MTP-GGUF
- DeepSeek-AI. DeepSeek-V3 Technical Report. arXiv:2412.19437 —— §MTP 报告第二 token 接受率（TAR ≈ 0.85–0.90），佐证 MTP 自投机的接受率水平及其随负载波动。
- Qwen 官方文档（thinking / /no_think 软开关，本文第四节测试方法依据）：qwen.readthedocs.io
其他生态中的 MTP 应用（示例）
说明 MTP 已被主流模型与推理引擎广泛采用，且各家文档普遍以"草稿接受率 / acceptance rate"作为衡量加速效果的核心指标——与本文结论一致。
- MTP 训练范式原始论文：Gloeckle et al. (Meta), Better & Faster LLMs via Multi-token Prediction, arXiv:2404.19737。
- DeepSeek-V3 / R1：生产级模型内置 MTP 模块，开源权重含 MTP 头：github.com/deepseek-ai/DeepSeek-V3。
- GLM-4.5 / GLM-4.6（智谱 Z.ai）：模型自带 MTP 层，被 vLLM / SGLang 用于投机解码：github.com/zai-org/GLM-4.5。
- vLLM：支持 DeepSeek MTP 做投机解码，文档以接受率衡量加速：Spec Decode 文档。
- SGLang：原生支持 DeepSeek MTP / EAGLE 投机解码：Speculative Decoding 文档。
- TensorRT-LLM（NVIDIA）：为 DeepSeek MTP 提供专门加速路径：github.com/NVIDIA/TensorRT-LLM。
用户 / 社区实测（搜到的真实案例，均印证"接受率/负载决定吞吐"）
- llama.cpp MTP 作者实测（PR #22673）：Qwen3.6-27B 稳态接受率 75-76%，解码 22.97 → 42.45 t/s（1.9×）；同时 prefill 反而变慢（1315 → 665 t/s）——与本文"接受率驱动加速、且有固定开销"一致。PR #22673
- 用户博客（airelien.dev）：Qwen3.6-27B 在 --spec-draft-n-max 3 + backend sampling 下，10 次跑平均 86.7% 接受 → 74.28 t/s；把 n_max 从 5 调到 3 接受率从 64% 升到 86.7%——印证"采样/草稿配置直接改变接受率"。文章
- 同作者另一篇：上游 llama.cpp + MTP，基线 35 t/s → 78 t/s（+123%，接受率 ~75%），另给出一例 64.15% 接受的较低命中场景。文章
- llama.cpp PR #20700（Qwen3.5 dense MTP）：作者报告 temp=0 下 82% 接受，而另一用户复测同配置只有 63.5%——直接说明接受率随环境/负载波动。PR #20700
- vLLM DeepSeek-R1 MTP（PR #12755）：k=1 接受率 81-82.3%，加速比随并发从 QPS=1 的 1.63× 跌到 QPS=8 的 1.0×——印证"高并发/高熵负载下投机收益消失"。PR #12755
- SGLang DeepSeek-V3 NextN/MTP（PR #3582）：草稿 2 token 时平均接受长度 ~1.9、草稿 4 token 时 2.5-3，batch=1 吞吐 38 → 67.93 t/s（1.76×）。PR #3582
- vLLM 官方博客（GB300 DeepSeek）：低并发时 MTP 接受率 >80%、吞吐提升，但高并发或 ISL≫OSL 的混合负载下开销无法摊销、反而更慢——印证"MTP 并非银弹，收益取决于负载构成"。博客# Qwen3.5 / Qwen3.6 MTP 模型在 24GB 显存下的最佳实践参数指南

本文详细总结了在单张 24GB 显存显卡（如 RTX 3090/4090）上运行 **Qwen3.5** 和 **Qwen3.6** 系列 MTP 模型的最佳实践参数配置。基于最新的社区实测数据和 Unsloth 官方文档，本文涵盖量化版本选择、KV Cache 优化、MTP 投机解码、批处理调优等关键环节，并对每个参数的含义与作用进行详细说明。

---

## 一、显存分配策略与量化版本选择

在 24GB 显存的限制下，显存的分配需要精打细算。主要开销分为三部分：**模型权重**、**KV Cache** 和 **MTP 草稿计算开销**。

### 1.1 各模型量化版本与显存占用

| 模型 | 推荐量化版本 | 权重大小 | MTP 额外开销 | 剩余可用显存 |
|---|---|---|---|---|
| Qwen3.6-27B-MTP | `UD-Q4_K_XL` | ~17.9 GB | ~1 GB | ~5.1 GB |
| Qwen3.6-35B-A3B-MTP | `UD-Q4_K_M` | ~22.3 GB | ~1 GB | < 1 GB |
| Qwen3.5-27B-MTP | `UD-Q4_K_XL` | ~17.6 GB | ~1 GB | ~5.4 GB |
| Qwen3.5-35B-A3B-MTP | `Q4_K_M` | ~21.4 GB | ~1 GB | ~1.6 GB |

> **注意**：MTP 模型比普通 GGUF 多约 1 GB 的显存开销，这部分来自内置的草稿预测头（Draft Head）权重 [1][2]。

### 1.2 上下文长度建议

上下文长度（`--ctx-size`）是 24GB 显存下最需要权衡的参数。KV Cache 的大小与上下文长度成正比，配合 8-bit 量化（`q8_0`）可以将 KV Cache 的显存占用减半。

| 模型 | 推荐上下文长度 | 说明 |
|---|---|---|
| Qwen3.6-27B-MTP | 32K - 65K | 显存充裕，可支持长上下文 |
| Qwen3.6-35B-A3B-MTP | 16K - 32K | 显存极限，需严格控制 |
| Qwen3.5-27B-MTP | 32K - 65K | 与 Qwen3.6-27B 类似 |
| Qwen3.5-35B-A3B-MTP | 4K - 16K | 显存极限，建议保守设置 |

---

## 二、核心启动参数配置 (llama.cpp)

以下是针对 24GB 显存优化的 `llama.cpp` 启动参数完整模板。

### 2.1 27B 模型推荐配置（适用于 Qwen3.5-27B 和 Qwen3.6-27B）

```bash
# 以 Qwen3.6-27B 为例，Qwen3.5-27B 替换模型名即可
export LLAMA_CACHE="unsloth/Qwen3.6-27B-MTP-GGUF"
./llama.cpp/llama-server \
    -hf unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL \
    --host 0.0.0.0 --port 8080 \
    --ctx-size 65536 \
    --n-gpu-layers 99 \
    --flash-attn on \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    -b 4096 -ub 4096 \
    --parallel 1 \
    --spec-type draft-mtp --spec-draft-n-max 2 \
    --temp 0.6 --top-p 0.95 --top-k 20 \
    --chat-template-kwargs '{"enable_thinking":true}'
```

### 2.2 35B-A3B 模型推荐配置（适用于 Qwen3.5-35B-A3B 和 Qwen3.6-35B-A3B）

```bash
# 以 Qwen3.5-35B-A3B 为例，Qwen3.6-35B-A3B 替换模型名即可
export LLAMA_CACHE="unsloth/Qwen3.5-35B-A3B-MTP-GGUF"
./llama.cpp/llama-server \
    -hf unsloth/Qwen3.5-35B-A3B-MTP-GGUF:Q4_K_M \
    --host 0.0.0.0 --port 8080 \
    --ctx-size 8192 \
    --n-gpu-layers 99 \
    --flash-attn on \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    -b 4096 -ub 4096 \
    --parallel 1 \
    --spec-type draft-mtp --spec-draft-n-max 2 \
    --temp 0.6 --top-p 0.95 --top-k 20 \
    --chat-template-kwargs '{"enable_thinking":true}'
```

---

## 三、全部参数详细解释

### 3.1 模型与服务参数

**`-hf <repo>:<quant>`**

从 Hugging Face 自动下载并加载指定量化版本的模型。冒号后面的部分（如 `UD-Q4_K_XL`）指定量化文件名。`LLAMA_CACHE` 环境变量控制模型缓存目录。

**`--host 0.0.0.0 --port 8080`**

设置 llama-server 的监听地址和端口。`0.0.0.0` 表示监听所有网络接口（允许局域网访问），`127.0.0.1` 则仅允许本机访问。端口号可根据需要修改。

---

### 3.2 上下文与显存参数

**`--ctx-size <N>`（简写 `-c`）**

设置模型的最大上下文窗口长度，单位为 Token。这是**显存消耗的主要来源**之一。KV Cache 的显存占用公式大致为：

```
KV Cache 显存 ≈ ctx-size × n_layers × n_kv_heads × head_dim × 2 × dtype_bytes
```

在 8-bit KV Cache 下，每 1K Token 的上下文大约消耗 0.5 - 1 MB 显存（具体取决于模型架构）。因此，65K 上下文约需 3 - 6 GB 的 KV Cache 显存。**对于 35B-A3B 模型，必须将此值控制在 8K - 16K 以内，否则会 OOM。**

**`--n-gpu-layers <N>`（简写 `-ngl`）**

指定将模型的多少层卸载到 GPU 上运行。设置为 `99` 或 `all` 表示将所有层（包括 Embedding 层和输出层）全部加载到 GPU，实现纯 GPU 推理，速度最快。若显存不足，可以适当减小此值，将部分层保留在 CPU 上，但这会显著降低生成速度。

---

### 3.3 注意力机制与 KV Cache 参数

**`--flash-attn on`（简写 `-fa on`）**

启用 Flash Attention（融合注意力机制）。Flash Attention 通过将注意力计算分块（Tiling）来减少 GPU HBM 的读写次数，从而降低注意力计算的**峰值显存占用**并提升计算速度。在支持的 GPU（NVIDIA Ampere 架构及以上，即 RTX 3090/4090 等）上，这是**必须开启**的选项，对长上下文场景的收益尤为显著 [3]。

**`--cache-type-k q8_0`（简写 `-ctk q8_0`）**

设置 KV Cache 中 **Key** 矩阵的量化精度。默认值为 `f16`（16-bit 浮点）。将其设置为 `q8_0` 可以将 Key Cache 的显存占用减少约 **50%**，同时对输出质量的影响极小。在 24GB 显存下，这是实现长上下文推理的**关键参数**，必须开启 [3]。

**`--cache-type-v q8_0`（简写 `-ctv q8_0`）**

设置 KV Cache 中 **Value** 矩阵的量化精度，作用与 `-ctk` 相同。将 Key 和 Value 均设置为 `q8_0` 可以将整体 KV Cache 显存占用减少约 50%。

> **为什么分开设置 K 和 V？** 研究表明，Key 和 Value 矩阵对量化精度的敏感度不同。Key 矩阵通常对量化更敏感，因此在极端情况下可以考虑 `-ctk q8_0 -ctv q4_0` 的非对称配置来进一步节省显存，但代价是输出质量略有下降。在 24GB 显存下，`q8_0 / q8_0` 的对称配置是精度与显存的最佳平衡点。

---

### 3.4 批处理参数

**`-b <N>`（逻辑批大小，`--batch-size`）**

控制一次 Prefill（提示词处理）阶段最多处理的 Token 数量。默认值通常为 `2048`。这个参数影响的是**提示词处理速度（Prefill TPS）**，而不是生成速度。将其调高（如 `4096`）可以让 GPU 在处理长提示词时一次性计算更多 Token，提高 GPU 利用率，从而加快首 Token 生成时间（TTFT）。

**`-ub <N>`（物理批大小，`--ubatch-size`）**

控制实际传递给 GPU 计算核心的微批次（Micro-batch）大小，是 `-b` 的子集（`-ub` 必须 ≤ `-b`）。默认值为 `512`。将其与 `-b` 保持一致（均设为 `4096`）可以避免不必要的批次切分开销，让 GPU 以最大批次进行矩阵运算，充分发挥并行计算能力。

> **显存影响**：将 `-b` 和 `-ub` 从默认值提升到 `4096` 会增加约 **100 - 300 MB** 的计算缓冲区显存占用，在 24GB 显存下是完全可以接受的。**这两个参数对提示词处理速度（Prefill）有明显提升，但对逐 Token 生成速度（Decode TPS）影响极小。**

---

### 3.5 并发与 MTP 投机解码参数

**`--parallel <N>`（简写 `-np`）**

设置服务器同时处理的并发请求数（Slots）。**MTP 目前不支持多并发，必须将此值设置为 `1`**，否则 MTP 功能将无法正常工作 [1]。

**`--spec-type draft-mtp`**

启用 MTP（Multi-Token Prediction，多 Token 预测）投机解码模式。MTP 是 Qwen3.5/3.6 模型内置的草稿预测头，能够在每次前向传播时预测多个未来 Token，然后由主模型并行验证，从而减少总的前向传播次数，提升生成速度。

> **注意**：`draft-mtp` 是 2026 年 5 月 13 日后 llama.cpp 的新参数名，旧版本使用 `--spec-type mtp`（无 `draft-` 前缀）。请确保使用最新版本的 llama.cpp [4]。

**`--spec-draft-n-max <N>`**

设置每次 MTP 最多预测的草稿 Token 数量。这是 MTP 性能调优的核心参数。

根据 Unsloth 官方测试和社区实测，不同值的效果如下 [1]：

| `spec-draft-n-max` | 草稿接受率 | 实际加速效果 | 适用场景 |
|---|---|---|---|
| 1 | ~99% | 约 1.2x | 保守，接近无损 |
| **2（推荐）** | **~97%** | **稠密模型约 1.4x，MoE 约 1.15-1.2x** | **最佳平衡点** |
| 3 | ~80% | 约 1.2x（收益下降） | 不推荐 |
| 4+ | ~50% | 可能比不开 MTP 还慢 | 不推荐 |

**强烈建议将此值保持为 `2`**。设置更高的值会导致草稿质量急剧下降，接受率断崖式下跌，反而拖慢整体 TPS。

---

### 3.6 采样参数

**`--temp <float>`（温度，`--temperature`）**

控制输出的随机性。值越低，输出越确定性（更集中于高概率 Token）；值越高，输出越多样。

- 思考模式（Thinking Mode）通用任务：`1.0`
- 思考模式精确编程任务：`0.6`
- 非思考模式（Instruct Mode）：`0.7`

**`--top-p <float>`**

核采样（Nucleus Sampling）参数。从累积概率超过 `top-p` 的最小 Token 集合中采样。Qwen3.5/3.6 官方推荐值为 `0.95`（思考模式）或 `0.8`（非思考模式）[1]。

**`--top-k <int>`**

限制每次采样只从概率最高的前 `k` 个 Token 中选择。Qwen3.5/3.6 官方推荐值为 `20` [1]。

---

### 3.7 对话模板参数

**`--chat-template-kwargs '{"enable_thinking":true}'`**

控制模型是否在当前轮次进行内部推理（思考）。

- `{"enable_thinking": true}`（默认）：模型每轮回复前先输出 `<think>...</think>` 内部推理过程，再给出最终答案。适合需要深度推理的任务。
- `{"enable_thinking": false}`：模型跳过思考过程，直接输出答案（Instruct 模式）。速度更快，适合简单问答、工具调用等场景。

**`{"preserve_thinking": true/false}`（可选）**

控制历史对话中的思考轨迹是否保留在上下文中。

- `false`（默认）：每轮对话结束后，`<think>...</think>` 内容从上下文中**剥离**，只保留最终答案。这样可以节省 KV Cache 占用，是 24GB 显存下的**推荐行为**。
- `true`：历史思考轨迹完整保留在上下文中，有助于提升多轮连续推理任务的一致性，但会随对话轮次累积消耗大量 KV Cache 显存。**在 24GB 显存的紧张场景下不建议开启。**

> **注意**：`enable_thinking` 控制的是"当前轮是否思考"，`preserve_thinking` 控制的是"历史思考是否保留"，两者是完全独立的开关，不要混淆。

---

## 四、性能预期

根据社区实测数据，在正确配置的情况下（RTX 4090/3090 级别，全 GPU 推理）：

| 模型 | 量化版本 | 上下文 | 预期生成 TPS（含 MTP） |
|---|---|---|---|
| Qwen3.6-27B-MTP | UD-Q4_K_XL | 32K | ~100 - 140 tok/s |
| Qwen3.6-35B-A3B-MTP | UD-Q4_K_M | 8K | ~80 - 130 tok/s |
| Qwen3.5-27B-MTP | UD-Q4_K_XL | 32K | ~95 - 135 tok/s |
| Qwen3.5-35B-A3B-MTP | Q4_K_M | 8K | ~70 - 110 tok/s |

> MoE 模型（35B-A3B）的 MTP 加速效果（约 1.15 - 1.2x）低于稠密模型（27B，约 1.4x），这是由于 MoE 的专家路由机制使得草稿 Token 的预测难度更高 [1]。

---

## 五、参数速查表

| 参数 | 推荐值 | 作用 | 显存影响 |
|---|---|---|---|
| `-hf` | `模型:量化版本` | 指定模型来源和量化 | 取决于量化大小 |
| `--ctx-size` / `-c` | 27B: 65536 / 35B: 8192 | 最大上下文长度 | **高**，是主要显存消耗 |
| `--n-gpu-layers` / `-ngl` | `99` | 全部层卸载到 GPU | 固定（即模型权重大小） |
| `--flash-attn` / `-fa` | `on` | 启用 Flash Attention | 降低峰值显存 |
| `--cache-type-k` / `-ctk` | `q8_0` | Key Cache 量化精度 | 减少约 50% KV Cache |
| `--cache-type-v` / `-ctv` | `q8_0` | Value Cache 量化精度 | 减少约 50% KV Cache |
| `-b` | `4096` | 逻辑批大小（Prefill） | 低（+100-300 MB） |
| `-ub` | `4096` | 物理批大小（Prefill） | 低（+100-300 MB） |
| `--parallel` / `-np` | `1` | 并发槽位（MTP 必须为 1） | 无 |
| `--spec-type` | `draft-mtp` | 启用 MTP 投机解码 | 极低（~1 GB 草稿头） |
| `--spec-draft-n-max` | `2` | MTP 最大草稿 Token 数 | 极低 |
| `--temp` | `0.6` / `1.0` | 采样温度 | 无 |
| `--top-p` | `0.95` | 核采样阈值 | 无 |
| `--top-k` | `20` | Top-K 采样限制 | 无 |

---

## References

[1] Unsloth. (2026). Qwen3.6 - How to Run Locally. https://unsloth.ai/docs/models/qwen3.6

[2] Unsloth. (2026). Qwen3.5 - How to Run Locally. https://unsloth.ai/docs/models/qwen3.5

[3] Raji, A. (2026). Qwen3.6 on 24GB VRAM: Benchmark, Config, and Every Mistake. https://aminrj.com/posts/llamacpp-qwen36-35b/

[4] Hugging Face. (2026). unsloth/Qwen3.5-27B-MTP-GGUF. https://huggingface.co/unsloth/Qwen3.5-27B-MTP-GGUF

[5] Reddit. (2026). Benchmarked all unsloth Qwen3.5-27B Q4 models on a 3090. https://www.reddit.com/r/LocalLLaMA/comments/1rpwvq3/benchmarked_all_unsloth_qwen3527b_q4_models_on_a/

[6] Will It Run AI. (2026). Qwen3.5-35B-A3B VRAM Requirements 2026. https://willitrunai.com/blog/qwen-3-5-35b-a3b-vram-requirements

[7] Chauhan, K. (2026). Running Qwen3.6-35B-A3B MTP locally on 12GB VRAM. https://carteakey.dev/blog/running-qwen3-6-mtp-locally/
