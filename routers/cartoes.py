from datetime import datetime
from decimal import Decimal
from typing import Optional

import pytz
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Cartao, GastoDiario
from schemas import CartaoBase
from schemas.cartoes import PagarFaturaIn

router = APIRouter()


def _pertence_a_fatura(
    gasto: GastoDiario, dia_fechamento: int, mes_ref: int, ano_ref: int
) -> bool:
    data = gasto.data
    mes_fatura = data.month
    ano_fatura = data.year
    if data.day >= dia_fechamento:
        mes_fatura += 1
        if mes_fatura > 12:
            mes_fatura = 1
            ano_fatura += 1
    return mes_fatura == mes_ref and ano_fatura == ano_ref


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
        dados = {
            coluna.name: getattr(cartao, coluna.name)
            for coluna in cartao.__table__.columns
        }
        dados["fatura_atual"] = _calcular_fatura_do_mes(
            gastos_por_cartao[cartao.id],
            cartao.data_fatura,
            hoje.month,
            hoje.year,
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
        mes_ref = pagamento.mes_ref if pagamento and pagamento.mes_ref else hoje.month
        ano_ref = pagamento.ano_ref if pagamento and pagamento.ano_ref else hoje.year

        gastos = db.query(GastoDiario).filter(
            GastoDiario.cartao_id == cartao.id,
            GastoDiario.tipo_pagamento == "credito",
            GastoDiario.pago.is_(False),
        ).with_for_update().all()
        gastos_da_fatura = [
            gasto for gasto in gastos
            if _pertence_a_fatura(
                gasto, cartao.data_fatura, mes_ref, ano_ref
            )
        ]
        soma_fatura = sum(
            (gasto.valor for gasto in gastos_da_fatura), Decimal("0")
        )
        if soma_fatura <= 0:
            raise HTTPException(status_code=409, detail="Nao ha fatura em aberto")

        valor_fatura = soma_fatura
        if pagamento and pagamento.valor is not None:
            if pagamento.valor > soma_fatura:
                raise HTTPException(
                    status_code=409,
                    detail=f"Valor informado ({pagamento.valor}) excede a fatura ({soma_fatura})",
                )
            valor_fatura = pagamento.valor

        if cartao.saldo < valor_fatura:
            raise HTTPException(status_code=409, detail="Saldo insuficiente")

        cartao.saldo -= valor_fatura
        cartao.limite += valor_fatura
        cartao.fatura_atual = Decimal("0")

        # Marca gastos como pagos (somente se pagou o total)
        if valor_fatura == soma_fatura:
            for gasto in gastos_da_fatura:
                gasto.pago = True

        db.commit()
        db.refresh(cartao)
        return {
            "mensagem": "Fatura paga com sucesso",
            "valor_pago": valor_fatura,
            "mes_ref": mes_ref,
            "ano_ref": ano_ref,
            "novo_saldo": cartao.saldo,
            "novo_limite": cartao.limite,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao pagar fatura")
