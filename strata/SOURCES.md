# 来源、版本与整理范围

[返回学习手册](README.md) · [原始材料归档](archive/README.md)

整理日期：2026-11-08。本手册把原 Strata 六篇笔记与 Basalt 分析重写为同一条学习路线。共同概念先解释，项目差异再展开，原稿保留以便追溯。

## 1. 为什么固定到具体提交

项目在继续演进，“Strata 支持什么”若没有版本和执行路径，就很容易与旧笔记冲突。本手册采用本地可复核的源码快照，不将其标为最新版本。

| 材料 | 固定版本 | 用途 |
|---|---|---|
| Strata 源码 | [`ffa80d73133ea5c548aefe57889a16e8085a938f`](https://github.com/Niko1221/Strata/tree/ffa80d73133ea5c548aefe57889a16e8085a938f) | 整体架构、服务、数据流、推理与源码路线的学习基线 |
| Basalt 源码 | [`4998eb3733ee83b7e7d6ff94854c399dd89cfebe`](https://github.com/jesdga95/basalt/tree/4998eb3733ee83b7e7d6ff94854c399dd89cfebe) | Basalt 0.3.1 的硬件优化、服务与模型接口 |
| 历史 Strata 断面 | [`e69c1fb6f129bf813e655b818b91414fb894c0a3`](https://github.com/jesdga95/basalt/tree/e69c1fb6f129bf813e655b818b91414fb894c0a3) | 识别 Basalt 继承的基础机制，不代替当前 Strata 对照 |
| 原 Strata 笔记 | 其中启动笔记标注 0.2.12 / engine 0.1.58 | 原始学习材料，行号与默认值需重新核对 |
| 原 Basalt 分析 | `basalt-analysis-2026-11-08` | 保留完整历史分析、性能记录与交互式图表 |

Strata 学习快照的 [AGENTS.md](https://github.com/Niko1221/Strata/blob/ffa80d73133ea5c548aefe57889a16e8085a938f/AGENTS.md) 标注应用 0.2.10 / engine 0.1.56，和原笔记并非同一版本。正文已重新核对关键入口，不能把原稿行号直接套用。历史 `e69c1fb6` 在当时 [CMake](https://github.com/jesdga95/basalt/blob/e69c1fb6f129bf813e655b818b91414fb894c0a3/CMakeLists.txt#L12) 中标为 Strata 0.1.39；这里没有将它认定为今日两个仓库的严格 merge-base。

## 2. 三种证据分别能说明什么

| 证据 | 可以支持 | 不能独自支持 |
|---|---|---|
| 源码和接口合同 | 某个条件分支、调用顺序、内存/状态职责确实存在 | 当前机器实际选了该路径，或一定更快 |
| 项目文档与提交记录 | 作者说明的适用条件、设计目的和测量结果 | 独立复测结论，或对所有模型/硬件的普遍保证 |
| 教学图与假设例子 | 帮助理解因果、阶段和数据流 | 真实模型的专家数量、精确 kernel 时序或性能 |

各章源码链接使用固定提交。性能数字在句旁标出项目记录；本次没有运行 5090 推理、GPU benchmark、数值精度测试，也没有编译两个引擎。图中的“4 个专家选 2 个”等是明确标注的教学假设。

## 3. 整理时处理的关键区别

- **继承与新增：** CPU/GPU 异构、文件后备、CUDA Graph、MTP 和多卡已有历史基础；Basalt 的重点是 sm_120 专用执行、调度优化及后续组织重构。
- **历史与当前：** 当前 Strata 学习基线也有 NVFP4 和独立 all-cards split 引擎，不能根据早期断面将它们写成 Basalt 独有或 Strata 缺失。
- **文件与数值格式：** `.basalt` 是分区资源容器；NVFP4、Q6_K 等描述具体权重/数值表达，两者不是同一层概念。
- **精度与阶段：** NVFP4 decode 与满足阈值的 FP4 prefill 使用不同计算路径，“4-bit 模型”不表示全程 W4A4。
- **服务与设备：** Python/原生进程的 stdin/stdout 协议，和 CPU/GPU 的 pinned/mapped 通信，是不同边界。
- **专家与会话：** 专家缓存保存权重，KV/递归状态与 checkpoint 保存会话历史；二者的命中与淘汰含义不同。
- **多种并行：** HTTP 连接、slot、replica、expert tier、layer split、tensor split、prefill/decode 分离逐一说明，避免统称“多卡并行”。
- **模型条件：** Qwen 与 DeepSeek 的 session、KV、draft、peer 数量和并发实现分开标注，避免把一个模型的默认值泛化到整个引擎。

## 4. 材料如何合并

| 原材料 | 新的主要阅读位置 |
|---|---|
| Strata cli-launch、server | [整体架构](02-architecture.md)、[源码路线](05-source-reading.md) |
| Strata memory-weights | [数据流向](03-dataflow.md)、[基础概念](01-foundations.md) |
| Strata engine-core、kernels-spec | [完整推理流程](04-inference.md) |
| Strata dsv41-split-ports | [架构差异](basalt/02-architecture-differences.md) |
| Basalt 原分析的历史比较 | [Basalt 专章入口](basalt/README.md) |
| Basalt 原分析的硬件/性能内容 | [Blackwell 优化](basalt/01-blackwell-optimizations.md) |
| 原图与详细分析 | [归档](archive/README.md)，新手册另有配套图表 |

这次合并的是文档与知识结构，没有把两个项目的引擎源码、模型格式或配置合并成一个软件。现有 Basalt 源码与原 Obsidian 材料不在本次改写范围内。

## 5. 图表和交付检查

正文中的 Mermaid 是图表内容的源文件，SVG 是同一内容的渲染结果。架构图说明组件职责，数据流图注明数据类型，时序图展示执行先后与等待关系；它们不是 profiler trace。

新文档的相对链接、固定源码文件与行号范围、Mermaid 渲染、归档字节一致性分别检查。具体结果与范围见 [validation.json](validation.json)；图表列表见[图表目录](assets/README.md)。旧 Basalt 归档中的 Archify JSON 是原报告的检查记录，不充当新手册的验收记录。

以后更新时，先修改分章正文，再同步 Mermaid/SVG 和单文件阅读版；同时更新源码提交与验证记录。若换了模型、后端或执行模式，应重新追踪条件分支，不能只替换版本号。
