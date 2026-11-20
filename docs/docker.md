# KubeCoach — Docker Containerization Guide

### Project ID: SJ-58
### Theme: Developer Tools
### Student: Bhushan Kailas Chaturbhuj (Reg. No: 2125PCAM1038)
### Day 12 Deliverable

---

## 1. Introduction to Docker

**Docker** is an open-source platform that packages an application and all its runtime dependencies (Python interpreter, libraries, system packages, configuration files) into a standardized unit called a **container**.

### Why KubeCoach Uses Docker:
1. **Eliminate "Works on My Machine" Syndrome:** Final-year students and evaluators run different operating systems (Windows, macOS, Ubuntu). A Docker container guarantees that KubeCoach runs identically everywhere.
2. **Deterministic Python Runtime:** Locks Python to version 3.11-slim with exact package versions from `requirements.txt`.
3. **Isolated Persistence:** Decouples the application code from local state (ChromaDB vectors, feedback records, user questions) using Docker named volumes.
4. **DevOps Alignment:** Containerization is the foundational prerequisite for Kubernetes deployment, which directly aligns with KubeCoach's mission as a Kubernetes educational tool.

---

## 2. Core Docker Concepts Explained

| Concept | Definition | Analogy |
|---|---|---|
| **Dockerfile** | A text document containing sequential instructions to build an image. | The recipe or blueprint. |
| **Docker Image** | A lightweight, standalone, immutable package containing code, runtime, libraries, and settings. | The frozen snapshot or class definition. |
| **Docker Container** | A runnable, isolated instance of an image executing in user space. | The living, running object created from the class. |
| **Docker Volume** | A storage mechanism managed by Docker outside the container filesystem. | An external hard drive plugged into the container. |
| **Port Mapping (`-p`)** | Forwards network traffic from a host machine port to a container port. | A mailbox or door number linking outside to inside. |

---

## 3. Dockerfile Architecture

The `Dockerfile` is located in the repository root and employs production best practices:

```dockerfile
# 1. Base Image: Lightweight, official, security-patched Python 3.11
FROM python:3.11-slim

# 2. Environment Variables: Prevent bytecode (.pyc) and enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    LLM_PROVIDER=mock \
    API_BASE_URL=http://127.0.0.1:8000

# 3. System Utilities: Install curl for Docker HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. Security Principle of Least Privilege: Create dedicated non-root user
RUN groupadd -r kubecoach && useradd -r -g kubecoach -u 1000 -m kubecoach

# 5. Working Directory
WORKDIR /app

# 6. Cache Optimization: Copy requirements first to cache dependency installation layer
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# 7. Copy Application Code & Assets
COPY app/ ./app/
COPY data/ ./data/
COPY prompts/ ./prompts/
COPY ui/ ./ui/
COPY .streamlit/ ./.streamlit/
COPY day01_intro.py day01_menu.py README.md .env.example pytest.ini ./
COPY docker-entrypoint.sh ./

# 8. Ownership & Permissions
RUN chmod +x docker-entrypoint.sh && \
    chown -R kubecoach:kubecoach /app

# 9. Non-Root Execution
USER kubecoach

# 10. Document Exposed Ports
EXPOSE 8000 8501

# 11. Container Health Check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 12. Flexible Entrypoint
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
```

---

## 4. `.dockerignore` Configuration

The `.dockerignore` file prevents sensitive, bulky, or platform-specific files from entering the Docker build context:

```text
# Version Control
.git
.gitignore
.github

# Virtual Environments
.venv/
.venv*/
venv/

# Caches & Bytecode
__pycache__/
*.py[cod]
.pytest_cache/
.coverage

# Secrets (Critical Security Guardrail)
.env
.env.*
!.env.example

# Local ephemeral data
data/chroma_db/
*.log
*.tmp
```

---

## 5. Entrypoint & Multi-Mode Execution (`docker-entrypoint.sh`)

KubeCoach provides a flexible shell entrypoint script supporting multiple operational modes:

| Mode | Command | Behavior |
|---|---|---|
| **API (Default)** | `docker run -p 8000:8000 kubecoach` | Launches FastAPI Uvicorn REST backend on `http://0.0.0.0:8000`. |
| **UI** | `docker run -p 8501:8501 kubecoach ui` | Launches Streamlit frontend on `http://0.0.0.0:8501`. |
| **All (Both)** | `docker run -p 8000:8000 -p 8501:8501 kubecoach all` | Runs FastAPI in background and Streamlit in foreground. |
| **Test** | `docker run --rm kubecoach test` | Runs the complete 150-test Pytest suite inside the container. |
| **Shell** | `docker run -it --rm kubecoach bash` | Opens an interactive non-root shell for inspection. |

---

## 6. Docker Command Reference

### A. Build the Image
```bash
# Build the Docker image tagged as 'kubecoach'
docker build -t kubecoach .

# Verify the image was created
docker images | grep kubecoach
```

### B. Run the Container
```bash
# Run FastAPI backend in detached mode with port mapping
docker run -d \
  --name kubecoach-container \
  -p 8000:8000 \
  kubecoach

# Run with persistent volume storage for datasets & ChromaDB
docker run -d \
  --name kubecoach-container \
  -p 8000:8000 \
  -v kubecoach_data:/app/data \
  kubecoach

# Run with live LLM API keys via environment variables (never hardcoded)
docker run -d \
  --name kubecoach-container \
  -p 8000:8000 \
  -e LLM_PROVIDER=groq \
  -e GROQ_API_KEY="your-groq-key-here" \
  kubecoach
```

### C. Container Inspection & Monitoring
```bash
# List running containers
docker ps

# List all containers (including stopped)
docker ps -a

# View container output logs
docker logs kubecoach-container

# Follow streaming container logs in real time
docker logs -f kubecoach-container

# Inspect container health status
docker inspect --format='{{json .State.Health}}' kubecoach-container
```

### D. Verify Endpoints
```bash
# Check application health
curl -X GET http://localhost:8000/health

# Open interactive Swagger UI documentation in browser:
# http://localhost:8000/docs
```

### E. Container Lifecycle Management
```bash
# Stop the running container
docker stop kubecoach-container

# Restart a stopped container
docker start kubecoach-container

# Remove the container
docker rm kubecoach-container

# Remove the container forcefully if running
docker rm -f kubecoach-container

# Remove the image
docker rmi kubecoach
```

---

## 7. Multi-Container Orchestration (`docker-compose.yml`)

For running both the FastAPI backend and Streamlit UI in isolated, networked containers:

```bash
# Start both backend (port 8000) and frontend (port 8501)
docker compose up -d

# View status of Compose services
docker compose ps

# View unified logs
docker compose logs -f

# Shut down services safely
docker compose down
```

---

## 8. Persistent Storage & Volumes

### Why Volumes Matter:
Containers have an ephemeral (temporary) writable layer. If a container is removed with `docker rm`, all files written inside it during execution are lost.

To safeguard:
- Saved student questions ([`data/questions.json`](data/questions.json))
- Thumbs-up/down feedback ([`data/feedback.json`](data/feedback.json))
- ChromaDB vector embeddings ([`data/chroma_db/`](data/chroma_db/))

We mount a Docker named volume (`kubecoach_data`) at `/app/data`:
```bash
docker volume create kubecoach_data
docker run -d -p 8000:8000 -v kubecoach_data:/app/data kubecoach
```

---

## 9. Troubleshooting Common Docker Issues

| Symptom | Cause | Solution |
|---|---|---|
| `failed to connect to docker API / daemon not running` | Docker Desktop is not started or service is stopped. | Start Docker Desktop from the Start Menu or system tray. |
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | Another local process (e.g. local Uvicorn) is using port 8000. | Stop the local process or map to a different host port: `-p 8080:8000`. |
| `Permission denied` inside container | Running as non-root user writing to an un-owned directory. | The Dockerfile sets `chown -R kubecoach:kubecoach /app`, ensuring write access to `/app/data`. |
| `429 Too Many Requests / LLM Provider Error` | Missing or invalid API key in container environment. | Container defaults to `LLM_PROVIDER=mock`, which requires zero keys and runs completely offline. |

---

## 10. Viva Talking Points for Evaluation

1. **Why multi-layer caching with `COPY requirements.txt .` first?**  
   Docker caches each layer sequentially. By copying `requirements.txt` and running `pip install` before copying source code, subsequent code changes do not re-trigger package installation, reducing build times from minutes to seconds.
2. **Why run as a non-root user (`USER kubecoach`)?**  
   Security best practice. Running as root inside a container poses a privilege escalation hazard if an exploit breaches the container runtime boundary.
3. **What is the difference between `EXPOSE` and `-p`?**  
   `EXPOSE` in the Dockerfile is documentation indicating which ports the software listens on. `-p 8000:8000` during `docker run` actually creates the firewall and NAT port forwarding rules on the host network.
4. **How are secrets protected?**  
   `.dockerignore` strictly excludes `.env` and `.env.*`. Keys are injected at runtime via `-e` or `--env-file`, never baked into image layers where `docker history` could inspect them.
