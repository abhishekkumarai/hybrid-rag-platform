# Shared image for the gateway, ingestion worker, and directory reconciler.
# All three run the same codebase and differ only in their compose command.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# PyMuPDF and RapidOCR need these shared libraries at runtime; curl backs the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies come from pyproject.toml so the image and a local `pip install -e .`
# never drift apart. architecture_plan.md is the declared readme and must be present
# for the build backend to resolve project metadata.
COPY pyproject.toml architecture_plan.md ./
COPY services/__init__.py services/
COPY contracts/__init__.py contracts/
COPY components/__init__.py components/

# Docling depends on torch, which resolves to the CUDA build by default and drags in several GB of
# NVIDIA wheels. This container never touches the GPU — VRAM is reserved for Ollama, and both the
# parsers and the FlashRank reranker run on CPU — so pin the CPU-only torch first and let the
# project install reuse it.
RUN pip install --upgrade pip && \
    pip install --index-url https://download.pytorch.org/whl/cpu torch && \
    pip install ".[parse]"

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "services.gateway.api:app", "--host", "0.0.0.0", "--port", "8000"]
