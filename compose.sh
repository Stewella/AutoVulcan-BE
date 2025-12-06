#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure host directories exist
mkdir -p "$PROJECT_DIR/executions"

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "[compose] ERROR: .env not found at $PROJECT_DIR/.env"
  echo "Create it with your staging SSH/DB values."
  exit 1
fi

# Build and start using env file (secrets are not baked into the image)
echo "[compose] Building image..."
docker compose --env-file "$PROJECT_DIR/.env" -f "$PROJECT_DIR/docker-compose.yml" build

echo "[compose] Starting service..."
docker compose --env-file "$PROJECT_DIR/.env" -f "$PROJECT_DIR/docker-compose.yml" up -d

echo "[compose] Service started. Health check: http://localhost:8000/health"
