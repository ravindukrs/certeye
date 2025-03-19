FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --system appgroup && useradd --system --group appgroup appuser

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY agent.py ./

RUN chown -R appuser:appgroup /app

USER appuser

CMD ["python", "agent.py"]
