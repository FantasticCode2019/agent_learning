#!/bin/bash
# usage: render_one.sh name   (reads src/name.mmd; renders svg + 2x png at natural size)
set -e
name="$1"
base="/Users/yajun/Documents/code/Strata/.analysis"
mmd="$base/diagrams/src/$name.mmd"
svg="$base/diagrams/svg/$name.svg"
png="$base/diagrams/png/$name.png"
node "$base/pm/render.mjs" -i "$mmd" -o "$svg" --theme github-light \
  --font "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Helvetica Neue, Arial" >/dev/null
read W H < <(python3 - "$svg" "$base/diagrams/_wrap.html" <<'PY'
import sys, re
svg_path, out = sys.argv[1], sys.argv[2]
s = open(svg_path).read()
m = re.search(r'viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"', s)
w, h = float(m.group(3)), float(m.group(4))
W, H = int(w + 0.999), int(h + 0.999)
s = re.sub(r'(<svg[^>]*?)\swidth="[\d.]+" height="[\d.]+"', r'\1', s, count=1)
open(out, 'w').write(f'''<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:20px;background:#ffffff;}} #box{{width:{W}px;}} #box svg{{width:100%;height:auto;display:block;}}</style>
</head><body><div id="box">{s}</div></body></html>''')
print(W, H)
PY
)
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --user-data-dir="$base/chrome-profile" --force-device-scale-factor=2 \
  --screenshot="$png" --window-size=$((W+40)),$((H+40)) "file://$base/diagrams/_wrap.html" >/dev/null 2>&1
echo "$name  natural ${W}x${H}  png $(du -h "$png" | cut -f1)"
