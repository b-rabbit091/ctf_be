FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    postgresql-client \
    libmagic1 \
  && rm -rf /var/lib/apt/lists/*


RUN useradd -m -u 10001 appuser

# Copy deps from the correct folder (relative to build context = ..)
COPY ctf_be/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy backend code
COPY ctf_be/ /app/

RUN chmod +x /app/entrypoint.sh

RUN mkdir -p /vol/static /vol/media && \
    chown -R appuser:appuser /app /vol

USER appuser

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
