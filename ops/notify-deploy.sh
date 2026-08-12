#!/usr/bin/env bash
set -Eeuo pipefail

STATUS="${1:?Informe success ou failure}"
REVISION="${2:?Informe a revisão implantada}"
RUN_URL="${3:?Informe a URL da execução}"
ENV_FILE="${DEPLOY_ALERT_ENV_FILE:-/etc/financas/backup.env}"

if [[ "$STATUS" != "success" && "$STATUS" != "failure" ]]; then
    echo "Status de deploy inválido: $STATUS" >&2
    exit 2
fi

if [[ ! -r "$ENV_FILE" ]]; then
    echo "Arquivo de credenciais do alerta não está acessível: $ENV_FILE" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN precisa ser configurado}"
: "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID precisa ser configurado}"

SHORT_REVISION="${REVISION:0:7}"

if [[ "$STATUS" == "success" ]]; then
    printf -v MESSAGE '%s\n\n%s\n\n%s' \
        '✅ Implantação concluída, senhor.' \
        "A versão ${SHORT_REVISION} foi publicada e passou por todas as verificações de saúde. O sistema financeiro está operacional e sob monitoramento contínuo." \
        '— J.A.R.V.I.S.'
else
    printf -v MESSAGE '%s\n\n%s\n\n%s\n\n%s' \
        "🚨 Senhor, interrompi a implantação da versão ${SHORT_REVISION}." \
        'Uma das verificações de segurança falhou. A versão que já estava funcionando foi preservada ou o rollback automático foi acionado.' \
        "Detalhes: ${RUN_URL}" \
        '— J.A.R.V.I.S.'
fi

for attempt in 1 2 3; do
    if curl --fail --silent --show-error --max-time 15 \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${MESSAGE}" >/dev/null; then
        echo "deploy_alert=sent status=${STATUS}"
        exit 0
    fi

    if (( attempt < 3 )); then
        sleep 2
    fi
done

echo "deploy_alert=failed status=${STATUS}" >&2
exit 1
