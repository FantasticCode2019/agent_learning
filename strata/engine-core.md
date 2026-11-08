# Strata 引擎核心（token 生成主循环）

只读静态分析，未编译未运行。"推测"= 未直接读到。

## 0. 二进制与一个 token 的形状

- `strata generate` 即真引擎：`src/program/generate.cpp:3274` `engine_main`（Linux/macOS/CUDA 下 `main` 就是它；Windows+HIP 另有 :21478 的 `main`，把 `engine_main` 放到新线程并预留低 1 TiB 地址空间以避开 #3431 栈别名）。
- `strata-device`（`src/core/device_main.cpp:26`）= 显存/planner 探测 + `DeviceArena` 自检；`strata-load`（`src/core/load_main.cpp:1-4`）= pinned arena 加载基准。二者不服务请求，与 generate 无进程关系。
- 一条 token（`generate.cpp:1-16`）：`embed_row` → 48 层捕获图（CPU expert pool 挂在 doorbell 后）→ `lm_head` → sample → 下一 `embed_row`。引擎无 tokenizer，prompt 是 id 列表。

## 1. 启动顺序

1. 参数：`Options` :602（`serve` :920）、`usage` :1023；`--version/--families` 在碰 GPU 前 :3299-3313；`--gpu`→`CUDA_VISIBLE_DEVICES` :3340-3359；`CUDA_MODULE_LOADING=EAGER` :3326。
2. 权重：`pool_bytes` :5126、`wt.load` :5177；layer-split 每 stage 只载自己那段 `load_stage_weights` :5741-5776、`GpuStage` :5784。
3. 显存/会话：`session_bytes`+`cudaMalloc` :6695、`session_init` :6697、`session_zero` :6712；per-stage session :6730；drafter MTP :7001/:7115、DFlash2 :7144；head :7233-7297；`ExpertCache` :7806，自动定容 7808-8173。
4. 构图：`session_capture` :9106，每层 `pre[l]`/`post[l]` 一对（pre 以 router+doorbell 收尾）；token graph :9619-9626（48 层一次 launch）。
5. 热身：`warm_gemm_libraries` :7353、`session_replay warm` :9435-9441。
6. 服务：`READY <ctx> stop` :13993 → `for (;;)` :15323。无 `--serve` 的 CLI 一次性路径约在 :20300-21100（推测）。

## 2. `--serve` 的 IPC

- 纯 stdin/stdout 按行文本，无共享内存；协议注释 :9645-9666。
- 读：独立线程 `strata-stdin` :13697（`read(2)`+手写 `getline_fd`，不用 `std::cin` 以免退出卡 flush）；`STOP` 直接置 `stop_req` :13729；`should_stop` :13746 让 prefill 在 chunk 间可停。
- 主循环 :15323：batch/pipeline 在飞时非阻塞 `try_next_line`，否则阻塞 `next_line`（:15328/:15345）；EOF 结束进程。
- 请求 `GEN <max_new> [k=v …] <id,id,…>` :15706-15808（`GENI` 带图片 embedding）。键：`logit_bias/pen_from/cvec/ckpt/prefill/pin/temperature/top_p/top_k/logprobs/allowed/min_p/penalty_*/seed/pcie_frac/spec_min_p/draft/pipe/aux_cpus/img_keys` :15762-15805。
- 回传：`PP`（每 chunk）、`RESUME/REUSED`、`T <id>` :19248（验证窗一完即发）、`LP`（`emit_lp_line` :220）、`DONE …` :19587（字段 :19572-19581）、`ERR`。
- 取消：`STOP` :13729→`finish="cancel"` :19354；`QUIT` :15418；batch 有 `BSTOP` :15355、`BYIELD` :15375。服务端 `serve/server.py:1803/1817`（`send_stop`）、`GEN` :2287/:2775、`BGEN` :2421。

## 3. Prefill

- 两条路，`windows_ok` :16718 决定：短尾部（默认 ≤64，:964，或跨 image 行）走 verify 窗，长段走批量 `Prefill`；决策 :17943。
- 批量：`read_part` :17130 → `Prefill::run` → `prefill.cpp:3301 run_impl`；chunk 由 `request_chunk` :9709（向上取 256）/`planned_chunk` :9738 定，自动上限 :9761（默认 8192）。
- 层循环 `prefill.cpp:4037`：每层先 hyper-connection 读（`gr_norm` 4149、down GEMM 4168、`gr_silu` 4176、up 4181），half 0 注意力 `qsa_prompt_attn_batch_gated` 4587（同时写 KV cache），half 1 MoE `moe_fused`/MMQ 4707-4713；两半共享 scratch :1438，层内不能并行。
- 尾部窗：`read_windows` :16862，`T=min(S,b-q)` → `ver.run` :16892 → `ver.commit(T)`+`mtp.prefill` :16914。
- 复用：切点 `cuts={reread_to,root_at,message_at,turn_at,n-1}` :17894，每段 `checkpoint_at` :17983，打印 `REUSED` :18008。

## 4. 一次 decode step

:18845 起：①惩罚行上传 :19115-19125 ②`set_spec_q` :19138 ③`ver.run(T,window,p,…)` :19141（48 层：doorbell→CPU pool→combine→`post[l]`）④接受 `while (a<T-1 && window[a+1]==outv[a]) ++a` :19168（等于贪心即精确匹配）⑤`ver.commit(a+1)` :19202（回放 GDN/indexer）⑥发 `T <id>` :19248-19256 ⑦下一批草稿 `draft_long` :19277 / `df2.draft` :18865 ⑧`x=outv[a]; p+=a+1` :19355。

- 窗末 `outv[a]` 是模型自采样，即 **bonus token**（`spec_prob.hpp:25`）；全拒也白得 1 token。
- 窗宽 `T=--spec`（默认 0 不投机 :851-853；启动器在 dflash2 配置下传 `--spec 6`，`strata_control/drafting.py:11`），上限 `kVerifyNarrowT=8`/`kWindowMaxT=STRATA_VERIFY_MAX_T`（8/12/16，`window_limits.hpp:21-25`）。
- MTP `mtp.hpp:1-21`（一层、512 experts 全驻 VRAM）；DFlash2 `dflash2.hpp:1-14`（5 层，读第 5/15/25/35/45 层 hc 均值，一次前向 7 draft）。
- `Verifier`（`verify.hpp:96`）：`run` :122、`commit` :230；图内 48 层+final mixer+head（`verify.cpp:2605-2618`），**采样在图外**（`verify.hpp:150`：参数否则被烘死）。

## 5. 批处理与会话缓存

- 主线程一次只跑一个 `GEN`；并发仅来自 `--batch 2..8` 的 slot：`BSlot` :14176、`bs` :14207、每 slot 每 stage 一个 `SessionState` :6914。
- `batch_step` :14483 组窗（每 slot 1 行+draft 行 :14559-14568，`win_cap` :14493）；`pump` :15067 驱动 `batch_launch`/`batch_poll` :15251/:15095；`BGEN/BDONE/BSTOP`。
- 会话缓存：checkpoint=位置态（12 层 KV 等）+运行态（36 层 GDN 等），约 118 MB（:2197-2208）；只留当前 token 前缀的（:2207）；`CheckpointPool` :2258，`SAVE/RESTORE` :15472。

## 6. 线程模型

主线程（host/服务循环）；`strata-stdin` :13697；`strata-watchdog` :13943（`STRATA_WATCHDOG_S`=60 无心跳 `abort`，交服务端重启）；CPU pool `strata-pool-N`（`kernels/cpu/pool.cpp:927`，flat batch 非 ring，`pool.hpp:1-32`）；expert 源 `strata-io`/`strata-lookahead`/`strata-ram`/`strata-fill`（`expert_source.cpp:1260/3094/4505/6525`）；prefill `strata-stage`/`strata-hand`/`strata-issue`（`prefill.cpp:753/513/3901`）；`strata-adapt` :19201；`strata-ckpt` :2349。
同步：**Doorbell**（mapped pinned，`layer.hpp:424-451`；GPU 写 `h_seq`，host 自旋 `*seq>=want` 且每轮必须 `cudaEventQuery`，`session.cpp:692-713`，之后 `load_fence` :714）。测量见 `layer.hpp:405-423`（图开始 0.050 ms 即拿到 handoff）。

## 7. 采样

链：penalties→top_k→top_p→min_p→temperature→pick（`sampler.hpp:1-6`，实现 `src/kernels/cuda/sampler.cu`）；`SamplerParams` :15-31（`top_k` 默认 20、`top_p` 0.95、`logit_bias` 在惩罚前加、`greedy`）。每请求 `ver.set_sampling` :17797、`ver.set_logit_bias` :17793；惩罚 history 每窗上传 :19115。**grammar/structured 不在引擎**：服务端 "prompt_and_validate"（`serve/server.py:5778`）。

## 8. 停止条件

EOS 默认 `{248044,248046}` :905-907（`--eos-ids` :3713）→`finish="stop"` :19353；长度 `produced_n<max_new` :18845→`"length"`；`STOP`→`"cancel"` :19354；非有限 logits→`"nonfinite"` :19214；watchdog 60 s abort :13943-13990；GPU 致命错 `exit_if_gpu_fatal` :3244。stop strings 在服务端截断（`serve/server.py:4684/6257`）。
