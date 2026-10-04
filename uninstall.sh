#!/usr/bin/env bash
# Désinstalleur : retire le CLI vibe et supprime toutes les données
# qu'il a sauvegardées (config, sessions, historique, worktrees, caches).
# Ne touche ni aux projects ni aux serveurs llama.cpp.
set -euo pipefail

VIBE_HOME="${VIBE_HOME:-$HOME/.vibe}"

confirm() {
  local answer
  read -r -p "$1 [oui/NON] " answer
  [[ "$answer" == "oui" || "$answer" == "o" || "$answer" == "y" || "$answer" == "yes" ]]
}

echo "==> Désinstallation de vibe-local-debian"
echo "    VIBE_HOME détecté: $VIBE_HOME"

echo
echo "Le script va supprimer :"
echo "  1. Le CLI vibe (uv tool mistral-vibe)"
echo "  2. Toutes les données de $VIBE_HOME :"
echo "     config.toml, sessions, historique, logs, worktrees,"
echo "     plans, caches, trusted_folders, .env"
[[ -d "$VIBE_HOME/worktrees" ]] && echo "     ATTENTION: worktrees existent dans $VIBE_HOME/worktrees"
echo
echo "NON supprimé : dépôts Git des projects, serveurs llama.cpp, uv, kitty."
echo

if ! confirm "Continuer ?"; then
  echo "Annulé."
  exit 0
fi

echo "==> Suppression du CLI vibe"
if uv tool list 2>/dev/null | grep -qE "^mistral-vibe(-v2x8.*)?:"; then
  uv tool uninstall mistral-vibe
else
  echo "    CLI vibe non installé via uv; ignoré."
fi

echo "==> Suppression des données: $VIBE_HOME"
if [[ -d "$VIBE_HOME" ]]; then
  rm -rf "$VIBE_HOME"
  echo "    Supprimé."
else
  echo "    $VIBE_HOME absent; rien à supprimer."
fi

echo "==> Nettoyage des références dans ~/.bashrc"
if [[ -f "$HOME/.bashrc" ]] && grep -q "127.0.0.1" "$HOME/.bashrc"; then
  echo "    ~/.bashrc mentionne les serveurs llama.cpp; à nettoyer manuellement si souhaité."
fi

echo
echo "Désinstallation terminée."
echo "Pour réinstaller plus tard : ./install.sh"
