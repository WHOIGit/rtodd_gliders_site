FROM python:3.12-slim

# Prevents Python from writing pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional but common). Keep minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY src/ /app/src/

ENV PYTHONPATH=/app/src
# --no-control-socket: the container runs as a UID with no home directory
# (see `user:` in compose.yml), so gunicorn's control socket would try to
# create /.gunicorn/ and fail with EACCES. We don't use `gunicornc` runtime
# management, so disable the socket entirely.
CMD ["gunicorn", "--no-control-socket", "-b", "0.0.0.0:8050", "src.app:server"]
