#!/usr/bin/env bash
set -Eeuo pipefail

# Restauração intencional e destrutiva. Nunca executar sem confirmar o banco alvo.

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.yml}"
AGE_IDENTITY="${AGE_IDENTITY:-}"
BACKUP_FILE="${1:-}"

if [[ -z "$BACKUP_FILE" || -z "$AGE_IDENTITY" ]]; then
    echo "Uso: AGE_IDENTITY=/caminho/identidade.age $0 /caminho/backup.dump.age" >&2
    exit 2
fi

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
    echo "Restauracao bloqueada. Defina CONFIRM_RESTORE=YES explicitamente." >&2
    exit 2
fi

test -f "$BACKUP_FILE"
test -f "$AGE_IDENTITY"

temporary_dump="$(mktemp --suffix=.financas.dump)"
trap 'rm -f -- "$temporary_dump"' EXIT

age --decrypt --identity "$AGE_IDENTITY" --output "$temporary_dump" "$BACKUP_FILE"
test -s "$temporary_dump"

echo "ATENCAO: o banco PostgreSQL do compose sera sobrescrito."
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c \
    'pg_restore --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    <"$temporary_dump"

echo "Restauracao concluida a partir de: $BACKUP_FILE"
