from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import AporteReserva, Cartao
from schemas.aportes_reserva import AporteReservaBase

router = APIRouter()


@router.post("/")
def criar_aporte(aporte_in: AporteReservaBase, db: Session = Depends(get_db)):
    try:
        cartao = (
            db.query(Cartao)
            .filter(Cartao.id == aporte_in.cartao_id)
            .with_for_update()
            .first()
        )
        if not cartao:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
        if cartao.saldo < aporte_in.valor:
            raise HTTPException(status_code=409, detail="Saldo insuficiente para guardar esse valor")

        cartao.saldo -= aporte_in.valor
        aporte = AporteReserva(**aporte_in.model_dump())
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
    db: Session = Depends(get_db),
):
    query = db.query(AporteReserva)
    if mes is not None:
        query = query.filter(extract("month", AporteReserva.data) == mes)
    if ano is not None:
        query = query.filter(extract("year", AporteReserva.data) == ano)
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
            raise HTTPException(status_code=404, detail="Aporte nao encontrado")
        cartao = db.query(Cartao).filter(Cartao.id == aporte.cartao_id).with_for_update().first()
        if not cartao:
            raise HTTPException(status_code=404, detail="Conta vinculada nao encontrada")
        cartao.saldo += aporte.valor
        db.delete(aporte)
        db.commit()
        return {"mensagem": "Aporte removido com sucesso"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("remover_aporte")
        raise HTTPException(status_code=500, detail="Erro ao remover aporte")
