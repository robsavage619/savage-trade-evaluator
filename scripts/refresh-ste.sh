#!/bin/zsh
# launchd entry point: daily refresh. Exit code is the refresh's (1 = failed, last good site kept).
set -u
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
mkdir -p data/refresh
exec uv run python scripts/refresh_daily.py
