#!/usr/bin/env bash
# Capture Savage Analytics SPA screenshots for the README.
# Headless Chrome doesn't reliably self-exit after --screenshot and macOS has no
# `timeout`, so each call runs in the background, we wait for the PNG to flush,
# then kill the lingering process.
# Usage: scripts/capture_screens.sh
set -uo pipefail

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE="http://localhost:5174"
OUT="docs/screenshots"
mkdir -p "$OUT"

bounded() {  # max_seconds  outfile  -- chrome args...
  local max="$1" outfile="$2"; shift 2
  "$CHROME" "$@" >/dev/null 2>&1 &
  local pid=$!
  local waited=0
  while [ "$waited" -lt "$max" ]; do
    # Done once the PNG exists and the process has stopped writing.
    if [ -s "$outfile" ] && ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1; waited=$((waited+1))
  done
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
}

shot() {  # name  path  team  width  height
  local name="$1" path="$2" team="$3" w="$4" h="$5"
  local prof; prof="$(mktemp -d)"
  # Single run: _seed.html sets the active-team localStorage, then client-redirects
  # to the real route. Same origin + same process → selection lives in memory.
  local url="$BASE/_seed.html?team=$team&next=$path"
  bounded 25 "$OUT/$name.png" --headless --disable-gpu --hide-scrollbars \
    --no-first-run --no-default-browser-check --user-data-dir="$prof" \
    --force-device-scale-factor=2 --window-size="$w,$h" \
    --virtual-time-budget=7000 --screenshot="$OUT/$name.png" "$url"
  rm -rf "$prof"
  local sz; sz=$(stat -f%z "$OUT/$name.png" 2>/dev/null || echo 0)
  echo "  $name.png  ($team $path  ${w}x${h})  ${sz}B"
}

echo "capturing →"
shot warroom-sell     "/warroom"        NYM 1480 1000
shot warroom-brief    "/warroom"        SDP 1480 2700
shot trade-builder    "/build"          NYM 1480 1100
shot org-explorer     "/orgs"           NYM 1480 1050
shot org-scout        "/orgs/HOU"       HOU 1480 1100
shot player-profile   "/player/677951"  KCR 1480 1100
shot pressly          "/case/pressly"   HOU 1480 1200
shot research         "/research"       NYM 1480 1100
echo "done."
