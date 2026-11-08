# Strata serve/ 服务器架构与请求生命周期

总览：纯标准库 `http.server`（非 asyncio），每连接一线程；引擎是常驻子进程，stdin/stdout 行协议；`Service.fifo` 把每次生成排成 FIFO，`--batch/--slots/--parallel` 时引擎内部再并行 slot。

## 1 HTTP 栈、入口、路由、中间件
- 入口 `python -m serve.server --engine strata --config X.json [--port 8095]`：`main` server.py:9874 → `_main` :9902（argparse :9918 起）；`Server(ThreadingHTTPServer)` :8946，`serve()` :9231 绑定并 `serve_forever`。
- `make_handler(svc)` :7536 造 `Handler(BaseHTTPRequestHandler)`；`protocol_version="HTTP/1.0"` :7538，`end_headers` 恒发 `Connection: close` :7697/:7702（SSE 以关连接结束）。
- 无路由表：`do_GET` :7809 / `do_POST` :8191 内按 `self.path`（去 query、`rstrip("/")`、`V1_V1_ALIASES` :293/:8201）逐条 if/elif。
- 中间件即 Handler 方法：鉴权 `_authorized` :7788（Bearer 或 x-api-key，遥测另有 `_authorized_telemetry` :7798）；CORS `_cors` :7739 仅 `/v1/*` + `cors_origins`，`do_OPTIONS` :7760 回 204；`log_message` 静默 :7546；无 gzip。
- 防护：无 key 时 Host 校验防 DNS rebinding :7667；`_foreign_page` :7676 要求 Origin 白名单 + JSON；`/unload`、`/load`、`/slots/*` 需 `_own_page` :8474。体积 `body_limit()` :7517，支持 chunked :7552，未读 body 5 s 排空 :7624。

## 2 服务器 ↔ 引擎进程
- `StrataEngine.__init__` :1144；:1210 `popen([exe,"--serve",*args], stdin/stdout=PIPE, text, bufsize=1, stderr→日志)`；参数由 `engine_args` :3782 组装（--vision、--layer-split、--parallel、--vram-*、drafting）。
- 就绪：启动循环读 `INFO k=v`、`READY <ctx> [stop] [multi=N]` 得 max_context/can_stop/batch（:1226-1249，`_pump`/`_ready_pump` :1391/:1516 供行）；超时 `ENGINE_READY_S`=900 s :388；失败按 `transient_start_failure` :696 重试（显存不足换 `mtp_retry_args` :3750）。
- 生成：`generate()` :2743 写 `GEN <max_new> [键…] [pin=N] <ids>` 或 `GENI … <embeddings 路径>`；引擎回 `T`/`LP`/`PP`/`RESUME`/`DONE`/`ERR`，`_parse_done` :1566 解析；静默 10 s yield None 当心跳。
- 排队：`Service.fifo`(:4783) 单轮，`_inference_fifo` :4972 带 deadline/cancel，纯 FIFO 无优先级；`--batch/--slots` → `generate_batched` :2230（slot_q/slot_cv/pick_slot :2649），`--parallel` → 每请求 `rid=` 独立队列 :2200。
- 取消：`_watch_client` :7705 每 0.5 s select+MSG_PEEK 探断开 → `note_client_disconnect` :4961 置 cancel → 引擎 `STOP[ rid]` 并 drain；无 HTTP cancel 端点（`/v1/responses/<id>/cancel` 直接 404 :8258）。
- 崩溃：`ensure_loaded` :5302 见 `not alive()` 即 `restart()` :1531（≤3 次）；流中断 `EngineDied` → 503 或 SSE error；`lifeline.popen`（lifeline.py:273）保证子进程不残留。
- replicas（replicas.py）：`Router` 用 64-token 块哈希估重读代价 +3000/在跑请求选副本（:513、:552），`heal` :529 后台重启，共享 expert arena。split（split.py:429）：decode 端要重读 ≥2048 token 时先让 prefill 引擎跑 `session_file("save")` 再 decode `restore`，失败回退。

## 3 /v1/chat/completions 全链路
1. `_post` :8197：`reserve_inference`（draining→503、准入满→429）→ 读 body → `begin_request` :5630。
2. `_openai` :8617：`openai_to_messages`（frontend.py:577）→ 校验 → `prepare_format`（structured.py:123）→ `svc.load()` → `stop_strings` → `_watch_client`。
3. `prepare` :5892：`encode_prompt` :5822 → `ChatTemplate.render`（chat_template.jinja，Jinja2 `ImmutableSandboxedEnvironment`，frontend.py:43-57）→ `tok.encode(..., parse_special=True)`（tokenizer 在 tools/strata_tokenizer.py，server.py:10108-10119 加载，缺省 `ByteTokenizer` :4546）→ 图片编码并展开 `<|image_pad|>` → 空间检查 `CTX_SLACK`(:294)：放不下 400，绝不截断；`fit_max_tokens` 只缩 max_new。
4. `Service.run` :6202 / `_run` :6214：合并默认采样 → `OutputParser`（frontend.py:1177）→ `Detokenizer` :4607 → `engine.generate` 逐 token `parser.feed` → `StopMatcher` :4704 截断 → yield `Event`。
5. `openai_chunks` :7159 转 chunk（reasoning_content/content/tool_calls delta/usage 的 `cached_tokens=reused`/timings）；`_sse` :8564 写 `data: …`、10 s 心跳 `: keep-alive`、`data: [DONE]`；非流式 `openai_collect` :7253。
6. 结束：`DONE` → `request_stats` :6849 / `request_timings` :6825 → `("done",{finish,…})`，finish ∈ stop/length/cancel/disconnect/timeout/error。

## 4 Anthropic 与 Responses 适配
- `/v1/messages`：`_anthropic` :8890 → `anthropic_to_messages`(frontend.py:677)/`anthropic_tools`(:655，deferred 可调用不列出) → 同一条 `Service.run`；`anthropic_events` :7402 出 `message_start`/`content_block_*`/`message_delta`/`message_stop`，stop_reason 映射 stop→end_turn、length→max_tokens、cancel→end_turn；usage 用 input_tokens=1、cache_read=复用数（防 Claude Code 双计，#1013）。`count_tokens` :8881 只编码。
- `/v1/responses`：`_responses` :8721 无状态（GET/DELETE→404），`_responses_prepare` :8821 用 responses.py 的 `check_request/input_messages/request_tools` + `Assembler`；SSE 为 `event: <type>`，长 prompt 每 15 s 补 `response.in_progress` 防 Codex 超时。
- 工具差异：OpenAI 拼 `tool_calls[].function.arguments`；Anthropic 发 `tool_use` 块 + `input_json_delta`；Responses 由 Assembler 组装 `function_call` item。

## 5 调度与并发
- 默认严格串行（docstring :7）；并行只来自引擎 slot（--batch/--slots）或多序列（--parallel）。
- 准入：`admission_limit()=max(1,batch)+max_queue` :4925，超出 429 `admission_full` :8249；等锁超 `queue_timeout_s` → 429 `queue_wait_timeout` :8335；等待期每 `QUEUE_BEAT_S`=10 s :289 心跳。
- 慢写：`STREAM_WRITE_TIMEOUT_S`=60 :321 让卡住的写抛 OSError 并断开；客户端断开即取消。
- 公平性：FIFO、无优先级；优雅停机 `begin_drain` :4994 / `wait_for_drain` :5001 / `cancel_owned_requests` :5012。

## 6 工具调用与 MCP
- 原生 XML `<tool_call><function=NAME><parameter=P>…`：`OutputParser` 状态机（reasoning/content/call/rcall/json），流式 hold-back（`_PREFIX_LOOKBACK=256`、`CLOSE_LOOKAHEAD_CHARS=1500`），容忍 `<=NAME>`、`<function:NAME>`、`<toolcall>`、JSON 参数、缺闭合（frontend.py:761-1170）；只认已声明或可唯一解析的别名。
- DSML：DeepSeek-V4.1 的 `<｜DSML｜ calls>`，dsml.py:48 `DsmlTranslator` 边流边改写为 Qwen 形态，:166 `DsmlOutputParser` 复用解析器；`set_family("deepseek41")` :4903 切 stop/parser/force。
- 结构化：structured.py `prepare_format` :123 / `validated_json` :237，失败 502 不重试。
- MCP：mcp.py `McpHub`（stdio 换行 JSON-RPC 或 Streamable HTTP），工具名 `<server>__<tool>`，`template_tools` 注入；`run_with_mcp` :6894 最多 `max_rounds`(8) 轮：执行→追加 call/result→`prepare` 重渲染续写；结果超 `max_result_chars`(20000) 截断，失败变 `error:` 文本，图片落 `/tool-media/<sha>`。

## 7 会话与前缀缓存
- 引擎侧 conversation cache（generate.cpp:929）：按 token 前缀 park/restore 会话快照，日志 `conversation cache: parked|restored`，`ConvCacheLog` :874 解析、`conversation_cache_view` :950 供监控；`DONE` 的 `RESUME <n>`/reused 即复用数。
- 服务器键：请求可带 `strata_prefix`（messages / message+chars / tokens），`resolve_prefix` :6083 算渲染后最长公共前缀 → `pin=N`（引擎在此打 checkpoint，generate.cpp:15767、16287）；`ckpt=0` 关一次性请求的 checkpoint（#830）。
- 多轮仍重发全量，靠渲染确定性 + 前缀复用省算；`pin_billing_stamp`（frontend.py:624）固定 Claude Code 每请求变化的 billing header（否则每轮丢 ~22K 前缀）；`PromptEncoder`（tools/strata_tokenizer.py:396，server.py:4944 引用）只重编码最后特殊 token 之后（#567）。
- 持久化：`--slot-save-path` + `POST /slots/0?action=save|restore`（`slot_action` :5020）。

## 8 视觉、图片、Web UI、load/unload
- 文生图：`POST /v1/images/generations` → images.py `parse_request` :86 / `gpu_turn` :382，起 `sd-cli`（Qwen-Image-2.1-Turbo 8 步）或 native runner；`gpu_policy` keep/shrink/unload/auto 决定文本引擎让不让显存（:345）；PNG 由 `/v1/images/files/<name>` 取回。
- 视觉输入：`Vision` :3214 常驻 `strata-vision` 子进程，`ENC <img> <out>` 写 embeddings，按图 hash 缓存（:3499），`prepare` 以 `GENI` 交引擎；DeepSeek-V4.1 用引擎自带 tower（ds_pictures.py）。
- Web UI：web/index.html 四 tab（Chat/Images/Monitor/About）；app.js 直接 `fetch("v1/chat/completions")` 读 SSE（app.js:1235）并带 `strata_mcp:true`；Monitor 轮询 `/metrics`（:184）；Settings 用 `/settings`、`/config`。
- load/unload：`POST /load`、`/unload`（可 `?wait=`）:8218/:8228，`POST /v1/unload`、`/v1/load` :8268；`unload()` :5500 存会话后停引擎，`load()` :5437 / `ensure_loaded()` :5302 惰性拉起（--lazy、idle_unload_s）。

## 9 监控与遥测
- `Service.metrics()` :5661 出 JSON（engine/live/requests/totals/hardware/history/conversation_cache）；`/metrics` 按 Accept 或 `?format=prometheus` 切文本（prometheus.py:16/63，vLLM 指标名 + TTFT/ITL/E2E 直方图）。
- `/metrics/prometheus` 固定文本；`/v1/telemetry` :7905 给 CLI 的 vLLM 风格快照（slot/replica 归属、活动事件、admission 计数）。
- 硬件：telemetry.py `Telemetry` 每秒采样（NVML / amdgpu sysfs / IOKit + psutil），留 60 点；`start_telemetry` :5580。
- 健康与兼容：`/health`、`/api/health` :8113；`/status`、`/slots`、`/props`、`/v1/models` 仿 llama.cpp；`/api/requests` + `/api-monitor` 留最近 100 条（需 --api-monitor）。
- 推测：`/metrics` 的 par_counters 与 stage/batch 采样依赖引擎日志（bstat/pstat），并非所有后端都有。
