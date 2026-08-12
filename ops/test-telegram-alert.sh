#!/usr/bin/env bash
set -Eeuo pipefail

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN precisa ser configurado}"
: "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID precisa ser configurado}"

curl --fail --silent --show-error \
    -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=Teste: alertas do backup de Financas estao ativos em $(hostname)." \
    >/dev/null

echo "Alerta de teste enviado ao Telegram."
