# 模型表示与三级存储（只读静态分析）

三级：GPU = 一个 `cudaMalloc` 的 dense arena + KV + 专家槽；CPU RAM = 全部专家（pinned arena 或 mmap）；SSD = `experts.bin` + PLE 表。

## 1 GGUF 读取与校验

- 容器：`open(O_RDONLY)+mmap(MAP_PRIVATE)`（`include/strata/artifact/gguf_reader.hpp:455-463`，Windows 走 `MapViewOfFile` :435-452）。`magic=0x46554747`、version 必须 3、`n_tensors/n_kv`（:481-486）；metadata 进 `std::map<std::string,MetaValue>`（:488-492）；张量目录 = name/ndim(1..4)/shape/type/offset（:497-509），重名在 open 时拒绝（:500-501）；对齐取 `general.alignment`（默认 32），`data_start_`（:510-514）。ARRAY 只保留前 64 项但记 count（:380-389）。
- 分片：`GgufModel` 打开全部分片（:565-635），`validate_split` 要求 shard0 带 `general.architecture`、各分片 `split.count/no/tensors.count` 一致、目录求和相符（:603-631），跨片重名拒绝（:571-578）；理由注释：UD-Q4_K_XL 的 shard1 只有 metadata，head 和 PLE 在 shard2（:554-564）。
- 命名：`blk.<layer>.<suffix>`（`src/core/layout.cpp:137-139`）。每层必备 2-D 张量表在 `layout.cpp:50-80`（hc_*、ffn_gate_inp/shexp、GDN 的 attn_qkv/ssm_*、QSA 的 attn_q/k/v/output、indexer.q_proj/k_proj），1-D 表在 :96-107。专家是 3-D 的 `blk.N.ffn_{gate,up,down}_exps.weight`（`tools/strata_pack.py:48,350`），打包时按 expert 切片。
- geometry：`read_geometry`（gguf_reader.hpp:677-800）从 `kCompiledGeometry` 起步，键表 :707-728：必需 block_count/embedding_length/expert_count/expert_used_count/attention.head_count/head_count_kv，可选 full_attention_interval、ssm.*、key_length、rope.dimension_count、indexer.*、hyper_connection.*、expert_feed_forward_length。交叉校验 :736-764（value_length==head_dim、ff_shexp==n_ff、n_head%n_head_kv、ssm.inner_size、n_rot）、`attention.compress_ratios` 必须 48 项且只在 QSA 层非零（:768-798，全零视为转换器占位 #2396）。`geometry_unsupported`（:805-844）把 48 层/12 QSA/SSM/hc/idx 全部钉死，**只有专家数、每 token 专家数、词表可变**（:802-804）。字段与 GGUF 键一一对照见 `include/strata/core/geometry.hpp:23-68`；`is_qsa_layer = l%4==3`（:75-77）→ 12 QSA / 36 GDN。

## 2 内存布局

- 常驻 GPU：`index.txt` 列出的全部 dense 张量（含 `token_embd.weight`、`output.weight`）进**一个** arena：`WeightTable::pool_bytes` 先量（`include/strata/core/weights.hpp:119`）→ `cudaMalloc(&arena,pool_bytes)`（`src/program/generate.cpp:5126-5131`）→ `wt.load`（:5177）。arena 是 bump 分配、不 free（`include/strata/core/device.hpp:3,80`）。
- 加载路径：`fopen` + 两个 `cudaHostAlloc` 8 MiB bounce 复用 + `cudaMemcpy(H2D)`（`src/core/weights.cpp:257-258,463`）——**无 mmap、无 O_DIRECT**。清单 `index.txt` 每行 19 字段（:202），file_id 0=dense/1=embd/2=experts/3=extra（:64-70）。
- 引擎形态≠包形态：`WeightKind{Verbatim,Bf16InF32,F32,F16InF32}`（weights.hpp:41-46）；张量拆成 codes/scales/offset 三个 plane（:67-69），每个 `Seg` 一个变换（weights.cpp:50-56,71-77），90/303 个量化张量的 fp16 scale 在此被加宽成 f32（weights.hpp:11-18）。
- 常驻 CPU：48×512 个专家 blob，`ArenaExpertSource` 的 `PinnedArena`（`include/strata/core/expert_source.hpp:1283-1357`）；`--mmap-experts` 时改 `FileExpertSource` 映射 `experts.bin`（:732+）；`--resident-experts` 只 pin GPU 装不下的补集（:778）。
- SSD：PLE 表逐行读（见 §6）；mapped 模式下专家也来自 SSD/页缓存。
- 校验：`check_layer/check_all` 在加载时核对每个 kernel 形状与 1-D 张量的 engine form 字节数（`layout.cpp:45-171`），并数 12/36 层型（:149-169）。

## 3 量化格式与 kernel 路径

- 格式表 `block_geometry`（gguf_reader.hpp:140-277）：F32/F16/BF16、Q4_0…Q8_K、IQ1_S/IQ2_XXS/IQ2_XS/IQ3_XXS/IQ3_S/IQ4_NL/IQ4_XS、MXFP4/NVFP4、TQ/PTQ。例：Q2_0=64 elem/18 B（:239-242）、IQ3_XXS=256/98、Q4_K=256/144、Q6_K=256/210、IQ4_NL=32/18。
- 典型包默认：attn/SSM/hc/shexp/PLE key、token_embd、head = Q8_0（UD-IQ4_XS 的 head 为 Q6_K），router F32、indexer BF16；路由专家 gate/up = Q2_0（canonical 包）或 IQ3_S/Q4_K，down = IQ4_NL/Q5_1/Q8_0（`docs/QUANTS.md:22-33`）；PLE 表 IQ4_NL 26.8 GiB 或 Q8_0 50.7 GiB。
- 激活格式不可由权重推出：`act_kind` + `wants_q8k()` 处理 Q5_0/Q5_K、IQ4_NL/IQ4_XS 这类 S-form 表达不了的对（weights.hpp:83-84；`tools/pack_index.py:81-88`）。
- kernel 选择不在 arch/family 表里，而是三层：①编译期按 ISA 分 TU（`src/kernels/cpu/q2_avx{1,2}.cpp`、`iq_avx{1,2,512}.cpp`、`kq_avx{1,2}.cpp`、`nvfp4_avx{2,512}.cpp`）+ 运行时 probe `cpu_avx512_ok/cpu_avx2_ok`、`STRATA_FORCE_ISA`（`include/strata/kernels/cpu/expert_layout.hpp:46-67`）；②按格式选，AVX-512 要求 F+BW+VL+VNNI+VBMI（`expert.hpp:96-101`）；③没有 AVX2 的 x86 落到 ggml-cpu 的 scalar `_generic` 点积（`src/kernels/cpu/iq_avx1.cpp:9-11`）。arch（gfx1151/gfx12 等）只通过默认 env 开关挑 kernel 变体（`src/core/arch_defaults.cpp:27-106`），family 只决定模型代码路径与受支持的 geometry（gguf_reader.hpp:638-641,849-857）——"按 family 切 kernel"属推测。

## 4 专家缓存

- 结构：`residency_[n_layers*n_expert] → slot`（`include/strata/core/expert_cache.hpp:266`）、`layer_next_`（:276）、`off_`（:277）、`live_slots_`（可 shrink，#533）。
- 策略：`admit` **从不驱逐**，匿名先到先得（:160）；`replace` 显式换（:163）；`set_per_layer_admission` 给每层固定槽区间（:185）；自适应 tier = 带衰减的 LFU：`adapt_every=4`、`adapt_decay=0.7`、`adapt_min_gain=1.5`、`adapt_swaps=96`（generate.cpp:885-923）。
- 容量：`auto_cache_slots(free_b, reserve_b, blob, min_slots, kLateAllocMib)`（`include/strata/core/auto_cache.hpp:33-47`），`blob = nibble_max_slot_bytes()`（generate.cpp:7903），reserve 含 `--vram-reserve-mib`+prefill+`mtp_bind`（:7902）；`kLateAllocMib=256` 补偿加载后 cuBLAS 等未计价分配（auto_cache.hpp:23）。
- 预热/学习：`profile.bin`（`STRP` + ranked 对 + n_layers×n_expert 频次，expert_cache.hpp:54-79；expert_cache.cpp:261-300）；`rank_learned_profile` 排序 = 已驻留 → heat → prior（expert_cache.cpp:233-262）。
- 与 CPU pool 协作：miss 在 host 线程 `pool(...)`（`src/core/session.cpp:731-732`），命中的专家由 GPU grouped kernel 算，`moe_combine` 在**本层**合并（:760-775 注释）。`ExpertSource` 是"专家字节从哪来"的抽象：mmap 文件 / pinned RAM / PCIe 别名 / 预取（expert_source.hpp:189-305）。

## 5 CPU 侧专家计算

- 内存：pinned arena + `cudaHostAlloc` staging；`pin_budget` 软/硬预留（Windows CUDA 640+160 MiB）与 `STRATA_ARENA_PIN_GIB` 提示（`include/strata/core/pin_budget.hpp:101-213`）。
- 线程池 `ExpertPool`：`run/run_split/run_split_multi/run_split_multi_native`（`include/strata/kernels/cpu/pool.hpp:238-250`），P/E 核与 NUMA 双片（:172-181），core 0 留给 host 自旋（:190），epoch+原子 head/done 领取任务（:339-340）。
- 内核：AVX2 `unpack_q2_0/block_dot`（`src/kernels/cpu/expert.cpp:124-138`）、AVX-512 multishift 16-code（:156-185）；IQ/K-quant/NVFP4 各有 avx1/avx2/avx512 实现。
- 与 GPU 并行：每层切两张图，router 后打 doorbell；host 自旋 `h_seq` 并用 `cudaEventQuery` 判断图是否还在跑（session.cpp:699-720），拿到 pinned `x_f/ids/weights` 后 GPU 先 launch、CPU pool 同时算（:726-740），结果 H2D 后 `post` 图合并（:751-768）。

## 6 PLE / n-gram 表

- 320,001,536 行 × 90 B（IQ4_NL，26.8 GiB）或 160 B（FP8，51.2 GB），**从不常驻内存**：每次 4 KiB 无缓冲读（`platform::DirectFile`），一个 token 要 16 行分散在 16 页（`include/strata/ngram/ple_reader.hpp:3-11`）。
- API：`issue(rows,n,out)`（token id 一确定就发）→ `collect(t)`（层 1 读前收），prefill 可一次发 16×N 行、按页去重排序（:7-12,62-73）。
- 缓存：行缓存（clock 驱逐），1M 行≈95 MB 可服务约 82% 读，长 prompt 内 20-34% 行复现；`set_keepalive` 防 SSD 睡（:14-16,76-84）；容量 0 关闭。
- 用法：`PleTable`（generate.cpp:5343），只在 layer 1 加回残差（`src/core/layer.cpp:1495-1525`）。prompt lookup 草稿是另一套（`src/split` 的 `suffix_draft`，`include/strata/core/lookup_default.hpp:18-25`），与本表无数据依赖——推测二者只在 spec 路径各自独立。

## 7 会话缓存

- 内存级 `ConversationCache(budget,slots)`（`include/strata/core/conversation_cache.hpp:240-299`）：按 token 前缀比较（:211-238）、最长匹配、`retain` 整份 KV、pinned 条目不被淘汰、旧的最先逐出；日志有 borrowed（子 agent 共享系统提示）。
- 文件级：`session_file_write/read`（`include/strata/core/conversation_file.hpp:162-178`），身份 = 模型（大小+首尾 MiB 指纹）+ 配置指纹（引擎版本、backend、`--kv`、`STRATA_KV_ROT`、`--kv-resident`、`--max-context`、`--mtp-window`、rope）（:25-98）；写入先落临时文件再 rename + 目录 fsync（SessionWriteOptions :144-148；实现在 `src/core/conversation_file.cpp:462-489`）。
- 粒度：`--prompt-cache-every N` 个 token 一个 checkpoint，另有 root checkpoint（`docs/DETAILS.md:726`）；checkpoint 含 GDN 状态、每 QSA 层 K/V 与 indexer、draft 层。
- 并发：`STRATA_CKPT_ASYNC=1` 时后台线程搬 GDN 状态，4 MiB 双 pinned 缓冲、每层 copy stream（`include/strata/core/conversation_snapshot.hpp:73-85`），读者先 `conversation_checkpoint_join`（:79）。

## 8 显存预算与 low-RAM

- 先算后分：`pool_bytes` 不加载即量出 dense arena，装不下就拒绝启动（weights.hpp:116-121）；`cudaMalloc` 失败时打印 free/total（generate.cpp:5126-5157）。
- 专家槽：`(free - reserve)/blob`，再与 `min_slots`（借给 prefill 256 token 的缓冲 + 128 槽）比较（generate.cpp:7906-7916）。
- 多卡/层切分：对每个候选 `[lb,le)` 用裁剪后 `pool_bytes` 重新计价（generate.cpp:5974-5989）。
- low-RAM 三档（`docs/DETAILS.md:242-252`）：`--mmap-experts`（专家走文件/页缓存）、`--resident-experts`（把 GPU 装不下的专家整份拷进 RAM）、`--resident-budget-gib N`（按 profile 热度拷 N GiB）；`--ram-keep-gib` 与 4 GiB（Windows 8 GiB）headroom（generate.cpp:723,1294；expert_source.hpp:1337-1346）。RAM 不足时 `fall_back_when_ram_short` 让调用方改用 mmap 模式（expert_source.hpp:1337）。
