#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/finan-as-release}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-finan-as}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/api/health}"
COMPOSE_WAIT_TIMEOUT="${COMPOSE_WAIT_TIMEOUT:-180}"
CANDIDATE_WAIT_TIMEOUT="${CANDIDATE_WAIT_TIMEOUT:-90}"
STATE_DIR="${DEPLOY_STATE_DIR:-${HOME}/.local/state/financas-deploy}"
TARGET_REVISION="${TARGET_REVISION:-}"
PREVIOUS_REVISION="${PREVIOUS_REVISION:-}"

log() {
    printf '[deploy] %s\n' "$*"
}

compose() {
    docker compose -p "$COMPOSE_PROJECT_NAME" "$@"
}

checkout_revision() {
    local revision="$1"
    git checkout --detach "$revision" || return $?
}

build_revision() {
    log "Construindo imagens da revisão $(git rev-parse --short HEAD) sem interromper a versão atual."
    compose build --pull || return $?
}

remove_candidate() {
    local candidate_name="$1"
    docker rm -f "$candidate_name" >/dev/null 2>&1 || true
}

validate_candidate() {
    local candidate_name="financas_api_candidate_$(git rev-parse --short=12 HEAD)"
    local candidate_status=""
    local waited=0

    remove_candidate "$candidate_name"
    log "Iniciando canário isolado para validar a nova API."

    if ! compose run -d --no-deps --name "$candidate_name" api >/dev/null; then
        log "ERRO: não foi possível iniciar o canário."
        remove_candidate "$candidate_name"
        return 1
    fi

    while (( waited < CANDIDATE_WAIT_TIMEOUT )); do
        candidate_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$candidate_name" 2>/dev/null || true)"

        if [[ "$candidate_status" == "healthy" ]]; then
            remove_candidate "$candidate_name"
            log "Canário aprovado pelo healthcheck."
            return 0
        fi

        if [[ "$candidate_status" == "unhealthy" || "$candidate_status" == "exited" || "$candidate_status" == "dead" ]]; then
            log "ERRO: canário terminou com estado ${candidate_status}."
            docker logs --tail 30 "$candidate_name" >&2 || true
            remove_candidate "$candidate_name"
            return 1
        fi

        sleep 2
        waited=$((waited + 2))
    done

    log "ERRO: canário não ficou saudável dentro de ${CANDIDATE_WAIT_TIMEOUT}s."
    docker logs --tail 30 "$candidate_name" >&2 || true
    remove_candidate "$candidate_name"
    return 1
}

promote_revision() {
    log "Promovendo revisão $(git rev-parse --short HEAD)."
    compose up -d --no-build --remove-orphans \
        --wait --wait-timeout "$COMPOSE_WAIT_TIMEOUT" || return $?
    curl --fail --silent --show-error --max-time 10 "$HEALTH_URL" >/dev/null || return $?
}

record_success() {
    local revision="$1"
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
    printf '%s\n' "$revision" >"$STATE_DIR/last-successful-revision"
    chmod 600 "$STATE_DIR/last-successful-revision"
}

show_status() {
    compose ps || true
}

rollback() {
    log "Iniciando rollback para $(git rev-parse --short "$PREVIOUS_REVISION")."
    checkout_revision "$PREVIOUS_REVISION" || return $?

    if ! build_revision; then
        log "ERRO: não foi possível reconstruir a revisão anterior."
        return 1
    fi

    if ! promote_revision; then
        log "ERRO: a revisão anterior também não passou nos healthchecks."
        show_status
        return 1
    fi

    record_success "$PREVIOUS_REVISION"
    log "Rollback concluído; a última versão saudável foi restaurada."
}

main() {
    cd "$PROJECT_DIR"

    if [[ -z "$TARGET_REVISION" ]]; then
        TARGET_REVISION="$(git rev-parse HEAD)"
    fi

    if [[ -z "$PREVIOUS_REVISION" ]]; then
        if [[ -f "$STATE_DIR/last-successful-revision" ]]; then
            PREVIOUS_REVISION="$(<"$STATE_DIR/last-successful-revision")"
        else
            PREVIOUS_REVISION="$(git rev-parse HEAD^)"
        fi
    fi

    git rev-parse --verify "${TARGET_REVISION}^{commit}" >/dev/null
    git rev-parse --verify "${PREVIOUS_REVISION}^{commit}" >/dev/null

    checkout_revision "$TARGET_REVISION"

    if ! build_revision; then
        log "ERRO: o build falhou; a versão em execução não foi substituída."
        checkout_revision "$PREVIOUS_REVISION"
        exit 1
    fi

    if ! validate_candidate; then
        log "ERRO: a validação canário falhou; a versão em execução não foi substituída."
        checkout_revision "$PREVIOUS_REVISION"
        exit 1
    fi

    if promote_revision; then
        record_success "$TARGET_REVISION"
        show_status
        log "Deploy concluído e validado pelos healthchecks."
        exit 0
    fi

    log "ERRO: a nova revisão não ficou saudável."
    show_status

    if rollback; then
        # O pipeline continua falhando para que o incidente seja visível e alertado.
        exit 1
    fi

    log "ERRO CRÍTICO: o deploy e o rollback falharam."
    exit 2
}

main "$@"
