#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
  echo "Packaging requires Apple Silicon arm64; current architecture: $ARCH" >&2
  exit 1
fi
cd "$ROOT_DIR/frontend"
pnpm build
cd "$ROOT_DIR/backend"
uv sync --group packaging
uv run --group packaging pyinstaller --clean --noconfirm "$ROOT_DIR/packaging/cost-data.spec"
echo "$ROOT_DIR/backend/dist/cost-data"
