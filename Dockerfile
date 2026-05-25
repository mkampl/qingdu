# --- Stage 1: build the Vue 3 frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime ---
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies. ffmpeg is here so faster-whisper can
# decode browser-recorded WebM/Opus and librosa's audioread backend
# can resample. libsndfile1 is the C library soundfile binds to.
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/data /app/static

# Copy application code + favicons/manifest (still served at /static).
# The Vue 3 frontend supersedes the legacy templates — see Stage 1 build.
COPY app/ /app/app/
COPY static/ /app/static/

# Copy the Vite build artefact from the frontend stage.
COPY --from=frontend-build /build/dist /app/frontend/dist

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Health check — use urllib (stdlib) so we don't pull in requests/curl
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
