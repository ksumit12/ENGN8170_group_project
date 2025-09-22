#!/usr/bin/env bash
set -euo pipefail

# Render docs/architecture.mmd to SVG, PNG, and PDF in docs/exports
# Prefers local Node+npx with a recent version; falls back to Docker if Node is too old.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_FILE="$ROOT_DIR/docs/architecture.mmd"
OUT_DIR="$ROOT_DIR/docs/exports"

mkdir -p "$OUT_DIR"

has_cmd() { command -v "$1" >/dev/null 2>&1; }

node_major() {
  if has_cmd node; then
    node -v | sed 's/^v//' | awk -F. '{print $1}'
  else
    echo 0
  fi
}

render_with_mmdc() {
  local in="$1"; shift
  local out_base="$1"; shift
  local CLI_VER="10.9.1"
  local base_args=(-i "$in" -t neutral)
  # SVG (transparent), PNG/PDF (white background) with higher scale
  npx --yes @mermaid-js/mermaid-cli@"${CLI_VER}" "${base_args[@]}" -o "${out_base}.svg" -b transparent -s 1.6
  npx --yes @mermaid-js/mermaid-cli@"${CLI_VER}" "${base_args[@]}" -o "${out_base}.png" -b white -s 2.0
  npx --yes @mermaid-js/mermaid-cli@"${CLI_VER}" "${base_args[@]}" -o "${out_base}.pdf" -b white -s 1.6
}

render_with_docker() {
  local in="$1"; shift
  local out_base="$1"; shift
  local IMG="ghcr.io/mermaid-js/mermaid-cli:mmdc-10.9.1"
  docker run --rm -u $(id -u):$(id -g) -v "$ROOT_DIR":"/data" "$IMG" \
    -i "/data/docs/architecture.mmd" -o "/data/docs/exports/architecture.svg" -t neutral -b transparent -s 1.6
  docker run --rm -u $(id -u):$(id -g) -v "$ROOT_DIR":"/data" "$IMG" \
    -i "/data/docs/architecture.mmd" -o "/data/docs/exports/architecture.png" -t neutral -b white -s 2.0
  docker run --rm -u $(id -u):$(id -g) -v "$ROOT_DIR":"/data" "$IMG" \
    -i "/data/docs/architecture.mmd" -o "/data/docs/exports/architecture.pdf" -t neutral -b white -s 1.6
}

main() {
  local nm=$(node_major)
  if has_cmd npx && [ "$nm" -ge 18 ]; then
    echo "Using local Node $nm with Mermaid CLI..." >&2
    render_with_mmdc "$SRC_FILE" "$OUT_DIR/architecture"
  elif has_cmd docker; then
    echo "Using Docker Mermaid CLI (Node too old or npx missing)..." >&2
    render_with_docker "$SRC_FILE" "$OUT_DIR/architecture"
  elif has_cmd npx; then
    echo "Found Node $nm (<18). Please upgrade Node to >=18 or install Docker. Falling back failed." >&2
    exit 1
  else
    echo "Neither Node+npx nor Docker found. Install one of them to render the diagram." >&2
    exit 1
  fi
  echo "Rendered files saved to $OUT_DIR:"
  ls -lh "$OUT_DIR" | awk '{print $9, $5}' | sed '/^$/d'
}

main "$@"
