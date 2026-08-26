from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app_logging import log_internal_error
from database import get_db
from models import (
    AlocacaoPagamentoFatura,
    Cartao,
    Compra,
    GastoDiario,
    PagamentoFatura,
)
from schemas import GastoDiarioBase
from schemas.gastos_diarios import ConciliarPagamentoIn, GastoDiarioPatch, TipoPagamento
from services.contas import creditar, debitar, garantir_conta_cartao, resolver_conta
from services.faturas import (
    processar_pagamento_fatura,
    referencia_fatura,
    sincronizar_fatura,
)

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


def _valor_alocado_ativo(db: Session, gasto_id: int) -> Decimal:
    alocacoes = (
        db.query(AlocacaoPagamentoFatura)
        .join(
            PagamentoFatura,
            PagamentoFatura.id == AlocacaoPagamentoFatura.pagamento_id,
        )
        .filter(
            AlocacaoPagamentoFatura.gasto_id == gasto_id,
            PagamentoFatura.estornado_em.is_(None),
        )
        .all()
    )
    return sum((item.valor for item in alocacoes), Decimal("0"))


def _itens_compra(db: Session, gasto: GastoDiario) -> list[GastoDiario]:
    if not gasto.compra_id:
        return [gasto]
    return (
        db.query(GastoDiario)
        .filter(GastoDiario.compra_id == gasto.compra_id)
        .with_for_update()
        .order_by(GastoDiario.numero_parcela)
        .all()
    )


def _sincronizar_competencias(db: Session, referencias: set[tuple[int, int, int]]) -> None:
    for cartao_id, mes_ref, ano_ref in referencias:
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if cartao:
            sincronizar_fatura(db, cartao, mes_ref, ano_ref, criar=False)


@router.post("/")
def criar_gasto_diario(
    gasto_in: GastoDiarioBase, db: Session = Depends(get_db)
):
    try:
        cartao = (
            _buscar_cartao_bloqueado(db, gasto_in.cartao_id)
            if gasto_in.cartao_id
            else None
        )
        conta = resolver_conta(
            db,
            conta_id=gasto_in.conta_id,
            cartao_id=gasto_in.cartao_id,
        )
        if gasto_in.tipo_pagamento in (TipoPagamento.debito, TipoPagamento.pix):
            debitar(db, conta, gasto_in.valor)
        else:
            if cartao.limite < gasto_in.valor:
                raise HTTPException(status_code=409, detail="Limite insuficiente")
            cartao.limite -= gasto_in.valor

        dados = gasto_in.model_dump(mode="python")
        dados["tipo_pagamento"] = gasto_in.tipo_pagamento.value
        dados["conta_id"] = conta.id

        compra_id = str(uuid4())
        compra = Compra(
            id=compra_id,
            descricao=gasto_in.descricao,
            valor_total=gasto_in.valor,
            data_compra=gasto_in.data,
            parcelas=gasto_in.parcelas,
            tipo_pagamento=gasto_in.tipo_pagamento.value,
            cartao_id=cartao.id if cartao else None,
            conta_id=conta.id,
            categoria_id=gasto_in.categoria_id,
            situacao="ativa",
        )
        db.add(compra)

        if gasto_in.parcelas == 1:
            gasto = GastoDiario(
                **dados, compra_id=compra_id, numero_parcela=1, pago=False
            )
            db.add(gasto)
            db.commit()
            db.refresh(gasto)
            return gasto

        valor_parcela = _centavos(gasto_in.valor / gasto_in.parcelas)
        valor_ultima = gasto_in.valor - valor_parcela * (gasto_in.parcelas - 1)
        
        novos_gastos = []
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
                conta_id=conta.id,
                pago=False,
            )
            novos_gastos.append(gasto)

        db.add_all(novos_gastos)
        db.commit()
        # db.refresh n funciona numa lista de uma vez, mas não precisamos pois os IDs não são lidos aqui.
        # Vamos retornar o primeiro gasto pegando do DB ou usando os obj criados
        # É melhor fazer o db.refresh(novos_gastos[0])
        db.refresh(novos_gastos[0])
        return novos_gastos[0]
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("criar_gasto_diario")
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
        
    total = query.count()
    items = query.order_by(GastoDiario.data.desc(), GastoDiario.id.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items
    }


@router.get("/{id}")
def buscar_gasto_diario(id: int, db: Session = Depends(get_db)):
    gasto = db.query(GastoDiario).filter(GastoDiario.id == id).first()
    if not gasto:
        raise HTTPException(status_code=404, detail="Gasto diario nao encontrado")
    return gasto


@router.patch("/{id}/conciliar-pagamento")
def conciliar_pagamento(
    id: int,
    conciliacao: ConciliarPagamentoIn,
    db: Session = Depends(get_db),
):
    """Registra pagamentos feitos antes/fora do sistema sem cobrá-los novamente."""
    try:
        gasto = (
            db.query(GastoDiario)
            .filter(GastoDiario.id == id)
            .with_for_update()
            .first()
        )
        if not gasto:
            raise HTTPException(status_code=404, detail="Gasto diario nao encontrado")
        if gasto.tipo_pagamento != TipoPagamento.credito.value:
            raise HTTPException(
                status_code=409,
                detail="A conciliacao manual e permitida apenas para gastos no credito",
            )

        if not conciliacao.pago:
            raise HTTPException(
                status_code=409,
                detail="Para reabrir uma parcela, estorne o pagamento da fatura",
            )
        mes_ref, ano_ref = referencia_fatura(gasto.data, gasto.cartao.data_fatura)
        valor_pendente = gasto.valor - _valor_alocado_ativo(db, gasto.id)
        if valor_pendente <= 0:
            raise HTTPException(status_code=409, detail="Parcela ja coberta por pagamento")
        resposta = processar_pagamento_fatura(
            db,
            cartao_id=gasto.cartao_id,
            mes_ref=mes_ref,
            ano_ref=ano_ref,
            valor=valor_pendente,
            idempotency_key=f"conciliacao-gasto-{gasto.id}",
            origem="conciliacao_manual",
            movimentar_saldo=False,
            restaurar_limite=True,
        )
        db.commit()
        db.refresh(gasto)
        return {"gasto": gasto, "pagamento": resposta}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("conciliar_pagamento")
        raise HTTPException(status_code=500, detail="Erro ao conciliar pagamento")


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
        if (gasto.compra_id and gasto.parcelas > 1) or gasto_in.parcelas > 1:
            raise HTTPException(
                status_code=409,
                detail="Edicao individual de compra parcelada nao e permitida",
            )

        if _valor_alocado_ativo(db, gasto.id) > 0:
            raise HTTPException(status_code=409, detail="Parcela com pagamento alocado; estorne a fatura primeiro")
        referencias = set()
        if gasto.tipo_pagamento == TipoPagamento.credito.value and gasto.cartao_id:
            cartao_ref = _buscar_cartao_bloqueado(db, gasto.cartao_id)
            mes_ref, ano_ref = referencia_fatura(gasto.data, cartao_ref.data_fatura)
            referencias.add((gasto.cartao_id, mes_ref, ano_ref))
        cartao_antigo = _buscar_cartao_bloqueado(db, gasto.cartao_id) if gasto.cartao_id else None
        conta_antiga = resolver_conta(db, conta_id=gasto.conta_id, cartao_id=gasto.cartao_id)
        if gasto.tipo_pagamento in (TipoPagamento.debito.value, TipoPagamento.pix.value):
            creditar(db, conta_antiga, gasto.valor)
        else:
            cartao_antigo.limite += gasto.valor
        cartao_novo = (
            cartao_antigo
            if gasto_in.cartao_id == gasto.cartao_id
            else _buscar_cartao_bloqueado(db, gasto_in.cartao_id)
        )
        conta_nova = resolver_conta(db, conta_id=gasto_in.conta_id, cartao_id=gasto_in.cartao_id)
        if gasto_in.tipo_pagamento in (TipoPagamento.debito, TipoPagamento.pix):
            debitar(db, conta_nova, gasto_in.valor)
        else:
            if cartao_novo.limite < gasto_in.valor:
                raise HTTPException(status_code=409, detail="Limite insuficiente")
            cartao_novo.limite -= gasto_in.valor

        gasto.descricao = gasto_in.descricao
        gasto.valor = gasto_in.valor
        gasto.data = gasto_in.data
        gasto.categoria_id = gasto_in.categoria_id
        gasto.cartao_id = gasto_in.cartao_id
        gasto.conta_id = conta_nova.id
        gasto.tipo_pagamento = gasto_in.tipo_pagamento.value
        gasto.parcelas = 1
        if gasto.compra:
            gasto.compra.descricao = gasto_in.descricao
            gasto.compra.valor_total = gasto_in.valor
            gasto.compra.data_compra = gasto_in.data
            gasto.compra.tipo_pagamento = gasto_in.tipo_pagamento.value
            gasto.compra.cartao_id = gasto_in.cartao_id
            gasto.compra.conta_id = conta_nova.id
            gasto.compra.categoria_id = gasto_in.categoria_id
        if gasto.tipo_pagamento == TipoPagamento.credito.value and gasto.cartao_id:
            mes_ref, ano_ref = referencia_fatura(gasto.data, cartao_novo.data_fatura)
            referencias.add((gasto.cartao_id, mes_ref, ano_ref))
        db.flush()
        _sincronizar_competencias(db, referencias)
        db.commit()
        db.refresh(gasto)
        return gasto
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("atualizar_gasto_diario")
        raise HTTPException(status_code=500, detail="Erro ao atualizar gasto diario")


@router.patch("/{id}")
def editar_gasto_diario(
    id: int, patch: GastoDiarioPatch, db: Session = Depends(get_db)
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

        if _valor_alocado_ativo(db, gasto.id) > 0:
            raise HTTPException(status_code=409, detail="Parcela com pagamento alocado; estorne a fatura primeiro")
        cartao = _buscar_cartao_bloqueado(db, gasto.cartao_id) if gasto.cartao_id else None
        referencias = set()
        if gasto.tipo_pagamento == TipoPagamento.credito.value and cartao:
            mes_ref, ano_ref = referencia_fatura(gasto.data, cartao.data_fatura)
            referencias.add((gasto.cartao_id, mes_ref, ano_ref))

        # Se o valor mudou, estorna o antigo e aplica o novo
        if patch.valor is not None and patch.valor != gasto.valor:
            if gasto.compra_id and gasto.parcelas > 1:
                raise HTTPException(status_code=409, detail="Altere o valor pela operacao da compra completa")
            conta = resolver_conta(db, conta_id=gasto.conta_id, cartao_id=gasto.cartao_id)
            tipo = TipoPagamento(gasto.tipo_pagamento)
            diferenca = patch.valor - gasto.valor
            if tipo in (TipoPagamento.debito, TipoPagamento.pix):
                if diferenca > 0:
                    debitar(db, conta, diferenca)
                else:
                    creditar(db, conta, -diferenca)
            elif diferenca > 0:
                if cartao.limite < diferenca:
                    raise HTTPException(status_code=409, detail="Limite insuficiente")
                cartao.limite -= diferenca
            else:
                cartao.limite += -diferenca
            gasto.valor = patch.valor
            if gasto.compra:
                gasto.compra.valor_total = patch.valor

        if patch.descricao is not None:
            irmaos = _itens_compra(db, gasto)
            for item in irmaos:
                item.descricao = (
                    f"{patch.descricao} ({item.numero_parcela}/{item.parcelas})"
                    if item.parcelas > 1 else patch.descricao
                )
            if gasto.compra:
                gasto.compra.descricao = patch.descricao
        if patch.data is not None:
            if gasto.compra_id and gasto.numero_parcela > 1:
                irmaos = db.query(GastoDiario).filter(
                    GastoDiario.compra_id == gasto.compra_id,
                ).order_by(GastoDiario.numero_parcela).all()
                if irmaos:
                    primeira = irmaos[0]
                    mes_esperado = primeira.data.month + gasto.numero_parcela - 1
                    ano_esperado = primeira.data.year + (mes_esperado - 1) // 12
                    mes_esperado = ((mes_esperado - 1) % 12) + 1
                    if patch.data.month != mes_esperado or patch.data.year != ano_esperado:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Data fora da sequencia: esperado {mes_esperado:02d}/{ano_esperado}",
                        )
            gasto.data = patch.data
        if patch.categoria_id is not None:
            for item in _itens_compra(db, gasto):
                item.categoria_id = patch.categoria_id
            if gasto.compra:
                gasto.compra.categoria_id = patch.categoria_id

        if gasto.tipo_pagamento == TipoPagamento.credito.value and cartao:
            mes_ref, ano_ref = referencia_fatura(gasto.data, cartao.data_fatura)
            referencias.add((gasto.cartao_id, mes_ref, ano_ref))
        db.flush()
        _sincronizar_competencias(db, referencias)
        db.commit()
        db.refresh(gasto)
        return gasto
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("editar_gasto_diario")
        raise HTTPException(status_code=500, detail="Erro ao editar gasto diario")


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

        cartao = _buscar_cartao_bloqueado(db, gasto.cartao_id) if gasto.cartao_id else None
        if gasto.compra_id:
            parcelas_pagas = db.query(GastoDiario).filter(
                GastoDiario.compra_id == gasto.compra_id,
                GastoDiario.pago.is_(True),
            ).count()
            if parcelas_pagas > 0:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Compra parcelada com {parcelas_pagas} parcela(s) ja paga(s); "
                        "estorne a fatura primeiro"
                    ),
                )
        itens = _itens_compra(db, gasto)
        if any(_valor_alocado_ativo(db, item.id) > 0 for item in itens):
            raise HTTPException(status_code=409, detail="Compra com pagamento alocado; estorne a fatura primeiro")
        total = sum((item.valor for item in itens), Decimal("0"))
        referencias = set()
        if gasto.tipo_pagamento == TipoPagamento.credito.value and cartao:
            for item in itens:
                mes_ref, ano_ref = referencia_fatura(item.data, cartao.data_fatura)
                referencias.add((gasto.cartao_id, mes_ref, ano_ref))
        if gasto.tipo_pagamento in (TipoPagamento.debito.value, TipoPagamento.pix.value):
            conta = resolver_conta(db, conta_id=gasto.conta_id, cartao_id=gasto.cartao_id)
            creditar(db, conta, total)
        else:
            cartao.limite += total
        compra = gasto.compra
        for item in itens:
            db.delete(item)
        if compra:
            compra.situacao = "cancelada"
        db.flush()
        _sincronizar_competencias(db, referencias)
        db.commit()
        return {"mensagem": "Compra cancelada com sucesso", "itens_cancelados": len(itens)}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log_internal_error("deletar_gasto_diario")
        raise HTTPException(status_code=500, detail="Erro ao deletar gasto diario")
