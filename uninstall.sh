#!/usr/bin/env bash
# Désinstalleur : retire le CLI vibe et supprime toutes les données
# qu'il a sauvegardées (config, sessions, historique, worktrees, caches).
# Ne touche ni aux projects ni aux serveurs llama.cpp.
set -euo pipefail

VIBE_HOME="${VIBE_HOME:-$HOME/.vibe}"
VIBE_HOME_RESOLVED=""

canonicalize_path() {
  realpath -m -- "$1"
}

validate_vibe_home() {
  local resolved home_resolved relative

  if [[ -z "$VIBE_HOME" ]]; then
    echo "Erreur: VIBE_HOME est vide; suppression refusée." >&2
    exit 4
  fi

  if ! resolved="$(canonicalize_path "$VIBE_HOME")"; then
    echo "Erreur: impossible de normaliser VIBE_HOME: $VIBE_HOME" >&2
    exit 4
  fi
  home_resolved="$(canonicalize_path "$HOME")"

  # Ne jamais supprimer la racine, HOME, un ancêtre de HOME, ni un répertoire
  # système de premier niveau. realpath -m neutralise aussi les chemins
  # contenant '.', '..' et les symlinks déjà existants.
  if [[ "$resolved" == "/" || "$resolved" == "$home_resolved" ]]; then
    echo "Erreur: VIBE_HOME dangereux ($resolved); suppression refusée." >&2
    exit 4
  fi
  if [[ "$home_resolved" == "$resolved/"* ]]; then
    echo "Erreur: VIBE_HOME ($resolved) est un ancêtre de HOME; suppression refusée." >&2
    exit 4
  fi

  case "$resolved" in
    /bin|/boot|/dev|/etc|/home|/lib|/lib64|/media|/mnt|/opt|/proc|/root|/run|/sbin|/srv|/sys|/tmp|/usr|/var)
      echo "Erreur: VIBE_HOME pointe vers un répertoire système ($resolved); suppression refusée." >&2
      exit 4
      ;;
  esac

  # Refuse également les autres chemins de premier niveau tels que /data.
  # Un VIBE_HOME personnalisé doit désigner un sous-répertoire précis.
  relative="${resolved#/}"
  if [[ "$relative" != */* ]]; then
    echo "Erreur: VIBE_HOME est trop large ($resolved); suppression refusée." >&2
    exit 4
  fi

  VIBE_HOME_RESOLVED="$resolved"
}

confirm() {
  local answer
  read -r -p "$1 [oui/NON] " answer
  [[ "$answer" == "oui" || "$answer" == "o" || "$answer" == "y" || "$answer" == "yes" ]]
}

validate_vibe_home

echo "==> Désinstallation de vibe-local-debian"
echo "    VIBE_HOME détecté: $VIBE_HOME_RESOLVED"
if [[ "$VIBE_HOME_RESOLVED" != "$VIBE_HOME" ]]; then
  echo "    (chemin normalisé depuis: $VIBE_HOME)"
fi

echo
echo "Le script va supprimer :"
echo "  1. Le CLI vibe (uv tool mistral-vibe)"
echo "  2. Toutes les données de $VIBE_HOME_RESOLVED :"
echo "     config.toml, sessions, historique, logs, worktrees,"
echo "     plans, caches, trusted_folders, .env"
[[ -d "$VIBE_HOME_RESOLVED/worktrees" ]] && echo "     ATTENTION: worktrees existent dans $VIBE_HOME_RESOLVED/worktrees"
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

echo "==> Suppression des données: $VIBE_HOME_RESOLVED"
if [[ -d "$VIBE_HOME_RESOLVED" ]]; then
  rm -rf -- "$VIBE_HOME_RESOLVED"
  echo "    Supprimé."
else
  echo "    $VIBE_HOME_RESOLVED absent; rien à supprimer."
fi

echo "==> Nettoyage des références dans ~/.bashrc"
if [[ -f "$HOME/.bashrc" ]] && grep -q "127.0.0.1" "$HOME/.bashrc"; then
  echo "    ~/.bashrc mentionne les serveurs llama.cpp; à nettoyer manuellement si souhaité."
fi

echo
echo "Désinstallation terminée."
echo "Pour réinstaller plus tard : ./install.sh"
