import os
import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Optional
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import extract, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import AuditoriaAgente, Cartao, Categoria, GastoDiario, Receita
from schemas.agente import LancamentoAgenteIn, TipoLancamento
from schemas.gastos_diarios import TipoPagamento

router = APIRouter()
CENTAVOS = Decimal("0.01")


def autenticar_agente(
    x_agent_token: Annotated[Optional[str], Header()] = None,
) -> str:
    token_esperado = os.getenv("HERMES_API_TOKEN")
    if not token_esperado:
        raise HTTPException(status_code=503, detail="Integracao Hermes nao configurada")
    if not x_agent_token or not secrets.compare_digest(x_agent_token, token_esperado):
        raise HTTPException(status_code=401, detail="Token do agente invalido")
    return "hermes"


def _resolver_cartao(db: Session, entrada: LancamentoAgenteIn, bloquear=False) -> Cartao:
    query = db.query(Cartao).filter(Cartao.ativo.is_(True))
    if entrada.conta_id:
        query = query.filter(Cartao.id == entrada.conta_id)
    else:
        query = query.filter(func.lower(Cartao.nome) == entrada.conta.strip().lower())
    if bloquear:
        query = query.with_for_update()
    cartoes = query.all()
    if not cartoes:
        raise HTTPException(status_code=422, detail="Conta ativa nao encontrada")
    if len(cartoes) > 1:
        raise HTTPException(
            status_code=409,
            detail={"mensagem": "Nome de conta ambiguo", "conta_ids": [c.id for c in cartoes]},
        )
    return cartoes[0]


def _resolver_categoria(db: Session, entrada: LancamentoAgenteIn) -> Optional[Categoria]:
    if entrada.categoria_id:
        categoria = db.query(Categoria).filter(Categoria.id == entrada.categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=422, detail="Categoria nao encontrada")
        return categoria
    if entrada.categoria:
        categorias = db.query(Categoria).filter(
            func.lower(Categoria.nome) == entrada.categoria.strip().lower()
        ).all()
        if not categorias:
            raise HTTPException(status_code=422, detail="Categoria nao encontrada")
        if len(categorias) > 1:
            raise HTTPException(status_code=409, detail="Nome de categoria ambiguo")
        return categorias[0]
    return None


def _validar_fundos(cartao: Cartao, entrada: LancamentoAgenteIn) -> None:
    if entrada.tipo_lancamento != TipoLancamento.gasto:
        return
    if entrada.tipo_pagamento in (TipoPagamento.debito, TipoPagamento.pix):
        if cartao.saldo < entrada.valor:
            raise HTTPException(status_code=409, detail="Saldo insuficiente")
    elif cartao.limite < entrada.valor:
        raise HTTPException(status_code=409, detail="Limite insuficiente")


def _aplicar_fundos(cartao: Cartao, entrada: LancamentoAgenteIn) -> None:
    if entrada.tipo_lancamento == TipoLancamento.receita:
        cartao.saldo += entrada.valor
    elif entrada.tipo_pagamento in (TipoPagamento.debito, TipoPagamento.pix):
        cartao.saldo -= entrada.valor
    else:
        cartao.limite -= entrada.valor


@router.get("/contas", dependencies=[Depends(autenticar_agente)])
def listar_contas(db: Session = Depends(get_db)):
    return [
        {"id": c.id, "nome": c.nome, "dono": c.dono, "saldo": c.saldo, "limite": c.limite}
        for c in db.query(Cartao).filter(Cartao.ativo.is_(True)).order_by(Cartao.nome).all()
    ]


@router.get("/categorias", dependencies=[Depends(autenticar_agente)])
def listar_categorias(db: Session = Depends(get_db)):
    return [
        {"id": c.id, "nome": c.nome}
        for c in db.query(Categoria).order_by(Categoria.nome).all()
    ]


@router.get("/resumo", dependencies=[Depends(autenticar_agente)])
def resumo_mensal(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=1900, le=2200),
    db: Session = Depends(get_db),
):
    receitas = db.query(func.sum(Receita.valor)).filter(
        extract("month", Receita.data) == mes,
        extract("year", Receita.data) == ano,
    ).scalar() or Decimal("0")
    gastos = db.query(func.sum(GastoDiario.valor)).filter(
        extract("month", GastoDiario.data) == mes,
        extract("year", GastoDiario.data) == ano,
    ).scalar() or Decimal("0")
    return {
        "mes": mes,
        "ano": ano,
        "total_receitas": receitas,
        "total_gastos": gastos,
        "saldo_do_periodo": receitas - gastos,
    }


@router.post("/lancamentos/preview", dependencies=[Depends(autenticar_agente)])
def prever_lancamento(entrada: LancamentoAgenteIn, db: Session = Depends(get_db)):
    cartao = _resolver_cartao(db, entrada)
    categoria = _resolver_categoria(db, entrada)
    _validar_fundos(cartao, entrada)
    return {
        "valido": True,
        "precisa_confirmacao": True,
        "resumo": {
            "tipo_lancamento": entrada.tipo_lancamento,
            "descricao": entrada.descricao,
            "valor": entrada.valor,
            "data": entrada.data,
            "conta": {"id": cartao.id, "nome": cartao.nome},
            "categoria": ({"id": categoria.id, "nome": categoria.nome} if categoria else None),
            "tipo_pagamento": entrada.tipo_pagamento,
            "parcelas": entrada.parcelas,
        },
    }


@router.post("/lancamentos")
def registrar_lancamento(
    entrada: LancamentoAgenteIn,
    agente: str = Depends(autenticar_agente),
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
):
    external_id = idempotency_key or entrada.external_id
    if not external_id:
        raise HTTPException(status_code=422, detail="Idempotency-Key ou external_id e obrigatorio")
    if len(external_id) > 120:
        raise HTTPException(status_code=422, detail="Chave de idempotencia excede 120 caracteres")

    existente = db.query(AuditoriaAgente).filter(
        AuditoriaAgente.external_id == external_id
    ).first()
    if existente:
        return {**existente.resposta, "idempotente": True}

    try:
        cartao = _resolver_cartao(db, entrada, bloquear=True)
        categoria = _resolver_categoria(db, entrada)
        _validar_fundos(cartao, entrada)
        _aplicar_fundos(cartao, entrada)

        ids = []
        entidade = entrada.tipo_lancamento.value
        if entrada.tipo_lancamento == TipoLancamento.receita:
            receita = Receita(
                descricao=entrada.descricao,
                valor=entrada.valor,
                data=entrada.data,
                cartao_id=cartao.id,
                categoria_id=categoria.id if categoria else None,
                origem=agente,
                external_id=external_id,
            )
            db.add(receita)
            db.flush()
            ids.append(receita.id)
        else:
            compra_id = str(uuid4()) if entrada.parcelas > 1 else None
            valor_parcela = (entrada.valor / entrada.parcelas).quantize(
                CENTAVOS, rounding=ROUND_HALF_UP
            )
            valor_ultima = entrada.valor - valor_parcela * (entrada.parcelas - 1)
            for indice in range(entrada.parcelas):
                numero = indice + 1
                gasto = GastoDiario(
                    descricao=(
                        f"{entrada.descricao} ({numero}/{entrada.parcelas})"
                        if entrada.parcelas > 1 else entrada.descricao
                    ),
                    valor=valor_ultima if numero == entrada.parcelas else valor_parcela,
                    data=entrada.data + relativedelta(months=indice),
                    tipo_pagamento=entrada.tipo_pagamento.value,
                    parcelas=entrada.parcelas,
                    compra_id=compra_id,
                    numero_parcela=numero,
                    categoria_id=categoria.id if categoria else None,
                    cartao_id=cartao.id,
                    pago=False,
                    origem=agente,
                    external_id=external_id,
                )
                db.add(gasto)
                db.flush()
                ids.append(gasto.id)

        resposta = {
            "status": "registrado",
            "tipo_lancamento": entidade,
            "lancamento_ids": ids,
            "external_id": external_id,
            "conta": {"id": cartao.id, "nome": cartao.nome},
            "saldo_resultante": cartao.saldo,
            "limite_resultante": cartao.limite,
            "idempotente": False,
        }
        auditoria = AuditoriaAgente(
            external_id=external_id,
            agente=agente,
            acao="registrar_lancamento",
            entidade=entidade,
            entidade_id=ids[0],
            status="registrado",
            requisicao=jsonable_encoder(entrada),
            resposta=jsonable_encoder(resposta),
        )
        db.add(auditoria)
        db.commit()
        return resposta
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        existente = db.query(AuditoriaAgente).filter(
            AuditoriaAgente.external_id == external_id
        ).first()
        if existente:
            return {**existente.resposta, "idempotente": True}
        raise HTTPException(status_code=409, detail="Chave de idempotencia em conflito")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao registrar lancamento do agente")


@router.get("/lancamentos/{external_id}", dependencies=[Depends(autenticar_agente)])
def consultar_lancamento(external_id: str, db: Session = Depends(get_db)):
    auditoria = db.query(AuditoriaAgente).filter(
        AuditoriaAgente.external_id == external_id
    ).first()
    if not auditoria:
        raise HTTPException(status_code=404, detail="Lancamento do agente nao encontrado")
    return {
        "external_id": auditoria.external_id,
        "agente": auditoria.agente,
        "status": auditoria.status,
        "criado_em": auditoria.criado_em,
        "resposta": auditoria.resposta,
    }


@router.delete("/lancamentos/{external_id}")
def estornar_lancamento(
    external_id: str,
    agente: str = Depends(autenticar_agente),
    db: Session = Depends(get_db),
):
    try:
        auditoria = db.query(AuditoriaAgente).filter(
            AuditoriaAgente.external_id == external_id
        ).with_for_update().first()
        if not auditoria:
            raise HTTPException(status_code=404, detail="Lancamento do agente nao encontrado")
        if auditoria.status == "estornado":
            return {**auditoria.resposta, "idempotente": True}

        if auditoria.entidade == TipoLancamento.gasto.value:
            gastos = db.query(GastoDiario).filter(
                GastoDiario.external_id == external_id
            ).with_for_update().all()
            if not gastos:
                raise HTTPException(status_code=409, detail="Gastos vinculados nao encontrados")
            if any(gasto.pago for gasto in gastos):
                raise HTTPException(status_code=409, detail="Fatura paga; estorne a fatura primeiro")
            cartao = db.query(Cartao).filter(
                Cartao.id == gastos[0].cartao_id
            ).with_for_update().first()
            total = sum((g.valor for g in gastos), Decimal("0"))
            if gastos[0].tipo_pagamento in (TipoPagamento.debito.value, TipoPagamento.pix.value):
                cartao.saldo += total
            else:
                cartao.limite += total
            for gasto in gastos:
                db.delete(gasto)
        else:
            receita = db.query(Receita).filter(
                Receita.external_id == external_id
            ).with_for_update().first()
            if not receita:
                raise HTTPException(status_code=409, detail="Receita vinculada nao encontrada")
            cartao = db.query(Cartao).filter(
                Cartao.id == receita.cartao_id
            ).with_for_update().first()
            if cartao.saldo < receita.valor:
                raise HTTPException(status_code=409, detail="Saldo insuficiente para estornar receita")
            cartao.saldo -= receita.valor
            db.delete(receita)

        resposta = {
            "status": "estornado",
            "external_id": external_id,
            "agente": agente,
            "idempotente": False,
        }
        auditoria.status = "estornado"
        auditoria.acao = "estornar_lancamento"
        auditoria.resposta = resposta
        db.commit()
        return resposta
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao estornar lancamento do agente")
