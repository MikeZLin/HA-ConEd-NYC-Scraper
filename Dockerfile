FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir '.[api]' \
    && useradd --system --uid 10001 --create-home coned \
    && mkdir -p /app/data \
    && chown coned:coned /app/data

USER coned

EXPOSE 8000

CMD ["python", "-m", "coned_scraper"]
