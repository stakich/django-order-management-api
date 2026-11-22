#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

git clone --quiet --depth 1 --branch 2.x https://github.com/bbulakh/tailwind-ecommerce.git "$TEMP_DIR/template"
mkdir -p "$ROOT/public/assets/images"
cp -a "$TEMP_DIR/template/src/assets/images/." "$ROOT/public/assets/images/"
cp "$TEMP_DIR/template/LICENSE" "$ROOT/TEMPLATE_LICENSE"
echo "MayBell images installed in frontend/public/assets/images/"
