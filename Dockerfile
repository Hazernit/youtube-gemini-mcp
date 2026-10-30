FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

# Non-root runtime and no embedded credentials.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

# Cloud Run provides PORT dynamically; default allows local Docker testing.
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
