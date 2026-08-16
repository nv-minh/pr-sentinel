#!/bin/bash
# One-shot auto review pass, launched by launchd every 2 minutes.
# Loads .env (ANTHROPIC_API_KEY etc.) if present, so the key never sits in the plist.
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
export PYTHONPATH=src
exec .venv/bin/python -m src.autoreview --once
