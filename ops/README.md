# Operação de backup do PostgreSQL

Os scripts desta pasta são executados no host Linux da VPS3, fora do container da API.
O volume Docker (`postgres_data`) não substitui backup.

## Configuração mínima

Instale `age` e `rclone` no host quando houver destino externo. Gere uma chave `age` de
backup fora da VPS e mantenha a chave privada em local separado. O host deve receber
somente a chave pública em `AGE_RECIPIENT`.

Exemplo de variáveis para o cron/systemd:

```text
PROJECT_DIR=/home/ubuntu/finan-as
BACKUP_ROOT=/var/backups/financas
AGE_RECIPIENT=age1...
BACKUP_REMOTE=backups-financas:financas-vps3
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

O script falha se `AGE_RECIPIENT` não existir, portanto não cria backup em texto aberto.
Quando `BACKUP_REMOTE` é informado, a cópia externa também precisa concluir para o job
ser considerado bem-sucedido.
Por padrão, `BACKUP_REMOTE` é obrigatório; use `REQUIRE_REMOTE=false` somente em um
ambiente de homologação.

## Recuperação do Google Drive e dos alertas

Quando o remote `gdrive:` retornar `unauthorized_client`, reconecte-o de forma
interativa com o mesmo usuário que executa o backup e valide a pasta antes de
considerar a cópia externa saudável:

```bash
sudo rclone config reconnect gdrive: --config /root/.config/rclone/rclone.conf
sudo rclone lsd gdrive:Backups --config /root/.config/rclone/rclone.conf
```

Em `/etc/financas/backup.env`, configure `BACKUP_REMOTE=gdrive:Backups`,
`REQUIRE_REMOTE=true`, `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Teste o alerta
sem provocar uma falha de backup:

```bash
sudo bash -lc 'set -a; source /etc/financas/backup.env; set +a; bash /home/ubuntu/finan-as/ops/test-telegram-alert.sh'
```

Depois, execute uma cópia completa e confira o estado da unidade:

```bash
sudo systemctl start financas-backup.service
sudo systemctl status financas-backup.service
```

As mesmas credenciais do Telegram são usadas pelo teste automático de
restauração. Qualquer falha na criação, no envio externo ou na restauração de
teste gera um alerta para o chat configurado.

## Execução semanal

Os arquivos `systemd/` podem ser instalados no host Linux:

```bash
sudo install -m 0644 ops/systemd/*.service ops/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now financas-backup.timer financas-backup-verify.timer
```

O agendamento atual é quinta-feira às 02:15 UTC (quarta-feira às 23:15 em
Brasília). O teste de restauração ocorre às 02:45 UTC (23:45 em Brasília).

Para uma instalação simples via cron, após testar manualmente:

```cron
15 2 * * 4 cd /home/ubuntu/finan-as && /home/ubuntu/finan-as/ops/backup-postgres.sh >> /var/log/financas-backup.log 2>&1
```

O script mantém 14 dias diários, 8 semanas e 12 meses por padrão. As cópias são
criptografadas antes de serem armazenadas ou enviadas ao destino externo.

## Teste de restauração

O teste abaixo descriptografa o arquivo e restaura o conteúdo em um container PostgreSQL
temporário. Ele não toca no banco da aplicação:

```bash
AGE_IDENTITY=/caminho/backup.age \
  ./ops/verify-postgres-backup.sh /var/backups/financas/daily/financas_....dump.age
```

Agende esse teste depois do backup, ou execute-o em um job separado com a mesma frequência
do backup.

## Restauração

Restauração sobrescreve dados e exige confirmação explícita:

```bash
CONFIRM_RESTORE=YES AGE_IDENTITY=/caminho/backup.age \
  ./ops/restore-postgres.sh /var/backups/financas/daily/financas_....dump.age
```

Faça a restauração em uma instância/banco de teste primeiro. O teste automático já foi
executado com sucesso em um container temporário na VPS3.
