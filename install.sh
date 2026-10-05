#!/usr/bin/env bash
# Installateur Debian 13 : terminal Kitty + gestionnaire uv pour le CLI vibe.
# Installe le CLI vibe (TUI Python) depuis ce dépôt, sans toolchain Rust.
set -euo pipefail

if [[ ! -r /etc/os-release ]]; then
  echo "Erreur: /etc/os-release absent; Debian 13 requis." >&2
  exit 2
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "13" ]]; then
  echo "Erreur: Debian 13 uniquement (détecté: ${PRETTY_NAME:-inconnu})." >&2
  exit 2
fi
echo "==> Système: ${PRETTY_NAME:-Debian 13}"

echo "==> Installation de Kitty (terminal recommandé pour le TUI)"
if ! dpkg -s kitty >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y kitty
else
  echo "    Kitty déjà installé."
fi

echo "==> Installation de uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | bash
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "    uv déjà installé: $(uv --version)"
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "Erreur: uv introuvable après installation; vérifie ~/.local/bin dans PATH." >&2
  exit 3
fi

echo "==> Installation du CLI vibe depuis ce dépôt (TUI Python, sans Rust)"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# VIBE_SKIP_RUST_TUI: le TUI Python de ce fork est la surface livrée ; le
# build ne doit ni exiger cargo ni compiler vibe/cli-rust.
export VIBE_SKIP_RUST_TUI=1
if uv tool list 2>/dev/null | grep -qE "^mistral-vibe "; then
  echo "    vibe déjà installé; mise à jour depuis ce dépôt..."
  # --reinstall depuis le chemin local: `upgrade` ne suit pas un dépôt local.
  uv tool install --reinstall "$SCRIPT_DIR"
else
  uv tool install "$SCRIPT_DIR"
fi

echo "==> Configuration globale (~/.vibe/config.toml)"
mkdir -p "$HOME/.vibe"
if [[ -f "$SCRIPT_DIR/.vibe/config.toml" && ! -f "$HOME/.vibe/config.toml" ]]; then
  cp "$SCRIPT_DIR/.vibe/config.toml" "$HOME/.vibe/config.toml"
  echo "    Config copiée."
else
  echo "    Config globale déjà présente ou config de projet absente; inchangée."
fi

if ! grep -q '.local/bin' <<<"$PATH"; then
  echo
  echo "Ajoutez ceci à votre ~/.bashrc puis rechargez:"
  echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo
echo "Terminé. Utilisation:"
echo "  kitty            # terminal recommandé"
echo "  vibe              # agent dans n'importe quel projet"
echo "  curl -s http://127.0.0.1:8080/v1/models   # worker1 (KAT) doit lister worker"
echo "  curl -s http://127.0.0.1:8081/v1/models   # worker2 (Qwen3.5) doit lister worker"
