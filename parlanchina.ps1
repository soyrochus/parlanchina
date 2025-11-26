#!/usr/bin/env pwsh

# Parlanchina startup script
# Starts the application using Hypercorn with auto-reload

$ErrorActionPreference = "Stop"

# Change to the script's directory
Set-Location -Path $PSScriptRoot

# Check if uv is available
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: uv is not installed" -ForegroundColor Red
    Write-Host ""
    Write-Host "To install uv, visit: https://docs.astral.sh/uv/getting-started/installation/"
    Write-Host "Or run: powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'"
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "Error: Virtual environment not found at .venv" -ForegroundColor Red
    Write-Host ""
    Write-Host "To set up the environment, run:"
    Write-Host "  uv sync"
    exit 1
}

Write-Host "Starting Parlanchina with uv..." -ForegroundColor Green
uv run hypercorn parlanchina:app --bind 127.0.0.1:5000 --reload
