#!/bin/sh
set -e

echo "A aplicar migrações da base de dados..."
alembic upgrade head

echo "A arrancar a API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
