#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MYSQL_BIN="${MYSQL_BIN:-/opt/homebrew/opt/mysql@8.0/bin/mysql}"
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
MYSQL_DB="${MYSQL_DB:-flash_sale}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/benchmark/.venv}"

MYSQL_ARGS=(--protocol=TCP -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_USER}" --default-character-set=utf8mb4 --init-command="SET SESSION sql_mode='';")
if [[ -n "${MYSQL_PASSWORD}" ]]; then
  MYSQL_ARGS+=("-p${MYSQL_PASSWORD}")
fi

"${MYSQL_BIN}" "${MYSQL_ARGS[@]}" -e "CREATE DATABASE IF NOT EXISTS \`${MYSQL_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
"${MYSQL_BIN}" "${MYSQL_ARGS[@]}" "${MYSQL_DB}" < "${ROOT_DIR}/src/main/resources/db/schema.sql"

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/benchmark/requirements.txt"

echo "Local benchmark environment initialized."
