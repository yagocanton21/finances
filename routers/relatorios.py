from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from database import get_db
from models import GastoDiario, Receita
from schemas.gastos_diarios import TipoPagamento

router = APIRouter()

@router.get("/resumo_mensal")
def resumo_mensal(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=1900, le=2200),
    db: Session = Depends(get_db)
):
    # Total de Receitas do mês
    total_receitas = db.query(func.sum(Receita.valor)).filter(
        extract("month", Receita.data) == mes,
        extract("year", Receita.data) == ano
    ).scalar() or Decimal("0.00")

    # Agrupar Gastos por Tipo de Pagamento
    gastos_agrupados = db.query(
        GastoDiario.tipo_pagamento,
        func.sum(GastoDiario.valor)
    ).filter(
        extract("month", GastoDiario.data) == mes,
        extract("year", GastoDiario.data) == ano
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
    saldo_final = total_receitas - total_gastos

    return {
        "mes": mes,
        "ano": ano,
        "receitas": {
            "total": total_receitas
        },
        "despesas": {
            "credito": gastos_credito,
            "debito": gastos_debito,
            "pix": gastos_pix,
            "total": total_gastos
        },
        "saldo_final": saldo_final
    }
