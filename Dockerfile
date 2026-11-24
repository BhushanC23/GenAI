# ==============================================================================
# KubeCoach Dockerfile (Day 12 - Containerization)
# ==============================================================================
# Official Python 3.11 slim base image for lightweight and secure deployment
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    LLM_PROVIDER=mock \
    API_BASE_URL=http://127.0.0.1:8000

# Install runtime utilities (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group
RUN groupadd -r kubecoach && useradd -r -g kubecoach -u 1000 -m kubecoach

# Set application working directory
WORKDIR /app

# Copy dependency requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies into system Python without saving pip cache
# Install CPU-optimized PyTorch first for lightweight, fast container builds
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code, datasets, prompts, tests, and configuration
COPY app/ ./app/
COPY data/ ./data/
COPY prompts/ ./prompts/
COPY ui/ ./ui/
COPY tests/ ./tests/
COPY docs/ ./docs/
COPY .streamlit/ ./.streamlit/
COPY day01_intro.py day01_menu.py README.md .env.example pytest.ini ./
COPY docker-entrypoint.sh ./

# Set executable permissions on entrypoint and transfer ownership to non-root user
RUN chmod +x docker-entrypoint.sh && \
    chown -R kubecoach:kubecoach /app

# Switch to non-root user for security
USER kubecoach

# Expose FastAPI backend (8000) and Streamlit frontend (8501)
EXPOSE 8000 8501

# Container health check against FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default entrypoint and command
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
