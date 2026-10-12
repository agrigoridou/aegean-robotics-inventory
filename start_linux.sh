#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
exec .venv/bin/python server.py --host 127.0.0.1 --port 8989
