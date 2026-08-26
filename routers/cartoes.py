from datetime import datetime
from decimal import Decimal
from typing import Optional

import pytz
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app_logging import log_internal_error
from database import get_db
from models import Cartao, Conta, Fatura, GastoDiario
from schemas import CartaoBase
from schemas.cartoes import PagarFaturaIn
from schemas.contas import EstornoIn
from services.contas import garantir_conta_cartao
from services.faturas import (
    estornar_pagamento_fatura,
    pertence_a_fatura,
    processar_pagamento_fatura,
    referencia_fatura_atual,
    sincronizar_fatura,
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
        dados = cartao_in.model_dump(exclude={"limite_total"})
        conta = Conta(
            nome=cartao_in.nome,
            dono=cartao_in.dono,
            tipo="corrente",
            saldo=cartao_in.saldo,
        )
        db.add(conta)
        db.flush()
        cartao = Cartao(
            **dados,
            limite_total=cartao_in.limite_total or cartao_in.limite,
            conta_padrao_id=conta.id,
        )
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
        conta = garantir_conta_cartao(db, cartao, bloquear=False)
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
        dados["saldo"] = conta.saldo
        dados["conta_padrao_id"] = conta.id
        dados["limite_total"] = cartao.limite_total
        resultado.append(dados)
    return resultado


@router.get("/{id}")
def buscar_cartao(id: int, db: Session = Depends(get_db)):
    cartao = db.query(Cartao).filter(Cartao.id == id, Cartao.ativo == True).first()
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")
    conta = garantir_conta_cartao(db, cartao, bloquear=False)
    dados = {coluna.name: getattr(cartao, coluna.name) for coluna in cartao.__table__.columns}
    dados["saldo"] = conta.saldo
    return dados


@router.put("/{id}")
def atualizar_cartao(
    id: int, cartao_in: CartaoBase, db: Session = Depends(get_db)
):
    try:
        cartao = db.query(Cartao).filter(Cartao.id == id, Cartao.ativo == True).first()
        if not cartao:
            raise HTTPException(status_code=404, detail="Cartao nao encontrado")
        limite_total = (
            cartao_in.limite_total
            if cartao_in.limite_total is not None
            else max(cartao.limite_total, cartao_in.limite)
        )
        if cartao_in.limite > limite_total:
            raise HTTPException(
                status_code=409,
                detail="Limite total nao pode ser menor que o limite disponivel",
            )
        for campo, valor in cartao_in.model_dump(
            exclude={"limite_total", "saldo", "fatura_atual", "ativo"}
        ).items():
            setattr(cartao, campo, valor)
        cartao.limite_total = limite_total
        conta = garantir_conta_cartao(db, cartao)
        conta.nome = cartao_in.nome
        conta.dono = cartao_in.dono
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
    hoje = None
    mes_ref = None
    ano_ref = None
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
            conta_id=pagamento.conta_id if pagamento else None,
            origem="sistema",
            movimentar_saldo=True,
            agora=hoje,
        )
        db.commit()
        return resposta
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        if (
            pagamento
            and pagamento.idempotency_key
            and mes_ref is not None
            and ano_ref is not None
            and hoje is not None
        ):
            resposta = processar_pagamento_fatura(
                db,
                cartao_id=id,
                mes_ref=mes_ref,
                ano_ref=ano_ref,
                valor=pagamento.valor,
                idempotency_key=pagamento.idempotency_key,
                origem="sistema",
                movimentar_saldo=True,
                conta_id=pagamento.conta_id,
                agora=hoje,
            )
            db.commit()
            return resposta
        raise HTTPException(status_code=409, detail="Pagamento em conflito")
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
    fatura, gastos = sincronizar_fatura(db, cartao, mes, ano, criar=False)
    if not fatura:
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

    pagamentos_ativos = [item for item in fatura.pagamentos if item.estornado_em is None]
    total_pago = sum((item.valor for item in pagamentos_ativos), Decimal("0"))
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
                "origem": item.origem,
                "conta_id": item.conta_id,
                "estornado_em": item.estornado_em,
            }
            for item in sorted(fatura.pagamentos, key=lambda item: item.data_pagamento)
        ],
    }


@router.post("/{id}/pagamentos/{pagamento_id}/estornar")
def estornar_pagamento(
    id: int,
    pagamento_id: int,
    entrada: EstornoIn,
    db: Session = Depends(get_db),
):
    try:
        resposta = estornar_pagamento_fatura(
            db,
            cartao_id=id,
            pagamento_id=pagamento_id,
            motivo=entrada.motivo,
            idempotency_key=entrada.idempotency_key,
        )
        db.commit()
        return resposta
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("estornar_pagamento_fatura")
        raise HTTPException(status_code=500, detail="Erro ao estornar pagamento de fatura")
