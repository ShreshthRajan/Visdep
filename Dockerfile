# Production Dockerfile for VisDep Backend
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies including git for repo cloning
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend ./backend
# Note: Environment variables are injected by Railway/Docker at runtime
# Do NOT copy .env files - they would override production env vars

# Copy startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Create data directories (will be overridden by volume mount)
RUN mkdir -p /data/faiss_indexes

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Health check - uses simple /health endpoint that always returns 200
# Increased start-period to 60s to allow for FAISS pre-warming on startup
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start command - use startup script
CMD ["/app/start.sh"]
