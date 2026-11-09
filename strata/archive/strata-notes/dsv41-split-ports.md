# dsv41 / split / Metal / SYCL 三条支线

## 1 DeepSeek V4.1（`strata-dsv41`）

- 40 层/384 专家/每词 6；MLA+压缩 KV+DSA+Engram+DSpark（ds4_model.cu:551）；注意力 64 头 MQA、窗口+FP4 行（ds4_attn_split.cuh:4-6）。
- 专家 MXFP4/低比特，支持 IQ1_M/IQ2_XXS/IQ2_XS（ds4_iq.cuh:23-24）＝1.75/2.00/2.25 bpw（DEEPSEEK41.md:29）。
- 单独二进制：独立包与协议、主引擎不认其选项（ds4_main.cpp:9-13；CMakeLists.txt:974-977）。
- 上下文 32768（ds4_model.hpp:28）、CLI 8192（dsv41_fit.py:507）；Faster/Full＝5/6 专家（ds4_experts_rule.hpp:30-31），小显存默认 Faster。
- 布局：层按段分卡（ds4_model.cu:2993-3005）；dense 常驻 VRAM，仅 routed 下沉：VRAM→RAM（ds4_store.hpp:1-12）→CPU mmap（ds4_model.hpp:43）/PCIe（ds4_pcie.hpp:1-9）→SSD。

## 2 split（`strata-split-N`）

- 单进程单机 N 卡，无网络代码（无多机）。
- 每层在每卡都算：切 heads、专家 FF 宽度、词表（model.hpp:1-4）；KV 每卡 1/NCARD 位置（kernels.hpp:138-144）。
- NVIDIA 无 peer，求和走 page-locked host（CMakeLists.txt:1-18）；prompt 沿 ring（pf_ring_plan.hpp:1-8）；AMD 可 peer push/RCCL；无需 NVLink（MULTI_GPU.md:102）。
- 会话在进程内（session.hpp:1-4），可存 host（engine.hpp:194-210）；跨卡交接用 SPLIT_SERVE 的 SAVE/RESTORE。
- 实为 `strata split-engine apply`（split_cmd.py:1-3），launch 自动改 exe/args 并回退（split_engine.py:269-295）；auto：NVIDIA 2 卡、AMD 4 卡 gfx1201。

## 3 Metal

- 同一套 host 源、独立二进制；CUDA 名经 metal_compat 映射，内核用 MSL（metal/CMakeLists.txt:1-9,:98-110）；DeepSeek 另出 strata_ds4（:131-172）。
- 统一内存：KV 与专家都在 MTLBuffer storageModeShared（runtime.cpp:3-11）；专家另用 SSD arena+预读，keep=max(7 GB,15%)（arena_budget.h:1-20）。
- 支持 Qwen3.8 Q2_0/IQ3_/Q4~Q6/Gyro，DeepSeek 2.00/2.25；限制：DeepSeek 纯文本、实测 32K、Qwen3.6 不支持。

## 4 SYCL

- 独立工程，源自 ../src，dpct 迁成 58 个 .dp.cpp（sycl/CMakeLists.txt:1-15）。
- kernel 1:1 映射，int8 DPAS/ESIMD；默认 SPIR-V JIT，AOT 用 -DSTRATA_SYCL_AOT=bmg-g31（:24）。
- 仅 Linux x86_64（targets.py:22-28），自带 oneAPI 运行时。

## 5 选择

- 包目录 `components/engine/<ver>-<平台>-<后端>`（cfg_paths.py:4-5），可写 `component:strata-engine`（engine_component.py:1155）；intel→sycl（targets.py:22-28）。
- dsv41：`engine-dsv41/`、exe `strata-dsv41`、arch=deepseek41（dsv41_engine.py:3-8）。
- split：二进制在引擎包内，`strata-split-N-sm<cc>`/`-gfx1201`（split_engine.py:575-580）。
