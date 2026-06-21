# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install OS deps needed by pymssql (for potential cross-module use) and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared lib packages first (better layer caching)
COPY modules/lib/openapi-flask-utils ./lib/openapi-flask-utils
COPY modules/lib/pytest-bdd-utils    ./lib/pytest-bdd-utils

# Copy application source
COPY modules/products/src/products ./src/products

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Make lib namespace packages available
ENV PYTHONPATH="/app/src:/app/lib/openapi-flask-utils:/app/lib/pytest-bdd-utils"

EXPOSE 5000

CMD ["python", "-m", "flask", "--app", "products.app:create_app", "run", \
     "--host", "0.0.0.0", "--port", "5000"]
