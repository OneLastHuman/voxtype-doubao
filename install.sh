#!/usr/bin/env bash
# One-command installer for voxtype-doubao.
#
#   curl -fsSL https://raw.githubusercontent.com/OneLastHuman/voxtype-doubao/main/install.sh | bash
#
# Installs into ${XDG_DATA_HOME:-~/.local/share}/voxtype-doubao, points
# voxtype at the local proxy, and installs the systemd user service.
set -euo pipefail

REPO_URL="https://github.com/OneLastHuman/voxtype-doubao.git"
INSTALL_DIR="${VOX_TYPE_DOUBAO_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/voxtype-doubao}"

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

repo_dir=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  candidate="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "$candidate/pyproject.toml" ]]; then
    repo_dir="$candidate"
  fi
fi

command -v voxtype >/dev/null 2>&1 || die "voxtype not found. Install it first: https://github.com/peteonrails/voxtype"
command -v python3 >/dev/null 2>&1 || die "python3 not found"

if command -v pacman >/dev/null 2>&1; then
  missing=()
  for pkg in git python libpulse gtk4 webkit2gtk-4.1 python-gobject; do
    pacman -Qq "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if ((${#missing[@]} > 0)); then
    say "Installing dependencies: ${missing[*]}"
    sudo pacman -S --needed --noconfirm "${missing[@]}"
  fi
fi

if [[ -z "$repo_dir" ]]; then
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    say "Updating $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only
  else
    say "Installing to $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
  repo_dir="$INSTALL_DIR"
fi

cd "$repo_dir"

if [[ ! -x .venv/bin/python ]]; then
  say "Creating Python environment"
  python3 -m venv --system-site-packages .venv
fi

say "Installing voxtype-doubao"
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -e .

mkdir -p "$HOME/.local/bin"
ln -sf "$repo_dir/.venv/bin/voxtype-doubao" "$HOME/.local/bin/voxtype-doubao"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) warn "$HOME/.local/bin is not on PATH; use $repo_dir/.venv/bin/voxtype-doubao" ;;
esac

say "Configuring voxtype"
.venv/bin/voxtype-doubao configure --yes

if [[ "${VOX_TYPE_DOUBAO_SKIP_LOGIN:-0}" != "1" ]]; then
  if [[ -z "${WAYLAND_DISPLAY:-}" && -z "${DISPLAY:-}" ]]; then
    warn "No graphical session detected."
    warn "Run this after logging in: $repo_dir/.venv/bin/voxtype-doubao login"
  elif ! .venv/bin/voxtype-doubao status --json 2>/dev/null | grep -q '"present": true'; then
    say "Opening the Doubao login window"
    .venv/bin/voxtype-doubao login || warn "Login window failed; run: $repo_dir/.venv/bin/voxtype-doubao login"
  fi
fi

if [[ "${VOX_TYPE_DOUBAO_SKIP_SERVICE:-0}" != "1" ]]; then
  say "Installing the background service"
  .venv/bin/voxtype-doubao install-service

  if systemctl --user cat voxtype.service >/dev/null 2>&1; then
    say "Restarting voxtype"
    systemctl --user restart voxtype
  fi
fi

if [[ "${VOX_TYPE_DOUBAO_SKIP_OMARCHY:-0}" != "1" ]] \
  && command -v omarchy >/dev/null 2>&1 \
  && [[ -d "$HOME/.config/omarchy" ]]; then
  say "Installing the Omarchy bar widget"
  .venv/bin/python "$repo_dir/scripts/omarchy_install.py"
  omarchy restart shell || warn "Restart the shell with: omarchy restart shell"
fi

say "Done"
.venv/bin/voxtype-doubao status

cat <<EOF

Press your voxtype hotkey and speak. If nothing happens:
  $repo_dir/.venv/bin/voxtype-doubao status
  journalctl --user -u voxtype-doubao -f
EOF
