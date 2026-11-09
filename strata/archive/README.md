# 原始材料归档

[返回学习地图](../README.md) · [来源与版本说明](../SOURCES.md)

这里保留整理前的材料，供追溯和进阶查阅。入门阅读请以新章节为主：原稿含密集行号、不同版本的默认值及尚未展开的术语，不能把其中每一条描述直接当成当前两个项目的共同实现。

## Strata 原始笔记

| 原稿 | 新手册中的主要去向 |
|---|---|
| [cli-launch.md](strata-notes/cli-launch.md) | 整体架构、源码阅读：安装/启动控制链路 |
| [server.md](strata-notes/server.md) | 整体架构、数据流、推理流程：API、IPC、排队与输出 |
| [engine-core.md](strata-notes/engine-core.md) | 推理流程、源码阅读：请求阶段与状态提交 |
| [memory-weights.md](strata-notes/memory-weights.md) | 数据流：参数、专家层级、会话状态与缓存 |
| [kernels-spec.md](strata-notes/kernels-spec.md) | 推理流程、Basalt 优化：算子与推测执行 |
| [dsv41-split-ports.md](strata-notes/dsv41-split-ports.md) | 整体架构和架构差异：模型专用引擎、split、后端 |

正式编号的旧 Mermaid 源图和对应 SVG 保留在 `strata-notes/diagrams/`。原目录里的实验图、重复预览图、带失效绝对路径的渲染脚本没有进入学习入口。

## Basalt 原报告

- [Basalt 项目分析](basalt-analysis-2026-11-08/Basalt项目分析.md)：完整比较、性能数据及固定源码引用。
- [原交互式架构图](basalt-analysis-2026-11-08/.archify/architecture-basalt-20261108-143000/basalt-architecture.html)：可独立打开。

Basalt 原报告及其附属文件按字节复制。旧 JSON 回执中的绝对路径、校验记录和浏览器检查描述的是原交付位置；归档不会自动改变它们，也不表示在此新路径再次运行过 Archify 验收。

[source-manifest.json](source-manifest.json) 记录复制来源、目标和 SHA-256。原素材位于 Obsidian 的 `agent_learning` 目录，本次整理未改写该目录中的文件。
