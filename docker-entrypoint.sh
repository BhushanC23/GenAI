#!/bin/sh
set -e

# ==============================================================================
# docker-entrypoint.sh for KubeCoach Container
# ==============================================================================
# Supported Modes:
#   api    - Start FastAPI REST backend with Uvicorn on port 8000 (default)
#   ui     - Start Streamlit frontend on port 8501
#   all    - Start both FastAPI (8000) and Streamlit (8501) concurrently
#   test   - Run the full 150-test regression suite with pytest
#   custom - Execute any custom binary / shell arguments
# ==============================================================================

case "$1" in
    api)
        echo "[KubeCoach] Starting FastAPI Uvicorn REST backend on http://0.0.0.0:8000..."
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
    ui)
        echo "[KubeCoach] Starting Streamlit Web UI on http://0.0.0.0:8501..."
        exec streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
        ;;
    all)
        echo "[KubeCoach] Starting both FastAPI (port 8000) and Streamlit (port 8501)..."
        uvicorn app.main:app --host 0.0.0.0 --port 8000 &
        UVICORN_PID=$!
        sleep 2
        streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0 &
        STREAMLIT_PID=$!
        trap "kill $UVICORN_PID $STREAMLIT_PID; exit 0" SIGINT SIGTERM
        wait
        ;;
    test)
        echo "[KubeCoach] Running full test suite with pytest..."
        exec pytest tests/ -v
        ;;
    *)
        exec "$@"
        ;;
esac
