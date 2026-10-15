#!/usr/bin/env bash
# Installateur optionnel : Ghidra 12.1.4 + JDK 21 + radare2 + serveur MCP REA
# (rea-agents). REA (Reverse Engineer Anything) est un serveur MCP stdio qui
# utilise Ghidra comme provider d'analyse native et radare2 comme moteur
# d'analyse nat rapide. Ce script est idempotent et peut être relancé sans
# risque.
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
# radare2 : retiré des dépôts Debian trixie, d'où le .deb épinglé depuis les
# releases officielles. REA l'utilise comme moteur d'analyse nat rapide.
RADARE2_VERSION="6.2.4"
RADARE2_DEB="radare2_${RADARE2_VERSION}_amd64.deb"
RADARE2_URL="https://github.com/radareorg/radare2/releases/download/${RADARE2_VERSION}/${RADARE2_DEB}"
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

check_radare2() {
  if command -v radare2 >/dev/null 2>&1; then
    say "radare2 $(radare2 -v 2>/dev/null | head -1 | awk '{print $2}') présent."
    return 0
  fi
  return 1
}

install_radare2() {
  say "Installation de radare2 ${RADARE2_VERSION} (absent des dépôts trixie)…"
  local tmp
  tmp="$(mktemp --suffix=.deb)"
  trap 'rm -f -- "$tmp"' RETURN
  if ! curl -LsSf "$RADARE2_URL" -o "$tmp"; then
    die "téléchargement de ${RADARE2_URL} impossible."
  fi
  sudo apt install -y "$tmp"
  if ! command -v radare2 >/dev/null 2>&1; then
    die "radare2 ne s'est pas installé correctement."
  fi
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

install_ghidra_desktop_entry() {
  # Entrée du menu d'applications (portée utilisateur, pas de sudo).
  # ~/.local/share/applications prime sur /usr/share/applications.
  local desktop_dir="$HOME/.local/share/applications"
  local desktop_file="$desktop_dir/ghidra.desktop"
  local icon_line=""
  if [[ -f "${GHIDRA_INSTALL_DIR}/support/ghidra.ico" ]]; then
    icon_line="Icon=${GHIDRA_INSTALL_DIR}/support/ghidra.ico"
  fi
  install -d "$desktop_dir"
  if [[ -f "$desktop_file" ]] && grep -q "^Exec=${GHIDRA_INSTALL_DIR}/ghidraRun$" "$desktop_file"; then
    say "Entrée de menu Ghidra déjà présente ($desktop_file)."
    return 0
  fi
  cat > "$desktop_file" <<DESKTOP_EOF
[Desktop Entry]
Name=Ghidra
Comment=Reverse engineering tool (Ghidra ${GHIDRA_VERSION})
Exec=${GHIDRA_INSTALL_DIR}/ghidraRun
${icon_line}
Terminal=false
Type=Application
Categories=Development;Utility;
DESKTOP_EOF
  # Wayland pur : le GUI Swing peut rester gris sans cette variable.
  if ! grep -q '_JAVA_AWT_WM_NONREPARENTING' "$HOME/.bashrc" 2>/dev/null; then
    printf 'export _JAVA_AWT_WM_NONREPARENTING=1\n' >> "$HOME/.bashrc"
  fi
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
  fi
  say "Entrée de menu Ghidra créée ($desktop_file)."
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
  if check_radare2; then :; else
    warn "radare2 absent — lancer ce script sans --doctor pour l'installer."
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
  check_radare2 || install_radare2
  check_node || install_node
  install_ghidra_desktop_entry

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
