# -*- coding: utf-8 -*-
"""Reusable process-swimlane renderer in the diagram-design editorial style.

Geometry is the legible-CJK variant used for figure 2: 4px grid, 168px label
column, 136px step slot, 120x100 nodes, 124px lanes, 92px legend strip.
"""
import html

PAPER = "#f5f5f5"; INK = "#2d3142"; MUTED = "#4f5d75"; SOFT = "#5a6580"
ACCENT = "#bf4520"; ACCENT_TINT = "rgba(191,69,32,0.08)"
SANS = "'Geist','Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif"
MONO = "'Geist Mono',ui-monospace,monospace"
CHIP = {"DB": "#5e7a9b", "WB": "#6e6479"}

LABEL_W = 168; SLOT = 136; NODE_W = 120; NODE_H = 100
HEADER = 52; LANE_H = 124; LEGEND_H = 92


def _esc(s):
    return html.escape(s, quote=False)


def render(cfg, outdir="/Users/yajun/Documents/code/Strata/.analysis/diagrams/gen"):
    lanes = cfg["lanes"]; steps = cfg["steps"]; nodes = cfg["nodes"]
    arrows = cfg.get("arrows") or [(i, i + 1) for i in range(len(steps) - 1)]
    focal_step = cfg["focal_step"]
    W = LABEL_W + 8 + len(steps) * SLOT
    H = HEADER + len(lanes) * LANE_H + LEGEND_H
    LEG_Y = HEADER + len(lanes) * LANE_H

    def cx(j):
        return LABEL_W + 8 + j * SLOT + 60

    def node_x(j):
        return cx(j) - NODE_W / 2

    def lane_top(k):
        return HEADER + k * LANE_H

    def node_y(k):
        return lane_top(k) + (LANE_H - NODE_H) / 2

    by_step = {n["step"]: n for n in nodes}
    out = []; a = out.append
    a(f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{cfg["slug"]}-title {cfg["slug"]}-desc" font-family="{SANS}">')
    a(f'<title id="{cfg["slug"]}-title">{_esc(cfg["title"])}</title>')
    a(f'<desc id="{cfg["slug"]}-desc">{_esc(cfg["desc"])}</desc>')
    a('<defs>')
    a(f'<marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{MUTED}"/></marker>')
    a(f'<marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{ACCENT}"/></marker>')
    a('</defs>')
    a(f'<rect width="100%" height="100%" fill="{PAPER}"/>')

    for k in range(0, len(lanes), 2):
        a(f'<rect x="{LABEL_W}" y="{lane_top(k)}" width="{W-LABEL_W}" height="{LANE_H}" fill="rgba(45,49,66,0.018)"/>')

    # arrows first so boxes always sit on top
    for (i, j) in arrows:
        src, dst = by_step[i], by_step[j]
        sk, dk = src["lane"], dst["lane"]
        sy = lane_top(sk) + LANE_H / 2
        sx = node_x(i) + NODE_W
        dx = cx(j)
        acc = (j == focal_step) or (i == focal_step)
        stroke = ACCENT if acc else MUTED
        marker = "arrow-accent" if acc else "arrow"
        sw = 1.2 if acc else 1.0
        if sk == dk:
            x2 = node_x(j) - 2
            a(f'<line x1="{sx}" y1="{sy}" x2="{x2}" y2="{sy}" stroke="{stroke}" stroke-width="{sw}" marker-end="url(#{marker})"/>')
            continue
        if dk > sk:
            v = node_y(dk)
            d = f'M{sx},{sy} H{dx-8} Q{dx},{sy} {dx},{sy+8} V{v-2}'
        else:
            v = node_y(dk) + NODE_H
            d = f'M{sx},{sy} H{dx-8} Q{dx},{sy} {dx},{sy+8} V{v+2}'
        a(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}" marker-end="url(#{marker})"/>')

    for k, (name, code) in enumerate(lanes):
        mid = lane_top(k) + LANE_H / 2
        a(f'<text x="{LABEL_W/2}" y="{mid-2}" text-anchor="middle" font-size="13" font-weight="600" fill="{INK}">{_esc(name)}</text>')
        a(f'<text x="{LABEL_W/2}" y="{mid+14}" text-anchor="middle" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{SOFT}">{code}</text>')
        a(f'<line x1="0" y1="{lane_top(k)}" x2="{W}" y2="{lane_top(k)}" stroke="rgba(45,49,66,0.12)" stroke-width="0.8"/>')
    a(f'<line x1="0" y1="{LEG_Y}" x2="{W}" y2="{LEG_Y}" stroke="rgba(45,49,66,0.12)" stroke-width="0.8"/>')
    a(f'<line x1="{LABEL_W}" y1="{HEADER}" x2="{LABEL_W}" y2="{LEG_Y}" stroke="rgba(45,49,66,0.20)" stroke-width="1"/>')

    for j, label in enumerate(steps):
        f = (j == focal_step)
        fill = "rgba(191,69,32,0.20)" if f else "rgba(45,49,66,0.12)"
        col = ACCENT if f else INK
        a(f'<rect x="{cx(j)-11}" y="10" width="22" height="22" rx="11" fill="{fill}"/>')
        a(f'<text x="{cx(j)}" y="25" text-anchor="middle" font-size="10" font-family="{MONO}" font-weight="600" fill="{col}">{j+1}</text>')
        a(f'<text x="{cx(j)}" y="46" text-anchor="middle" font-size="12" font-weight="500" fill="{ACCENT if f else MUTED}">{_esc(label)}</text>')

    for n in nodes:
        k, j = n["lane"], n["step"]
        x, y = node_x(j), node_y(k)
        is_focal = bool(n.get("focal"))
        fill = ACCENT_TINT if is_focal else "#ffffff"
        stroke = ACCENT if is_focal else "rgba(45,49,66,0.25)"
        a(f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="6" fill="{PAPER}"/>')
        a(f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="{1.2 if is_focal else 1}"/>')
        key = lanes[k][1]
        rc_fill = "rgba(191,69,32,0.18)" if is_focal else "rgba(45,49,66,0.07)"
        rc_text = ACCENT if is_focal else MUTED
        a(f'<rect x="{x+8}" y="{y+8}" width="30" height="14" rx="2" fill="{rc_fill}" stroke="{rc_text}" stroke-opacity="0.35" stroke-width="0.8"/>')
        a(f'<text x="{x+23}" y="{y+18}" text-anchor="middle" font-size="8" font-family="{MONO}" font-weight="600" letter-spacing="0.08em" fill="{rc_text}">{key}</text>')
        a(f'<text x="{x+NODE_W/2}" y="{y+46}" text-anchor="middle" font-size="14" font-weight="600" fill="{INK}">{_esc(n["title"])}</text>')
        a(f'<text x="{x+NODE_W/2}" y="{y+63}" text-anchor="middle" font-size="9.5" font-family="{MONO}" fill="{MUTED}">{_esc(n["sub"])}</text>')
        a(f'<text x="{x+NODE_W/2}" y="{y+77}" text-anchor="middle" font-size="9.5" font-family="{MONO}" fill="{SOFT}">{_esc(n["tool"])}</text>')
        cin, cout = n.get("cin"), n.get("cout")
        if cin:
            a(f'<rect x="{x+8}" y="{y+84}" width="20" height="12" rx="2" fill="{CHIP[cin]}"/>')
            a(f'<text x="{x+18}" y="{y+93}" text-anchor="middle" font-size="7" font-family="{MONO}" font-weight="700" fill="#ffffff">{cin}</text>')
        if cout:
            a(f'<rect x="{x+NODE_W-28}" y="{y+84}" width="20" height="12" rx="2" fill="{CHIP[cout]}"/>')
            a(f'<text x="{x+NODE_W-18}" y="{y+93}" text-anchor="middle" font-size="7" font-family="{MONO}" font-weight="700" fill="#ffffff">{cout}</text>')

    # legend
    a(f'<line x1="0" y1="{LEG_Y-8}" x2="{W}" y2="{LEG_Y-8}" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>')
    a(f'<text x="24" y="{LEG_Y+14}" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{MUTED}">STEPS</text>')
    a(f'<text x="24" y="{LEG_Y+42}" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{MUTED}">DATA</text>')
    a(f'<text x="24" y="{LEG_Y+70}" font-size="8" font-family="{MONO}" letter-spacing="0.14em" fill="{MUTED}">FLOW</text>')
    for j, label in enumerate(steps):
        a(f'<rect x="{cx(j)-30}" y="{LEG_Y+4}" width="16" height="16" rx="8" fill="rgba(45,49,66,0.10)"/>')
        a(f'<text x="{cx(j)-22}" y="{LEG_Y+15}" text-anchor="middle" font-size="8" font-family="{MONO}" fill="{MUTED}">{j+1}</text>')
        a(f'<text x="{cx(j)-8}" y="{LEG_Y+15}" font-size="10" fill="{MUTED}">{_esc(label)}</text>')

    data_items = cfg.get("data", [])
    slots = [cx(0), cx(3), cx(6)]
    for idx, (code, label) in enumerate(data_items[:3]):
        bx = slots[idx] - 30
        a(f'<rect x="{bx}" y="{LEG_Y+32}" width="20" height="12" rx="2" fill="{CHIP[code]}"/>')
        a(f'<text x="{bx+10}" y="{LEG_Y+41}" text-anchor="middle" font-size="7" font-family="{MONO}" font-weight="700" fill="#ffffff">{code}</text>')
        a(f'<text x="{bx+26}" y="{LEG_Y+41}" font-size="10" fill="{MUTED}">{_esc(label)}</text>')
    if cfg.get("hint"):
        a(f'<text x="{cx(len(steps)-1)-30}" y="{LEG_Y+41}" font-size="9" font-family="{MONO}" fill="{SOFT}">{_esc(cfg["hint"])}</text>')
    a(f'<line x1="{cx(0)-30}" y1="{LEG_Y+64}" x2="{cx(0)+10}" y2="{LEG_Y+64}" stroke="{MUTED}" stroke-width="1" marker-end="url(#arrow)"/>')
    a(f'<text x="{cx(0)+18}" y="{LEG_Y+67}" font-size="10" fill="{MUTED}">{_esc(cfg.get("flow_label", "角色交接"))}</text>')
    a(f'<line x1="{cx(2)-30}" y1="{LEG_Y+64}" x2="{cx(2)+10}" y2="{LEG_Y+64}" stroke="{ACCENT}" stroke-width="1.2" marker-end="url(#arrow-accent)"/>')
    a(f'<text x="{cx(2)+18}" y="{LEG_Y+67}" font-size="10" fill="{MUTED}">{_esc(cfg["focal_label"])}</text>')
    a('</svg>')

    svg = "\n".join(out)
    open(f"{outdir}/{cfg['slug']}.svg", "w").write(svg)

    page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(cfg["h1"])}</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: {SANS}; background: {PAPER}; color: {INK}; min-height: 100vh;
    display: flex; align-items: center; justify-content: center; padding: 3rem 2rem; }}
  .frame {{ max-width: {W + 48}px; width: 100%; }}
  .eyebrow {{ font-family: {MONO}; font-size: 0.66rem; font-weight: 500; letter-spacing: 0.18em;
    text-transform: uppercase; color: {MUTED}; margin-bottom: 0.5rem; }}
  h1 {{ font-family: 'Instrument Serif','Songti SC','STSong',serif; font-size: clamp(1.5rem, 2.4vw + 0.75rem, 2rem);
    font-weight: 400; letter-spacing: -0.01em; line-height: 1.2; color: {INK}; margin-bottom: 1.5rem; }}
  svg {{ width: 100%; min-width: {W}px; display: block; }}
</style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">{_esc(cfg["eyebrow"])}</p>
    <h1>{_esc(cfg["h1"])}</h1>
    <div class="diagram-container">{svg}</div>
  </div>
</body>
</html>
'''
    open(f"{outdir}/{cfg['slug']}.html", "w").write(page)
    return W, H


def export(slug, outdir="/Users/yajun/Documents/code/Strata/.analysis/diagrams/gen", w=0, h=0):
    """Standalone SVG (fonts @import) + wrap.html for the 2x Chrome screenshot."""
    svg = open(f"{outdir}/{slug}.svg").read()
    svg2 = svg.replace("<svg ", f'<svg width="{w}" height="{h}" ', 1)
    style = ("<style>\n@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&amp;"
             "family=Geist:wght@400;500;600&amp;family=Geist+Mono:wght@400;500;600&amp;display=swap');\n</style>\n")
    svg2 = svg2.replace("<defs>", style + "<defs>", 1)
    open(f"{outdir}/{slug}_standalone.svg", "w").write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg2)
    wrap = ('<!DOCTYPE html><html><head><meta charset="utf-8">\n<style>body{margin:0;background:#f5f5f5;'
            'display:flex;align-items:flex-start;justify-content:center;padding:20px}svg{display:block}</style>\n'
            '</head><body>' + svg2 + '</body></html>')
    open(f"{outdir}/{slug}_wrap.html", "w").write(wrap)
