#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

API_HEALTH_URL="${API_HEALTH_URL:?API_HEALTH_URL precisa ser configurada}"
MONITOR_NAME="${MONITOR_NAME:-API de Financas}"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-2}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-10}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-${TELEGRAM_ALLOWED_USERS:-}}"
MONITOR_DRY_RUN="${MONITOR_DRY_RUN:-false}"
state_directory="${STATE_DIRECTORY:-/var/lib/financas-api-monitor}"
state_file="$state_directory/state"

mkdir -p -- "$state_directory"

previous_status="unknown"
failures=0
if [[ -s "$state_file" ]]; then
    read -r previous_status failures <"$state_file" || true
fi
if ! [[ "$failures" =~ ^[0-9]+$ ]]; then
    failures=0
fi

save_state() {
    local status="$1"
    local failure_count="$2"
    printf '%s %s\n' "$status" "$failure_count" >"$state_file.tmp"
    mv -- "$state_file.tmp" "$state_file"
}

send_alert() {
    local message="$1"
    if [[ "$MONITOR_DRY_RUN" == "true" ]]; then
        printf 'dry_run_alert=%s\n' "$message"
        return 0
    fi
    if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$TELEGRAM_CHAT_ID" ]]; then
        echo "monitor_alert=not_configured" >&2
        return 1
    fi
    if curl --fail --silent --show-error \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${message}" >/dev/null; then
        echo "monitor_alert=sent"
        return 0
    fi
    echo "monitor_alert=failed" >&2
    return 1
}

if curl --fail --silent --show-error \
    --max-time "$CURL_TIMEOUT_SECONDS" \
    --output /dev/null \
    "$API_HEALTH_URL"; then
    if [[ "$previous_status" == "down" ]]; then
        if ! send_alert "✅ Boas notícias, senhor. O sistema financeiro está operacional novamente.

A API respondeu normalmente e o acesso foi restabelecido. O monitoramento contínuo permanece ativo.

— J.A.R.V.I.S."; then
            save_state "down" 0
            echo "monitor_status=recovery_alert_pending url=$API_HEALTH_URL" >&2
            exit 1
        fi
    fi
    save_state "up" 0
    echo "monitor_status=up url=$API_HEALTH_URL"
    exit 0
fi

failures=$((failures + 1))
next_status="failing"
if (( failures >= FAIL_THRESHOLD )); then
    if [[ "$previous_status" == "down" ]]; then
        next_status="down"
    elif send_alert "🚨 Senhor, detectei uma interrupção no sistema financeiro.

A API deixou de responder após ${failures} verificações consecutivas. O acesso pode estar temporariamente indisponível.

Continuarei monitorando e avisarei assim que tudo estiver normalizado.

— J.A.R.V.I.S."; then
        next_status="down"
    else
        next_status="failing"
    fi
fi
save_state "$next_status" "$failures"
echo "monitor_status=$next_status failures=$failures url=$API_HEALTH_URL" >&2
exit 1
