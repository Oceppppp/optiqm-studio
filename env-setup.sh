#!/usr/bin/env bash
set -euo pipefail

# Izinkan environment PATH pada bash non-interaktif
sed -i '/case \$- in/,/esac/d' ~/.bashrc 2>/dev/null || true

REPO_DIR="/home/antigravity/optiqm-studio"
VENV_DIR="$REPO_DIR/.venv"

export PATH="$VENV_DIR/bin:$PATH"
LINE="export PATH=\"$VENV_DIR/bin:\$PATH\""
grep -qxF "$LINE" ~/.bashrc 2>/dev/null || echo "$LINE" >> ~/.bashrc

if [ -d "$REPO_DIR" ]; then
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    if command -v uv >/dev/null 2>&1; then
      uv venv "$VENV_DIR" --python 3.11 || python3 -m venv "$VENV_DIR"
    else
      python3 -m venv "$VENV_DIR"
    fi
  fi

  if [ -f "$REPO_DIR/backend/pyproject.toml" ]; then
    if command -v uv >/dev/null 2>&1; then
      uv pip install --python "$VENV_DIR/bin/python" -q -e "$REPO_DIR/backend[dev]"
    else
      "$VENV_DIR/bin/pip" install -q -e "$REPO_DIR/backend[dev]"
    fi
  fi

  if [ -d "$REPO_DIR/frontend" ] && [ -f "$REPO_DIR/frontend/package.json" ]; then
    if [ ! -d "$REPO_DIR/frontend/node_modules" ]; then
      if [ -f "$REPO_DIR/frontend/package-lock.json" ]; then
        npm --prefix "$REPO_DIR/frontend" ci --silent
      else
        npm --prefix "$REPO_DIR/frontend" install --silent
      fi
    fi
    if [ ! -f "$REPO_DIR/frontend/dist/index.html" ]; then
      npm --prefix "$REPO_DIR/frontend" run build
    fi
  fi

  "$VENV_DIR/bin/python" -c "from optiqm.core import discover, all_modules; discover(); mods = all_modules(); assert len(mods) >= 43, len(mods)"
fi
