from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import Cartao, Compra, GastoDiario, ReembolsoCompra
from routers.gastos_diarios import (
    _sincronizar_competencias,
    _valor_alocado_ativo,
)
from schemas.compras import AtualizarCompraIn, ReembolsoCompraIn
from schemas.gastos_diarios import TipoPagamento
from services.contas import creditar, resolver_conta
from services.faturas import referencia_fatura

router = APIRouter()


def _buscar_compra(db: Session, compra_id: str, *, bloquear=False) -> Compra:
    query = db.query(Compra).filter(Compra.id == compra_id)
    if bloquear:
        query = query.with_for_update()
    compra = query.first()
    if not compra:
        raise HTTPException(status_code=404, detail="Compra nao encontrada")
    return compra


def _resposta(compra: Compra):
    return {
        "id": compra.id,
        "descricao": compra.descricao,
        "valor_total": compra.valor_total,
        "valor_reembolsado": compra.valor_reembolsado,
        "valor_liquido": compra.valor_total - compra.valor_reembolsado,
        "data_compra": compra.data_compra,
        "parcelas": compra.parcelas,
        "tipo_pagamento": compra.tipo_pagamento,
        "situacao": compra.situacao,
        "cartao_id": compra.cartao_id,
        "conta_id": compra.conta_id,
        "categoria_id": compra.categoria_id,
        "itens": [
            {
                "id": item.id,
                "descricao": item.descricao,
                "valor": item.valor,
                "data": item.data,
                "numero_parcela": item.numero_parcela,
                "parcelas": item.parcelas,
                "pago": item.pago,
            }
            for item in sorted(compra.itens, key=lambda item: item.numero_parcela)
        ],
        "reembolsos": [
            {
                "id": item.id,
                "valor": item.valor,
                "motivo": item.motivo,
                "criado_em": item.criado_em,
            }
            for item in sorted(compra.reembolsos, key=lambda item: item.criado_em)
        ],
    }


@router.get("/")
def listar_compras(db: Session = Depends(get_db)):
    return [_resposta(item) for item in db.query(Compra).order_by(Compra.data_compra.desc()).all()]


@router.get("/{compra_id}")
def consultar_compra(compra_id: str, db: Session = Depends(get_db)):
    return _resposta(_buscar_compra(db, compra_id))


@router.patch("/{compra_id}")
def atualizar_compra(
    compra_id: str, entrada: AtualizarCompraIn, db: Session = Depends(get_db)
):
    try:
        compra = _buscar_compra(db, compra_id, bloquear=True)
        if entrada.descricao is not None:
            compra.descricao = entrada.descricao
            for item in compra.itens:
                item.descricao = (
                    f"{entrada.descricao} ({item.numero_parcela}/{item.parcelas})"
                    if item.parcelas > 1
                    else entrada.descricao
                )
        if entrada.categoria_id is not None:
            compra.categoria_id = entrada.categoria_id
            for item in compra.itens:
                item.categoria_id = entrada.categoria_id
        db.commit()
        return _resposta(compra)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("atualizar_compra")
        raise HTTPException(status_code=500, detail="Erro ao atualizar compra")


@router.post("/{compra_id}/reembolsos")
def reembolsar_compra(
    compra_id: str, entrada: ReembolsoCompraIn, db: Session = Depends(get_db)
):
    try:
        if entrada.idempotency_key:
            existente = db.query(ReembolsoCompra).filter(
                ReembolsoCompra.idempotency_key == entrada.idempotency_key
            ).first()
            if existente:
                if existente.compra_id != compra_id or (
                    entrada.valor is not None and existente.valor != entrada.valor
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Chave de idempotencia utilizada em outro reembolso",
                    )
                return {
                    "reembolso": {
                        "id": existente.id,
                        "valor": existente.valor,
                        "motivo": existente.motivo,
                    },
                    "compra": _resposta(existente.compra),
                    "idempotente": True,
                }

        compra = _buscar_compra(db, compra_id, bloquear=True)
        itens = (
            db.query(GastoDiario)
            .filter(GastoDiario.compra_id == compra.id)
            .with_for_update()
            .order_by(GastoDiario.data.desc(), GastoDiario.numero_parcela.desc())
            .all()
        )
        disponivel = sum(
            (item.valor for item in itens if _valor_alocado_ativo(db, item.id) == 0),
            Decimal("0"),
        )
        valor = entrada.valor or disponivel
        if valor > disponivel:
            raise HTTPException(
                status_code=409,
                detail="Reembolso excede o valor ainda nao pago; estorne a fatura primeiro",
            )

        referencias = set()
        restante = valor
        cartao = None
        if compra.tipo_pagamento == TipoPagamento.credito.value:
            cartao = (
                db.query(Cartao)
                .filter(Cartao.id == compra.cartao_id)
                .with_for_update()
                .first()
            )
        for item in itens:
            if restante <= 0 or _valor_alocado_ativo(db, item.id) > 0:
                continue
            if cartao:
                mes_ref, ano_ref = referencia_fatura(item.data, cartao.data_fatura)
                referencias.add((cartao.id, mes_ref, ano_ref))
            abatimento = min(item.valor, restante)
            item.valor -= abatimento
            restante -= abatimento

        if cartao:
            cartao.limite += valor
        else:
            conta = resolver_conta(db, conta_id=compra.conta_id, bloquear=True)
            creditar(db, conta, valor)
        compra.valor_reembolsado += valor
        if compra.valor_reembolsado >= compra.valor_total:
            compra.situacao = "reembolsada"
        else:
            compra.situacao = "reembolso_parcial"
        reembolso = ReembolsoCompra(
            compra=compra,
            valor=valor,
            motivo=entrada.motivo,
            idempotency_key=entrada.idempotency_key,
        )
        db.add(reembolso)
        db.flush()
        _sincronizar_competencias(db, referencias)
        db.commit()
        return {
            "reembolso": {
                "id": reembolso.id,
                "valor": reembolso.valor,
                "motivo": reembolso.motivo,
            },
            "compra": _resposta(compra),
            "idempotente": False,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("reembolsar_compra")
        raise HTTPException(status_code=500, detail="Erro ao reembolsar compra")
