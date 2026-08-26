from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import AporteReserva, MetaReserva
from schemas.aportes_reserva import AporteReservaBase
from services.contas import creditar, debitar, resolver_conta

router = APIRouter()


@router.post("/")
def criar_aporte(aporte_in: AporteReservaBase, db: Session = Depends(get_db)):
    try:
        conta = resolver_conta(
            db, conta_id=aporte_in.conta_id, cartao_id=aporte_in.cartao_id
        )
        meta = None
        if aporte_in.meta_id:
            meta = (
                db.query(MetaReserva)
                .filter(MetaReserva.id == aporte_in.meta_id, MetaReserva.ativa.is_(True))
                .with_for_update()
                .first()
            )
            if not meta:
                raise HTTPException(status_code=404, detail="Meta de reserva nao encontrada")
        debitar(db, conta, aporte_in.valor)
        dados = aporte_in.model_dump()
        dados["conta_id"] = conta.id
        aporte = AporteReserva(**dados, tipo="aporte")
        if meta:
            meta.saldo += aporte.valor
        db.add(aporte)
        db.commit()
        db.refresh(aporte)
        return aporte
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("registrar_aporte")
        raise HTTPException(status_code=500, detail="Erro ao registrar aporte")


@router.get("/")
def listar_aportes(
    mes: Optional[int] = Query(default=None, ge=1, le=12),
    ano: Optional[int] = Query(default=None, ge=1900, le=2200),
    meta_id: Optional[int] = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    query = db.query(AporteReserva)
    if mes is not None:
        query = query.filter(extract("month", AporteReserva.data) == mes)
    if ano is not None:
        query = query.filter(extract("year", AporteReserva.data) == ano)
    if meta_id is not None:
        query = query.filter(AporteReserva.meta_id == meta_id)
    return query.order_by(AporteReserva.data.desc(), AporteReserva.id.desc()).all()


@router.delete("/{id}")
def deletar_aporte(id: int, db: Session = Depends(get_db)):
    try:
        aporte = (
            db.query(AporteReserva)
            .filter(AporteReserva.id == id)
            .with_for_update()
            .first()
        )
        if not aporte:
            raise HTTPException(status_code=404, detail="Movimento de reserva nao encontrado")
        conta = resolver_conta(
            db, conta_id=aporte.conta_id, cartao_id=aporte.cartao_id
        )
        meta = None
        if aporte.meta_id:
            meta = (
                db.query(MetaReserva)
                .filter(MetaReserva.id == aporte.meta_id)
                .with_for_update()
                .first()
            )
        if aporte.tipo == "retirada":
            debitar(db, conta, aporte.valor)
            if meta:
                meta.saldo += aporte.valor
        else:
            creditar(db, conta, aporte.valor)
            if meta:
                meta.saldo = max(meta.saldo - aporte.valor, Decimal("0"))
        db.delete(aporte)
        db.commit()
        return {"mensagem": "Movimento de reserva removido com sucesso"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("remover_aporte")
        raise HTTPException(status_code=500, detail="Erro ao remover movimento de reserva")
