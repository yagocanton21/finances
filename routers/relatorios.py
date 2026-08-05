from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from database import get_db
from models import AporteReserva, Cartao, Categoria, GastoDiario, Receita
from schemas.gastos_diarios import TipoPagamento

router = APIRouter()


@router.get("/resumo_mensal")
def resumo_mensal(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=1900, le=2200),
    dono: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    filtro_conta = Cartao.dono == dono if dono else True

    total_receitas = db.query(func.sum(Receita.valor)).join(
        Cartao, Receita.cartao_id == Cartao.id
    ).filter(
        extract("month", Receita.data) == mes,
        extract("year", Receita.data) == ano,
        filtro_conta,
    ).scalar() or Decimal("0.00")

    gastos_agrupados = db.query(
        GastoDiario.tipo_pagamento,
        func.sum(GastoDiario.valor),
    ).join(Cartao, GastoDiario.cartao_id == Cartao.id).filter(
        extract("month", GastoDiario.data) == mes,
        extract("year", GastoDiario.data) == ano,
        filtro_conta,
    ).group_by(GastoDiario.tipo_pagamento).all()

    gastos_credito = Decimal("0.00")
    gastos_debito = Decimal("0.00")
    gastos_pix = Decimal("0.00")
    for tipo, valor in gastos_agrupados:
        if tipo == TipoPagamento.credito.value:
            gastos_credito += valor
        elif tipo == TipoPagamento.debito.value:
            gastos_debito += valor
        elif tipo == TipoPagamento.pix.value:
            gastos_pix += valor

    total_gastos = gastos_credito + gastos_debito + gastos_pix
    categorias = db.query(
        Categoria.nome,
        func.sum(GastoDiario.valor),
    ).join(GastoDiario, GastoDiario.categoria_id == Categoria.id).join(
        Cartao, GastoDiario.cartao_id == Cartao.id
    ).filter(
        extract("month", GastoDiario.data) == mes,
        extract("year", GastoDiario.data) == ano,
        filtro_conta,
    ).group_by(Categoria.nome).order_by(func.sum(GastoDiario.valor).desc()).all()

    guardado = db.query(func.sum(AporteReserva.valor)).join(
        Cartao, AporteReserva.cartao_id == Cartao.id
    ).filter(
        extract("month", AporteReserva.data) == mes,
        extract("year", AporteReserva.data) == ano,
        filtro_conta,
    ).scalar() or Decimal("0.00")

    return {
        "mes": mes,
        "ano": ano,
        "receitas": {"total": total_receitas},
        "despesas": {
            "credito": gastos_credito,
            "debito": gastos_debito,
            "pix": gastos_pix,
            "total": total_gastos,
        },
        "saldo_final": total_receitas - total_gastos,
        "categorias": [{"nome": nome, "total": total} for nome, total in categorias],
        "guardado": guardado,
    }
