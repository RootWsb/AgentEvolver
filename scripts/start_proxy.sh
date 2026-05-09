#!/bin/bash
set -e
cd "$(dirname "$0")/.."
uv run python -m agent_evolver.proxy.server
