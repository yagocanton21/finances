#!/usr/bin/env bash
set -Eeuo pipefail

# Testa a restauração em um PostgreSQL descartável, sem tocar no banco da aplicação.

AGE_IDENTITY="${AGE_IDENTITY:-}"
BACKUP_FILE="${1:-}"
VERIFY_IMAGE="${VERIFY_IMAGE:-postgres:15-alpine}"
container_name="financas-backup-verify-$$"
temporary_dump="$(mktemp --suffix=.financas.dump)"

cleanup() {
    docker rm -f "$container_name" >/dev/null 2>&1 || true
    rm -f -- "$temporary_dump"
}
trap cleanup EXIT

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
