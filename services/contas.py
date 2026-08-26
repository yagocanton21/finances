from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Cartao, Conta


def garantir_conta_cartao(db: Session, cartao: Cartao, *, bloquear: bool = True) -> Conta:
    conta = None
    if cartao.conta_padrao_id:
        query = db.query(Conta).filter(Conta.id == cartao.conta_padrao_id, Conta.ativa.is_(True))
        if bloquear:
            query = query.with_for_update()
        conta = query.first()
    if conta is None:
        conta = Conta(
            nome=cartao.nome,
            dono=cartao.dono,
            tipo="corrente",
            saldo=cartao.saldo,
        )
        db.add(conta)
        db.flush()
        cartao.conta_padrao_id = conta.id
    return conta


def resolver_conta(
    db: Session,
    *,
    conta_id: Optional[int] = None,
    cartao_id: Optional[int] = None,
    bloquear: bool = True,
) -> Conta:
    if conta_id:
        query = db.query(Conta).filter(Conta.id == conta_id, Conta.ativa.is_(True))
        if bloquear:
            query = query.with_for_update()
        conta = query.first()
        if not conta:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
        return conta
    if not cartao_id:
        raise HTTPException(status_code=422, detail="Conta nao informada")
    query = db.query(Cartao).filter(Cartao.id == cartao_id, Cartao.ativo.is_(True))
    if bloquear:
        query = query.with_for_update()
    cartao = query.first()
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartao/conta nao encontrado")
    return garantir_conta_cartao(db, cartao, bloquear=bloquear)


def espelhar_saldo_legado(db: Session, conta: Conta) -> None:
    for cartao in db.query(Cartao).filter(Cartao.conta_padrao_id == conta.id).all():
        cartao.saldo = conta.saldo


def debitar(db: Session, conta: Conta, valor: Decimal) -> None:
    if conta.saldo < valor:
        raise HTTPException(status_code=409, detail="Saldo insuficiente")
    conta.saldo -= valor
    espelhar_saldo_legado(db, conta)


def creditar(db: Session, conta: Conta, valor: Decimal) -> None:
    conta.saldo += valor
    espelhar_saldo_legado(db, conta)
