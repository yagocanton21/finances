from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import Conta, Transferencia
from schemas.contas import ContaBase, EstornoIn, TransferenciaIn
from services.contas import creditar, debitar

router = APIRouter()


@router.post("/")
def criar_conta(entrada: ContaBase, db: Session = Depends(get_db)):
    try:
        conta = Conta(**entrada.model_dump())
        db.add(conta)
        db.commit()
        db.refresh(conta)
        return conta
    except Exception:
        db.rollback()
        log_internal_error("criar_conta")
        raise HTTPException(status_code=500, detail="Erro ao criar conta")


@router.get("/")
def listar_contas(db: Session = Depends(get_db)):
    return db.query(Conta).filter(Conta.ativa.is_(True)).order_by(Conta.nome).all()


@router.post("/transferencias")
def transferir(entrada: TransferenciaIn, db: Session = Depends(get_db)):
    try:
        if entrada.idempotency_key:
            existente = db.query(Transferencia).filter(
                Transferencia.idempotency_key == entrada.idempotency_key
            ).first()
            if existente:
                if (
                    existente.conta_origem_id != entrada.conta_origem_id
                    or existente.conta_destino_id != entrada.conta_destino_id
                    or existente.valor != entrada.valor
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Chave de idempotencia utilizada em outra transferencia",
                    )
                return {"transferencia": existente, "idempotente": True}

        ids = sorted([entrada.conta_origem_id, entrada.conta_destino_id])
        contas = (
            db.query(Conta)
            .filter(Conta.id.in_(ids), Conta.ativa.is_(True))
            .order_by(Conta.id)
            .with_for_update()
            .all()
        )
        por_id = {conta.id: conta for conta in contas}
        origem = por_id.get(entrada.conta_origem_id)
        destino = por_id.get(entrada.conta_destino_id)
        if not origem or not destino:
            raise HTTPException(status_code=404, detail="Conta de origem ou destino nao encontrada")
        debitar(db, origem, entrada.valor)
        creditar(db, destino, entrada.valor)
        transferencia = Transferencia(**entrada.model_dump())
        db.add(transferencia)
        db.commit()
        db.refresh(transferencia)
        return {"transferencia": transferencia, "idempotente": False}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("transferir_entre_contas")
        raise HTTPException(status_code=500, detail="Erro ao transferir entre contas")


@router.post("/transferencias/{transferencia_id}/estornar")
def estornar_transferencia(
    transferencia_id: int, entrada: EstornoIn, db: Session = Depends(get_db)
):
    try:
        transferencia = (
            db.query(Transferencia)
            .filter(Transferencia.id == transferencia_id)
            .with_for_update()
            .first()
        )
        if not transferencia:
            raise HTTPException(status_code=404, detail="Transferencia nao encontrada")
        if transferencia.estornada_em is not None:
            return {"mensagem": "Transferencia ja estornada", "idempotente": True}
        ids = sorted([transferencia.conta_origem_id, transferencia.conta_destino_id])
        contas = db.query(Conta).filter(Conta.id.in_(ids)).order_by(Conta.id).with_for_update().all()
        por_id = {conta.id: conta for conta in contas}
        origem = por_id[transferencia.conta_origem_id]
        destino = por_id[transferencia.conta_destino_id]
        debitar(db, destino, transferencia.valor)
        creditar(db, origem, transferencia.valor)
        from datetime import datetime
        import pytz

        transferencia.estornada_em = datetime.now(pytz.timezone("America/Sao_Paulo"))
        db.commit()
        return {"mensagem": "Transferencia estornada", "idempotente": False}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("estornar_transferencia")
        raise HTTPException(status_code=500, detail="Erro ao estornar transferencia")


@router.get("/{conta_id}")
def consultar_conta(conta_id: int, db: Session = Depends(get_db)):
    conta = db.query(Conta).filter(Conta.id == conta_id, Conta.ativa.is_(True)).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta nao encontrada")
    return conta
