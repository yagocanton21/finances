# Pagamentos de fatura pelo Hermes

Para pagar a fatura usando o saldo cadastrado no sistema, o Hermes deve chamar
`POST /agent/v1/pagamentos/fatura/preview` antes e pedir confirmação. Depois,
envie `POST /agent/v1/pagamentos/fatura` com `confirmado: true` e a mesma
`Idempotency-Key`.

Consulte `GET /agent/v1/contas-bancarias` e envie `conta_pagamento_id` quando a
fatura for paga por uma conta diferente da conta padrão do cartão. Quando a
competência não for informada, a API usa a fatura em formação calculada pelo
dia de fechamento do cartão, exatamente como o frontend.

Quando o usuário disser que já pagou a fatura diretamente no banco ou no app do
cartão, use `POST /agent/v1/pagamentos/fatura/reconciliar`. Essa operação
registra o histórico e marca as parcelas cobertas, mas não debita novamente o
saldo. O valor conciliado é devolvido ao limite disponível do cartão.

O pagamento é alocado cronologicamente entre as parcelas da competência. Uma
parcela só aparece como paga quando seu valor inteiro estiver coberto.
