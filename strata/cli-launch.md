# strata launch：安装 / 启动 / 控制链路（静态分析）

Strata 0.2.12、engine 0.1.58；未编译、未运行。列出的文件名在仓库内唯一（runner.py = strata_cli/launch/runner.py 等）。

## 1 命令分层

- 入口 strata.py:32-38：先跑纯 stdlib 的 `handover.maybe_hand_over`/`refuse_old_updater`（`strata update` 装的新 Control 在导入重模块前接管），再 import cli。
- strata.py:14-27 `_preflight`：只对 serve/bench 查 SERVER_PACKAGES，缺则退出 5，永不自动 pip。
- cli.py:40 `parser()`，cli.py:45 `add_subparsers(required=True)`；命令表：serve:46、profile:69-105、repair-access:107、doctor:109、components/update:114-140、models:141-172、split-engine:175、engine:176-190、install:192、runtime:199-240、ops:257、bench:293-347、timeskip:350、tune:397-490、**launch/connect:490-491**（`launch_cmd.add_parsers`）、status/monitor/logs/connection:492-495、code:496-507；:509-521 统一补 `--json/--quiet`。
- 分派 cli.py:2244 `main` → cli.py:2128 `_run`；launch/connect → `run_launch`/`run_connect`（cli.py:2165-2167）；多余参数给 "Did you mean" 退出 2（cmd.py:183-198）。
- 两层结构：`strata` 的 argparse 只管命令与少量全局旗标（`--json`=--output json、`--quiet` 走 `_QuietCapture`，cli.py:509-521），`launch` 自己的几十个旗标由 cmd.py 的 parser 解析，二者不共用命名空间（推测）。

## 2 `strata launch` 各阶段

- runner.py:183 `STAGES=(engine,model,config,tune,start,access)`；runner.py:2713-2754 顺序：check_own_files → check_serving（已在服务则复用）→ ensure_engine → ensure_model → ensure_drafter → build_config → ensure_profile → tune → start → save_choices → open_access → 打印地址。
- 解析：cmd.py:212-330 `settings_from_args`（--preset 起点逐项覆盖）；cmd.py:393-470 `apply_defaults`（无模型用 `catalog.recommendation`，探 backend，context 取 max_context，按 verdict 警告）。
- plan：`--plan` 只读。runner.py:2476-2500 返回 profile、settings（去 key）、warnings、flags、steps、model{model_gb,own_files,folder}、download、drafting、speed，DeepSeek 多文件另加 placement；打印在 cmd.py:930-960，逐行为 model（标题+GB）、context/pictures/parallel、download 一句话、drafting、speed、cards、`tuning … access … port …`、`[!]` 警告、`same as` 等价旗标，末行 `Nothing was changed.`；机器模式为 `{"schema_version":1,"ok":true,"plan":…}`（cmd.py:934）。
- 无 TUI 时要人确认：`Start it now? … [Y/n]`（cmd.py:974-981），`--yes` 跳过。
- 选引擎：engine_component.py:514-560 `detect_backend()` 顺序 env `STRATA_ENGINE_BACKEND` → `engine-backend.json` 保存值 → macOS=metal → Windows 显示适配器（NV→AMD→Intel）→ nvidia-smi/rocminfo/sycl-ls → sysfs；engine_component.py:1067-1152 `resolve()` 按 platform、backend、arch covers、min_runtime、min_driver 过滤后逐文件 sha256 校验。
- 下载校验：runner.py:741-800 `ensure_engine()` 起 `strata update --no-control --output jsonl`；feed 为 `strata-feed.json` + detached Ed25519（feed.py:1-28），manifest.signature 覆盖全部文件哈希（engine_component.py:355-401），每文件 sha256 必验，`STRATA_REQUIRE_SIGNED_COMPONENTS` 可强制。
- 模型：runner.py:1169-1290 起 `setup.py`（`STRATA_CONTROL_INSTALL=1`、`STRATA_INSTALL_DIR`），已装且 desc 匹配则复用；runner.py:2322 `download_plan()` 报模型分片、草稿层、mmproj、DFlash2 的缺口。
- fit：catalog.py:33-60 `fit_on()`（DENSE_GB=5、SYSTEM_ROOM_GB=10；experts=mem-1，on_gpu=min(experts,vram-5)，ram_room=ram-10，余量 spill 到 SSD）；gpu_fit.py:1-20 先单卡、不够才加卡；vram_fit.py:1-45 明令不改 context、不改并发，只降 `--kv-resident`、专家缓存槽、`--prefill`、`--vram-reserve-mib`，由 serve 起引擎时应用；磁盘用 hardware.disk_free_gb 与 download 的 GB。
- 配置：runner.py:1684-1713 `build_config()` 写 `<state>/launch/<name>.json`（0600 原子写，runner.py:589-608）。字段见 runner.py:537-586：host、port、api_key、drafting、split_engine、parallel、mtp、vision、gpu、exe=`component:strata-engine`、log、user_args/env；base 是 setup 的 `strata-<model>.json`（setup.py:9498-9521）。
- 启动：runner.py:1810-1829 建 profile `launch-<slug>`（overrides=host/port/parallel）；runner.py:2151-2200 `start()` 停残留（LEFTOVER_STATES，runner.py:2910）→ 查端口（:2234）→ `runtime.start`。runtime 只起**服务器**：`[sys.executable,"-m","serve.server","--config",<run config>,"--ready-file",…,"--owner-fd",…]`（runtime.py:952-992），env 置 `STRATA_NO_ACQUIRE=1`、`STRATA_RUNTIME_PROFILE`、`STRATA_OWNER_ATTEST_KEY`；引擎由 server 按 run config 起。ready 文件只证明端口已绑，readiness.py:84 再验 telemetry 并做一次 one-token 生成才算 ready。
- 输出：cmd.py:1019-1076 各 URL（本机/网络/CF/TS，加 `/v1`）、Anthropic 基址（不带 /v1）、掩码 key、engine 日志路径；`--output json` 见 cmd.py:1011。

## 3 配置与环境变量

- 位置：`state_base()`（paths.py:12-21）下 launch/、runtime/；profile 在 `$XDG_CONFIG_HOME/strata/profiles`（profiles.py:38-46）；launch 预设在同级 `launch-presets/`（store.py:1-8，含 key 故 0600）；组件在 `<components>/engine`（engine_component.py:176-190）。
- 键：settings.py:111-170 `LaunchSettings`（family、model、context、kv、vision、parallel、speed、drafting、split_engine、mtp、tune、access、port、api_key、extra）；profile 覆盖键 profiles.py:28。
- 环境变量：`STRATA_COMPONENTS_DIR`、`STRATA_ENGINE_BACKEND`、`STRATA_REQUIRE_SIGNED_COMPONENTS`（engine_component.py:59-61）、`STRATA_RUNTIME_DIR`（runtime.py:101）、`STRATA_PROFILE_DIR`（profiles.py:38）、`STRATA_LAUNCH_PRESET_DIR`（store.py:1-8）、`STRATA_INSTALL_DIR`（discovery.py:1-15）、`STRATA_SPLIT_ENGINE=0`（split_engine.py:1-28）。
- 映射：run config 的 `args` 由 setup 生成，launch 只做覆盖（runner.py:537-586 收尾调 `arg_layers.layer()`，优先级 显式 CLI > 持久覆盖 > 校准 > Auto），Advanced 表的键名就是引擎旗标名（params.py:1-6），`--set k=v` 进 extra；`tune_knobs.apply_to_env` 写 STRATA_* 环境变量。preset 分两类：launch 预设=屏幕答案（store.py:1-8），调优预设=测量结果+身份（presets.py:1-14，hard/soft 变化）。

## 4 引擎组件下载 / 更新 / 回滚

- 布局 `<components>/engine/<version>-<platform>-<backend>[-variant]/`（updater.py:522-524）+ 内含 manifest；状态在 `<components>/.updates/state.json`（updater.py:172-177：active、previous、pinned、failed、skipped、history）。
- 安装：先 `test_start` 试启动，再 move 进 engine/，切换前清 pin 并复验，选不中则移 `engine/.rejected/`（updater.py:1147-1230）；旧包留到 `components remove`（:1083）。
- 回滚：写 pinned 让启动优先旧包，下次成功更新清 pin；无 previous 退出 2（updater.py:1355-1380）。模型在跑时：engine_update.py:1-26，无人可问则下载前退出 7，同意则下载→停→切→按原设置重启。

## 5 status / stop / 日志 / TUI

- `--status` 遍历 `launch-*` 后问 `runtime.status`，人读一行 `name: state at url`，JSON 为 `{schema_version:1,ok,running[]}`（cmd.py:753-787）；`--stop` = `runtime.stop`+`stop_tunnel`（cmd.py:594-611）；`--show-key` 先查预设再回落 `strata-<model>.json`（cmd.py:791-870）。
- 通信不是进程扫描：runtime.py:414-468 一行 JSON，POSIX 用 owner 私有 AF_UNIX + flock，Windows 用 loopback TCP + 256-bit token；PID 只比较不下发信号。
- 日志：engine `<state>/launch/<name>.engine.log`（runner.py:1694）、server `runtime/<profile>.server.log`（runner.py:2211-2216）；logs/status/monitor 走 HTTP 白名单 `/v1/telemetry`、`/v1/status`、`/metrics`、`/health`（client.py:101-134）。TUI：screens.py:31-32 十屏（DeepSeek 插 speed、可用时插 drafting），跑完进 Monitor（app.py:1-6，七视图，键 7 Connect）。

## 6 connect

- harness.py:1-8：每个 app 一份实测配置（opencode、codex、claude-code、omp、pi、hermes、openclaw）；`render()` 生成文件，`write_file` 先备份再合并；常量 TESTED_CONTEXT=32768。
- cmd.py:1079-1100：无参列 App 表；`--check` 进 check.py:1-10，按该 app 的 wire format（codex=responses、claude-code=messages，其余 chat）发 prompt + tool call 校验。

## 7 桌面 app 与 Terminal

- Tauri 壳只是 carrier（main.rs:1-28）：起 App Host、同 origin 开 webview、退出收摊；可跑多个引擎，各占 `app-N` profile。
- main.rs:446-495 以 `node server/index.mjs` 起 host（STRATA_PORT/STRATA_DIST/STRATA_PACKAGED/STRATA_BIND=127.0.0.1/STRATA_SHUTDOWN_TOKEN），`/api/health` 探活；会话凭据 `~/.strata/app-session.json`（0600，shell.rs:14-16）。
- host：index.mjs:2-26 单进程手写路由（`/api/events` SSE、`/api/native/*`、`/api/tune/*`），:979-990 校验 Origin、串行写操作。app→Terminal 走 control-runtime.mjs:1-16 的 `runCli`（JSON in/out、无 shell）调自带 Control（`<components>/control/active.json` 定版本），再由 Control 的 owner runtime 起引擎。

## 8 split / 多 GPU

- split_engine.py:1-28：`strata-split-N` 让每卡分每层，用 page-locked 主机内存交换；auto 默认。条件：Linux、2–4 张同型号卡、已实测架构（NVIDIA sm_86 双卡、AMD gfx1201 四卡）、GGUF 张量类型在名单、专家全进显存、RAM 够、context ≤128K。
- 编排：build_config 之后 runner.py:1715-1743 `apply_split_engine` 换 exe 并加参数，异常只回滚 parallel、不中止 launch；引擎拒绝或起不来时 serve 回落普通 layer split（split_engine.py:1-28）。
