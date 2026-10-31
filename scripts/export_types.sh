#!/usr/bin/env bash
# Generate frontend TypeScript API types from the running backend's OpenAPI schema.
# Never hand-write these types.
set -euo pipefail
API_URL="${API_URL:-http://127.0.0.1:8000}"
cd "$(dirname "$0")/../frontend"
npx openapi-typescript "$API_URL/openapi.json" -o src/api/schema.ts
echo "Wrote frontend/src/api/schema.ts from $API_URL/openapi.json"
