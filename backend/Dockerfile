FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY optiqm ./optiqm

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn optiqm.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
