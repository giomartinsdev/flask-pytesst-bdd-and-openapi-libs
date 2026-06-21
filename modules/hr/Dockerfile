# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install OS deps: pymssql needs FreeTDS headers; gcc for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    freetds-dev \
    freetds-bin \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared lib packages first (better layer caching)
COPY modules/lib/openapi-flask-utils ./lib/openapi-flask-utils
COPY modules/lib/pytest-bdd-utils    ./lib/pytest-bdd-utils

# Copy application source
COPY modules/hr/src/hr ./src/hr

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Make lib namespace packages available
ENV PYTHONPATH="/app/src:/app/lib/openapi-flask-utils:/app/lib/pytest-bdd-utils"

EXPOSE 5001

CMD ["python", "-m", "flask", "--app", "hr.app:create_app", "run", \
     "--host", "0.0.0.0", "--port", "5001"]
