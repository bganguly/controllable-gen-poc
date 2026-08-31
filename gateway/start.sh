#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in your API keys, then re-run."
  exit 1
fi

set -a
source .env
set +a

if ! command -v psql &>/dev/null; then
  echo "PostgreSQL not found. Install via: brew install postgresql && brew services start postgresql"
  exit 1
fi

if ! command -v redis-cli &>/dev/null; then
  echo "Redis not found. Install via: brew install redis && brew services start redis"
  exit 1
fi

DB_NAME="llm_gateway"
psql -lqt 2>/dev/null | cut -d '|' -f1 | grep -qw "$DB_NAME" || createdb "$DB_NAME"
echo "Database '$DB_NAME' ready."

redis-cli ping &>/dev/null || { echo "Redis is not running. Start with: brew services start redis"; exit 1; }
echo "Redis ready."

pip install -q -r requirements.txt

exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
