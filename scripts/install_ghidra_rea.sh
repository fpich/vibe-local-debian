#!/usr/bin/env bash
# Installateur optionnel : Ghidra 12.1.4 + JDK 21 + serveur MCP REA (rea-agents).
# REA (Reverse Engineer Anything) est un serveur MCP stdio qui utilise Ghidra
# comme provider d'analyse native. Ce script est idempotent et peut être
# relancé sans risque.
#
# Usage :
#   scripts/install_ghidra_rea.sh            # installe tout (JDK, Ghidra, REA)
#   scripts/install_ghidra_rea.sh --doctor   # vérifie seulement l'état
#
# Après installation, déclarer REA dans ~/.vibe/config.toml :
#   [[mcp_servers]]
#   name = "rea"
#   transport = "stdio"
#   command = "npx"
#   args = ["-y", "rea-agents@6.4.0", "mcp"]
#   env = { GHIDRA_INSTALL_DIR = "/opt/ghidra_12.1.4_PUBLIC", JAVA_HOME = "/usr/lib/jvm/java-21-openjdk-amd64" }

set -euo pipefail

# Versions épinglées (identifiant immuable, jamais un tag mouvant).
GHIDRA_VERSION="12.1.4"
GHIDRA_TAG="Ghidra_12.1.4_build"
GHIDRA_ZIP="ghidra_12.1.4_PUBLIC_20260921.zip"
GHIDRA_URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/${GHIDRA_TAG}/${GHIDRA_ZIP}"
GHIDRA_INSTALL_DIR="/opt/ghidra_${GHIDRA_VERSION}_PUBLIC"
JDK_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
NODE_MAJOR_MIN=18
# Version npm épinglée : la doc REA indique que la prochaine mineure peut
# casser les contrats, d'où une version exacte et pas @latest.
REA_VERSION="6.4.0"

DOCTOR_ONLY=0
if [[ "${1:-}" == "--doctor" ]]; then
  DOCTOR_ONLY=1
fi

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mAvertissement:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mErreur:\033[0m %s\n' "$*" >&2; exit 1; }

check_jdk() {
  if [[ -x "${JDK_HOME}/bin/java" ]]; then
    say "JDK 21 présent (${JDK_HOME})."
    return 0
  fi
  return 1
}

install_jdk() {
  say "Installation d'OpenJDK 21 (apt)…"
  sudo apt update
  sudo apt install -y openjdk-21-jdk unzip
}

check_ghidra() {
  if [[ -x "${GHIDRA_INSTALL_DIR}/support/launch.sh" ]]; then
    say "Ghidra ${GHIDRA_VERSION} présent (${GHIDRA_INSTALL_DIR})."
    return 0
  fi
  return 1
}

install_ghidra() {
  say "Téléchargement de Ghidra ${GHIDRA_VERSION}…"
  local tmp
  tmp="$(mktemp)"
  trap 'rm -f -- "$tmp"' RETURN
  if ! curl -LsSf "$GHIDRA_URL" -o "$tmp"; then
    die "téléchargement de ${GHIDRA_URL} impossible."
  fi
  say "Extraction vers /opt…"
  sudo unzip -q "$tmp" -d /opt
}

check_node() {
  command -v node >/dev/null 2>&1 || return 1
  local major
  major="$(node --version | tr -d 'v' | cut -d. -f1)"
  [[ "$major" -ge "$NODE_MAJOR_MIN" ]]
}

install_node() {
  say "Installation de Node.js/npm (apt)…"
  sudo apt install -y nodejs npm
}

doctor() {
  local failed=0
  if check_jdk; then :; else
    warn "JDK 21 absent — lancer ce script sans --doctor pour l'installer."
    failed=1
  fi
  if check_ghidra; then :; else
    warn "Ghidra ${GHIDRA_VERSION} absent — lancer ce script sans --doctor."
    failed=1
  fi
  if check_node; then
    say "Node.js $(node --version) présent."
  else
    warn "Node.js absent (>= ${NODE_MAJOR_MIN} requis pour REA)."
    failed=1
  fi
  if command -v npx >/dev/null 2>&1; then
    say "Vérification du provider Ghidra côté REA (doctor)…"
    local doctor_json
    if GHIDRA_INSTALL_DIR="$GHIDRA_INSTALL_DIR" JAVA_HOME="$JDK_HOME" \
      doctor_json="$(npx -y "rea-agents@${REA_VERSION}" doctor --provider ghidra --json 2>/dev/null)"
    then
      :
    fi
    # Le doctor REA sort non-zéro pour des avis informatifs (skill manquant,
    # hôte non listé…). La santé réelle du provider est dans providerInspections.
    local ghidra_ok
    ghidra_ok="$(printf '%s' "$doctor_json" \
      | tr -d '\n' \
      | sed -n 's/.*"id":"ghidra","configured":true,"available":\(true\|false\).*/\1/p')"
    if [[ "$ghidra_ok" == "true" ]]; then
      say "REA (rea-agents@${REA_VERSION}) opérationnel avec Ghidra."
    else
      warn "provider Ghidra non configuré côté REA — GHIDRA_INSTALL_DIR=${GHIDRA_INSTALL_DIR}"
      warn "Sortie doctor (extrait) : $(printf '%s' "$doctor_json" | head -c 400)"
      failed=1
    fi
  else
    warn "npx absent — vérification REA impossible."
    failed=1
  fi
  if [[ "$failed" -eq 1 ]]; then
    die "des éléments manquent ou échouent (voir avertissements)."
  fi
  say "Tout est en ordre."
}

main() {
  if [[ "$DOCTOR_ONLY" -eq 1 ]]; then
    doctor
    return
  fi
  check_jdk || install_jdk
  check_ghidra || install_ghidra
  check_node || install_node

  say "Écriture des variables d'environnement dans ~/.bashrc…"
  local rc="$HOME/.bashrc"
  touch "$rc"
  if ! grep -q 'GHIDRA_INSTALL_DIR=' "$rc"; then
    printf '\n# REA / Ghidra (scripts/install_ghidra_rea.sh)\nexport GHIDRA_INSTALL_DIR=%s\nexport JAVA_HOME=%s\n' \
      "$GHIDRA_INSTALL_DIR" "$JDK_HOME" >> "$rc"
  fi

  doctor
  say "Terminé. Recharger l'environnement : source ~/.bashrc"
  say "Puis déclarer REA dans ~/.vibe/config.toml (voir en-tête de ce script)."
}

main
