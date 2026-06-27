FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG INSTALL_LOCAL_AI=0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-optional.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && if [ "$INSTALL_LOCAL_AI" = "1" ]; then pip install -r requirements-optional.txt; fi

COPY . .
RUN mkdir -p data logs

EXPOSE 8000

CMD uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8000}
