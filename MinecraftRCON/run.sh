#!/usr/bin/env bash
set -eo pipefail

# --- Configurações ---
SERVER_DIR="/share/minecraftRCON"
BACKUP_DIR="$SERVER_DIR/backups"
LAST_VERSION_FILE="$SERVER_DIR/lastversion.txt"
SERVER_BIN="$SERVER_DIR/bedrock_server"
DEBUG=${DEBUG:-false}
EULA=${EULA:-true}
PACKAGE_BACKUP_KEEP=${PACKAGE_BACKUP_KEEP:-2}

# Cores para log
INTRO='\033[0;42m\033[1;37m'
WHITE='\033[1;37m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'


log() {
  local color="$1"; shift
  echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${color}$*${RESET}"
}

isTrue() {
  [[ "${1,,}" =~ ^(true|on|1)$ ]]
}

if isTrue "$DEBUG"; then
  set -x
fi

log $WHITE "."
log $WHITE ".."
log $WHITE "..."
log $WHITE "...."
log $WHITE "....."
log $INTRO "=========== Iniciando Minecraft Bedrock RCON ==========="

mkdir -p "$SERVER_DIR" "$BACKUP_DIR"

if ! isTrue "$EULA"; then
  log $RED "EULA não aceita. Configure EULA=true para continuar."
  exit 1
fi

# --- Consulta a API oficial para obter versão e URL de download ---
lookupVersion() {
  local platform="$1"
  local api_response
  local version_info

  if [[ "$platform" != "serverBedrockLinux" && "$platform" != "serverBedrockPreviewLinux" ]]; then
    log $RED "Plataforma inválida: $platform"
    exit 2
  fi

  log $YELLOW "Consultando a API oficial do Minecraft Bedrock..."
  if ! api_response=$(curl -fsSL "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"); then
    log $RED "Falha ao consultar a API oficial de downloads do Minecraft."
    exit 2
  fi

  if ! version_info=$(printf '%s' "$api_response" | python3 -c '
import json
import re
import sys

platform = sys.argv[1]
expected_path = {
    "serverBedrockLinux": "bin-linux",
    "serverBedrockPreviewLinux": "bin-linux-preview",
}.get(platform)

try:
    payload = json.load(sys.stdin)
    link = next(
        item for item in payload["result"]["links"]
        if item["downloadType"] == platform
    )
    download_url = link["downloadUrl"]
    pattern = (
        rf"https://www\.minecraft\.net/bedrockdedicatedserver/"
        rf"{re.escape(expected_path)}/bedrock-server-"
        r"([0-9]+(?:\.[0-9]+)*)\.zip"
    )
    match = re.fullmatch(pattern, download_url)
    if match is None:
        raise ValueError("Unexpected download URL")
    print(match.group(1) + "|" + download_url)
except (KeyError, TypeError, StopIteration, ValueError, json.JSONDecodeError) as error:
    print("Invalid download API response: " + str(error), file=sys.stderr)
    sys.exit(1)
' "$platform"); then
    log $RED "A API retornou uma resposta inválida para a plataforma $platform."
    exit 2
  fi

  VERSION="${version_info%%|*}"
  DOWNLOAD_URL="${version_info#*|}"
  if [[ -z "$VERSION" || -z "$DOWNLOAD_URL" ]]; then
    log $RED "A API não retornou versão e URL de download válidas."
    exit 2
  fi
}

# --- Verifica versão instalada (se houver) ---
INSTALLED_VERSION=""
if [[ -f "$LAST_VERSION_FILE" ]]; then
  INSTALLED_VERSION=$(<"$LAST_VERSION_FILE")
fi

# --- Busca última versão disponível online ---
lookupVersion serverBedrockLinux
log $GREEN "Versão disponível online: $VERSION"
log $GREEN "Versão instalada localmente: ${INSTALLED_VERSION:-nenhuma}"

# --- Decide se precisa atualizar ---
NEED_UPDATE=true
if [[ "$VERSION" == "$INSTALLED_VERSION" ]] && [[ -f "$SERVER_BIN" ]]; then
  log $GREEN "Servidor já está na última versão, não será atualizado!"
  NEED_UPDATE=false
else
  log $YELLOW "Versão instalada ($INSTALLED_VERSION) diferente da disponível ($VERSION), atualizando..."
  log $GREEN "URL para download: $DOWNLOAD_URL"
fi

# --- Backup e restauração ---
BACKUP_TARGET=""

do_backup() {
  local timestamp
  timestamp=$(date '+%Y%m%d-%H%M%S')
  BACKUP_TARGET="$BACKUP_DIR/backup-$timestamp"

  log $YELLOW "Criando backup seletivo em $BACKUP_TARGET..."
  mkdir -p "$BACKUP_TARGET"

  for item in worlds behavior_packs resource_packs structures server.properties permissions.json allowlist.json; do
    if [[ -e "$SERVER_DIR/$item" ]]; then
      log $YELLOW "Salvando $item..."
      cp -r "$SERVER_DIR/$item" "$BACKUP_TARGET/"
    fi
  done

  log $YELLOW "Removendo backups antigos, mantendo os $PACKAGE_BACKUP_KEEP mais recentes..."
  find "$BACKUP_DIR" -maxdepth 1 -type d -name "backup-*" | sort -r | tail -n +$((PACKAGE_BACKUP_KEEP + 1)) | xargs -r rm -rf
}

restore_custom_packs() {
  local item backup_dir pack_source target_dir pack_name

  # Keep the packs shipped with the freshly downloaded server. Restore custom
  # packs only when the new distribution does not provide that directory.
  for item in behavior_packs resource_packs; do
    backup_dir="$BACKUP_TARGET/$item"
    target_dir="$SERVER_DIR/$item"

    [[ -d "$backup_dir" ]] || continue
    mkdir -p "$target_dir"

    while IFS= read -r -d '' pack_source; do
      pack_name="${pack_source##*/}"

      # Never restore old copies of packs bundled by the official server.
      case "$pack_name" in
        vanilla|vanilla_*|chemistry|chemistry_*|editor|editor_*|experimental|experimental_*|experimental-*)
          log $YELLOW "Mantendo pacote oficial da nova versão: $item/$pack_name"
          continue
          ;;
      esac

      if [[ ! -e "$target_dir/$pack_name" ]]; then
        log $YELLOW "Restaurando pacote personalizado: $item/$pack_name"
        cp -r "$pack_source" "$target_dir/"
      else
        log $YELLOW "Mantendo pacote já fornecido pela nova versão: $item/$pack_name"
      fi
    done < <(find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -print0)
  done
}

# --- Executa atualização se necessário ---
if $NEED_UPDATE; then
  do_backup

  TMP_ZIP="$SERVER_DIR/server.zip"
  log $YELLOW "Baixando servidor Bedrock versão $VERSION..."
  curl -fsSL -o "$TMP_ZIP" -A "itzg/minecraft-bedrock-server" "$DOWNLOAD_URL"

  total=$(unzip -l "$TMP_ZIP" | grep -E '^[ ]+[0-9]' | wc -l)
  log $YELLOW "Extraindo arquivos... Total: $total"

  count=0
  last_percent=0
  unzip -o "$TMP_ZIP" -d "$SERVER_DIR" | while read -r line; do
    if echo "$line" | grep -q "inflating:"; then
      count=$((count + 1))
      percent=$((count * 100 / total))
      if [ "$percent" -ne "$last_percent" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Extraindo arquivos... $percent%"
        last_percent=$percent
      fi
    fi
  done

  log $YELLOW "Extração concluída em ${SECONDS}s! Restaurando dados e pacotes personalizados..."

  # Restore world data and settings, but keep the official content packs
  # extracted from the new server archive.
  for item in worlds structures server.properties permissions.json allowlist.json; do
    if [[ -e "$BACKUP_TARGET/$item" ]]; then
      log $YELLOW "Restaurando $item..."
      rm -rf "$SERVER_DIR/$item"
      cp -r "$BACKUP_TARGET/$item" "$SERVER_DIR/"
    fi
  done

  restore_custom_packs

  log $YELLOW "Removendo $TMP_ZIP"
  chmod +x "$SERVER_BIN"
  rm "$TMP_ZIP"

  echo "$VERSION" > "$LAST_VERSION_FILE"

  log $GREEN "Atualização concluída para a versão $VERSION."
fi

# --- Inicia servidor ---
cd "$SERVER_DIR"

log $YELLOW "Iniciando servidor Minecraft Bedrock..."
screen -dmS mc bash -c "./bedrock_server | tee /share/minecraftRCON/server.log /proc/1/fd/1"

sleep 10

log $YELLOW "Iniciando RCON personalizado..."
python3 /rcon_server.py &

log $GREEN "Servidor Minecraft Bedrock e RCON online."

wait
