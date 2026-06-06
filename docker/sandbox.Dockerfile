# docker/sandbox.Dockerfile
# Minimal Python sandbox image for Ambrio's Maker-Checker executor.
# No pip, no shell access, read-only filesystem at runtime.
FROM python:3.11-slim

# Create non-root sandbox user
RUN useradd -m -u 1000 sandbox \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
USER sandbox

# No ENTRYPOINT — docker_runner.py specifies the command explicitly
