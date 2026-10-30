#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v parecord >/dev/null 2>&1; then
  echo "warning: parecord not found; install pulseaudio-utils for pre-stream mode" >&2
fi

python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

cat <<'EOF'

Installed.

Next steps:
  1. .venv/bin/voxtype-doubao login
     (or import existing doubao-murmur credentials:
      .venv/bin/voxtype-doubao import)
  2. .venv/bin/voxtype-doubao install-service
  3. point voxtype's [whisper] remote_endpoint at http://127.0.0.1:8788

See README.md for the voxtype config snippet and troubleshooting.
EOF
