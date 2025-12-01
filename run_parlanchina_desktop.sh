#!/usr/bin/env bash

# Parlanchina desktop startup script
# Launches the desktop mode through the package entry point

set -e

cd "$(dirname "$0")"

if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed"
    echo ""
    echo "To install uv, visit: https://docs.astral.sh/uv/getting-started/installation/"
    echo "Or run: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment not found at .venv"
    echo ""
    echo "To set up the environment, run:"
    echo "  uv sync"
    exit 1
fi

echo "Starting Parlanchina desktop mode with uv..."
uv run -m parlanchina desktop "$@"
