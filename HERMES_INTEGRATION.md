# Integração do Hermes

## Configuração

Defina um token longo e aleatório no `.env` da API:

```env
HERMES_API_TOKEN=seu-token-secreto
```

O Hermes deve enviar esse valor no cabeçalho `X-Agent-Token`. Toda criação também
precisa de `Idempotency-Key`, usando preferencialmente o ID imutável da mensagem
que originou o lançamento.

## Pagamento de fatura

Para pagar usando o saldo do sistema, use `POST /agent/v1/pagamentos/fatura/preview`
e depois `POST /agent/v1/pagamentos/fatura` com `confirmado: true`.

Quando o usuário disser que já pagou diretamente no banco ou no cartão, use
`POST /agent/v1/pagamentos/fatura/reconciliar`. Essa operação registra o histórico
e marca as parcelas cobertas sem debitar novamente o saldo.

## Fluxo recomendado

1. Consulte `GET /agent/v1/contas` e `GET /agent/v1/categorias`.
2. Monte um lançamento estruturado e envie para `POST /agent/v1/lancamentos/preview`.
3. Se os dados estiverem corretos, confirme com `POST /agent/v1/lancamentos`.
4. Em timeout, repita com a mesma `Idempotency-Key`; a API não duplicará o registro.
5. Consulte o resultado com `GET /agent/v1/lancamentos/{external_id}`.

Para desfazer um lançamento, use `DELETE /agent/v1/lancamentos/{external_id}`.
Uma correção deve ser feita como estorno seguido de um novo lançamento com uma
nova chave idempotente, preservando o histórico. O resumo financeiro está em
`GET /agent/v1/resumo?mes=8&ano=2026`.

## Exemplo de gasto parcelado

```http
POST /agent/v1/lancamentos
X-Agent-Token: <token>
Idempotency-Key: telegram-12345-message-678
Content-Type: application/json

{
  "tipo_lancamento": "gasto",
  "descricao": "Geladeira",
  "valor": "2400.00",
  "data": "2026-08-05T12:00:00-03:00",
  "conta": "Nubank",
  "categoria": "Casa",
  "tipo_pagamento": "credito",
  "parcelas": 12
}
```

## Exemplo de receita

```json
{
  "tipo_lancamento": "receita",
  "descricao": "Salário",
  "valor": "5000.00",
  "data": "2026-08-05T09:00:00-03:00",
  "conta_id": 1
}
```

Não escolha silenciosamente entre contas ou categorias ambíguas. Quando a API
responder `409` ou `422`, o Hermes deve apresentar a mensagem ao usuário e pedir
a informação que estiver faltando.
