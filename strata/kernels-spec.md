# Strata 内核与单层数学（Qwen3.8-Flash-Next / arch `qwen4exp`）

几何：48 层、`qsa_interval=4`、`is_qsa_layer`=`layer%4==3`（include/strata/core/geometry.hpp:25-26,75-76）→ 12 层 QSA 全注意力 + 36 层 GDN 线性注意力；n_embd 2560、4 条残差流（hc=4）、每层 512 专家（48×512=24576）、top-10。

## 1 单层前向
入口 `block_layer_pre`（src/core/layer.cpp:1473），按 stage 顺序：
- stage0 `gr_read(R,w_norm,w_down,w_up,w_inject)`→`mixed`/`inject`（layer.cpp:1558；融合版 :1556）
- stage1 混合器 `if(qsa) qsa_layer else gdn_layer`（layer.cpp:1562；`qsa` 见 :1531）
- stage2 `gr_write(R,block_out,inject)`（:1564）
- stage3 第二次 `gr_read`（`hc_ffn_*`）→`inject2`（:1582；融合版 :1580）
- stage4 `moe_route`（:1585）+`moe_shared`（:1587）

`block_layer_post`（:1622）= `moe_finish`（等 host 专家池回填 `parts`）→combine→`gr_write`；`block_layer`（:1647）=pre+post。所以残差不是 `x+attn`，而是每层两次超连接读、两次写、一次混合器、一次 MoE。
- GR 数学（include/strata/kernels/gr.hpp:112-128）：`lo=silu((bf16(xn)@w_down.T)/hc)`（÷hc 在 silu 内）、`mixed=mean_c(xn*sigmoid(bf16(lo)@w_up.T))`、`inject=bf16(xn)@w_inject.T`；写回 `R[i]+=block_out[d]*2*sigmoid(inject/hc)`。
- GDN 层（layer.cpp:251-384）：`gemv_quantized(attn_qkv)`→conv+`silu_inplace`（先整段 SiLU 再切 q|k|v）→`native_gdn_l2_norm`（只 norm q,k）→`native_gdn_beta_gate`+`native_gdn_gate`→`native_gdn_step`→`gemv_quantized(attn_gate)`→`native_gdn_out_norm`（y=rms(o)·ssm_norm·sigmoid(z)）→`gemv_quantized(ssm_out)`。
- QSA 层（layer.cpp:1144-1324）：bf16 idx 投影→`gemv_quantized(attn_k/v)`→`normalize_rotate`→`kv_append_*`(+`fwht256_inplace_cuda`)→`native_qsa_indexer_append`→`gemv_quantized(attn_q)`（q|gate 取前后半）→`qsa_block_scores`+`qsa_block_topk`→`qsa_kv_resolve`→`qsa_decode_attn_step`→`native_qsa_gate_apply`→`gemv_quantized(attn_output)`。即"先 top-k 选 cell，再只对选中 cell 做 attention"。
- PLE（仅 layer 1，layer.cpp:1511）：`ple_block` 把 16 行 160 维投影进 4 条残差流；ngram hash 与行 gather 在 host（:1482-1489）。
- head：`gemv_quantized(wo,…,head_q8k,logits)`（:1426）。

## 2 MoE
- 路由：`project_bf16`(bf16_gemv_split)→`native_router_top10`（512/10 专用；softmax、无 selection bias、并列取小下标）否则 `router_top10`（layer.cpp:405-440）；路由权重必须 bf16（layer.hpp:124-160）。
- 每 token 激活 10 个 routed + 1 个 shared（共 11 路）。shared 与路由无关：`moe_shared` 用 bf16 标量 gate（layer.cpp:468），`moe_combine_parts`/`native_moe_combine` 按 10 个权重求和（:514），shared 结果直接相加不占 top-10 名额。
- prefill 分组：每 16 专家一次 MMQ（src/prefill/prefill.cpp:1464 `MMQ_GROUP`；组缓冲 `MMQ_TAIL=4096` 填充 :1470；`MmqPlan` :1484 选 direct/group_sort）；`pf_wmma()`（:1500）=IQ 权重走 FP16 tensor-core 分组 GEMM。
- 融合 gate/up：Q2_0 核用 int8 `mma.sync m16n8k32` + magic-add（`as_float(0x4B400000+dot)` 一次减掉 int8 偏置），THREADS=512/WROWS=256/STAGES=4，gate 在行 2f、up 在 2f+1（src/prefill/moe_fused.cu:1-40）。
- WS 变体（include/strata/prefill/moe_ws.hpp）：权重驻留，gate/up 与 down 各一次 launch，仅 sm_60/GP100 实验路径。
- decode：`native_route_resident` 可把 margin 内的非驻留尾 rank 专家换成驻留专家（native_router.hpp）。

## 3 量化核
- MMVQ（decode）：量化权重×Q8_1 激活、ncols 1..8、纯 dp4a 无 tensor core（src/kernels/cuda/native_mmvq.cu:27）；覆盖 Q2_0/Q4_0/Q5_0/Q8_0/Q3_K/Q4_K/Q5_K/Q6_K/IQ4_NL/IQ4_XS（include/strata/kernels/native_mmvq.hpp:5-30）。
- MMQ（prompt）：llama.cpp `mmq.cuh`（固定 commit，MIT），int8 tensor core + q8_1 激活、按专家 gather；IQ trellis 由 `is_tq` 给 34/26/30/42/50/58 B/128 权（src/prefill/moe_mmq.cu:144-149）。
- 统一分发 `gemv_quantized`（layer.cpp:168）：native→MMVQ；2-bit→`s2_gemv_q8`；否则 `s_gemv_q8_0_split`/`s_gemv_q8k_split`。SForm 的 `act_kind`（Q8_0 vs Q8_K）不可由其它字段推出（s_gemv.hpp:21）。
- NVFP4：W4A8（int8 tc，默认）/W4A4（仅 sm_120a 的 FP4 MMA，首 token KL 0.0004-0.03）/FP16 参考（mmq_nvfp4_w4a4.cu:1-8；moe_mmq.hpp:22）。
- FP8 只用于 PLE 表行反量化（ngram.hpp:48），无 FP8 GEMM；dense 投影是 cuBLAS/hipBLASLt BF16（gemm.hpp:6），WMMA 只在 `bf16_hcd_exact` 这类定点复现路径（src/prefill/wmma_gemm.cu），未见 WGMMA。

## 4 Prefill
- 一个 chunk 走完 48 层：投影=tensor-core GEMM（量化权重即时反量化到 BF16/FP16），线性注意力递推在一核内走完 chunk，专家按专家分组、非驻留者经 pinned ring 从 host arena 拷贝（include/strata/prefill/prefill.hpp:1-20）。
- 8K chunk：`--prefill auto` 取 32768/16384/8192（默认 8192），Windows HIP 封顶 6144（src/program/generate.cpp:3543-3565；host_limits.hpp:24）；auto 从大到小试装（:10840-10862），不足退 1024/512/256（:8005-8026）。
- 专家环：`ring_slots()` 个 slot，拷贝流 `m.copy` + 每 slot 事件 `m.copied`，算流 `cudaStreamWaitEvent`（prefill.cpp:3999,4008），`m.used` 记录用完才复用→双缓冲。设计目的写明"让上一层专家在本层 attention 期间到达"（:230-233；实测 384 slot 1294 vs 96 slot 1153 tok/s，:329）。
- 预取深度：`staged<=j+lookahead`，`lookahead=group_resident?STAGE_GRP-MMQ_GROUP-1:STAGE-1`（:6029-6053）；`STAGE=8`（:217）、`stream_all_min=1024`（:261）；KV 另用 `m.kv_copy` 预取（:3345-3364）。
- GDN chunked 扫描：64 token/块，`gdn_chunk_cumsum/kkt/fwd`（src/prefill/gdn_chunk.cu:49,72,123），解 `(I+lower(A))δ=b`；仅 Volta cc7.0 启用、非逐位一致（gdn_chunk.hpp）。

## 5 KV
- 默认 fp16 分页 `[page][kv_head][page_size][head_dim]`，page_size=4 cell（include/strata/kernels/qsa.hpp:63-76,115）；可选 INT8（code+每 64 个 fp16 scale）、Q4_0（FWHT-256 旋转，144 B/head/cell）、K8V4 混合（kv_stream.hpp:36）。
- 长上下文分层：`--kv-resident` 时权威 K/V 在 pinned host，VRAM 只放 `n_slots` 页，`page_table` 变驻留图（-1=不在）；`kv_stream_resolve` 在 attention 前把选中块搬入 VRAM（1024 线程 walk→CLOCK 二次机会换出→零拷贝 PCIe），写者恒写 host、仅驻留时写 slot，故拒绝草稿/恢复会话无需失效（kv_stream.hpp:1-20）。VRAM 窗口下限 4096 cell 够用，因每行最多读 2051 cell（layer.cpp:772）。
- QSA 特殊性：选择宽度 `min(n_kv, idx_top_k+idx_block-1)=2051`（qsa.hpp:133），attention 只读选中 cell；per-token 老选择器上限 32768 cell（qsa.hpp:279-282），更长上下文改用 block 选择/two-pass，为 3xTF32 打分 + 误差界内重算（qsa_two_pass.hpp:1-20）。
- prompt attention 用 m16n8k16 FP16 MMA + online softmax，q/p 拆 hi+lo 保 ~22 bit（qsa_prompt_attn.hpp:1-20）。

## 6 投机解码
- MTP 层（include/strata/core/mtp.hpp:1-40）：`e=fc_embedding(rms(embed)*(1+w))`、`h=fc_hidden(rms10240(R)*(1+w))`、`R=h+e`→QSA（自带 KV）→MoE(512/10)→`R+=y*2sigmoid(inject/hc)`→head；实测接受 0.89/0.86/0.85，草稿 3-4 条。
- DFlash2（include/strata/core/dflash2.hpp:1-25）：5 层 2560 隐层、吃第 5/15/25/35/45 层 hidden tap，anchor+7 mask 一次前向出 7 草稿，head top-16 + rank-256 选择器走路径；ring 只存已提交行，被拒零回滚；每 n=1..8 一个 graph。
- 控制流：`choose_window()` 定 T（window_rule.hpp）→`DraftPolicy::choose()` 按 E[committed]/cost 在 MTP 与 lookup 间选（draft_policy.hpp:1-30，margin 0.03、kMaxT=16）→verify→`policy.observe()`（generate.cpp:21113）。放弃草稿：`Controller` 只在最优选择比朴素解码多出 5% 以上时才取 k>0，否则 k=0 直接 decode（include/strata/spec/controller.hpp:1-15）。suffix drafter 三元组哈希 + 4 路最近位置（suffix_drafter.hpp）；gated proposal 只掩码概率、不重归一（gated_proposal.hpp）。
- 验证：T 行一次 graph 过 48 层，每行 argmax 与逐 token 贪心逐位相同，故"接受=贪心也会产出"（verify.hpp:1-22）；`commit(n_keep)` 用存下的输入重放 GDN conv/递推、恢复 indexer key tail 并重 append、PLE 历史回滚，越界 K/V 直接被覆盖；窗口受 `min(win_cap, max_context-p)` 截断（generate.cpp:20935）。

## 7 采样
- 链：penalties→top_k→top_p→min_p→temperature→pick（include/strata/kernels/sampler.hpp:1-20）；`logit_bias` 在 penalty/filter 之前加、-inf 即封禁；验证窗口每行有独立 history。
- `logits`/`out` 必须是 device 指针（sampler.hpp:24-40 明确警告）；贪心可走 8-CTA cluster（sm_90+）；STRATA_SPEC_PROB 时用拒绝采样把草稿 q 与目标 p 对齐（sampler.hpp 后半）。
