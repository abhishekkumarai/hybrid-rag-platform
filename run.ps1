<#
.SYNOPSIS
  Task runner for Hybrid RAG Platform on Windows PowerShell (Alternative to GNU make).

.EXAMPLE
  .\run.ps1 serve
  .\run.ps1 eval
  .\run.ps1 test
  .\run.ps1 check
  .\run.ps1 demo
#>

param (
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

function Show-Help {
    Write-Host "Hybrid RAG Platform Task Runner (PowerShell)" -ForegroundColor Cyan
    Write-Host "Usage: .\run.ps1 <target>" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Available targets:"
    Write-Host "  serve          - Launch SOA REST & SSE Gateway + Web Client (http://localhost:8000)"
    Write-Host "  run            - Launch Langflow with custom components (http://localhost:7860)"
    Write-Host "  eval           - Run offline evaluation & faithfulness benchmark"
    Write-Host "  gate           - Run CI/CD evaluation regression quality gate"
    Write-Host "  demo           - Run end-to-end pipeline test against Ollama & Qdrant"
    Write-Host "  test           - Run all pytest unit & integration tests"
    Write-Host "  check          - Run ruff linter and full pytest suite"
    Write-Host "  services-up    - Start infrastructure only (Qdrant, Redis, PostgreSQL)"
    Write-Host "  services-down  - Stop all Docker containers"
    Write-Host "  stack-up       - Build and start the entire stack (infra + gateway + worker + scheduler)"
    Write-Host "  stack-down     - Stop the entire stack"
    Write-Host "  stack-logs     - Tail logs from the containerised app services"
    Write-Host "  scheduler      - Run directory reconciler daemon"
    Write-Host "  worker         - Run asynchronous Redis queue worker daemon"
    Write-Host "  clean          - Remove __pycache__, .pytest_cache, and .ruff_cache"
}

switch ($Target.ToLower()) {
    "serve" {
        Write-Host "Starting SOA Gateway on http://localhost:8000..." -ForegroundColor Green
        python -m uvicorn services.gateway.api:app --host 0.0.0.0 --port 8000 --reload
    }
    "run" {
        Write-Host "Starting Langflow UI on http://localhost:7860..." -ForegroundColor Green
        langflow run --host 0.0.0.0 --port 7860 --workers 1 --no-open-browser
    }
    "eval" {
        Write-Host "Running evaluation benchmark harness..." -ForegroundColor Green
        python tests/eval/eval_harness.py
    }
    "gate" {
        Write-Host "Running CI/CD evaluation regression gate..." -ForegroundColor Green
        python tests/eval/regression_gate.py
    }
    "demo" {
        Write-Host "Running live RAG pipeline demo..." -ForegroundColor Green
        python scripts/demo_pipeline.py
    }
    "test" {
        Write-Host "Running pytest test suite..." -ForegroundColor Green
        python -m pytest tests -v
    }
    "check" {
        Write-Host "Checking code quality with ruff..." -ForegroundColor Green
        python -m ruff check .
        Write-Host "Running test suite..." -ForegroundColor Green
        python -m pytest tests -v
    }
    "services-up" {
        Write-Host "Starting infrastructure (Qdrant, Redis, PostgreSQL)..." -ForegroundColor Green
        docker compose up -d qdrant redis postgres
    }
    "services-down" {
        Write-Host "Stopping Docker containers..." -ForegroundColor Green
        docker compose down
    }
    "stack-up" {
        Write-Host "Building and starting the entire stack..." -ForegroundColor Green
        docker compose up -d --build
    }
    "stack-down" {
        Write-Host "Stopping the entire stack..." -ForegroundColor Green
        docker compose down
    }
    "stack-logs" {
        Write-Host "Tailing app service logs (Ctrl+C to exit)..." -ForegroundColor Green
        docker compose logs -f gateway worker scheduler
    }
    "scheduler" {
        Write-Host "Starting directory reconciler..." -ForegroundColor Green
        python services/scheduler/reconciler.py
    }
    "worker" {
        Write-Host "Starting asynchronous Redis queue worker..." -ForegroundColor Green
        python services/scheduler/worker.py
    }
    "clean" {
        Write-Host "Cleaning cache directories..." -ForegroundColor Green
        Get-ChildItem -Path . -Include __pycache__, .pytest_cache, .ruff_cache -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
        Write-Host "Done!" -ForegroundColor Green
    }
    Default {
        Show-Help
    }
}
