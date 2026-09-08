# Makefile for Hybrid RAG Platform (SOA + Langflow)

.PHONY: help setup services-up services-down test check run serve eval gate scheduler worker clean

help:
	@echo "Available targets:"
	@echo "  make setup          - Sync and install Python dependencies via uv"
	@echo "  make services-up    - Start Docker infrastructure (Qdrant & Redis)"
	@echo "  make services-down  - Stop Docker infrastructure"
	@echo "  make test           - Run all unit tests"
	@echo "  make check          - Run ruff linting and unit tests"
	@echo "  make run            - Launch Langflow with custom components (:7860)"
	@echo "  make serve          - Launch SOA REST & SSE Gateway + UI (:8000)"
	@echo "  make eval           - Run offline evaluation & faithfulness benchmark"
	@echo "  make gate           - Run CI/CD evaluation regression quality gate"
	@echo "  make scheduler      - Run directory reconciler daemon"
	@echo "  make worker         - Run asynchronous Redis queue worker daemon"
	@echo "  make clean          - Clean up temporary files and caches"

setup:
	uv sync

services-up:
	docker compose up -d

services-down:
	docker compose down

test:
	python -m pytest tests/unit -v

check:
	ruff check .
	python -m pytest tests/unit -v

run:
	langflow run --host 0.0.0.0 --port 7860 --workers 1 --no-open-browser

serve:
	python -m uvicorn services.gateway.api:app --host 0.0.0.0 --port 8000 --reload

eval:
	python tests/eval/eval_harness.py

gate:
	python tests/eval/regression_gate.py

scheduler:
	python services/scheduler/reconciler.py

worker:
	python services/scheduler/worker.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
