# MCP Reddit Server - Streamable HTTP
# For self-hosting on VPS with nginx reverse proxy

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Create non-root user for security
RUN addgroup --gid 1001 --system nodejs && \
    adduser --system --uid 1001 mcp
RUN chown -R mcp:nodejs /app
USER mcp

# Expose port for HTTP server
EXPOSE 8080

# Environment variables (can be overridden at runtime)
ENV PORT=8080
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Start the HTTP server
CMD ["python", "-m", "mcp_reddit.http_server"]
