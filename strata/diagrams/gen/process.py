# -*- coding: utf-8 -*-
"""Generate the process-type diagram for the Strata inference flow (diagram-design)."""
import html

PAPER = "#f5f5f5"; INK = "#2d3142"; MUTED = "#4f5d75"; SOFT = "#5a6580"
ACCENT = "#bf4520"; ACCENT_TINT = "rgba(191,69,32,0.08)"
SANS = "'Geist','Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif"
MONO = "'Geist Mono',ui-monospace,monospace"
CHIP = {"DB": "#5e7a9b", "WB": "#6e6479"}

LANES = [("客户端", "CLT"), ("接入层", "SRV"), ("引擎", "ENG")]
STEPS = ["请求", "适配", "预填", "草稿", "验证", "输出", "渲染"]

# lane, step, title, sub, tool, chips(in,out), focal
NODES = [
    (0, 0, "发起请求", "messages + tools", "OpenAI SDK",     (None, "DB"), False),
    (1, 1, "适配 · 排队", "Jinja2 → ids · FIFO", "ChatTemplate", ("DB", "DB"), False),
    (2, 2, "分块预填", "8K chunk · 专家 ring", "MMQ · PCIe",   ("DB", None), False),
    (2, 3, "出草稿", "MTP · DFlash2", "choose_window", (None, None), False),
    (2, 4, "验证窗口", "T 行 · 48 层一次", "verify · sample",  (None, None), True),
    (1, 5, "增量输出", "SSE · tool calls", "OutputParser",    (None, "WB"), False),
    (0, 6, "渲染展示", "stream → UI", "SDK",                  ("WB", None), False),
]
# (from_step, to_step)
ARROWS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]

W = 1140; LABEL_W = 168; SLOT = 136; NODE_W = 120; NODE_H = 100
HEADER = 52; LANE_H = 124; LEGEND_Y = HEADER + len(LANES) * LANE_H  # 548
H = LEGEND_Y + 92
def cx(j): return LABEL_W + 8 + j * SLOT + 60
def node_x(lane, j): return cx(j) - NODE_W / 2
def lane_top(k): return HEADER + k * LANE_H
def node_y(k): return lane_top(k) + (LANE_H - NODE_H) / 2

out = []
a = out.append
a(f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="strata-process-title strata-process-desc" font-family="{SANS}">')
a('<title id="strata-process-title">Strata 一次请求的四层接力</title>')
a('<desc id="strata-process-desc">四个角色（客户端、接入层、引擎、算力与存储）与七个阶段的端到端推理流程：请求经模板与准入进入引擎，分块预填、出草稿、一次验证 T 行，再增量输出回客户端。</desc>')
a('<defs>')
a('<marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="%s"/></marker>' % MUTED)
a('<marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="%s"/></marker>' % ACCENT)
a('</defs>')
a(f'<rect width="100%" height="100%" fill="{PAPER}"/>')

# lane zebra tints (lanes 0 and 2)
for k in (0, 2):
    a(f'<rect x="{LABEL_W}" y="{lane_top(k)}" width="{W-LABEL_W}" height="{LANE_H}" fill="rgba(45,49,66,0.018)"/>')

# arrows first (z-order), then boxes
focal = [n for n in NODES if n[6]][0]
focal_step = focal[1]
for (i, j) in ARROWS:
    src = [n for n in NODES if n[1] == i][0]
    dst = [n for n in NODES if n[1] == j][0]
    sk, dk = src[0], dst[0]
    sx = node_x(sk, i) + NODE_W; sy = lane_top(sk) + LANE_H / 2
    dx = cx(j)
    acc = (j == focal_step) or (i == focal_step)
    stroke = ACCENT if acc else MUTED
    marker = "arrow-accent" if acc else "arrow"
    sw = 1.2 if acc else 1.0
    if sk == dk:
        # same lane, adjacent: straight horizontal in the corridor
        x2 = node_x(dk, j) - 2
        a(f'<line x1="{sx}" y1="{sy}" x2="{x2}" y2="{sy}" stroke="{stroke}" stroke-width="{sw}" marker-end="url(#{marker})"/>')
    else:
        if dk > sk:  # destination lane below: enter top edge
            ey = node_y(dk); v = ey
            d = f'M{sx},{sy} H{dx-8} Q{dx},{sy} {dx},{sy+8} V{v-2}'
        else:        # destination above: enter bottom edge
            ey = node_y(dk) + NODE_H; v = ey
            d = f'M{sx},{sy} H{dx-8} Q{dx},{sy} {dx},{sy+8} V{v+2}'
        a(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}" marker-end="url(#{marker})"/>')

# lane labels + dividers
for k, (name, code) in enumerate(LANES):
    mid = lane_top(k) + LANE_H / 2
    a(f'<text x="{LABEL_W/2}" y="{mid-2}" text-anchor="middle" font-size="13" font-weight="600" fill="{INK}">{name}</text>')
    a(f'<text x="{LABEL_W/2}" y="{mid+14}" text-anchor="middle" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{SOFT}">{code}</text>')
    a(f'<line x1="0" y1="{lane_top(k)}" x2="{W}" y2="{lane_top(k)}" stroke="rgba(45,49,66,0.12)" stroke-width="0.8"/>')
a(f'<line x1="0" y1="{LEGEND_Y}" x2="{W}" y2="{LEGEND_Y}" stroke="rgba(45,49,66,0.12)" stroke-width="0.8"/>')
a(f'<line x1="{LABEL_W}" y1="{HEADER}" x2="{LABEL_W}" y2="{LEGEND_Y}" stroke="rgba(45,49,66,0.20)" stroke-width="1"/>')

# step headers
for j, label in enumerate(STEPS):
    f = (j == focal_step)
    fill = "rgba(191,69,32,0.20)" if f else "rgba(45,49,66,0.12)"
    col = ACCENT if f else INK
    a(f'<rect x="{cx(j)-11}" y="10" width="22" height="22" rx="11" fill="{fill}"/>')
    a(f'<text x="{cx(j)}" y="25" text-anchor="middle" font-size="10" font-family="{MONO}" font-weight="600" fill="{col}">{j+1}</text>')
    a(f'<text x="{cx(j)}" y="46" text-anchor="middle" font-size="12" font-weight="500" fill="{ACCENT if f else MUTED}">{label}</text>')

# nodes
for (k, j, title, sub, tool, chips, is_focal) in NODES:
    x, y = node_x(k, j), node_y(k)
    fill = ACCENT_TINT if is_focal else "#ffffff"
    stroke = ACCENT if is_focal else "rgba(45,49,66,0.25)"
    a(f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="6" fill="{PAPER}"/>')
    a(f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="{1.2 if is_focal else 1}"/>')
    # role chip
    key = LANES[k][1]
    rc_fill = "rgba(191,69,32,0.18)" if is_focal else "rgba(45,49,66,0.07)"
    rc_text = ACCENT if is_focal else MUTED
    a(f'<rect x="{x+8}" y="{y+8}" width="30" height="14" rx="2" fill="{rc_fill}" stroke="{rc_text}" stroke-opacity="0.35" stroke-width="0.8"/>')
    a(f'<text x="{x+23}" y="{y+18}" text-anchor="middle" font-size="8" font-family="{MONO}" font-weight="600" letter-spacing="0.08em" fill="{rc_text}">{key}</text>')
    a(f'<text x="{x+NODE_W/2}" y="{y+46}" text-anchor="middle" font-size="14" font-weight="600" fill="{INK}">{title}</text>')
    a(f'<text x="{x+NODE_W/2}" y="{y+63}" text-anchor="middle" font-size="9.5" font-family="{MONO}" fill="{MUTED}">{sub}</text>')
    a(f'<text x="{x+NODE_W/2}" y="{y+77}" text-anchor="middle" font-size="9.5" font-family="{MONO}" fill="{SOFT}">{tool}</text>')
    cin, cout = chips
    if cin:
        a(f'<rect x="{x+8}" y="{y+84}" width="20" height="12" rx="2" fill="{CHIP[cin]}"/>')
        a(f'<text x="{x+18}" y="{y+93}" text-anchor="middle" font-size="7" font-family="{MONO}" font-weight="700" fill="#ffffff">{cin}</text>')
    if cout:
        a(f'<rect x="{x+NODE_W-28}" y="{y+84}" width="20" height="12" rx="2" fill="{CHIP[cout]}"/>')
        a(f'<text x="{x+NODE_W-18}" y="{y+93}" text-anchor="middle" font-size="7" font-family="{MONO}" font-weight="700" fill="#ffffff">{cout}</text>')

# legend
a(f'<line x1="0" y1="{LEGEND_Y-8}" x2="{W}" y2="{LEGEND_Y-8}" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>')
a(f'<text x="24" y="{LEGEND_Y+14}" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{MUTED}">STEPS</text>')
a(f'<text x="24" y="{LEGEND_Y+42}" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{MUTED}">DATA</text>')
a(f'<text x="24" y="{LEGEND_Y+70}" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{MUTED}">FLOW</text>')
for j, label in enumerate(STEPS):
    a(f'<rect x="{cx(j)-30}" y="{LEGEND_Y+4}" width="16" height="16" rx="8" fill="rgba(45,49,66,0.10)"/>')
    a(f'<text x="{cx(j)-22}" y="{LEGEND_Y+15}" text-anchor="middle" font-size="8" font-family="{MONO}" fill="{MUTED}">{j+1}</text>')
    a(f'<text x="{cx(j)-8}" y="{LEGEND_Y+15}" font-size="10" fill="{MUTED}">{label}</text>')
a(f'<rect x="{cx(0)-30}" y="{LEGEND_Y+32}" width="20" height="12" rx="2" fill="{CHIP["DB"]}"/><text x="{cx(0)-20}" y="{LEGEND_Y+41}" text-anchor="middle" font-size="7" font-family="{MONO}" font-weight="700" fill="#ffffff">DB</text>')
a(f'<text x="{cx(0)-4}" y="{LEGEND_Y+41}" font-size="10" fill="{MUTED}">请求体 / token id</text>')
a(f'<rect x="{cx(3)-30}" y="{LEGEND_Y+32}" width="20" height="12" rx="2" fill="{CHIP["WB"]}"/><text x="{cx(3)-20}" y="{LEGEND_Y+41}" text-anchor="middle" font-size="7" font-family="{MONO}" font-weight="700" fill="#ffffff">WB</text>')
a(f'<text x="{cx(3)-4}" y="{LEGEND_Y+41}" font-size="10" fill="{MUTED}">SSE 流</text>')
a(f'<text x="{cx(5)-30}" y="{LEGEND_Y+41}" font-size="9" font-family="{MONO}" fill="{SOFT}">左 = 输入 · 右 = 输出</text>')
a(f'<line x1="{cx(0)-30}" y1="{LEGEND_Y+64}" x2="{cx(0)+10}" y2="{LEGEND_Y+64}" stroke="{MUTED}" stroke-width="1" marker-end="url(#arrow)"/>')
a(f'<text x="{cx(0)+18}" y="{LEGEND_Y+67}" font-size="10" fill="{MUTED}">角色交接</text>')
a(f'<line x1="{cx(2)-30}" y1="{LEGEND_Y+64}" x2="{cx(2)+10}" y2="{LEGEND_Y+64}" stroke="{ACCENT}" stroke-width="1.2" marker-end="url(#arrow-accent)"/>')
a(f'<text x="{cx(2)+18}" y="{LEGEND_Y+67}" font-size="10" fill="{MUTED}">焦点路径：验证窗口</text>')
a('</svg>')

svg = "\n".join(out)
open("/Users/yajun/Documents/code/Strata/.analysis/diagrams/gen/process.svg", "w").write(svg)

page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>一次请求的四层接力</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&family=Noto+Serif:ital@0;1&family=Noto+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@400&family=Noto+Sans+TC:wght@400;500;600&family=Noto+Serif+TC:wght@400&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --color-paper: #f5f5f5; --color-ink: #2d3142; --color-muted: #4f5d75; --color-accent: #bf4520;
    --font-sans: 'Geist','Noto Sans SC','PingFang SC','Microsoft YaHei',system-ui,sans-serif;
    --font-serif: 'Instrument Serif','Noto Serif','Songti SC','STSong',serif;
    --font-mono: 'Geist Mono',ui-monospace,monospace;
  }}
  body {{ font-family: var(--font-sans); background: var(--color-paper); color: var(--color-ink);
    min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 3rem 2rem; }}
  .frame {{ max-width: 1188px; width: 100%; }}
  .diagram-container {{ width: 100%; overflow-x: auto; }}
  .eyebrow {{ font-family: var(--font-mono); font-size: 0.66rem; font-weight: 500; letter-spacing: 0.18em;
    text-transform: uppercase; color: var(--color-muted); margin-bottom: 0.5rem; }}
  h1 {{ font-family: var(--font-serif); font-size: clamp(1.5rem, 2.4vw + 0.75rem, 2rem); font-weight: 400;
    letter-spacing: -0.01em; line-height: 1.2; color: var(--color-ink); margin-bottom: 1.5rem; }}
  svg {{ width: 100%; min-width: 1140px; display: block; }}
  @media print {{ .diagram-container {{ overflow-x: visible; }} svg {{ min-width: 0; }} }}
</style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">Process · Strata Inference</p>
    <h1>一次请求，四层接力</h1>
    <div class="diagram-container">
      {svg}
    </div>
  </div>
</body>
</html>
'''
open("/Users/yajun/Documents/code/Strata/.analysis/diagrams/gen/process.html", "w").write(page)
print("wrote", W, H)
