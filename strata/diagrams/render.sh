#!/bin/bash
# usage: render.sh file.mmd  -> writes file.svg and file.png, tolerant of chrome not exiting
set -u
f="$1"; base="${f%.mmd}"
export PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
rm -f "$base.svg" "$base.png"
/opt/homebrew/bin/mmdc -p "$(dirname "$0")/pptr.json" -i "$f" -o "$base.svg" -b white -w 1600 >/dev/null 2>&1 &
pid=$!
for i in $(seq 1 90); do [ -s "$base.svg" ] && sleep 1 && break; sleep 1; done
kill $pid 2>/dev/null
if [ ! -s "$base.svg" ]; then echo "FAIL $f"; exit 1; fi
/opt/homebrew/bin/mmdc -p "$(dirname "$0")/pptr.json" -i "$f" -o "$base.png" -b white -w 1600 -s 2 >/dev/null 2>&1 &
pid=$!
for i in $(seq 1 90); do [ -s "$base.png" ] && sleep 1 && break; sleep 1; done
kill $pid 2>/dev/null
[ -s "$base.png" ] && echo "OK $f" || echo "OK-SVG-ONLY $f"
