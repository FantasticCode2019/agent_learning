const fs=require("fs");
const P=[
 {id:"ui",type:"frontend",label:"聊天输入框",sublabel:"ui-conversation",sources:[{path:"packages/client/ui-conversation/src/client/service.ts",line:229,end_line:297,label:"sendSession"}]},
 {id:"client",type:"frontend",label:"客户端 Session",sublabel:"ctx.remote 代理",sources:[{path:"packages/api/session-controller/src/client/sessions/session.ts",line:254,end_line:315,label:"prompt"},{path:"packages/api/gateway/src/client/index.ts",line:417,end_line:461,label:"unary/stream"}]},
 {id:"conn",type:"security",label:"Connection",sublabel:"/api 信任栅栏",sources:[{path:"packages/client/connection/src/index.ts",line:139,end_line:159},{path:"packages/client/connection/src/rpc-host.ts",line:103,end_line:113,label:"admit"}]},
 {id:"gw",type:"backend",label:"API Gateway",sublabel:"Typert Remote",sources:[{path:"packages/api/gateway/src/index.ts",line:232,end_line:238,label:"intercept /api"},{path:"packages/api/gateway/src/index.ts",line:686,end_line:741,label:"派发"}]},
 {id:"ctl",type:"backend",label:"会话控制器",sublabel:"namespace session",sources:[{path:"packages/api/session-controller/src/commands.ts",line:311,end_line:377,label:"prompt"},{path:"packages/api/session-controller/src/agent.ts",line:183,end_line:229,label:"resolve"}]},
 {id:"agent",type:"backend",label:"Agent",sublabel:"ReactLoopAgent",sources:[{path:"packages/core/agent-loop/src/agent.ts",line:154,end_line:173,label:"send/followup"},{path:"packages/core/agent-loop/src/agent.ts",line:214,end_line:235,label:"wakeDriver"}]},
 {id:"log",type:"database",label:"Session 日志",sublabel:"append-only",sources:[{path:"packages/core/session/src/index.ts",line:722,end_line:773,label:"append"}]}
];
const M=[
 ["seg","订阅（打开会话时）"],
 ["follow","client","gw","WS session.follow","dashed","打开 /api/remote.mux 上的流"],
 ["seg","发送一条消息"],
 ["prompt","ui","client","session.prompt()","emphasis"],
 ["post","client","conn","POST /api/session/prompt","emphasis"],
 ["admit","conn","gw","admit 通过 → 派发","security","校验 Host/Origin + Cookie/token"],
 ["remote","gw","ctl","@Remote prompt()","default"],
 ["resolve","ctl","agent","get / resume / create","default","没有活的 Agent 就恢复或新建"],
 ["followup","ctl","agent","followup(message)","emphasis","steer 模式则进 next-step"],
 ["spliced","agent","log","agent/inbox/spliced","dashed"],
 ["accepted","ctl","client","{ accepted: true }","return","立即返回，不等待回合结束"],
 ["seg","Agent 开始工作 · 结果回流"],
 ["wake","agent","log","turn/start → user/message …","dashed","wakeDriver: idle → running"],
 ["event","log","ctl","session/event","dashed"],
 ["stream","agent","ctl","agent/assistant-stream","dashed"],
 ["item","ctl","client","WS item 帧","return"],
 ["render","client","ui","刷新消息列表","return"]
];
let y=165,msgs=[],segs=[],cur=null;const Y={};
for(const m of M){ if(m[0]==="seg"){ if(cur){cur.to=y-28+10;segs.push(cur);y+=10;} cur={from:y-14,label:m[1]}; continue;}
 const o={id:m[0],from:m[1],to:m[2],y,label:m[3],variant:m[4]}; if(m[5])o.note=m[5]; msgs.push(o);Y[m[0]]=y;y+=28;}
cur.to=y-28+10;segs.push(cur);
const act=(p,a,b,t)=>({participant:p,from:Y[a]-5,to:Y[b]+5,type:t});
const c={schema_version:1,diagram_type:"sequence",meta:{title:"③ 消息入口：从按下发送到 Agent 被唤醒",locale:"zh-CN",output:".archify/dsh-guide-20260929-171932/03-ingress/ingress.html",viewBox:[1080,696],column_fit:"spread",quality_profile:"showcase",repository:{url:"https://github.com/deepseek-ai/deepseek-harness.git",provider:"github",link_mode:"web",revision:"4878cdabd87d4041bdaff61d04c966883b9fd07a"}},
participants:P,segments:segs,messages:msgs,
activations:[act("client","prompt","accepted","frontend"),act("gw","admit","remote","backend"),act("ctl","remote","accepted","backend"),act("agent","resolve","stream","backend"),act("ctl","event","item","backend")],
cards:[
 {dot:"cyan",title:"两条通道",items:["一次性调用（prompt / create / commands）走 HTTP POST /api/<ns>/<method>","持续推送（follow / control / $events）走 WebSocket /api/remote.mux","两条通道都先经过 Connection 的信任校验"]},
 {dot:"emerald",title:"消息怎么交给 Agent",items:["Session Controller 先找到 Agent：内存里有就用，否则从磁盘恢复（resume）或新建（create）","followup 把消息放进 inbox 的 next-turn 队列，并写一条 agent/inbox/spliced 事件","inbox 的状态完全由日志事件折叠而来，重启后也不会丢"]},
 {dot:"violet",title:"结果怎么回到浏览器",items:["每次 session.append 都会广播 session/event；模型吐字时还有 agent/assistant-stream 实时帧","session.follow 流把这些事件打包成 WS item 帧推给客户端","客户端先收到快照，再增量追加，所以断线重连不会漏消息"]}
]};
fs.writeFileSync(__dirname+"/candidate.json",JSON.stringify(c,null,2)+"\n");console.log("end y",y);
