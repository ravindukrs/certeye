FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    build-essential \
    rustc \
    cargo \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system appgroup && useradd --system --group appgroup appuser

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY agent.py ./

RUN chown -R appuser:appgroup /app

USER appuser

CMD ["python", "agent.py"]