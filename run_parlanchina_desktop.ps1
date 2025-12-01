#!/usr/bin/env pwsh

# Parlanchina desktop startup script
# Launches the desktop mode through the package entry point

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: uv is not installed" -ForegroundColor Red
    Write-Host ""
    Write-Host "To install uv, visit: https://docs.astral.sh/uv/getting-started/installation/"
    Write-Host "Or run: powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'"
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Error: Virtual environment not found at .venv" -ForegroundColor Red
    Write-Host ""
    Write-Host "To set up the environment, run:"
    Write-Host "  uv sync"
    exit 1
}

Write-Host "Starting Parlanchina desktop mode with uv..." -ForegroundColor Green
uv run -m parlanchina desktop @Args
