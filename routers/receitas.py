from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import Receita
from schemas.receitas import ReceitaBase
from services.contas import creditar, debitar, resolver_conta

router = APIRouter()


@router.post("/")
def criar_receita(receita_in: ReceitaBase, db: Session = Depends(get_db)):
    try:
        conta = resolver_conta(
            db, conta_id=receita_in.conta_id, cartao_id=receita_in.cartao_id
        )
        dados = receita_in.model_dump()
        dados["conta_id"] = conta.id
        receita = Receita(**dados)
        creditar(db, conta, receita.valor)
        db.add(receita)
        db.commit()
        db.refresh(receita)
        return receita
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("criar_receita")
        raise HTTPException(status_code=500, detail="Erro ao criar receita")


@router.get("/")
def listar_receitas(db: Session = Depends(get_db)):
    return db.query(Receita).order_by(Receita.data.desc(), Receita.id.desc()).all()


@router.get("/{id}")
def buscar_receita(id: int, db: Session = Depends(get_db)):
    receita = db.query(Receita).filter(Receita.id == id).first()
    if not receita:
        raise HTTPException(status_code=404, detail="Receita nao encontrada")
    return receita


@router.put("/{id}")
def atualizar_receita(
    id: int, receita_in: ReceitaBase, db: Session = Depends(get_db)
):
    try:
        receita = (
            db.query(Receita)
            .filter(Receita.id == id)
            .with_for_update()
            .first()
        )
        if not receita:
            raise HTTPException(status_code=404, detail="Receita nao encontrada")
        conta_antiga = resolver_conta(
            db, conta_id=receita.conta_id, cartao_id=receita.cartao_id
        )
        if conta_antiga.saldo < receita.valor:
            raise HTTPException(
                status_code=409,
                detail="Saldo insuficiente para reduzir ou mover esta receita",
            )
        debitar(db, conta_antiga, receita.valor)
        conta_nova = resolver_conta(
            db, conta_id=receita_in.conta_id, cartao_id=receita_in.cartao_id
        )
        for campo, valor in receita_in.model_dump().items():
            setattr(receita, campo, valor)
        receita.conta_id = conta_nova.id
        creditar(db, conta_nova, receita.valor)
        db.commit()
        db.refresh(receita)
        return receita
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("atualizar_receita")
        raise HTTPException(status_code=500, detail="Erro ao atualizar receita")


@router.delete("/{id}")
def deletar_receita(id: int, db: Session = Depends(get_db)):
    try:
        receita = (
            db.query(Receita)
            .filter(Receita.id == id)
            .with_for_update()
            .first()
        )
        if not receita:
            raise HTTPException(status_code=404, detail="Receita nao encontrada")
        conta = resolver_conta(
            db, conta_id=receita.conta_id, cartao_id=receita.cartao_id
        )
        if conta.saldo < receita.valor:
            raise HTTPException(
                status_code=409,
                detail="Saldo insuficiente para estornar esta receita",
            )
        debitar(db, conta, receita.valor)
        db.delete(receita)
        db.commit()
        return {"mensagem": "Receita deletada com sucesso"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("deletar_receita")
        raise HTTPException(status_code=500, detail="Erro ao deletar receita")
