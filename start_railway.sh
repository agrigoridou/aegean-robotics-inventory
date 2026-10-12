#!/bin/sh
set -eu
: "${PORT:=8080}"
exec python server.py --host 0.0.0.0 --port "$PORT"
