#!/usr/bin/env bash
set -Eeuo pipefail

TOKEN_FILE="${1:?Informe o arquivo temporario com o token OAuth}"
REMOTE_NAME="${REMOTE_NAME:-gdrive}"
DRIVE_FOLDER="${DRIVE_FOLDER:-Backups}"
CONFIG_FILE="${RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}"

test -s "$TOKEN_FILE"
install -d -m 0700 "$(dirname "$CONFIG_FILE")"

token="$(cat "$TOKEN_FILE")"
{
    printf '[%s]\n' "$REMOTE_NAME"
    printf 'type = drive\n'
    printf 'scope = drive\n'
    printf 'token = %s\n' "$token"
} >"$CONFIG_FILE"
chmod 0600 "$CONFIG_FILE"

rclone mkdir "$REMOTE_NAME:$DRIVE_FOLDER" --config "$CONFIG_FILE"
rclone lsd "$REMOTE_NAME:$DRIVE_FOLDER" --config "$CONFIG_FILE" >/dev/null

echo "Remote $REMOTE_NAME configurado; pasta $DRIVE_FOLDER validada."
