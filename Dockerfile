# Production Dockerfile for Defuse the Downloads on Google Cloud Run
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure working directory layout exists
RUN mkdir -p Messy_Downloads Organized_Safe/Documents Organized_Safe/Images Organized_Safe/Installers Organized_Safe/Code Organized_Safe/Receipts Trash_Bin

# Expose container port (Cloud Run injects PORT environment variable)
EXPOSE 8080

# Run with Gunicorn using high-concurrency threaded workers
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 backend.app:app
