from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract
from sqlalchemy.orm import Session

from database import get_db
from models import Cartao, GastoDiario
from schemas import GastoDiarioBase
from schemas.gastos_diarios import TipoPagamento

router = APIRouter()
CENTAVOS = Decimal("0.01")


def _centavos(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _buscar_cartao_bloqueado(db: Session, cartao_id: int) -> Cartao:
    cartao = (
        db.query(Cartao)
        .filter(Cartao.id == cartao_id)
        .with_for_update()
        .first()
    )
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartao/conta nao encontrado")
    return cartao


def _aplicar_gasto(cartao: Cartao, tipo: TipoPagamento, valor: Decimal) -> None:
    if tipo in (TipoPagamento.debito, TipoPagamento.pix):
        if cartao.saldo < valor:
            raise HTTPException(status_code=409, detail="Saldo insuficiente")
        cartao.saldo -= valor
        return

    if cartao.limite < valor:
        raise HTTPException(status_code=409, detail="Limite insuficiente")
    cartao.limite -= valor


def _estornar_gasto(cartao: Cartao, gasto: GastoDiario) -> None:
    if gasto.tipo_pagamento in (TipoPagamento.debito.value, TipoPagamento.pix.value):
        cartao.saldo += gasto.valor
    elif gasto.tipo_pagamento == TipoPagamento.credito.value:
        cartao.limite += gasto.valor


@router.post("/")
def criar_gasto_diario(
    gasto_in: GastoDiarioBase, db: Session = Depends(get_db)
):
    try:
        cartao = _buscar_cartao_bloqueado(db, gasto_in.cartao_id)
        _aplicar_gasto(cartao, gasto_in.tipo_pagamento, gasto_in.valor)

        dados = gasto_in.model_dump(mode="python")
        dados["tipo_pagamento"] = gasto_in.tipo_pagamento.value

        if gasto_in.parcelas == 1:
            gasto = GastoDiario(
                **dados, compra_id=None, numero_parcela=1, pago=False
            )
            db.add(gasto)
            db.commit()
            db.refresh(gasto)
            return gasto

        compra_id = str(uuid4())
        valor_parcela = _centavos(gasto_in.valor / gasto_in.parcelas)
        valor_ultima = gasto_in.valor - valor_parcela * (gasto_in.parcelas - 1)
        primeiro_gasto = None

        for indice in range(gasto_in.parcelas):
            numero = indice + 1
            gasto = GastoDiario(
                descricao=f"{gasto_in.descricao} ({numero}/{gasto_in.parcelas})",
                valor=valor_ultima if numero == gasto_in.parcelas else valor_parcela,
                data=gasto_in.data + relativedelta(months=indice),
                tipo_pagamento=TipoPagamento.credito.value,
                parcelas=gasto_in.parcelas,
                compra_id=compra_id,
                numero_parcela=numero,
                categoria_id=gasto_in.categoria_id,
                cartao_id=gasto_in.cartao_id,
                pago=False,
            )
            db.add(gasto)
            if primeiro_gasto is None:
                primeiro_gasto = gasto

        db.commit()
        db.refresh(primeiro_gasto)
        return primeiro_gasto
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao criar gasto diario")


@router.get("/")
def listar_gastos_diarios(
    mes: Optional[int] = Query(default=None, ge=1, le=12),
    ano: Optional[int] = Query(default=None, ge=1900, le=2200),
    compra_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(GastoDiario)
    if mes is not None:
        query = query.filter(extract("month", GastoDiario.data) == mes)
    if ano is not None:
        query = query.filter(extract("year", GastoDiario.data) == ano)
    if compra_id is not None:
        query = query.filter(GastoDiario.compra_id == compra_id)
    return query.order_by(GastoDiario.data.desc(), GastoDiario.id.desc()).offset(
        offset
    ).limit(limit).all()


@router.get("/{id}")
def buscar_gasto_diario(id: int, db: Session = Depends(get_db)):
    gasto = db.query(GastoDiario).filter(GastoDiario.id == id).first()
    if not gasto:
        raise HTTPException(status_code=404, detail="Gasto diario nao encontrado")
    return gasto


@router.put("/{id}")
def atualizar_gasto_diario(
    id: int, gasto_in: GastoDiarioBase, db: Session = Depends(get_db)
):
    try:
        gasto = (
            db.query(GastoDiario)
            .filter(GastoDiario.id == id)
            .with_for_update()
            .first()
        )
        if not gasto:
            raise HTTPException(status_code=404, detail="Gasto diario nao encontrado")
        if gasto.pago:
            raise HTTPException(
                status_code=409,
                detail="Gasto pago nao pode ser alterado; estorne a fatura primeiro",
            )
        if gasto.compra_id or gasto_in.parcelas > 1:
            raise HTTPException(
                status_code=409,
                detail="Edicao individual de compra parcelada nao e permitida",
            )

        cartao_antigo = _buscar_cartao_bloqueado(db, gasto.cartao_id)
        _estornar_gasto(cartao_antigo, gasto)
        cartao_novo = (
            cartao_antigo
            if gasto_in.cartao_id == gasto.cartao_id
            else _buscar_cartao_bloqueado(db, gasto_in.cartao_id)
        )
        _aplicar_gasto(cartao_novo, gasto_in.tipo_pagamento, gasto_in.valor)

        gasto.descricao = gasto_in.descricao
        gasto.valor = gasto_in.valor
        gasto.data = gasto_in.data
        gasto.categoria_id = gasto_in.categoria_id
        gasto.cartao_id = gasto_in.cartao_id
        gasto.tipo_pagamento = gasto_in.tipo_pagamento.value
        gasto.parcelas = 1
        db.commit()
        db.refresh(gasto)
        return gasto
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar gasto diario")


@router.delete("/{id}")
def deletar_gasto_diario(id: int, db: Session = Depends(get_db)):
    try:
        gasto = (
            db.query(GastoDiario)
            .filter(GastoDiario.id == id)
            .with_for_update()
            .first()
        )
        if not gasto:
            raise HTTPException(status_code=404, detail="Gasto diario nao encontrado")
        if gasto.pago:
            raise HTTPException(
                status_code=409,
                detail="Gasto pago nao pode ser excluido; estorne a fatura primeiro",
            )

        cartao = _buscar_cartao_bloqueado(db, gasto.cartao_id)
        _estornar_gasto(cartao, gasto)
        db.delete(gasto)
        db.commit()
        return {"mensagem": "Gasto diario deletado com sucesso"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao deletar gasto diario")
