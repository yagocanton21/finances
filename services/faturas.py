from datetime import datetime
from decimal import Decimal
from typing import Optional

import pytz
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Cartao, Fatura, GastoDiario, PagamentoFatura


def _avancar_mes(mes: int, ano: int, quantidade: int) -> tuple[int, int]:
    indice = ano * 12 + mes - 1 + quantidade
    return indice % 12 + 1, indice // 12


def referencia_fatura(data: datetime, dia_fechamento: int) -> tuple[int, int]:
    """Retorna o mes de vencimento da fatura que contem o lancamento.

    Ex.: com fechamento no dia 28, a fatura de setembro cobre 28/07 a 27/08.
    """
    meses_a_frente = 2 if data.day >= dia_fechamento else 1
    return _avancar_mes(data.month, data.year, meses_a_frente)


def referencia_fatura_atual(agora: datetime, dia_fechamento: int) -> tuple[int, int]:
    """Retorna a competencia da proxima fatura em formacao."""
    meses_a_frente = 2 if agora.day >= dia_fechamento else 1
    return _avancar_mes(agora.month, agora.year, meses_a_frente)


def pertence_a_fatura(
    gasto: GastoDiario, dia_fechamento: int, mes_ref: int, ano_ref: int
) -> bool:
    mes_fatura, ano_fatura = referencia_fatura(gasto.data, dia_fechamento)
    return mes_fatura == mes_ref and ano_fatura == ano_ref


def _resposta_pagamento(
    cartao: Cartao, fatura: Fatura, pagamento: PagamentoFatura, *, idempotente=False
):
    total_pago = sum((item.valor for item in fatura.pagamentos), Decimal("0"))
    saldo_restante = max(fatura.total - total_pago, Decimal("0"))
    return {
        "mensagem": "Fatura registrada com sucesso",
        "pagamento_id": pagamento.id,
        "fatura_id": fatura.id,
        "valor_pago": pagamento.valor,
        "situacao": pagamento.situacao,
        "origem": pagamento.origem,
        "movimentou_saldo": pagamento.movimentou_saldo,
        "mes_ref": fatura.mes_ref,
        "ano_ref": fatura.ano_ref,
        "saldo_restante": saldo_restante,
        "novo_saldo": cartao.saldo,
        "novo_limite": cartao.limite,
        "idempotente": idempotente,
    }


def _marcar_parcelas_cobertas(gastos, valor_pago: Decimal) -> None:
    """Aloca o pagamento em ordem cronológica e marca parcelas totalmente cobertas."""
    acumulado = Decimal("0")
    for gasto in sorted(gastos, key=lambda item: (item.data, item.id)):
        acumulado += gasto.valor
        gasto.pago = acumulado <= valor_pago


def _aplicar_pagamento_cartao(
    cartao: Cartao,
    valor_pagamento: Decimal,
    *,
    movimentar_saldo: bool,
    restaurar_limite: bool,
) -> None:
    if movimentar_saldo:
        cartao.saldo -= valor_pagamento
    if restaurar_limite:
        cartao.limite += valor_pagamento


def processar_pagamento_fatura(
    db: Session,
    *,
    cartao_id: int,
    mes_ref: int,
    ano_ref: int,
    valor: Optional[Decimal] = None,
    idempotency_key: Optional[str] = None,
    origem: str = "sistema",
    movimentar_saldo: bool = True,
    restaurar_limite: Optional[bool] = None,
    agora: Optional[datetime] = None,
):
    if restaurar_limite is None:
        restaurar_limite = movimentar_saldo

    cartao = (
        db.query(Cartao)
        .filter(Cartao.id == cartao_id, Cartao.ativo.is_(True))
        .with_for_update()
        .first()
    )
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    fatura = (
        db.query(Fatura)
        .filter(
            Fatura.cartao_id == cartao.id,
            Fatura.mes_ref == mes_ref,
            Fatura.ano_ref == ano_ref,
        )
        .with_for_update()
        .first()
    )

    if idempotency_key:
        anterior = (
            db.query(PagamentoFatura)
            .filter(
                PagamentoFatura.cartao_id == cartao.id,
                PagamentoFatura.idempotency_key == idempotency_key,
            )
            .first()
        )
        if anterior:
            return _resposta_pagamento(
                cartao, anterior.fatura, anterior, idempotente=True
            )

    gastos = db.query(GastoDiario).filter(
        GastoDiario.cartao_id == cartao.id,
        GastoDiario.tipo_pagamento == "credito",
    ).with_for_update().all()
    gastos_da_fatura = [
        gasto for gasto in gastos
        if pertence_a_fatura(gasto, cartao.data_fatura, mes_ref, ano_ref)
    ]
    soma_fatura = sum((gasto.valor for gasto in gastos_da_fatura), Decimal("0"))

    if fatura is None:
        if soma_fatura <= 0:
            raise HTTPException(status_code=409, detail="Nao ha fatura em aberto")
        fatura = Fatura(
            cartao_id=cartao.id,
            mes_ref=mes_ref,
            ano_ref=ano_ref,
            total=soma_fatura,
            situacao="aberta",
            criada_em=agora or datetime.now(pytz.timezone("America/Sao_Paulo")),
        )
        db.add(fatura)
        db.flush()
    else:
        fatura.total = max(fatura.total, soma_fatura)

    total_pago = sum((item.valor for item in fatura.pagamentos), Decimal("0"))
    saldo_restante = fatura.total - total_pago
    if saldo_restante <= 0:
        raise HTTPException(status_code=409, detail="Nao ha fatura em aberto")

    valor_pagamento = saldo_restante if valor is None else valor
    if valor_pagamento > saldo_restante:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Valor informado ({valor_pagamento}) excede o saldo restante "
                f"({saldo_restante})"
            ),
        )
    if movimentar_saldo and cartao.saldo < valor_pagamento:
        raise HTTPException(status_code=409, detail="Saldo insuficiente")

    _aplicar_pagamento_cartao(
        cartao,
        valor_pagamento,
        movimentar_saldo=movimentar_saldo,
        restaurar_limite=restaurar_limite,
    )

    novo_saldo_restante = saldo_restante - valor_pagamento
    situacao = "total" if novo_saldo_restante == 0 else "parcial"
    fatura.situacao = "paga" if situacao == "total" else "parcial"
    pagamento = PagamentoFatura(
        fatura=fatura,
        cartao=cartao,
        mes_ref=mes_ref,
        ano_ref=ano_ref,
        valor=valor_pagamento,
        data_pagamento=agora or datetime.now(pytz.timezone("America/Sao_Paulo")),
        situacao=situacao,
        origem=origem,
        movimentou_saldo=movimentar_saldo,
        idempotency_key=idempotency_key,
    )
    db.add(pagamento)
    _marcar_parcelas_cobertas(gastos_da_fatura, total_pago + valor_pagamento)
    db.flush()
    return _resposta_pagamento(cartao, fatura, pagamento)
