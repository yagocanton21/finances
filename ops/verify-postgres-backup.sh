#!/usr/bin/env bash
set -Eeuo pipefail

# Testa a restauração em um PostgreSQL descartável, sem tocar no banco da aplicação.

AGE_IDENTITY="${AGE_IDENTITY:-}"
BACKUP_FILE="${1:-}"
VERIFY_IMAGE="${VERIFY_IMAGE:-postgres:15-alpine}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
container_name="financas-backup-verify-$$"
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

cleanup() {
    docker rm -f "$container_name" >/dev/null 2>&1 || true
    if [[ -n "$temporary_dump" ]]; then
        rm -f -- "$temporary_dump"
    fi
}

on_exit() {
    local exit_code=$?
    trap - EXIT
    cleanup
    if [[ "$exit_code" -ne 0 ]]; then
        send_alert "ALERTA: teste de restauracao do backup de Financas falhou na VPS ($(hostname))."
    fi
    exit "$exit_code"
}
trap on_exit EXIT

temporary_dump="$(mktemp --suffix=.financas.dump)"

if [[ -z "$BACKUP_FILE" || -z "$AGE_IDENTITY" ]]; then
    echo "Uso: AGE_IDENTITY=/caminho/identidade.age $0 /caminho/backup.dump.age" >&2
    exit 2
fi
test -f "$BACKUP_FILE"
test -f "$AGE_IDENTITY"

age --decrypt --identity "$AGE_IDENTITY" --output "$temporary_dump" "$BACKUP_FILE"
test -s "$temporary_dump"

docker run --detach --name "$container_name" \
    --env POSTGRES_PASSWORD=verify \
    "$VERIFY_IMAGE" >/dev/null

for tentativa in $(seq 1 30); do
    if docker exec "$container_name" pg_isready -U postgres >/dev/null 2>&1; then
        break
    fi
    if [[ "$tentativa" == "30" ]]; then
        echo "PostgreSQL descartável não ficou pronto para a restauração." >&2
        exit 1
    fi
    sleep 2
done

docker cp "$temporary_dump" "$container_name:/tmp/financas.dump"
docker exec "$container_name" sh -c \
    'pg_restore --exit-on-error --no-owner --no-privileges -U postgres -d postgres /tmp/financas.dump'

echo "Restauração de teste concluída com sucesso: $BACKUP_FILE"
