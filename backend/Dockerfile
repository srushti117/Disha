FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data MODELS_DIR=/models
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
COPY constraints.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 8 -r requirements.txt -c constraints.txt
COPY app ./app
RUN mkdir -p /data /models && useradd -m disha && chown -R disha /data /models /app
USER disha
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
