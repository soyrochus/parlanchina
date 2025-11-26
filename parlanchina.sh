#!/usr/bin/env bash

# Parlanchina startup script
# Starts the application using Hypercorn with auto-reload

set -e

# Change to the script's directory
cd "$(dirname "$0")"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed"
    echo ""
    echo "To install uv, visit: https://docs.astral.sh/uv/getting-started/installation/"
    echo "Or run: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment not found at .venv"
    echo ""
    echo "To set up the environment, run:"
    echo "  uv sync"
    exit 1
fi

echo "Starting Parlanchina with uv..."
uv run hypercorn parlanchina:app --bind 127.0.0.1:5000 --reload
