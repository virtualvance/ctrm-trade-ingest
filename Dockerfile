# ==============================================================================
# STAGE 1: BUILDER
# Compile Python dependencies inside an isolated virtual environment so build tools
# (gcc, headers) stay out of the final production image.
# ==============================================================================
# Pin a specific Debian Bookworm slim image rather than floating "latest" tags
# to guarantee repeatable builds and predictable security patches.
FROM python:3.11-slim-bookworm AS builder

# Set an isolated working directory for dependency compilation.
WORKDIR /build

# Copy only requirements.txt first so Docker can cache the dependency layer
# and skip reinstalling packages when only application code changes.
COPY requirements.txt .

# Install C build tools and PostgreSQL client headers needed if wheels must compile,
# create an isolated virtual environment, and install dependencies without cache files.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ==============================================================================
# STAGE 2: RUNTIME
# Copy only the compiled virtual environment and app source into a clean base image.
# ==============================================================================
FROM python:3.11-slim-bookworm AS runner

# Create a dedicated non-root system group and user (UID 10001).
# Running containers as non-root limits blast radius if the app is ever compromised.
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash appuser

# Create and switch to the application runtime directory.
WORKDIR /app

# Copy the pre-built virtual environment from the builder stage without build compilers.
COPY --from=builder /opt/venv /opt/venv

# Copy application source files into the container (excluded files filtered by .dockerignore).
COPY app/ ./app

# Prepend the virtual environment to PATH so uvicorn runs automatically, and disable
# stdout buffering so JSON logs stream immediately to Kubernetes log collectors.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Transfer ownership of /app to the unprivileged user and drop root privileges.
RUN chown -R appuser:appgroup /app
USER appuser

# Document the network port Uvicorn listens on inside the container.
EXPOSE 8000

# Launch Uvicorn bound to all interfaces (0.0.0.0) so Kubernetes Services can route traffic in.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]