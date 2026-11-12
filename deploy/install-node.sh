#!/bin/zsh
# Run on the iMac. Installs Node 22 under ~/.local/node (no brew, nothing system-wide), because the
# system Node is 14 and Vite 8 needs 20.19+ or 22.12+. Verifies the tarball against nodejs.org's SHASUMS.
set -eu
BASE="https://nodejs.org/dist/latest-v22.x"
[[ "$(uname -m)" == "x86_64" ]] && ARCH=x64 || ARCH=arm64
cd "$(mktemp -d)"
curl -fsSL "$BASE/SHASUMS256.txt" -o SHASUMS256.txt
FILE="$(grep -o "node-v22[0-9.]*-darwin-$ARCH.tar.gz" SHASUMS256.txt | head -1)"
curl -fsSL "$BASE/$FILE" -o "$FILE"
grep " $FILE\$" SHASUMS256.txt | shasum -a 256 -c -
rm -rf "$HOME/.local/node"
mkdir -p "$HOME/.local/node"
tar -xzf "$FILE" -C "$HOME/.local/node" --strip-components=1
"$HOME/.local/node/bin/node" -v
PATH="$HOME/.local/node/bin:$PATH" npm -v
