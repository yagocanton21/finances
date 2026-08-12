from datetime import datetime
from decimal import Decimal
from typing import Optional

import pytz
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import Cartao, Fatura, GastoDiario
from schemas import CartaoBase
from schemas.cartoes import PagarFaturaIn
from services.faturas import (
    pertence_a_fatura,
    processar_pagamento_fatura,
    referencia_fatura_atual,
)

router = APIRouter()


def _pertence_a_fatura(
    gasto: GastoDiario, dia_fechamento: int, mes_ref: int, ano_ref: int
) -> bool:
    return pertence_a_fatura(gasto, dia_fechamento, mes_ref, ano_ref)


def _calcular_fatura_do_mes(
    gastos: list[GastoDiario], dia_fechamento: int, mes_ref: int, ano_ref: int
) -> Decimal:
    return sum(
        (gasto.valor for gasto in gastos if _pertence_a_fatura(
            gasto, dia_fechamento, mes_ref, ano_ref
        )),
        Decimal("0"),
    )


@router.post("/")
def criar_cartao(cartao_in: CartaoBase, db: Session = Depends(get_db)):
    try:
        cartao = Cartao(**cartao_in.model_dump())
        db.add(cartao)
        db.commit()
        db.refresh(cartao)
        return cartao
    except Exception:
        db.rollback()
        log_internal_error("criar_cartao")
        raise HTTPException(status_code=500, detail="Erro ao criar cartao")


@router.get("/")
def listar_cartoes(db: Session = Depends(get_db)):
    cartoes = db.query(Cartao).filter(Cartao.ativo == True).all()
    if not cartoes:
        return []

    hoje = datetime.now(pytz.timezone("America/Sao_Paulo"))
    ids_cartoes = [cartao.id for cartao in cartoes]
    gastos = db.query(GastoDiario).filter(
        GastoDiario.cartao_id.in_(ids_cartoes),
        GastoDiario.tipo_pagamento == "credito",
        GastoDiario.pago.is_(False),
    ).all()
    gastos_por_cartao = {cartao.id: [] for cartao in cartoes}
    for gasto in gastos:
        gastos_por_cartao[gasto.cartao_id].append(gasto)

    resultado = []
    for cartao in cartoes:
        mes_fatura, ano_fatura = referencia_fatura_atual(hoje, cartao.data_fatura)
        dados = {
            coluna.name: getattr(cartao, coluna.name)
            for coluna in cartao.__table__.columns
        }
        dados["fatura_atual"] = _calcular_fatura_do_mes(
            gastos_por_cartao[cartao.id],
            cartao.data_fatura,
            mes_fatura,
            ano_fatura,
        )
        resultado.append(dados)
    return resultado


@router.get("/{id}")
def buscar_cartao(id: int, db: Session = Depends(get_db)):
    cartao = db.query(Cartao).filter(Cartao.id == id, Cartao.ativo == True).first()
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")
    return cartao


@router.put("/{id}")
def atualizar_cartao(
    id: int, cartao_in: CartaoBase, db: Session = Depends(get_db)
):
    try:
        cartao = db.query(Cartao).filter(Cartao.id == id, Cartao.ativo == True).first()
        if not cartao:
            raise HTTPException(status_code=404, detail="Cartao nao encontrado")
        for campo, valor in cartao_in.model_dump().items():
            setattr(cartao, campo, valor)
        db.commit()
        db.refresh(cartao)
        return cartao
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("atualizar_cartao")
        raise HTTPException(status_code=500, detail="Erro ao atualizar cartao")


@router.delete("/{id}")
def deletar_cartao(id: int, db: Session = Depends(get_db)):
    try:
        cartao = db.query(Cartao).filter(Cartao.id == id).first()
        if not cartao:
            raise HTTPException(status_code=404, detail="Cartao nao encontrado")
        
        cartao.ativo = False
        db.commit()
        return {"mensagem": "Cartao deletado com sucesso"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("deletar_cartao")
        raise HTTPException(status_code=500, detail="Erro ao deletar cartao")


@router.post("/{id}/pagar_fatura")
def pagar_fatura(
    id: int,
    pagamento: Optional[PagarFaturaIn] = Body(default=None),
    db: Session = Depends(get_db),
):
    try:
        cartao = (
            db.query(Cartao)
            .filter(Cartao.id == id)
            .with_for_update()
            .first()
        )
        if not cartao:
            raise HTTPException(status_code=404, detail="Cartao nao encontrado")

        hoje = datetime.now(pytz.timezone("America/Sao_Paulo"))
        mes_atual, ano_atual = referencia_fatura_atual(hoje, cartao.data_fatura)
        mes_ref = pagamento.mes_ref if pagamento and pagamento.mes_ref else mes_atual
        ano_ref = pagamento.ano_ref if pagamento and pagamento.ano_ref else ano_atual

        resposta = processar_pagamento_fatura(
            db,
            cartao_id=id,
            mes_ref=mes_ref,
            ano_ref=ano_ref,
            valor=pagamento.valor if pagamento else None,
            idempotency_key=pagamento.idempotency_key if pagamento else None,
            origem="sistema",
            movimentar_saldo=True,
            agora=hoje,
        )
        db.commit()
        return resposta
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("pagar_fatura")
        raise HTTPException(status_code=500, detail="Erro ao pagar fatura")


@router.get("/{id}/fatura")
def consultar_fatura(
    id: int,
    mes_ref: Optional[int] = Query(default=None, ge=1, le=12),
    ano_ref: Optional[int] = Query(default=None, ge=1900, le=2200),
    db: Session = Depends(get_db),
):
    cartao = db.query(Cartao).filter(Cartao.id == id).first()
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    hoje = datetime.now(pytz.timezone("America/Sao_Paulo"))
    mes_atual, ano_atual = referencia_fatura_atual(hoje, cartao.data_fatura)
    mes = mes_ref or mes_atual
    ano = ano_ref or ano_atual
    fatura = (
        db.query(Fatura)
        .filter(Fatura.cartao_id == id, Fatura.mes_ref == mes, Fatura.ano_ref == ano)
        .first()
    )
    if not fatura:
        gastos = db.query(GastoDiario).filter(
            GastoDiario.cartao_id == id,
            GastoDiario.tipo_pagamento == "credito",
            GastoDiario.pago.is_(False),
        ).all()
        total = _calcular_fatura_do_mes(gastos, cartao.data_fatura, mes, ano)
        return {
            "mes_ref": mes,
            "ano_ref": ano,
            "total": total,
            "total_pago": Decimal("0"),
            "saldo_restante": total,
            "situacao": "aberta" if total > 0 else "sem_lancamentos",
            "pagamentos": [],
        }

    total_pago = sum((item.valor for item in fatura.pagamentos), Decimal("0"))
    return {
        "id": fatura.id,
        "mes_ref": fatura.mes_ref,
        "ano_ref": fatura.ano_ref,
        "total": fatura.total,
        "total_pago": total_pago,
        "saldo_restante": max(fatura.total - total_pago, Decimal("0")),
        "situacao": fatura.situacao,
        "pagamentos": [
            {
                "id": item.id,
                "valor": item.valor,
                "data_pagamento": item.data_pagamento,
                "situacao": item.situacao,
            }
            for item in sorted(fatura.pagamentos, key=lambda item: item.data_pagamento)
        ],
    }
