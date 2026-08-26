from datetime import datetime
from decimal import Decimal
from typing import Optional

import pytz
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import (
    AlocacaoPagamentoFatura,
    Cartao,
    Conta,
    Fatura,
    GastoDiario,
    PagamentoFatura,
)
from services.contas import creditar, debitar, garantir_conta_cartao


def _avancar_mes(mes: int, ano: int, quantidade: int) -> tuple[int, int]:
    indice = ano * 12 + mes - 1 + quantidade
    return indice % 12 + 1, indice // 12


def referencia_fatura(data: datetime, dia_fechamento: int) -> tuple[int, int]:
    """Retorna o mes de vencimento da fatura que contem o lancamento."""
    meses_a_frente = 2 if data.day >= dia_fechamento else 1
    return _avancar_mes(data.month, data.year, meses_a_frente)


def referencia_fatura_atual(agora: datetime, dia_fechamento: int) -> tuple[int, int]:
    """Retorna a competencia da proxima fatura em formacao."""
    return referencia_fatura(agora, dia_fechamento)


def pertence_a_fatura(
    gasto: GastoDiario, dia_fechamento: int, mes_ref: int, ano_ref: int
) -> bool:
    mes_fatura, ano_fatura = referencia_fatura(gasto.data, dia_fechamento)
    return mes_fatura == mes_ref and ano_fatura == ano_ref


def _pagamentos_ativos(fatura: Fatura) -> list[PagamentoFatura]:
    return [item for item in fatura.pagamentos if item.estornado_em is None]


def _total_pago(fatura: Fatura) -> Decimal:
    return sum((item.valor for item in _pagamentos_ativos(fatura)), Decimal("0"))


def _resposta_pagamento(
    cartao: Cartao, fatura: Fatura, pagamento: PagamentoFatura, *, idempotente=False
):
    total_pago = _total_pago(fatura)
    saldo_restante = max(fatura.total - total_pago, Decimal("0"))
    saldo = pagamento.conta.saldo if pagamento.conta is not None else cartao.saldo
    return {
        "mensagem": "Fatura registrada com sucesso",
        "pagamento_id": pagamento.id,
        "fatura_id": fatura.id,
        "valor_pago": pagamento.valor,
        "situacao": pagamento.situacao,
        "origem": pagamento.origem,
        "movimentou_saldo": pagamento.movimentou_saldo,
        "conta_id": pagamento.conta_id,
        "mes_ref": fatura.mes_ref,
        "ano_ref": fatura.ano_ref,
        "saldo_restante": saldo_restante,
        "novo_saldo": saldo,
        "novo_limite": cartao.limite,
        "idempotente": idempotente,
    }


def _marcar_parcelas_cobertas(gastos, valor_pago: Decimal) -> None:
    """Compatibilidade: marca parcelas integralmente cobertas em ordem cronologica."""
    acumulado = Decimal("0")
    for gasto in sorted(gastos, key=lambda item: (item.data, item.id or 0)):
        acumulado += gasto.valor
        gasto.pago = acumulado <= valor_pago


def _aplicar_pagamento_cartao(
    cartao: Cartao,
    valor_pagamento: Decimal,
    *,
    movimentar_saldo: bool,
    restaurar_limite: bool,
) -> None:
    """Helper legado usado por chamadas sem uma Conta separada."""
    if movimentar_saldo:
        cartao.saldo -= valor_pagamento
    if restaurar_limite:
        cartao.limite += valor_pagamento


def gastos_da_competencia(
    db: Session, cartao: Cartao, mes_ref: int, ano_ref: int, *, bloquear=False
) -> list[GastoDiario]:
    query = db.query(GastoDiario).filter(
        GastoDiario.cartao_id == cartao.id,
        GastoDiario.tipo_pagamento == "credito",
    )
    if bloquear:
        query = query.with_for_update()
    return [
        gasto
        for gasto in query.all()
        if pertence_a_fatura(gasto, cartao.data_fatura, mes_ref, ano_ref)
    ]


def _atualizar_situacao(fatura: Fatura) -> None:
    pago = _total_pago(fatura)
    if fatura.total <= 0:
        fatura.situacao = "sem_lancamentos"
    elif pago <= 0:
        fatura.situacao = "aberta"
    elif pago < fatura.total:
        fatura.situacao = "parcial"
    else:
        fatura.situacao = "paga"


def sincronizar_fatura(
    db: Session,
    cartao: Cartao,
    mes_ref: int,
    ano_ref: int,
    *,
    criar=False,
    bloquear=False,
    agora: Optional[datetime] = None,
) -> tuple[Optional[Fatura], list[GastoDiario]]:
    query = db.query(Fatura).filter(
        Fatura.cartao_id == cartao.id,
        Fatura.mes_ref == mes_ref,
        Fatura.ano_ref == ano_ref,
    )
    if bloquear:
        query = query.with_for_update()
    fatura = query.first()
    gastos = gastos_da_competencia(
        db, cartao, mes_ref, ano_ref, bloquear=bloquear
    )
    total_lancado = sum((gasto.valor for gasto in gastos), Decimal("0"))
    if fatura is None and criar and total_lancado > 0:
        fatura = Fatura(
            cartao_id=cartao.id,
            mes_ref=mes_ref,
            ano_ref=ano_ref,
            total=total_lancado,
            situacao="aberta",
            criada_em=agora or datetime.now(pytz.timezone("America/Sao_Paulo")),
        )
        db.add(fatura)
        db.flush()
    elif fatura is not None:
        total_pago = _total_pago(fatura)
        if total_lancado < total_pago:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Os lancamentos da fatura ficaram abaixo do valor ja pago; "
                    "estorne o pagamento antes de editar ou reembolsar"
                ),
            )
        fatura.total = total_lancado
        _atualizar_situacao(fatura)
    return fatura, gastos


def _reconstruir_alocacoes(
    db: Session, fatura: Fatura, gastos: list[GastoDiario]
) -> None:
    pagamentos = sorted(
        _pagamentos_ativos(fatura), key=lambda item: (item.data_pagamento, item.id or 0)
    )
    ids_pagamentos = [item.id for item in fatura.pagamentos if item.id]
    if ids_pagamentos:
        db.query(AlocacaoPagamentoFatura).filter(
            AlocacaoPagamentoFatura.pagamento_id.in_(ids_pagamentos)
        ).delete(synchronize_session=False)
        db.flush()

    restante_por_gasto = {gasto.id: gasto.valor for gasto in gastos}
    for gasto in gastos:
        gasto.pago = False
    for pagamento in pagamentos:
        restante_pagamento = pagamento.valor
        for gasto in sorted(gastos, key=lambda item: (item.data, item.id or 0)):
            if restante_pagamento <= 0:
                break
            restante_gasto = restante_por_gasto[gasto.id]
            if restante_gasto <= 0:
                continue
            alocado = min(restante_gasto, restante_pagamento)
            db.add(
                AlocacaoPagamentoFatura(
                    pagamento_id=pagamento.id,
                    gasto_id=gasto.id,
                    valor=alocado,
                )
            )
            restante_por_gasto[gasto.id] -= alocado
            restante_pagamento -= alocado
    for gasto in gastos:
        gasto.pago = restante_por_gasto[gasto.id] == 0
    _atualizar_situacao(fatura)


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
    conta_id: Optional[int] = None,
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

    if idempotency_key:
        anterior = db.query(PagamentoFatura).filter(
            PagamentoFatura.idempotency_key == idempotency_key
        ).first()
        if anterior:
            if (
                anterior.cartao_id != cartao.id
                or anterior.mes_ref != mes_ref
                or anterior.ano_ref != ano_ref
                or (valor is not None and anterior.valor != valor)
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Chave de idempotencia utilizada com outro pagamento",
                )
            return _resposta_pagamento(
                cartao, anterior.fatura, anterior, idempotente=True
            )

    fatura, gastos = sincronizar_fatura(
        db,
        cartao,
        mes_ref,
        ano_ref,
        criar=True,
        bloquear=True,
        agora=agora,
    )
    if fatura is None:
        raise HTTPException(status_code=409, detail="Nao ha fatura em aberto")

    total_pago = _total_pago(fatura)
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

    conta: Optional[Conta] = None
    if movimentar_saldo:
        if conta_id:
            conta = (
                db.query(Conta)
                .filter(Conta.id == conta_id, Conta.ativa.is_(True))
                .with_for_update()
                .first()
            )
            if not conta:
                raise HTTPException(status_code=404, detail="Conta de pagamento nao encontrada")
        else:
            conta = garantir_conta_cartao(db, cartao)
        debitar(db, conta, valor_pagamento)
    if restaurar_limite:
        cartao.limite += valor_pagamento

    novo_saldo_restante = saldo_restante - valor_pagamento
    situacao = "total" if novo_saldo_restante == 0 else "parcial"
    pagamento = PagamentoFatura(
        fatura=fatura,
        cartao=cartao,
        conta=conta,
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
    db.flush()
    _reconstruir_alocacoes(db, fatura, gastos)
    db.flush()
    return _resposta_pagamento(cartao, fatura, pagamento)


def estornar_pagamento_fatura(
    db: Session,
    *,
    cartao_id: int,
    pagamento_id: int,
    motivo: str,
    idempotency_key: str,
    agora: Optional[datetime] = None,
):
    repetido = db.query(PagamentoFatura).filter(
        PagamentoFatura.estorno_idempotency_key == idempotency_key
    ).first()
    if repetido:
        if repetido.id != pagamento_id or repetido.cartao_id != cartao_id:
            raise HTTPException(
                status_code=409,
                detail="Chave de idempotencia utilizada com outro estorno",
            )
        return {
            "mensagem": "Pagamento ja estornado",
            "pagamento_id": repetido.id,
            "fatura_id": repetido.fatura_id,
            "idempotente": True,
        }

    pagamento = (
        db.query(PagamentoFatura)
        .filter(
            PagamentoFatura.id == pagamento_id,
            PagamentoFatura.cartao_id == cartao_id,
        )
        .with_for_update()
        .first()
    )
    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento de fatura nao encontrado")
    if pagamento.estornado_em is not None:
        raise HTTPException(status_code=409, detail="Pagamento ja estornado")
    cartao = (
        db.query(Cartao)
        .filter(Cartao.id == cartao_id)
        .with_for_update()
        .first()
    )
    if pagamento.movimentou_saldo:
        conta = pagamento.conta or garantir_conta_cartao(db, cartao)
        creditar(db, conta, pagamento.valor)
    cartao.limite -= pagamento.valor
    pagamento.estornado_em = agora or datetime.now(
        pytz.timezone("America/Sao_Paulo")
    )
    pagamento.estorno_idempotency_key = idempotency_key
    pagamento.motivo_estorno = motivo
    pagamento.situacao = "estornado"
    fatura = pagamento.fatura
    gastos = gastos_da_competencia(
        db, cartao, fatura.mes_ref, fatura.ano_ref, bloquear=True
    )
    _reconstruir_alocacoes(db, fatura, gastos)
    db.flush()
    return {
        "mensagem": "Pagamento de fatura estornado com sucesso",
        "pagamento_id": pagamento.id,
        "fatura_id": fatura.id,
        "valor_estornado": pagamento.valor,
        "novo_saldo": pagamento.conta.saldo if pagamento.conta else cartao.saldo,
        "novo_limite": cartao.limite,
        "situacao_fatura": fatura.situacao,
        "idempotente": False,
    }
