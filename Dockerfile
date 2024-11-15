# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean && \
    rm -rf /var/cache/apt/* && \
    pip install --upgrade pip && \
    pip install --upgrade uv

# Copy dependency files
COPY pyproject.toml ./

# Create virtual environment and install dependencies
RUN python -m venv .venv && \
    . .venv/bin/activate && \
    uv pip install -e .

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy virtual environment from builder
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/pyproject.toml ./

# Copy application code
COPY diun2homer.py ./

# Create data directory and set permissions
RUN mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

# Volume for persistent data
VOLUME /app/data

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "diun2homer.py"]
