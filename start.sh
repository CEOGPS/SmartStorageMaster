#!/usr/bin/env bash
# Start Storage Manager Pro (backend + web UI) and open it.
cd "$(dirname "$0")" || exit 1
command -v node >/dev/null || { echo "Node.js was not found. Install it from https://nodejs.org"; exit 1; }
exec node scripts/launch.mjs "$@"
