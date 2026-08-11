#!/usr/bin/env bash
set -Eeuo pipefail

# Backup criptografado do PostgreSQL executado no host da VPS.
# Requisitos: docker compose, age e, quando BACKUP_REMOTE for usado, rclone.

umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/financas}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
REQUIRE_REMOTE="${REQUIRE_REMOTE:-true}"
AGE_RECIPIENT="${AGE_RECIPIENT:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
RETENTION_DAILY_DAYS="${RETENTION_DAILY_DAYS:-14}"
RETENTION_WEEKLY_WEEKS="${RETENTION_WEEKLY_WEEKS:-8}"
RETENTION_MONTHLY_MONTHS="${RETENTION_MONTHLY_MONTHS:-12}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
date_key="$(date -u +%F)"
day_of_week="$(date -u +%u)"
day_of_month="$(date -u +%d)"
daily_dir="$BACKUP_ROOT/daily"
weekly_dir="$BACKUP_ROOT/weekly"
monthly_dir="$BACKUP_ROOT/monthly"
archive_name="financas_${timestamp}.dump.age"
archive_path="$daily_dir/$archive_name"
temporary_dump=""

send_alert() {
    local message="$1"
    if [[ -n "$TELEGRAM_BOT_TOKEN" && -n "$TELEGRAM_CHAT_ID" ]]; then
        curl --fail --silent --show-error \
            -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=${message}" >/dev/null || true
    fi
}

on_error() {
    local exit_code=$?
    send_alert "ALERTA: backup do PostgreSQL de Financas falhou na VPS ($(hostname))."
    if [[ -n "$temporary_dump" ]]; then
        rm -f -- "$temporary_dump"
    fi
    exit "$exit_code"
}
trap on_error ERR
cleanup() {
    if [[ -n "$temporary_dump" ]]; then
        rm -f -- "$temporary_dump"
    fi
}
trap cleanup EXIT

if [[ -z "$AGE_RECIPIENT" ]]; then
    echo "AGE_RECIPIENT precisa ser configurado; backup em texto aberto foi bloqueado." >&2
    exit 2
fi

if [[ -n "$BACKUP_REMOTE" ]] && ! command -v rclone >/dev/null 2>&1; then
    echo "BACKUP_REMOTE foi configurado, mas rclone nao esta instalado." >&2
    exit 2
fi
if [[ "$REQUIRE_REMOTE" == "true" && -z "$BACKUP_REMOTE" ]]; then
    echo "BACKUP_REMOTE precisa ser configurado; backup apenas local foi bloqueado." >&2
    exit 2
fi

mkdir -p -- "$daily_dir" "$weekly_dir" "$monthly_dir"
temporary_dump="$(mktemp "$BACKUP_ROOT/.financas_${timestamp}.XXXXXX.dump")"

docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c \
    'pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    >"$temporary_dump"

test -s "$temporary_dump"
age --recipient "$AGE_RECIPIENT" --output "$archive_path" "$temporary_dump"
test -s "$archive_path"

# Uma cópia semanal/mensal do mesmo dump evita depender de um único conjunto diário.
if [[ "$day_of_week" == "7" ]]; then
    cp -- "$archive_path" "$weekly_dir/financas_${date_key}.dump.age"
fi
if [[ "$day_of_month" == "01" ]]; then
    cp -- "$archive_path" "$monthly_dir/financas_${date_key}.dump.age"
fi

if [[ -n "$BACKUP_REMOTE" ]]; then
    rclone copyto -- "$archive_path" "$BACKUP_REMOTE/$archive_name"
    rclone copyto -- "$archive_path" "$BACKUP_REMOTE/latest.dump.age"
fi

find "$daily_dir" -type f -name '*.dump.age' -mtime "+$RETENTION_DAILY_DAYS" -delete
find "$weekly_dir" -type f -name '*.dump.age' -mtime "+$((RETENTION_WEEKLY_WEEKS * 7))" -delete
find "$monthly_dir" -type f -name '*.dump.age' -mtime "+$((RETENTION_MONTHLY_MONTHS * 31))" -delete

echo "Backup criado: $archive_path"
