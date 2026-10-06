#!/usr/bin/env bash
# Installateur Debian 13 : terminal Kitty + gestionnaire uv pour le CLI vibe.
# Installe aussi le CLI vibe depuis ce dépôt.
set -euo pipefail

# PATH de l'utilisateur avant toute modification par ce script : sert au
# message final, car on exporte ~/.local/bin pour installer uv ci-dessous.
USER_PATH="$PATH"

# Version épinglée + empreinte du script officiel uv. Mettre à jour les deux
# valeurs ensemble lors d’un changement de version.
UV_INSTALLER_VERSION="0.11.26"
UV_INSTALLER_SHA256="92fa9085d24c214bb4445cc1da8c15ca9cca8cffb34726240fa08c5302e94ccc"

sha256_of() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    return 1
  fi
}

install_uv_verified() {
  local installer actual_sha256
  installer="$(mktemp)"

  if ! curl -LsSf "https://astral.sh/uv/${UV_INSTALLER_VERSION}/install.sh" -o "$installer"; then
    rm -f -- "$installer"
    echo "Erreur: téléchargement de l’installateur uv impossible." >&2
    exit 3
  fi

  if ! actual_sha256="$(sha256_of "$installer")"; then
    rm -f -- "$installer"
    echo "Erreur: aucun outil SHA-256 disponible pour vérifier uv." >&2
    exit 3
  fi

  if [[ "$actual_sha256" != "$UV_INSTALLER_SHA256" ]]; then
    rm -f -- "$installer"
    echo "Erreur: empreinte SHA-256 de l’installateur uv invalide; exécution refusée." >&2
    echo "  attendue: $UV_INSTALLER_SHA256" >&2
    echo "  obtenue : $actual_sha256" >&2
    exit 3
  fi

  if ! sh "$installer"; then
    rm -f -- "$installer"
    echo "Erreur: installation de uv échouée." >&2
    exit 3
  fi
  rm -f -- "$installer"
}

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

echo "==> Dépendances système"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  curl ca-certificates

echo "==> Installation de Kitty (terminal)"
if ! dpkg -s kitty >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y kitty
else
  echo "    Kitty déjà installé."
fi

echo "==> Installation de uv"
if ! command -v uv >/dev/null 2>&1; then
  install_uv_verified
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "    uv déjà installé: $(uv --version)"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Erreur: uv introuvable après installation; vérifie ~/.local/bin dans PATH." >&2
  exit 3
fi

echo "==> Installation du CLI vibe depuis ce dépôt"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Toujours installer explicitement la copie locale pour éviter toute résolution
# accidentelle du nom de distribution sur un index public.
uv tool install --force "$SCRIPT_DIR"

echo "==> Configuration globale (~/.vibe/config.toml)"
install -d -m 700 "$HOME/.vibe"
if [[ -f "$SCRIPT_DIR/.vibe/config.toml" && ! -f "$HOME/.vibe/config.toml" ]]; then
  cp "$SCRIPT_DIR/.vibe/config.toml" "$HOME/.vibe/config.toml"
  chmod 600 "$HOME/.vibe/config.toml"
  echo "    Config copiée."
else
  echo "    Config globale déjà présente ou config de projet absente; inchangée."
fi

if ! grep -q '.local/bin' <<<"$USER_PATH"; then
  echo
  echo "Ajoutez ceci à votre ~/.bashrc puis rechargez:"
  echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo
echo "Terminé. Utilisation:"
echo "  kitty            # terminal recommandé"
echo "  vibe              # agent dans n'importe quel projet"
echo "  ${HOME}/.vibe/config.toml   # configure api_base pour tes serveurs llama.cpp"
if [[ -f "$HOME/.vibe/config.toml" ]]; then
  echo "  Endpoints configurés:"
  grep -E '^[[:space:]]*api_base[[:space:]]*=' "$HOME/.vibe/config.toml" \
    | sed 's/^/    /' || true
fi
