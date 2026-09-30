const fs=require("fs");
const P=[
 {id:"loop",type:"backend",label:"Agent Loop",sublabel:"step()",sources:[{path:"packages/core/agent-loop/src/agent.ts",line:398,end_line:544,label:"step"}]},
 {id:"llm",type:"backend",label:"ctx.llm",sublabel:"LLM 运行时",sources:[{path:"packages/llm/llm/src/index.ts",line:936,end_line:983,label:"prepareCall"},{path:"packages/llm/llm/src/index.ts",line:1033,end_line:1149,label:"stream"}]},
 {id:"hooks",type:"messagebus",label:"llm/stream",sublabel:"瀑布监听器",sources:[{path:"packages/core/agent-loop/src/invariant.ts",line:19,end_line:57,label:"不变量"},{path:"packages/session/session-checkpoint-policy/src/index.ts",line:29,end_line:68,label:"checkpoint"}]},
 {id:"adapter",type:"backend",label:"DeepSeek 适配器",sublabel:"llm-deepseek",sources:[{path:"packages/llm/llm-deepseek/src/adapter.ts",line:43,end_line:157},{path:"packages/llm/llm-deepseek/src/serialize.ts",line:56,end_line:168,label:"serialize"}]},
 {id:"api",type:"external",label:"DeepSeek API",sublabel:"/v1/messages",sources:[{path:"packages/llm/llm-deepseek/src/messages-api.ts",line:4,end_line:17},{path:"packages/llm/llm-deepseek/src/sse.ts",line:13,end_line:28,label:"SSE"}]},
 {id:"retry",type:"security",label:"llm-retry",sublabel:"重试策略",sources:[{path:"packages/llm/llm-retry/src/index.ts",line:199,end_line:252},{path:"packages/llm/llm/src/retry-policy.ts",line:14,end_line:24,label:"默认策略"}]},
 {id:"log",type:"database",label:"Session 日志",sublabel:"append-only",sources:[{path:"packages/core/agent-loop/src/assistant-stream.ts",line:78,end_line:109,label:"settle"}]}
];
const M=[
 ["seg","准备：确定这次用哪个适配器"],
 ["prep","loop","llm","prepareCall(config)","default"],
 ["aprep","llm","adapter","adapter.prepareCall()","default"],
 ["info","adapter","llm","模型信息 / 默认值","return"],
 ["prepared","llm","loop","PreparedLlmCall","return","一次性 stream()，绑定本次配置"],
 ["seg","发送：请求穿过插件链到达 API"],
 ["stream","loop","llm","stream(request)","emphasis"],
 ["wf","llm","hooks","llm/stream 瀑布","default","先校验请求 ≡ 日志，并把会话落盘"],
 ["next","hooks","adapter","next() → adapterStream","default"],
 ["post","adapter","api","POST /v1/messages","emphasis","x-api-key 认证，Anthropic Messages 格式，SSE"],
 ["sse","api","adapter","SSE 事件流","return"],
 ["chunks","adapter","loop","StreamChunk*","return","text / reasoning / tool-call 增量 + usage + finish"],
 ["commit","loop","log","assistant/message","dashed"],
 ["seg","失败：记录并决定是否重试"],
 ["attempt","loop","log","assistant/attempt","dashed","失败的尝试只进日志，不进模型历史"],
 ["reqerr","loop","retry","agent/request-error","security"],
 ["again","retry","loop","{ kind: retry }","return","指数退避后回到 prepareCall"]
];
let y=165,msgs=[],segs=[],cur=null;const Y={};
for(const m of M){ if(m[0]==="seg"){ if(cur){cur.to=y-28+10;segs.push(cur);y+=10;} cur={from:y-14,label:m[1]}; continue;}
 const o={id:m[0],from:m[1],to:m[2],y,label:m[3],variant:m[4]}; if(m[5])o.note=m[5]; msgs.push(o);Y[m[0]]=y;y+=28;}
cur.to=y-28+10;segs.push(cur);
const act=(p,a,b,t)=>({participant:p,from:Y[a]-5,to:Y[b]+5,type:t});
const c={schema_version:1,diagram_type:"sequence",meta:{title:"⑦ 一次模型调用：从 prepareCall 到流式结果",locale:"zh-CN",output:".archify/dsh-guide-20260929-171932/07-llm-call/llm-call.html",viewBox:[1080,696],column_fit:"spread",quality_profile:"showcase",repository:{url:"https://github.com/deepseek-ai/deepseek-harness.git",provider:"github",link_mode:"web",revision:"4878cdabd87d4041bdaff61d04c966883b9fd07a"}},
participants:P,segments:segs,messages:msgs,
activations:[act("llm","prep","prepared","backend"),act("adapter","aprep","info","backend"),act("llm","stream","next","backend"),act("adapter","next","chunks","backend"),act("api","post","sse","external"),act("retry","reqerr","again","security")],
cards:[
 {dot:"cyan",title:"ctx.llm 是一个“接缝”",items:["它只定义接口；DeepSeek、pi-ai（OpenAI/Anthropic 等）都是向它 registerAdapter 的实现","base 默认路由 provider=deepseek-official，model=deepseek-flash","prepareCall 先向适配器要模型信息，补全默认 maxTokens / reasoningEffort，再返回只能用一次的 stream()"]},
 {dot:"emerald",title:"DeepSeek 适配器做了什么",items:["把 dsh 消息序列化为 Anthropic Messages 格式：system、tool_use/tool_result、thinking 等","POST {baseURL}/v1/messages（默认 https://api.deepseek.com/anthropic），用 x-api-key 认证","解析 SSE，把 text_delta / thinking_delta / input_json_delta 翻译成统一的 StreamChunk"]},
 {dot:"violet",title:"流式结果去哪",items:["每个 chunk 立刻以 agent/assistant-stream 实时帧推给 UI（不落盘）","流结束后把完整内容一次写成 assistant/message（带 usage 和紧凑流记录）","finish 为 tool-calls 就进入工具执行；max-tokens 则不执行工具"]},
 {dot:"rose",title:"重试规则",items:["可重试：RATE_LIMIT、SERVER、TIMEOUT、TRANSPORT、EMPTY_RESPONSE；默认最多 5 次","退避：0.5s 起翻倍，封顶 10s，±10% 抖动；服务端给了 retry-after 就优先用它","AUTH、QUOTA、INVALID_REQUEST、CONTEXT_WINDOW_EXCEEDED 默认不重试，turn 以 error 结束"]}
]};
fs.writeFileSync(__dirname+"/candidate.json",JSON.stringify(c,null,2)+"\n");console.log("end y",y);
