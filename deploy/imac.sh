#!/bin/zsh
# Ship the committed tree (git archive HEAD) to the iMac, install deps, build, and print the
# sudo steps for you to run. Usage: deploy/imac.sh user@host [remote_dir]
# Never copies the database, .env, or node_modules: the DB is copied by hand once (see docs/imac-cutover.md).
set -eu
HOST="${1:?usage: deploy/imac.sh user@host [remote_dir]}"
DIR="${2:-Projects/savage-trade-evaluator}"
cd "$(dirname "$0")/.."

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
git archive HEAD | tar -x -C "$STAGE"
ssh "$HOST" "mkdir -p '$DIR'"
rsync -a --delete \
  --exclude '/data/' --exclude '.env*' --exclude '.venv/' \
  --exclude 'frontend/node_modules/' --exclude 'frontend/dist*/' \
  "$STAGE/" "$HOST:$DIR/"
# Tracked data/ files (prospect FV caches etc.) ship without --delete, so the DB and refresh state stay put.
(cd "$STAGE" && find data -type f -not -name '*.db' -not -name '*.wal') | rsync -a --files-from=- "$STAGE/" "$HOST:$DIR/"

ssh -t "$HOST" "cd '$DIR' && export PATH=\$HOME/.local/node/bin:\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:\$PATH && uv sync --locked && (cd frontend && npm ci) && mkdir -p data/duckdb data/refresh"
ssh "$HOST" "test -f '$DIR/data/duckdb/trades.db'" || { echo "trades.db missing on $HOST: copy it first" >&2; exit 1; }
ssh "$HOST" "cd '$DIR' && export PATH=\$HOME/.local/node/bin:\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:\$PATH && uv run python scripts/refresh_daily.py --build-only"

cat <<EOF

Code is on $HOST:$DIR and the site is built. Remaining steps are yours (sudo):
  ssh -t $HOST
  cd $DIR
  for j in refresh web; do sed -e "s#__USER__#\$USER#g" -e "s#__APP_DIR__#\$PWD#g" deploy/com.savage.ste-\$j.plist | sudo tee /Library/LaunchDaemons/com.savage.ste-\$j.plist >/dev/null; sudo chown root:wheel /Library/LaunchDaemons/com.savage.ste-\$j.plist; sudo launchctl bootstrap system /Library/LaunchDaemons/com.savage.ste-\$j.plist; done
  tailscale serve --bg 8097
EOF
